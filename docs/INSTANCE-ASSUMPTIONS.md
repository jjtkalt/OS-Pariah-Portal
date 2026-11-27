# Instance assumptions (single instance today, multi-grid later)

OS-Pariah is **one portal per host** today. Operators will eventually want several
isolated grids on one server (separate portal, permissions, and grid each, with no
overlap). That is an epic and is deliberately **not designed here**. This page records
what the code assumes, so the first-boot wizard and later work do not make the future
harder, and so nobody has to rediscover the assumptions by grepping.

Tracked in GitHub as a `roadmap:future` placeholder issue (linked from issue #25).

## What exists now

* `app/utils/instance.py` resolves an **instance** (`default` only) to the canonical
  layout: conf, secrets, setup token, state/upload dirs, runtime socket, log dir, DB
  name/user, systemd unit, nginx vhost, texture cache, backup dir. Asking for any other
  id raises `ReservedInstanceError`. `tests/test_instance.py` pins the `default`
  values to the RPM spec, unit file, vhost and [NAMING.md](NAMING.md).
* New code (the setup wizard, `os-pariah-bootstrap`) goes through that resolver and
  records the instance id in `setup_state` (`_install.instance_id`). `OS_PARIAH_INSTANCE`
  is written into the conf by bootstrap; only `default` is accepted.
* The wizard also goes through a **grid provider** (`app/setup/providers.py`). Only
  `external` exists: an already-running grid, read-only. See "Related seams" below.

Existing scripts are **not** migrated onto the resolver yet (deliberately: no refactor
of working code in this slice). They keep their literals, inventoried next.

## Legacy single-instance literals

These all assume exactly one portal on the host. A multi-instance design will need to
route each of them through the resolver (or an equivalent) and decide per item whether
it is per-instance or shared.

| Where | Assumption |
|-------|------------|
| `wsgi.py` | loads `/etc/os-pariah/os-pariah.conf`, then `/etc/os-pariah/secrets` |
| `app/__init__.py` | state dir `/var/lib/os-pariah`; IAR worker lock under `/run/os-pariah/`; starts `os-pariah-worker-iar.service` via sudo |
| `app/config.py` | DB defaults `os-pariah` / `os_pariah`; secrets path |
| `app/utils/schema.py` | default paths: `/home/opensim/Log`, `/home/opensim/FSAssets/...os-pariah-cache`, backup dir; `robust_systemd_service` |
| `scripts/migrate.py` | conf path, DB name; writes `/etc/os-pariah/secrets` via `ensure_secrets.py` |
| `scripts/ensure_secrets.py` | `/etc/os-pariah/secrets`, user `os-pariah` |
| `scripts/check_mariadb.py` | conf path, DB name/user |
| `scripts/os_pariah_env.py` | conf path, DB identity, `/var/log/os-pariah/sync_workers.log` |
| `scripts/worker.py` | conf path, DB identity, `/home/opensim/Log` fallback, texture cache path |
| `scripts/backup_portal.py` | conf, secrets, nginx vhost and Cloudflare real-IP conf, `/var/lib/os-pariah/uploads`, worker timer drop-in, backup unit name |
| `scripts/apply_robust_texture_indexes.py` | conf path, `/opt/os-pariah/...` |
| `packaging/` | one unit set (`os-pariah*.service/.timer`), one vhost, one sudoers file, one RPM `%files` tree, one Linux user |

Everything **shared by design** today and therefore a hard problem for multi-grid:

* One Linux user (`os-pariah`) and group relationships with `opensim`.
* One set of narrow sudoers rules that call `sync_firewall.py` / `sync_robust.py` and
  control OpenSim/Robust units. These act on a single OpenSim install.
* One firewall rule set and one Robust configuration for ban enforcement.
* One nginx vhost with one Cloudflare real-IP include; one Turnstile site key per
  portal; one OIDC key pair.
* One `config` table: it is per database, so a second DB gives a second config, but the
  environment (`ROBUST_DB_*`) names a single Robust.

## Isolation dimensions (what "no overlap" means)

A future multi-instance design has to separate, per instance:

1. **Identity and files:** conf, secrets, setup token, state/uploads, logs, socket.
2. **Portal database and DB account** (`os_pariah` and its user).
3. **Grid access:** which Robust DB, read-only account, and (for providers that control
   it) which OpenSim services.
4. **Permissions (RBAC) and sessions:** separate `user_rbac`, separate cookie
   name/signing key, so a Super Admin on one portal is nobody on another.
5. **Network:** unix socket, nginx vhost/server name, TLS certificate, Cloudflare
   zone/Turnstile keys.
6. **systemd:** unit names, timers, and worker locks (template units such as
   `os-pariah@<id>.service` are a likely shape, not a decision).
7. **Package layout:** a single RPM tree under `/opt/os-pariah` can serve all
   instances (code is shared and root-owned); per-instance state must live elsewhere.
8. **Shared host resources:** firewall rules, Robust ban injection, backup targets.
   These need an explicit ownership model before more than one grid can use them.

## Design rules until the epic starts

1. New code that needs a path, unit name, DB identity or similar goes through
   `app/utils/instance.py`; do not add new `/etc/os-pariah/...` literals.
2. Anything persisted about the install records the instance id (as `setup_state`
   already does).
3. Never assume there is one `config` row set per host in new tables or keys: keep
   per-instance state in the instance's own database.
4. Do not make `robust_*` or ban/firewall behavior depend on being the only portal;
   say so in a comment where the single-grid assumption is unavoidable.
5. Wizard steps stay provider-scoped and instance-agnostic: they receive their
   context (connection, resolver) rather than reading globals or the filesystem.
6. `--instance` stays rejected for anything but `default` until the epic ships. A
   reserved id failing loudly is better than a half-isolated second instance.

## Related seams (kept ready, not built)

* **Installation provider:** `app/setup/providers.py` declares provider capabilities.
  `external` has only `READ_GRID`. A provider that installs OpenSim (the future merge
  with OS-Pariah Installation, see [ROADMAP.md](ROADMAP.md)) must declare mutating
  capabilities and contributes extra steps through the same registry. First boot of
  the portal never installs or reconfigures OpenSim; tests fail if wizard or bootstrap
  code references OpenSim ini files, `sync_robust`/`sync_firewall` or OpenSim units.
* **Versioned steps and advisory nudges:** later releases add steps without gating
  working installs ([OPERATIONS.md](OPERATIONS.md#setup-steps)).
* **Answers file versioning:** `os-pariah-bootstrap --answers` requires
  `answers_version`, so an installer or automation can drive it across releases.
