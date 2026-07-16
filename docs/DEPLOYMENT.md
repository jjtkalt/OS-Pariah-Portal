# Deployment (openSUSE — Gunicorn + Nginx)

Production stack for OS-Pariah-Portal:

- **OS:** openSUSE Leap 15.6 (currently supported; Leap 16 tracked as a future target)
- **Database:** MariaDB (two databases: portal `os_pariah` and OpenSimulator `robust`)
- **App server:** Gunicorn bound to a Unix socket
- **Reverse proxy:** Nginx on the origin with **HTTPS** and **Cloudflare** at the edge
- **Python:** 3.12

Before installing or upgrading, check [COMPATIBILITY.md](../COMPATIBILITY.md) for the OpenSimulator version matrix.

## 1. MariaDB

Create a dedicated portal database and user (adjust names/passwords as needed). The Robust database is owned by OpenSimulator — grant the portal a **read-only** account against it.

```bash
sudo mariadb <<'SQL'
CREATE DATABASE os_pariah CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'pariah'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON os_pariah.* TO 'pariah'@'localhost';

-- Read-only access to the existing Robust database
CREATE USER 'robust_ro'@'localhost' IDENTIFIED BY 'CHANGE_ME_TOO';
GRANT SELECT ON robust.* TO 'robust_ro'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Automated tests mock both DB pools (no MariaDB service required for `pytest`).

## 2. Install via RPM (recommended)

```bash
# Optional: import the Pariah ecosystem signing key (see README.md)
sudo zypper install ./os-pariah-portal-*.rpm
# or: sudo rpm -Uvh ./os-pariah-portal-*.rpm

sudo vi /etc/os_pariah/os-pariah.conf   # DB credentials (see .env.example)
# SECRET_KEY is auto-generated into /etc/os_pariah/secrets on first service start
sudo systemctl enable --now pariah
sudo nginx -t && sudo systemctl reload nginx
```

The RPM:

- Creates the `pariah` system user
- Installs code to `/opt/os_pariah/`
- Ships config template as `/etc/os_pariah/os-pariah.conf` (`%config(noreplace)`)
- Installs systemd units, the nginx vhost, and `cloudflare-real-ip.conf`
- Builds the Python 3.12 virtualenv and installs `requirements.txt`

## 3. Manual install (unsupported; for development)

```bash
sudo useradd -r -g nginx -d /opt/os_pariah -s /sbin/nologin \
    -c "OS Pariah Portal Daemon User" pariah

sudo mkdir -p /opt/os_pariah /etc/os_pariah /var/log/os_pariah \
    /home/opensim/FSAssets/pariahcache /home/opensim/Backups/downloads
sudo chown pariah:pariah /opt/os_pariah /home/opensim/FSAssets/pariahcache
sudo chown pariah:opensim /var/log/os_pariah
sudo chmod 0770 /var/log/os_pariah

# Deploy application code to /opt/os_pariah (git clone / rsync)
cd /opt/os_pariah
python3.12 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

sudo cp .env.example /etc/os_pariah/os-pariah.conf
sudo chmod 0640 /etc/os_pariah/os-pariah.conf
sudo chown pariah:opensim /etc/os_pariah/os-pariah.conf
# Edit PARIAH_DB_* and ROBUST_DB_* (leave SECRET_KEY unset)

sudo cp packaging/pariah.service packaging/pariah-worker-*.service \
        packaging/pariah-worker-*.timer /usr/lib/systemd/system/
sudo cp packaging/OS-Pariah.conf /etc/nginx/vhosts.d/
sudo cp packaging/cloudflare-real-ip.conf /etc/nginx/conf.d/
sudo cp packaging/pariah_worker.sudo /etc/sudoers.d/pariah_worker
sudo chmod 0440 /etc/sudoers.d/pariah_worker

sudo systemctl daemon-reload
sudo systemctl enable --now pariah
sudo nginx -t && sudo systemctl reload nginx
```

## 4. Secrets (`/etc/os_pariah/secrets`)

`scripts/migrate.py` creates `/etc/os_pariah/secrets` (mode `0600`, owned by `pariah`) on first run with a strong auto-generated `SECRET_KEY`. It is loaded by systemd (`EnvironmentFile=-/etc/os_pariah/secrets`) and by `wsgi.py` after the main conf. The file is **not** shipped in the RPM.

Existing deployments that still set `FLASK_SECRET_KEY` in the conf continue to work; prefer migrating to the auto-generated secrets file.

**Rotate after a suspected leak:**

```bash
sudo systemctl stop pariah
sudo rm /etc/os_pariah/secrets
sudo systemctl start pariah
```

All users must log in again.

**Backups:** Include `/etc/os_pariah/secrets` in ops backups **separately** from MariaDB dumps.

**Override:** Set `SECRET_KEY` in the process environment to skip auto-generation (useful for HA — every node must share the same key).

## 5. Bootstrap admin

OS-Pariah authenticates against OpenSimulator accounts. Portal Super Admin is granted automatically on first login by an account with OpenSimulator `userLevel >= 250`.

Optionally, set `ADMIN_UUID=<opensim-uuid>` in `/etc/os_pariah/os-pariah.conf` to pre-seed Super Admin for a specific account on every migrate (idempotent; never downgrades). See `scripts/migrate.py`.

## 6. Database migrations

Migrations run automatically on service start via `ExecStartPre`. Manual run:

```bash
cd /opt/os_pariah
./venv/bin/python scripts/migrate.py
```

Numbered SQL files live in `migrations/` and are tracked in the `schema_versions` table.

## 7. Cloudflare origin HTTPS

1. Install a valid certificate on the origin (paths in `packaging/OS-Pariah.conf`).
2. Cloudflare dashboard → SSL/TLS → **Full (strict)**.
3. Confirm `/etc/nginx/conf.d/cloudflare-real-ip.conf` is installed so `$remote_addr` reflects the real visitor via `CF-Connecting-IP`. Refresh Cloudflare IP ranges periodically.

## 8. Verification

- `curl -I https://portal.example.com/` returns 200/302.
- `curl -I https://portal.example.com/manual.html` returns 200.
- `systemctl status pariah` is active.
- `journalctl -u pariah -n 50` shows migration success and (on first start) `Generated SECRET_KEY in /etc/os_pariah/secrets`.
- Session cookies work over HTTPS (`SESSION_COOKIE_SECURE=true`).

## Related docs

- [OPERATIONS.md](OPERATIONS.md) — day-to-day runbook (workers, logs, upgrades)
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- [../COMPATIBILITY.md](../COMPATIBILITY.md) — OpenSimulator version matrix
- End-user help: `/manual.html` on a running portal
