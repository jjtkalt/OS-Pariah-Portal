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

When the RPM bumps the system Python (for example **3.12 → 3.13**), `%post` recreates `/opt/os-pariah/venv` with `python3.13 -m venv --clear`. On Leap 16, `zypper` can pull `python313` via the package recommends; on Leap 15.6 you must already have provided `/usr/bin/python3.13`. For a manual install, recreate the venv the same way before restarting.

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
