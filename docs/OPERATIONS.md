# Operations notes

Lightweight runbook for day-to-day operation of OS-Pariah-Portal on openSUSE
(Gunicorn, Nginx, Cloudflare, MariaDB). Complements [DEPLOYMENT.md](DEPLOYMENT.md).

## Service management

```bash
sudo systemctl status pariah.service mariadb.service nginx.service
sudo journalctl -u pariah.service -f
```

After code or dependency updates (RPM upgrade, or a manual deploy into `/opt/os_pariah`):

```bash
sudo systemctl restart pariah.service
```

`ExecStartPre` re-runs `sync_requirements.py`, `check_mariadb.py`, and `migrate.py` on every start.

## Background workers

| Unit | Purpose |
|------|---------|
| `pariah-worker-iar.service` | Process user-requested IAR inventory backups |
| `pariah-worker-log.service` + `.timer` | Ingest gatekeeper logs; clean texture cache |
| `pariah-worker-calendar.service` + `.timer` | Deliver calendar notification emails / in-world messages |

```bash
sudo systemctl list-timers 'pariah-*'
sudo journalctl -u pariah-worker-iar.service -u pariah-worker-log.service \
                 -u pariah-worker-calendar.service -n 100
```

Worker logs also land in `/var/log/os_pariah/` when that directory is writable by the
`pariah` user.

## Paths cheat sheet

| Resource | Path |
|----------|------|
| Application | `/opt/os_pariah/` |
| Virtualenv | `/opt/os_pariah/venv/` |
| Config | `/etc/os_pariah/os-pariah.conf` |
| Secrets (`SECRET_KEY`) | `/etc/os_pariah/secrets` (auto-generated; mode `0600`) |
| Runtime socket | `/run/os_pariah/pariah.sock` |
| Logs | `/var/log/os_pariah/` |
| Texture gallery cache | `/home/opensim/FSAssets/pariahcache/` (override in System Settings) |
| IAR downloads | `/home/opensim/Backups/downloads/` |
| Nginx vhost | `/etc/nginx/vhosts.d/OS-Pariah.conf` |
| Cloudflare real-IP | `/etc/nginx/conf.d/cloudflare-real-ip.conf` |

## Secrets rotation

```bash
sudo systemctl stop pariah
sudo rm /etc/os_pariah/secrets
sudo systemctl start pariah
```

All sessions are invalidated. Back up the secrets file **separately** from MariaDB dumps
(see [DEPLOYMENT.md](DEPLOYMENT.md) §4).

## Upgrades

1. Check [COMPATIBILITY.md](../COMPATIBILITY.md) for the OpenSimulator version.
2. Install the new RPM (`zypper install` / `rpm -Uvh`). Config is `%config(noreplace)`.
3. `systemctl restart pariah` — migrations and dependency sync run automatically.
4. Confirm `journalctl -u pariah -n 50` shows a clean migrate.
5. Spot-check `/manual.html`, login, and one admin page.

## Common troubleshooting

| Symptom | Check |
|---------|-------|
| Service fails at start | `journalctl -u pariah -n 100` — usually MariaDB unreachable or a migration error |
| Wrong visitor IP / bans misfire | Confirm Cloudflare Full (strict) and `cloudflare-real-ip.conf` is included |
| Sessions keep dropping after restart | `/etc/os_pariah/secrets` was regenerated or is missing from backups |
| No Super Admin after install | Log in once with a `userLevel >= 250` account, or set `ADMIN_UUID` and restart |
| Static CSS 404 after upgrade | `custom_css_path` still points at `/static/css/central.css` — migration `010` should have fixed the default; clear or update the setting |

## Related docs

- [DEPLOYMENT.md](DEPLOYMENT.md) — install and first-boot
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- End-user help: `/manual.html`
