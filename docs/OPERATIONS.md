# Operations notes

Lightweight runbook for day-to-day operation of OS-Pariah on openSUSE
(Gunicorn, Nginx, Cloudflare, MariaDB). Complements [DEPLOYMENT.md](DEPLOYMENT.md).

## Service management

```bash
sudo systemctl status os-pariah.service mariadb.service nginx.service
sudo journalctl -u os-pariah.service -f
```

After code or dependency updates (RPM upgrade, or a manual deploy into `/opt/os-pariah`):

```bash
sudo systemctl restart os-pariah.service
```

`ExecStartPre` re-runs `sync_requirements.py` (as root via the `+` prefix, because `/opt/os-pariah` is root-owned), `check_mariadb.py`, and `migrate.py` on every start.

## Background workers

| Unit | Purpose |
|------|---------|
| `os-pariah-worker-iar.service` | Process user-requested IAR inventory backups (same entrypoint as the sweep timer) |
| `os-pariah-worker-iar.timer` | Periodic full IAR worker run (pending catch-up + retention cleanup); default every **7 days**, synced from `iar_sweep_interval_days` by the portal backup job |
| `os-pariah-worker-log.service` + `.timer` | Ingest gatekeeper logs; clean texture JPG cache; refresh texture gallery snapshot |
| `os-pariah-worker-calendar.service` + `.timer` | Deliver calendar notification emails / in-world messages (timer fires every **1 minute**; windows are tolerant of ~60–90 s lateness and deduplicated) |
| `os-pariah-cloudflare-ip.service` + `.timer` | Refresh Cloudflare proxy ranges in nginx real-IP conf (root; pulled in by `os-pariah.service`) |
| `os-pariah-backup.service` + `.timer` | Daily self-backup of the `os_pariah` DB + conf/secrets + durable uploads (ticket attachments); not cache/IAR downloads. Backup dir is `os-pariah:opensim` `0750`. |

```bash
sudo systemctl list-timers 'os-pariah-*'
sudo journalctl -u os-pariah-worker-iar.service -u os-pariah-worker-log.service \
                 -u os-pariah-worker-calendar.service -u os-pariah-cloudflare-ip.service \
                 -u os-pariah-backup.service -n 100
```

Worker logs also land in `/var/log/os-pariah/` when that directory is writable by the
`os-pariah` user.

## Paths cheat sheet

| Resource | Path |
|----------|------|
| Application | `/opt/os-pariah/` |
| Virtualenv | `/opt/os-pariah/venv/` |
| Config | `/etc/os-pariah/os-pariah.conf` (`0640 os-pariah:opensim`) |
| Config directory | `/etc/os-pariah/` (`0750 os-pariah:opensim` — workers need group traverse) |
| Secrets (`SECRET_KEY`) | `/etc/os-pariah/secrets` (auto-generated; mode `0600`, `os-pariah` only) |
| Setup token (first boot only) | `/etc/os-pariah/setup_token` (`0600 os-pariah`; written by `os-pariah-bootstrap`, deleted when setup completes) |
| Runtime socket | `/run/os-pariah/os-pariah.sock` |
| Logs | `/var/log/os-pariah/` |
| Texture gallery snapshot | `os_pariah` table `texture_gallery_snapshot` (log worker; ≥14 days and ≥2000 rows by default, see System Settings) |
| Texture gallery cache | `/home/opensim/FSAssets/os-pariah-cache/` (`0775 os-pariah:opensim`; override path in System Settings) |
| Ticket uploads (private) | `/var/lib/os-pariah/uploads/tickets/` (`0750 os-pariah:os-pariah`; served only via authenticated routes, not nginx static) |
| IAR downloads | `/home/opensim/Backups/downloads/` |
| Self-backups | `/home/opensim/Backups/portal/` (`0750 os-pariah:opensim`; override with `portal_backup_dir`; DB dump + conf/secrets + `/var/lib/os-pariah/uploads`) |
| Nginx vhost | `/etc/nginx/vhosts.d/os-pariah.conf` |
| Cloudflare real-IP | `/etc/nginx/conf.d/os-pariah-cloudflare-ip.conf` |

## Secrets rotation

```bash
sudo systemctl stop os-pariah
sudo rm /etc/os-pariah/secrets
sudo systemctl start os-pariah
```

All sessions are invalidated. Back up the secrets file **separately** from MariaDB dumps
(see [DEPLOYMENT.md](DEPLOYMENT.md) §4).

## Releasing (GitHub → signed RPM)

Stable releases are published from **`main` only** (never `develop`). Publishing a GitHub Release tag (`vX.Y.Z`) triggers [`.github/workflows/release-rpm.yml`](../.github/workflows/release-rpm.yml):

| Job | Runs on | Responsibility |
|-----|---------|----------------|
| `ci-gate` | Ubuntu host | **Policy only:** release commit must be on `main` (`target_commitish` ≠ `develop`, compare `main...SHA` has `ahead_by=0`); *Automated Tests* must have succeeded for that SHA |
| `build-rpm` | `opensuse/leap:16.0` container | **Packaging only:** checkout tagged tree, `rpmbuild`, GPG sign, write `os-pariah-….rpm.sha256`, attach the main RPM + checksum (not debugsource) to the Release |

Verify a downloaded RPM against the release checksum:

```bash
sha256sum -c os-pariah-*.rpm.sha256
```

Keep git ancestry / branch policy out of `build-rpm`. The Leap container bind-mounts the Actions workspace, and a follow-up `git fetch` / `merge-base` there hits “dubious ownership” (git exit 128) even when the commit is on `main`.

Workflow YAML for a given release is the copy at the **tagged commit**. Fixing the workflow after tagging does not change a re-run of that release; ship a new patch tag (or a new Release) that includes the fixed workflow if the RPM job must be rebuilt.

## Upgrades

1. Check [COMPATIBILITY.md](../COMPATIBILITY.md) for the OpenSimulator version.
2. Ensure `/usr/bin/python3.13` exists **before** installing v1.1.0+ (Leap 16: `zypper install python313`; Leap 15.6: see [DEPLOYMENT.md](DEPLOYMENT.md#python-313-on-leap-156)).
3. Install the new RPM (`zypper install` / `rpm -Uvh`). Config is `%config(noreplace)`.
4. `systemctl restart os-pariah` — migrations and dependency sync run automatically.
5. Confirm `journalctl -u os-pariah -n 50` shows a clean migrate.
6. Spot-check `/manual.html`, login, and one admin page.
7. If a release added setup steps, Super Admins see a "Setup: N steps still need your attention" banner; nothing is blocked ([Setup steps](#setup-steps)).

When the RPM bumps the system Python (for example **3.12 → 3.13**), `%post` recreates `/opt/os-pariah/venv` with `python3.13 -m venv --clear`. On Leap 16, `zypper` can pull `python313` via the package recommends; on Leap 15.6 you must already have provided `/usr/bin/python3.13`. For a manual install, recreate the venv the same way before restarting.

## Setup steps

First-boot configuration is a registry of **versioned steps** (`app/setup/steps.py`) with persisted state in the `setup_state` table (migration 013). `scripts/migrate.py` reconciles it on every start.

**Who is gated.** Only an install created by `os-pariah-bootstrap` on an empty database (origin `fresh`, conf contains `OS_PARIAH_INSTANCE`) is redirected to `/setup` until every *blocking* step is done or (if skippable) skipped. Installs that existed before the wizard, hand-configured installs, and local dev databases are `upgraded`: all steps are backfilled as done and nothing is ever gated. Every error path (missing table, DB hiccup, never reconciled) fails open.

**Access.** During first boot, the one-time token (`/etc/os-pariah/setup_token`) unlocks `/setup/unlock`; it is deleted when setup completes (`sudo os-pariah-bootstrap --new-token` re-issues it). Afterwards `/setup` is Super Admin only. Wrong tokens are rate limited.

**Inspect or reopen state:**

```bash
sudo mariadb os_pariah -e "SELECT step_id, step_version, status, updated_at FROM setup_state"
sudo mariadb os_pariah -e "SELECT detail FROM setup_state WHERE step_id = '_install'"   # origin, provider, instance, first_boot_complete
sudo mariadb os_pariah -e "UPDATE setup_state SET status='pending' WHERE step_id='turnstile'"  # reopen one step (shows as an admin banner)
```

Reopening a step after first boot is a nudge (admin banner), not a lock-out. The `_install` row is bookkeeping, not a step; do not delete it.

**How a release adds or changes a step** (rules at the top of `app/setup/steps.py`):

1. Step `id`s are stable forever (rows are keyed by them). Never rename one.
2. A step added after the wizard shipped must be `StepKind.ADVISORY`: existing installs see it as a pending item and a banner for Super Admins; it never gates a working portal.
3. Bump a step's `version` when its requirements change; installs that completed an older version get it reopened as pending (advisory).
4. Settings come from `KNOWN_SETTINGS` (`app/utils/schema.py`), the single source of truth for labels, types and defaults. Bootstrap-level facts (DB credentials, `ADMIN_UUID`, hostnames) belong to the conf file and the bootstrap CLI, not a step.
5. Steps never touch OpenSim. The `external` grid provider is read-only by construction; only a future provider that declares a mutating capability may contribute such steps (tests enforce that the wizard and bootstrap never reference OpenSim ini files, `sync_robust`/`sync_firewall`, or OpenSim service units).

## Theming (custom CSS)

Appearance is configured under **System Settings → Grid Identity**:

| Setting | Default | Applies to |
|---------|---------|------------|
| `custom_css_path` | `/static/css/base.css` | Every portal page **and** the viewer splash (`/comms/splash`) |
| `portal_background_image` | `/static/images/background.png` | Page background (`--portal-background-image`) |
| `portal_favicon` | `/static/images/os-pariah.ico` | Browser tab icon |

**Rules for theme authors**

- `custom_css_path` **replaces** `base.css`; it is not layered on top. Start from a copy of
  `base.css` and keep every component block, including the `.splash-screen`, `.group--accent`, and
  `.group--danger` rules, or those pages will lose their layout.
- Prefer changing the `:root` design tokens (`--primary`, `--card-bg`, `--border-color`,
  `--info-bg`, `--danger-bg`, `--font-body`, …) instead of editing component rules. Components and
  the splash use tokens only (no hard-coded colors), so a token change re-themes everything.
- Keep your file outside `/opt/os-pariah/app/static/`; the RPM replaces the packaged tree on upgrade, which
  would overwrite edits to `base.css` itself.

**Rules for template authors**

- Pages extend `base.html`. A page that must stay standalone (today only the viewer splash, which skips the
  nav bar, Turnstile, and CSRF scripts for the embedded browser) must include
  `{% include '_head_theme.html' %}` in its `<head>`. That partial emits the favicon, the configured stylesheet,
  and the background-image variable, and `base.html` uses the same one so the two cannot drift. Never link
  `css/base.css` directly.
- Reuse existing classes and utilities from `base.css` (`.panel`, `.card-header`, `.group`, `.alert.*`,
  `.btn*`, `.text-*`, `.mt-*`/`.mb-*`) instead of inline `style=` attributes. For accent borders on `.group`,
  use `.group--accent` (primary) or `.group--danger` (alert).
- The splash frame is `<div class="main splash-screen">`: `.main` supplies the themed card frame, and
  `.splash-screen` only adds the two-column grid.

## Robust indexes (Texture Gallery)

The gallery listing can peg MariaDB on large grids without indexes on Robust
`fsassets` / `inventoryitems`. These are **additive only** (no schema/data
changes) and do not require restarting OpenSim/Robust.

After upgrading OS-Pariah (or before first use of the optimized gallery on a large
grid), apply once as a MariaDB admin (not the portal `robust_ro` user):

```bash
# Dry-run: report missing indexes
sudo /opt/os-pariah/venv/bin/python \
  /opt/os-pariah/scripts/apply_robust_texture_indexes.py --dry-run

# Apply (unix_socket as root when run via sudo)
sudo /opt/os-pariah/venv/bin/python \
  /opt/os-pariah/scripts/apply_robust_texture_indexes.py
```

Equivalent SQL: `scripts/sql/robust_texture_gallery_indexes.sql`.

Then force a snapshot refresh (or wait for the log timer):

```bash
sudo systemctl start os-pariah-worker-log.service
```

## Common troubleshooting

| Symptom | Check |
|---------|-------|
| Service fails at start | `journalctl -u os-pariah -n 100` — usually MariaDB unreachable or a migration error |
| Worker fails with access denied / cannot read conf | `/etc/os-pariah` must be `0750 os-pariah:opensim` (not `os-pariah:os-pariah`). The withdrawn v1.0.1 release (old `os_pariah` paths, user `pariah`) had this bug — see [#61](https://github.com/jjtkalt/OS-Pariah-Portal/issues/61). Workaround: `sudo chown os-pariah:opensim /etc/os-pariah && sudo chmod 0750 /etc/os-pariah` |
| Texture cache cleanup cannot delete JPGs | `/home/opensim/FSAssets/os-pariah-cache` must be `0775 os-pariah:opensim` so `opensim` workers can write. Workaround: `sudo chown -R os-pariah:opensim /home/opensim/FSAssets/os-pariah-cache && sudo chmod 0775 /home/opensim/FSAssets/os-pariah-cache` |
| Wrong visitor IP / bans misfire | Confirm Cloudflare Full (strict) and `os-pariah-cloudflare-ip.conf` is included; check `os-pariah-cloudflare-ip.timer` |
| Sessions keep dropping after restart | `/etc/os-pariah/secrets` was regenerated or is missing from backups |
| No Super Admin after install | Set `ADMIN_UUID` to your OpenSim PrincipalID and restart (migrate grants Super Admin; see [NAMING.md](NAMING.md)) |
| Static CSS 404 after upgrade | `custom_css_path` still points at `/static/css/central.css` — migration `010` should have fixed the default; clear or update the setting |
| Viewer splash (`/comms/splash`) ignores the custom theme | Upgrade to v1.2.4+ (earlier releases hard-coded `base.css` and skipped the background setting); see [Theming](#theming-custom-css) |
| Texture gallery hangs before tiles | Confirm migration `011` applied; run `apply_robust_texture_indexes.py`; start `os-pariah-worker-log` to fill `texture_gallery_snapshot` |

## OIDC login

OpenID Connect **authorization requires a row in `oidc_clients`** (`client_id`,
`client_secret`, exact `redirect_uri`, `app_name`). Unregistered clients are rejected.
Place the RSA signing key at `/etc/os-pariah/oidc_private.pem` (preferred) or
`/opt/os-pariah/private.pem`. Password login against the grid remains the supported
default path; do not expose OIDC to production clients until those rows and the key exist.

## Packaged timers

Enable only the master unit (`sudo systemctl enable --now os-pariah.service`). Packaged timers
(`os-pariah-worker-*.timer`, `os-pariah-cloudflare-ip.timer`, `os-pariah-backup.timer`) are pulled in by
`os-pariah.service` via `Requires=`; do not enable them individually. The IAR worker service is
`Wants=` only, so an IAR failure never stops the web app.

## Related docs

- [DEPLOYMENT.md](DEPLOYMENT.md) — install and first-boot
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- [NAMING.md](NAMING.md) — naming standard, on-host layout, and `ADMIN_UUID` exception
- [ROADMAP.md](ROADMAP.md) — product naming and merge context
- End-user help: `/manual.html`
