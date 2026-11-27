"""In-memory stand-ins for the portal DB (``setup_state`` + ``config``) used by setup tests.

Not a SQL engine: it understands exactly the statements app/setup issues and fails loudly
on anything else, so a new query in the wizard code shows up as a test failure here.
"""

from __future__ import annotations

import json


class FakeCursor:
    def __init__(self, db: FakeConn):
        self.db = db
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        q = " ".join(sql.split())
        db = self.db
        db.statements.append((q, tuple(params)))
        self._rows = []
        if q.startswith("SELECT detail FROM setup_state WHERE step_id ="):
            row = db.state.get(params[0])
            self._rows = [{"detail": row["detail"]}] if row else []
        elif q.startswith(
            "SELECT step_id, step_version, status, detail FROM setup_state "
            "WHERE step_id <>"
        ):
            self._rows = [
                {"step_id": sid, **row}
                for sid, row in db.state.items()
                if sid != params[0]
            ]
        elif q.startswith("INSERT INTO setup_state"):
            step_id, version, status, detail = params
            db.state[step_id] = {
                "step_version": version,
                "status": status,
                "detail": detail,
            }
        elif q.startswith("SELECT config_key, config_value FROM config WHERE"):
            self._rows = [
                {"config_key": k, "config_value": v}
                for k, v in db.config.items()
                if k in params
            ]
        elif q.startswith("SELECT config_value FROM config WHERE config_key ="):
            value = db.config.get(params[0])
            self._rows = [{"config_value": value}] if value is not None else []
        elif q.startswith("INSERT INTO config"):
            db.config[params[0]] = params[1]
        elif q.startswith("DELETE FROM config WHERE config_key ="):
            db.config.pop(params[0], None)
        else:
            raise AssertionError(f"Unexpected SQL in setup code: {q}")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class FakeConn:
    def __init__(self):
        # setup_state rows as stored (detail is a JSON string, like the real column).
        self.state: dict[str, dict] = {}
        self.config: dict[str, str] = {}
        self.statements: list[tuple[str, tuple]] = []
        self.commits = 0

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass

    # Test helpers ----------------------------------------------------------------

    def step_status(self, step_id: str) -> str | None:
        row = self.state.get(step_id)
        return row["status"] if row else None

    def set_step(self, step_id: str, version: int, status: str, detail=None) -> None:
        self.state[step_id] = {
            "step_version": version,
            "status": status,
            "detail": json.dumps(detail or {}),
        }
