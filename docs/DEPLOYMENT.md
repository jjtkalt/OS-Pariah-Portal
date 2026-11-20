# Deployment (openSUSE — Gunicorn + Nginx)

Production stack for OS-Pariah (this web component; see [NAMING.md](NAMING.md) for slugs and paths):

- **OS:** openSUSE Leap **16** preferred (Platform Standards; stock Python 3.13). Leap **15.6** is supported only if you provide `/usr/bin/python3.13` yourself (see below).
- **Database:** MariaDB (two databases: OS-Pariah `os_pariah` and OpenSimulator `robust`)
- **App server:** Gunicorn bound to a Unix socket
- **Reverse proxy:** Nginx on the origin with **HTTPS** and **Cloudflare** at the edge
- **Python:** 3.13 (`/usr/bin/python3.13`)

Before installing or upgrading, check [COMPATIBILITY.md](../COMPATIBILITY.md) for the OpenSimulator version matrix.

## Python 3.13 prerequisite

The RPM requires `/usr/bin/python3.13` (and recommends the Leap 16 `python313` / `python313-devel` packages). `%post` builds `/opt/os-pariah/venv` with that interpreter.

### Leap 16 (recommended)

```bash
sudo zypper install python313 python313-devel
python3.13 --version
```

### Python 3.13 on Leap 15.6

Leap 15.6 official repositories stop at Python **3.12**. The OBS `devel:languages:python:Factory` repo for 15.6 currently publishes 3.12 as well, so there is **no reliable stock package** for 3.13 on 15.6.

**Preferred:** upgrade the host to Leap 16, then install `python313` as above.

**If you must stay on Leap 15.6**, install CPython 3.13 from source (altinstall) and expose it as `/usr/bin/python3.13` **before** installing the OS-Pariah RPM:

```bash
# Build dependencies
sudo zypper install -y gcc make tar wget \
  openssl-devel libffi-devel zlib-devel readline-devel \
  sqlite3-devel xz-devel libbz2-devel ncurses-devel libuuid-devel

PYTHON_VER=3.13.14   # pin to a current 3.13.x patch you trust
cd /usr/local/src
sudo wget "https://www.python.org/ftp/python/${PYTHON_VER}/Python-${PYTHON_VER}.tgz"
sudo tar xf "Python-${PYTHON_VER}.tgz"
cd "Python-${PYTHON_VER}"

# --prefix=/usr/local keeps system /usr/bin/python3 untouched
sudo ./configure --prefix=/usr/local --enable-optimizations --with-ensurepip=install
sudo make -j"$(nproc)"
sudo make altinstall

# Satisfy the RPM file require used by packaging/os-pariah.spec
sudo ln -sf /usr/local/bin/python3.13 /usr/bin/python3.13
python3.13 --version
python3.13 -m venv --help >/dev/null
```

Notes for Leap 15.6 altinstalls:

- Do **not** replace `/usr/bin/python3` (system tools still expect the distro Python).
- After upgrading OS-Pariah from a 3.12-based install, `%post` runs `python3.13 -m venv --clear /opt/os-pariah/venv` so the old venv is discarded.
- If `pip install` later needs to compile a wheel, install matching headers (`openssl-devel`, etc.) — there is no `python313-devel` package on 15.6.
- Leap 15.6 is past its normal support window; plan a Leap 16 migration when you can.

## 1. MariaDB

Create a dedicated OS-Pariah database and user (adjust passwords as needed). The database is named `os_pariah` (underscore — SQL identifier) and the DB user is `os-pariah` (quote it in SQL). Config uses `OS_PARIAH_DB_*`. The Robust database is owned by OpenSimulator — grant OS-Pariah a **read-only** account against it.

```bash
sudo mariadb <<'SQL'
CREATE DATABASE os_pariah CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'os-pariah'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON os_pariah.* TO 'os-pariah'@'localhost';

-- Read-only access to the existing Robust database
CREATE USER 'robust_ro'@'localhost' IDENTIFIED BY 'CHANGE_ME_TOO';
GRANT SELECT ON robust.* TO 'robust_ro'@'localhost';
FLUSH PRIVILEGES;
SQL
```

Automated tests mock both DB pools (no MariaDB service required for `pytest`).

## 2. Install via RPM (recommended)

On Leap 15.6, finish the [Python 3.13 prerequisite](#python-313-prerequisite) first.

```bash
# Optional: import the OS-Pariah ecosystem signing key (see README.md)
sudo zypper install ./os-pariah-*.rpm
# or: sudo rpm -Uvh ./os-pariah-*.rpm

sudo vi /etc/os-pariah/os-pariah.conf   # DB credentials (see .env.example)
# SECRET_KEY is auto-generated into /etc/os-pariah/secrets on first service start
sudo systemctl enable --now os-pariah   # master unit only; timers are pulled in
sudo nginx -t && sudo systemctl reload nginx
```

The RPM:

- Creates the `os-pariah` system user and group
- Installs code to `/opt/os-pariah/` (root-owned) and creates private ticket-upload storage at `/var/lib/os-pariah/uploads/tickets/`
- Ships config template as `/etc/os-pariah/os-pariah.conf` (`%config(noreplace)`)
- Installs systemd units, the nginx vhost, and `os-pariah-cloudflare-ip.conf`
- Requires `/usr/bin/python3.13`; builds the Python 3.13 virtualenv and installs the hashed `requirements.txt` (`--require-hashes`)

## 3. Manual install (unsupported; for development)

```bash
sudo groupadd -r os-pariah
sudo useradd -r -g os-pariah -d /opt/os-pariah -s /sbin/nologin \
    -c "OS-Pariah Daemon User" os-pariah
# The service unit runs with User=os-pariah, Group=nginx (socket access).

sudo mkdir -p /opt/os-pariah /etc/os-pariah /var/log/os-pariah \
    /var/lib/os-pariah/uploads/tickets \
    /home/opensim/FSAssets/os-pariah-cache /home/opensim/Backups/downloads
sudo chown os-pariah:os-pariah /opt/os-pariah
sudo chown -R os-pariah:os-pariah /var/lib/os-pariah
sudo chmod 0750 /var/lib/os-pariah /var/lib/os-pariah/uploads /var/lib/os-pariah/uploads/tickets
sudo chown os-pariah:opensim /etc/os-pariah /var/log/os-pariah /home/opensim/FSAssets/os-pariah-cache
sudo chmod 0750 /etc/os-pariah
sudo chmod 0770 /var/log/os-pariah
sudo chmod 0775 /home/opensim/FSAssets/os-pariah-cache

# Deploy application code to /opt/os-pariah (git clone / rsync)
cd /opt/os-pariah
python3.13 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install --require-hashes -r requirements.txt   # hashed lockfile (pip-compile --generate-hashes)

sudo cp .env.example /etc/os-pariah/os-pariah.conf
sudo chmod 0640 /etc/os-pariah/os-pariah.conf
sudo chown os-pariah:opensim /etc/os-pariah/os-pariah.conf
# Edit OS_PARIAH_DB_* (DB user os-pariah) and ROBUST_DB_* (leave SECRET_KEY unset)

sudo cp packaging/os-pariah.service packaging/os-pariah-worker-*.service \
        packaging/os-pariah-worker-*.timer packaging/os-pariah-cloudflare-ip.service \
        packaging/os-pariah-cloudflare-ip.timer packaging/os-pariah-backup.service \
        packaging/os-pariah-backup.timer /usr/lib/systemd/system/
sudo mkdir -p /home/opensim/Backups/portal
sudo chmod 0750 /home/opensim/Backups/portal
sudo cp packaging/os-pariah.conf /etc/nginx/vhosts.d/
sudo cp packaging/os-pariah-cloudflare-ip.conf /etc/nginx/conf.d/
sudo cp packaging/os-pariah-worker.sudo /etc/sudoers.d/os-pariah-worker
sudo chmod 0440 /etc/sudoers.d/os-pariah-worker

sudo systemctl daemon-reload
sudo systemctl enable --now os-pariah
sudo nginx -t && sudo systemctl reload nginx
```

## 4. Secrets (`/etc/os-pariah/secrets`)

`scripts/migrate.py` creates `/etc/os-pariah/secrets` (mode `0600`, owned by `os-pariah`) on first run with a strong auto-generated `SECRET_KEY`. It is loaded by systemd (`EnvironmentFile=-/etc/os-pariah/secrets`) and by `wsgi.py` after the main conf. The file is **not** shipped in the RPM.

Existing deployments that still set `FLASK_SECRET_KEY` in the conf continue to work; prefer migrating to the auto-generated secrets file.

**Rotate after a suspected leak:**

```bash
sudo systemctl stop os-pariah
sudo rm /etc/os-pariah/secrets
sudo systemctl start os-pariah
```

All users must log in again.

**Backups:** `os-pariah-backup.timer` (pulled in by `os-pariah.service`) runs
`scripts/backup_portal.py` daily. Each run dumps the `os_pariah` MariaDB database and
copies significant files (`os-pariah.conf`, `secrets`, nginx vhost, Cloudflare
real-IP conf) under `portal_backup_dir` (default `/home/opensim/Backups/portal`).
Texture cache and user IAR download trees are not included. Keep an off-host copy
of that directory; treat backup trees that contain `secrets` as sensitive.

**Override:** Set `SECRET_KEY` in the process environment to skip auto-generation (useful for HA — every node must share the same key).

## 5. Bootstrap admin

OS-Pariah authenticates against OpenSimulator accounts. Set `ADMIN_UUID=<opensim-uuid>` in `/etc/os-pariah/os-pariah.conf` to grant Super Admin to that PrincipalID on migrate and first matching login (idempotent; never downgrades). See `scripts/migrate.py` and [NAMING.md](NAMING.md).

## 6. Database migrations

Migrations run automatically on service start via `ExecStartPre`. Manual run:

```bash
cd /opt/os-pariah
./venv/bin/python scripts/migrate.py
```

Numbered SQL files live in `migrations/` and are tracked in the `schema_versions` table.

## 7. Cloudflare origin HTTPS

1. Install a valid certificate on the origin (paths in `packaging/os-pariah.conf`).
2. Cloudflare dashboard → SSL/TLS → **Full (strict)**.
3. Confirm `/etc/nginx/conf.d/os-pariah-cloudflare-ip.conf` is installed so `$remote_addr` reflects the real visitor via `CF-Connecting-IP`. Enabling `os-pariah` also starts `os-pariah-cloudflare-ip.timer` (daily refresh); run `systemctl start os-pariah-cloudflare-ip.service` for a one-shot update.
4. **Upgrading from an older package:** remove leftover `/etc/nginx/conf.d/cloudflare-real-ip.conf` if present, so nginx does not load duplicate `set_real_ip_from` / `real_ip_header` directives.

## 8. Verification

- `curl -I https://portal.example.com/` returns 200/302.
- `curl -I https://portal.example.com/manual.html` returns 200.
- `systemctl status os-pariah` is active.
- `journalctl -u os-pariah -n 50` shows migration success and (on first start) `Generated SECRET_KEY in /etc/os-pariah/secrets`.
- Session cookies work over HTTPS (`SESSION_COOKIE_SECURE=true`).

## Related docs

- [OPERATIONS.md](OPERATIONS.md) — day-to-day runbook (workers, logs, upgrades)
- [../SECURITY.md](../SECURITY.md) — vulnerability reporting
- [../COMPATIBILITY.md](../COMPATIBILITY.md) — OpenSimulator version matrix
- End-user help: `/manual.html` on a running instance
