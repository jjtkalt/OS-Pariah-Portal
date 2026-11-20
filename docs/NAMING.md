# OS-Pariah naming standard

This repository is the **web / grid-management component** of the broader
**OS-Pariah** project. With a zero installed user base during QA, naming is
aligned to a single slug everywhere it matters for operators and packaging.

## Product vs slug

| Kind | Value | Used for |
|------|-------|----------|
| Proper / product name | **OS-Pariah** | Docs titles, UI copy, Descriptions, CHANGELOG |
| Filesystem / unit / package / conf slug | **os-pariah** | Paths, systemd units, RPM `Name:`, nginx files, Linux user |
| MariaDB database name | **os_pariah** | SQL identifier (hyphens would need quoting) |
| Env var prefix | **OS_PARIAH_*** | Config (`OS_PARIAH_DB_*`, `OS_PARIAH_UPLOAD_FOLDER`, …) |

The GitHub repository may still be named `OS-Pariah-Portal` historically; that does
not change the on-host slug. Prefer saying **OS-Pariah** in prose. “Portal” is an
internal nickname for this web component, not a separate product.

## Canonical on-host layout

| Surface | Path / name |
|---------|-------------|
| Install root | `/opt/os-pariah/` |
| Config | `/etc/os-pariah/os-pariah.conf` |
| Secrets | `/etc/os-pariah/secrets` |
| Runtime | `/run/os-pariah/` (`RuntimeDirectory=os-pariah`) |
| Unix socket | `/run/os-pariah/os-pariah.sock` |
| Logs | `/var/log/os-pariah/` |
| Private state (uploads) | `/var/lib/os-pariah/uploads/tickets/` |
| Texture JPG cache | `/home/opensim/FSAssets/os-pariah-cache/` |
| Linux user / group | `os-pariah` (service `User=os-pariah`, `Group=nginx` for the socket) |
| Master unit | `os-pariah.service` |
| Workers / timers | `os-pariah-worker-{iar,log,calendar}`, `os-pariah-cloudflare-ip`, `os-pariah-backup` |
| Sudoers | `/etc/sudoers.d/os-pariah-worker` |
| Nginx vhost | `/etc/nginx/vhosts.d/os-pariah.conf` |
| Cloudflare real-IP | `/etc/nginx/conf.d/os-pariah-cloudflare-ip.conf` |
| RPM | `os-pariah-*.rpm` (`Name: os-pariah`) |

Enable **only** the master unit (`systemctl enable --now os-pariah`). Packaged timers
are pulled in via `Requires=`; the IAR oneshot uses `Wants=` so a failed IAR run
never stops the web app.

## Intentional OpenSim exception: `ADMIN_UUID`

Platform Standards describe bootstrap admins by username. OS-Pariah authenticates
against OpenSimulator accounts whose stable identity is the **principal UUID**
(first/last name can change). Therefore:

- `ADMIN_UUID` in `/etc/os-pariah/os-pariah.conf` is the supported Super Admin seed
  (`scripts/migrate.py` + matching login path).
- There is no `ADMIN_USERNAME` bootstrap.
- Bare `userLevel >= 250` alone does **not** grant portal Super Admin.

## Future merge (roadmap context)

Long term, this web component and **OS-Pariah Installation** (openSUSE + OpenSimulator
hypergrid base install) are expected to merge behind a single install wizard that
can bring up a full enterprise grid with minimal admin experience. Naming here is
chosen so a merged tree can share one `os-pariah` slug without another rename.

See [ROADMAP.md](ROADMAP.md).
