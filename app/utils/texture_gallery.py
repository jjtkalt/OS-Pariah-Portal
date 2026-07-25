"""Texture gallery listing helpers (inverted Robust query + Pariah snapshot).

The gallery used to drive from inventoryitems JOIN fsassets with GROUP BY/ORDER BY
before LIMIT, which pegs a single MariaDB thread on large grids. Callers should:

1. Prefer reading ``texture_gallery_snapshot`` in the Pariah DB (filled by the worker
   for a recent time window — default last 14 days, topped up to at least 2000 rows —
   for casual admin monitoring).
2. Fall back to ``fetch_textures_inverted`` against Robust (fsassets-first plan).
"""

from __future__ import annotations

from typing import Any

# Oversample recent fsassets before inventory type filters so LIMIT still yields
# enough texture rows when many newest assets are non-textures.
_CANDIDATE_MULTIPLIER = 20
_CANDIDATE_FLOOR = 200

_INVERTED_SELECT = """
    SELECT f.id AS id,
           f.hash AS hash,
           MAX(i.inventoryName) AS name,
           f.create_time AS create_time,
           MAX(i.avatarID) AS owner_uuid,
           MAX(CONCAT(u.FirstName, ' ', u.LastName)) AS owner_name
    FROM (
        SELECT id, hash, create_time
        FROM fsassets
        ORDER BY create_time DESC
        LIMIT %s
    ) AS f
    INNER JOIN inventoryitems i
            ON i.assetID = f.id
           AND i.assetType = 0
           AND i.inventoryName NOT LIKE %s
           AND i.inventoryName NOT LIKE %s
    LEFT JOIN useraccounts u ON i.avatarID = u.PrincipalID
"""


def _candidate_limit(limit: int, offset: int) -> int:
    need = max(limit + offset, 1)
    return max(need * _CANDIDATE_MULTIPLIER, _CANDIDATE_FLOOR)


def normalize_owner_names(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        if not row.get("owner_name"):
            row["owner_name"] = "System / Orphaned / HG"
    return rows


def fetch_textures_inverted(
    robust_conn,
    *,
    limit: int,
    offset: int = 0,
    owner_uuid: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent textures using an fsassets-first plan (small working set)."""
    if limit < 1:
        return []

    baked = "%Baked%"
    mesh = "%Mesh%"
    cand = _candidate_limit(limit, offset)

    if owner_uuid:
        # Per-user listings are selective; join from that avatar's texture items.
        sql = """
            SELECT f.id AS id,
                   f.hash AS hash,
                   MAX(i.inventoryName) AS name,
                   MAX(f.create_time) AS create_time,
                   MAX(i.avatarID) AS owner_uuid,
                   MAX(CONCAT(u.FirstName, ' ', u.LastName)) AS owner_name
            FROM inventoryitems i
            INNER JOIN fsassets f ON f.id = i.assetID
            LEFT JOIN useraccounts u ON i.avatarID = u.PrincipalID
            WHERE i.assetType = 0
              AND i.avatarID = %s
              AND i.inventoryName NOT LIKE %s
              AND i.inventoryName NOT LIKE %s
            GROUP BY f.hash
            ORDER BY MAX(f.create_time) DESC
            LIMIT %s OFFSET %s
        """
        params: tuple[Any, ...] = (owner_uuid, baked, mesh, limit, offset)
    else:
        sql = (
            _INVERTED_SELECT
            + """
            GROUP BY f.id, f.hash, f.create_time
            ORDER BY f.create_time DESC
            LIMIT %s OFFSET %s
        """
        )
        params = (cand, baked, mesh, limit, offset)

    with robust_conn.cursor() as cursor:
        cursor.execute(sql, params)
        return normalize_owner_names(list(cursor.fetchall() or []))


def _texture_select_sql(*, where_extra: str = "") -> str:
    """Shared SELECT for inventory textures joined to fsassets/useraccounts."""
    return f"""
        SELECT f.id AS id,
               f.hash AS hash,
               MAX(i.inventoryName) AS name,
               f.create_time AS create_time,
               MAX(i.avatarID) AS owner_uuid,
               MAX(CONCAT(u.FirstName, ' ', u.LastName)) AS owner_name
        FROM fsassets f
        INNER JOIN inventoryitems i
                ON i.assetID = f.id
               AND i.assetType = 0
               AND i.inventoryName NOT LIKE %s
               AND i.inventoryName NOT LIKE %s
        LEFT JOIN useraccounts u ON i.avatarID = u.PrincipalID
        {where_extra}
        GROUP BY f.id, f.hash, f.create_time
        ORDER BY f.create_time DESC
        LIMIT %s
    """


def fetch_textures_for_snapshot(
    robust_conn,
    *,
    since_unix: int,
    min_rows: int = 2000,
    max_rows: int = 50000,
) -> list[dict[str, Any]]:
    """Build the Pariah snapshot row set for casual monitoring.

    1. Include **all** textures with ``create_time >= since_unix`` (default window:
       last 14 days), up to ``max_rows``.
    2. If that window has fewer than ``min_rows`` (default 2000), top up with the
       next-newest textures outside the window until ``min_rows`` (or until the
       grid runs out — take all we can).
    3. Never exceed ``max_rows`` (busy-grid safety cap).
    """
    if max_rows < 1:
        return []
    if min_rows < 1:
        min_rows = 1
    if min_rows > max_rows:
        min_rows = max_rows

    baked = "%Baked%"
    mesh = "%Mesh%"

    with robust_conn.cursor() as cursor:
        # Pass 1: everything in the time window (capped).
        cursor.execute(
            _texture_select_sql(where_extra="WHERE f.create_time >= %s"),
            (baked, mesh, int(since_unix), int(max_rows)),
        )
        window_rows = list(cursor.fetchall() or [])

        if len(window_rows) >= min_rows or len(window_rows) >= max_rows:
            return normalize_owner_names(window_rows[:max_rows])

        # Pass 2: newest overall to top up quiet / low-population grids.
        cursor.execute(
            _texture_select_sql(where_extra=""),
            (baked, mesh, int(min_rows)),
        )
        newest_rows = list(cursor.fetchall() or [])

    by_hash: dict[str, dict[str, Any]] = {}
    for row in window_rows:
        h = row.get("hash")
        if h:
            by_hash[h] = row
    for row in newest_rows:
        h = row.get("hash")
        if not h or h in by_hash:
            continue
        by_hash[h] = row
        if len(by_hash) >= min_rows:
            break

    merged = sorted(
        by_hash.values(),
        key=lambda r: int(r.get("create_time") or 0),
        reverse=True,
    )
    return normalize_owner_names(merged[:max_rows])


def replace_texture_gallery_snapshot(pariah_conn, rows: list[dict[str, Any]]) -> int:
    """Replace the snapshot table contents in one transaction. Returns row count."""
    with pariah_conn.cursor() as cursor:
        cursor.execute("DELETE FROM texture_gallery_snapshot")
        if rows:
            cursor.executemany(
                """
                INSERT INTO texture_gallery_snapshot
                    (hash, asset_id, name, create_time, owner_uuid, owner_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        r.get("hash"),
                        r.get("id"),
                        r.get("name"),
                        int(r.get("create_time") or 0),
                        r.get("owner_uuid"),
                        r.get("owner_name"),
                    )
                    for r in rows
                    if r.get("hash")
                ],
            )
        pariah_conn.commit()
        return len(rows)


def snapshot_count(pariah_conn) -> int:
    with pariah_conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS c FROM texture_gallery_snapshot")
        row = cursor.fetchone() or {}
        return int(row.get("c") or 0)


def fetch_textures_from_snapshot(
    pariah_conn,
    *,
    limit: int,
    offset: int = 0,
    owner_uuid: str | None = None,
) -> list[dict[str, Any]]:
    """Read paginated gallery rows from the Pariah snapshot (request path)."""
    if limit < 1:
        return []

    if owner_uuid:
        sql = """
            SELECT asset_id AS id, hash, name, create_time, owner_uuid, owner_name
            FROM texture_gallery_snapshot
            WHERE owner_uuid = %s
            ORDER BY create_time DESC
            LIMIT %s OFFSET %s
        """
        params: tuple[Any, ...] = (owner_uuid, limit, offset)
    else:
        sql = """
            SELECT asset_id AS id, hash, name, create_time, owner_uuid, owner_name
            FROM texture_gallery_snapshot
            ORDER BY create_time DESC
            LIMIT %s OFFSET %s
        """
        params = (limit, offset)

    with pariah_conn.cursor() as cursor:
        cursor.execute(sql, params)
        return normalize_owner_names(list(cursor.fetchall() or []))
