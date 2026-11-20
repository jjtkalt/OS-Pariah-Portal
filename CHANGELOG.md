# Changelog

All notable changes to OS-Pariah (this web component; formerly “OS Pariah Portal”) are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where practical. Release history was migrated from the former `ROADMAP.md` completed sections; future release notes should be appended here.

## [Unreleased]

### Known issues

- None recorded. Track new findings as GitHub issues or append here before tagging a release.

---

## [1.2.0] – 2026-11-20

Minor release with a **breaking rename** to the `os-pariah` slug and a focused security/hardening pass. Operators on v1.1.x must reinstall against the new paths/units (no in-place path migration).

### Breaking

- **Rename to the `os-pariah` slug** ([docs/NAMING.md](docs/NAMING.md)): product name **OS-Pariah**; RPM `os-pariah` (was `os-pariah-portal`); install root `/opt/os-pariah`, config `/etc/os-pariah`, runtime `/run/os-pariah` (socket `os-pariah.sock`), logs `/var/log/os-pariah`; Linux user/group `os-pariah` (was `pariah`); master unit `os-pariah.service` with `os-pariah-worker-{iar,log,calendar}`, `os-pariah-cloudflare-ip`, `os-pariah-backup` (was `pariah*`); sudoers `/etc/sudoers.d/os-pariah-worker`; nginx `os-pariah.conf` / `os-pariah-cloudflare-ip.conf`; texture cache `/home/opensim/FSAssets/os-pariah-cache`. Database name stays `os_pariah`; env vars are `OS_PARIAH_DB_*`. Enable only `os-pariah.service`. No in-place migration from v1.x paths/units is provided (zero installed base during QA).
- **Private ticket uploads:** attachments move to `/var/lib/os-pariah/uploads/tickets` (`0750`), served only through authenticated routes (not `app/static/uploads`).
- `docs/ARCHITECTURE-EXCEPTIONS.md` removed; replaced by `docs/NAMING.md` (naming + `ADMIN_UUID` exception) and `docs/ROADMAP.md`.

### Security

- **CSP / headers:** Content-Security-Policy (`object-src 'none'`, Turnstile allowlist) plus `Permissions-Policy`, `Referrer-Policy`, and HSTS `max-age=31536000; includeSubDomains` on the packaged vhost; Flask sends the same CSP/frame/nosniff/permissions/referrer headers as a non-nginx fallback.
- **Session refresh:** session permissions and `userLevel` are re-synced from the databases on every request, so bans and role/level changes take effect without waiting for cookie expiry.
- **Supply chain:** `requirements.txt` is hash-pinned (`pip-compile --generate-hashes`) and installed with `--require-hashes`.
- **RBAC:** role form accepts only known single-bit permissions (blocks composite values that previously minted Super Admin); `set_level` is Super-Admin-only with range checks; login bootstrap grants Super Admin only for configured `ADMIN_UUID` (not bare `userLevel >= 250`).
- **CSRF:** Flask-WTF `CSRFProtect` enabled globally (API bot + OIDC token exempt); logout is POST; templates inject CSRF meta/token.
- **Host-header:** `ProxyFix` no longer trusts `X-Forwarded-Host`/`Prefix`; emailed/OIDC absolute URLs use configured `portal_url`.
- **XSS / IDOR:** approvals and settings admin JS use `data-*` attributes; ticket replies require owner or staff.
- **OIDC:** requires registered `oidc_clients` row, exact redirect URI, and client secret; signing key prefers `/etc/os-pariah/oidc_private.pem`.
- **Secrets / captcha:** production refuses insecure default `SECRET_KEY`; Turnstile defaults are empty (fail closed until configured); audit log uses its own DB connection (no mid-request commit).
- **`migrate.py`:** exits non-zero on failure; resolves `migrations/` from repo root.
- **Packaging:** `/opt/os-pariah` (code, scripts, venv) is now `root:root` with `go-w`; only upload/runtime dirs stay `os-pariah`-owned. `opensim` group is created in `%pre` if missing; sudoers drop-in is `0440 root:root`; `sudo` and `screen` are RPM `Requires:`.
- **sudoers:** the `os-pariah` user may only `systemctl start os-pariah-worker-iar.service` (stop/restart removed).
- **Release workflow:** RPM builds are gated on a successful *Automated Tests* run for the release SHA; `softprops/action-gh-release` is pinned by commit; tag/run values are passed via `env`.
- **Nginx:** removed duplicate `include` of the Cloudflare real-IP conf; security headers repeated in nested locations (`always`); `limit_req_status 429`; client-supplied `X-Forwarded-Host` / `X-Forwarded-Prefix` cleared.
- **`SECURITY.md`:** reports go through GitHub Private Vulnerability Reporting; supported versions = latest release on `main`.

### Changed

- **systemd:** `os-pariah.service` uses `Wants=` for the IAR worker (timers stay `Requires=`); `sync_requirements.py` runs as root via `ExecStartPre=+`. `os-pariah-worker-iar.service` no longer `Requires=os-pariah.service`.
- **Calendar:** `os-pariah-worker-calendar.timer` now fires every **1 minute**; start/halfway/reminder windows in `scripts/calendar_notifications.py` are late-tolerant (90 s / 90 s / 60 s) and rely on `notification_already_sent` for dedup.
- **Firewall sync:** `scripts/sync_firewall.py` diffs against `firewall-cmd --permanent --direct --get-all-rules`, removing Host-ID DROP rules for hosts no longer banned and only adding missing rules.
- **Backup:** IAR timer drop-in now resets `OnUnitActiveSec=` before setting the configured interval.
- **Pre-commit:** only Ruff runs on commit; the full `check-local` gate runs on `pre-push`.
- **requirements.txt:** test-only packages and unused `dicttoxml` / `Pygments` removed; added `Flask-WTF`. Dependabot + follow-up pins including `icalendar` 7.3.2 and `ruff` 0.17.6 (CI / pre-commit aligned).

### Added

- Branded static error pages (`app/static/errors/`), `app/error_handlers.py` + `templates/errors/*`, static `app/static/manual.html` served by nginx at `/manual.html`.
- `Makefile` (`lint`, `fmt`, `test`, `check`, `audit`, `sync`, `lock`), `tests/test_packaging_units.py`, `docs/NAMING.md`, `docs/ROADMAP.md`, OIDC notes in `docs/OPERATIONS.md`.
- Dependabot tracks GitHub Actions.
- Regression tests for composite RBAC bits, `set_level` gate, and ticket reply IDOR.

### Known issues

- None recorded.

---

## [1.1.1] – 2026-11-20

Patch release: dependency security updates, portal self-backup / IAR sweep timers, and CI/release workflow hardening for the `develop`/`main` branch model.

### Added

- **Portal self-backup:** `pariah-backup.service` / `.timer` runs `scripts/backup_portal.py` daily (03:30) to dump the Pariah MariaDB database and copy significant files (`/etc/os_pariah/os-pariah.conf`, `secrets`, nginx vhost, Cloudflare real-IP conf) under `portal_backup_dir` (default `/home/opensim/Backups/portal`), with `portal_backup_retention_days` (default 14). Cache and user IAR download trees are excluded.
- **IAR sweep timer:** `pariah-worker-iar.timer` periodically starts the same `worker.py iar` entrypoint used for on-demand IAR creation (pending catch-up + retention cleanup). Interval defaults to **7 days** via `iar_sweep_interval_days`; the backup job writes a systemd drop-in so the timer tracks that setting.
- Worker cleanup tests covering IAR retention SQL/file removal and texture cache age keep/clear behavior.
- **CI:** `delete-merged-branch.yml` removes merged feature branches while protecting `main` and `develop`. Pull-request CI now runs for both `main` and `develop`. RPM builds refuse releases whose commit is not on `main`.

### Changed

- Dynamic config resolution treats **DB override → `KNOWN_SETTINGS` schema default → call-site default** as authority in both `app.utils.db.get_dynamic_config` and `scripts/worker.py` (call-site defaults no longer shadow schema). Worker retention helpers use `get_dynamic_config_int` for `iar_retention_days` and `texture_cache_retention_days`.
- Dependency security and maintenance bumps (Dependabot + `pip-audit` track), including `certifi` 2026.10.23, `cryptography` 50.0.2, `gunicorn` 27.0.1, `numpy` 2.5.5, `PyJWT` 2.15.1, `urllib3` 2.8.0, `Werkzeug` 3.1.9, and related transitive pins.
- Ruff pinned to **0.17.5** across CI, pre-commit, and `requirements-dev.txt`.

### Known issues

- None recorded.

---

## [1.1.0] – 2026-09-15

Minor release: Python **3.13** runtime, packaging ownership hotfixes (#61), texture gallery performance, and ops/docs polish. Prefer this over withdrawn **v1.0.1**. Operators still on **v1.0.0** should upgrade here (not via 1.0.1).

### Fixed

- **Texture gallery hang:** global listing no longer drives from a full `inventoryitems` ⨝ `fsassets` join on the request path. Recent rows are served from Pariah `texture_gallery_snapshot` (refreshed by `pariah-worker-log`: at least the last **14 days**, topped up to at least **2000** rows on quiet grids, capped for busy grids); Robust queries use an fsassets-first plan. Optional additive Robust indexes via `scripts/apply_robust_texture_indexes.py` (see #59).
- **`/etc/os_pariah` directory ownership:** restore group `opensim` (`0750 pariah:opensim`) so worker units (`User=opensim`) can read `os-pariah.conf`. v1.0.1 incorrectly used `pariah:pariah`, which made workers fall back to default `pariah_user` and fail MariaDB auth (#61). Secrets remain `0600` / `pariah`-only.
- **Texture cache directory ownership:** `/home/opensim/FSAssets/pariahcache/` is `0775 pariah:opensim` so the portal can write JPGs and `opensim` workers can run cache cleanup (#61).

### Added

- **Local CI gate:** `scripts/check_local.py` runs Ruff lint/format check, pytest, and `pip-audit` (wired as a pre-commit hook; see Contributing in `README.md`). Ruff is pinned to **0.16.1** across CI, pre-commit, and `requirements-dev.txt`.
- Migration `011_texture_gallery_snapshot.sql` and settings `texture_gallery_snapshot_days` (default 14), `texture_gallery_snapshot_min_rows` (default 2000), `texture_gallery_snapshot_limit` (max-row safety cap).
- Ops one-off: `scripts/apply_robust_texture_indexes.py` + `scripts/sql/robust_texture_gallery_indexes.sql`.
- **Portal favicon:** default `app/static/images/pariah.ico` linked from `base.html`, splash, and the user manual; override via System Settings → Grid Identity → `portal_favicon`. `/favicon.ico` redirects to the configured icon for clients that probe the site root (nginx now proxies that path instead of swallowing it).
- **Dependabot:** group all pip dependency updates into a single monthly PR (`groups.all-dependencies` with `patterns: ["*"]`).
- Deployment notes for providing Python 3.13 on **Leap 15.6** (no stock 3.13) versus Leap 16 OSS packages.

### Changed

- **Python 3.13:** runtime target bumped from 3.12 (CI, Ruff `target-version = "py313"`, deployment docs). Aligns with Platform Standards and openSUSE Leap 16. RPM requires `/usr/bin/python3.13` (recommends `python313` / `python313-devel`); `%post` uses `python3.13 -m venv --clear` so upgrades recreate the venv cleanly. `%pre` fails early with install hints when 3.13 is missing.
- **Registration password rationale** documented under Portal → Registration Page in `PHILOSOPHY.md` (createuser immediately, park at `UserLevel -1`, never store plaintext in Pariah).

### Removed

- **`DesignProcess.md`:** retired design-era draft (~3.5k lines of stale code snapshots). Living docs are `PHILOSOPHY.md`, `docs/DEPLOYMENT.md`, `docs/OPERATIONS.md`, and the codebase.

---

## [1.0.1] – 2026-07-20

> **WITHDRAWN — do not install.** GitHub release artifacts removed. Packaging regression: `/etc/os_pariah` was owned `pariah:pariah` mode `0750`, so `opensim` workers could not read the config and failed with `Access denied for user 'pariah_user'@'localhost'`. Stay on **v1.0.0** or apply the workaround in [#61](https://github.com/jjtkalt/OS-Pariah-Portal/issues/61) until **v1.1.0**.

Maintenance release focused on dependency security updates and Platform Standards alignment. Changes since [1.0.0](#100--2026-05-31).

### Security

- **Dependency updates** addressing current advisories and supply-chain freshness: `cryptography` 46.0.7 → 49.0.0, `PyJWT` 2.12.0 → 2.13.0, plus `certifi`, `bleach`, and related transitive pins.
- **Secrets separation (ADR-013):** `SECRET_KEY` is generated and stored in `/etc/os_pariah/secrets` (mode 0600, owned by `pariah`), not in the main config file; development uses a project-root `.secrets` fallback via `scripts/ensure_secrets.py`.
- **Cloudflare client IP trust:** packaged `pariah-cloudflare-ip` timer/service keeps nginx `set_real_ip_from` ranges current so access control and audit logs see true client addresses behind Cloudflare Full (strict).

### Added

- Daily Cloudflare IP range updater (`scripts/update_cloudflare_real_ip.py`, `pariah-cloudflare-ip.service` / `.timer`), pulled in by the master `pariah.service`.
- Dependabot configuration for pip dependency PRs.
- Ruff lint and format with pre-commit hooks and a CI `lint` job.
- Platform Standards packaging and docs depth: tabbed `/manual.html`, `app/static/css/base.css` tokens, `docs/DEPLOYMENT.md`, and `docs/OPERATIONS.md`.

### Changed

- Align portal install layout with Platform Standards (secrets path, CSS rename `central.css` → `base.css` with migration `010_rename_central_css.sql`, Cloudflare conf naming).
- Admin template markup cleanup for consistency with shared form styling.

### Dependencies

- Bumped: `cachelib`, `certifi`, `charset-normalizer`, `cryptography`, `DBUtils`, `Flask-Caching`, `packaging`, `PyJWT`, `PyMySQL`, `pytest`, `markdown`, `bleach`.

---

## [1.0.0] – 2026-05-31

First stable release. Changes since [0.10.1](#0101).

### Added

- **Calendar and events:** month/week/schedule views, recurring events, community suggestions with staff moderation, follows with email and in-world reminders, iCal/RSS subscription feeds, and tier/category filtering.
- **Grid Service Bot integration:** in-world group chat and notice delivery for event announcements; admin bot message queue with retry; packaged LSL scripts and `pariah-worker-calendar` timer/service.
- **Online users page** (`/comms/online`): portal view of who is online, respecting RBAC for all-regions vs public-only visibility (shared logic with the online HUD).
- **Registration application notes:** pending registration details are persisted to staff user notes in the same transaction as the application.
- **`sync_requirements.py`:** pre-start dependency sync invoked from `pariah.service` so RPM installs stay aligned with `requirements.txt`.

### Security

- Texture proxy and IAR download routes validate normalized paths against their base directories to block path traversal (CodeQL findings).

### Changed

- Role management audit log entries include human-readable RBAC labels before and after permission changes.
- GitHub Actions workflows use refined `permissions` scopes.

### Dependencies

- `idna` updated (Dependabot maintenance track).
- New calendar dependencies: `python-dateutil`, `icalendar`.

---

## [0.10.1] – 2026-05-12

Changes since [0.10.0](#0100).

### Security

- Manage Roles: restrict changing your own permission mask unless you are already Super Admin; reserve destructive capabilities (e.g. purge assets, delete grid users, assign Super Admin) for Super Admins, not only for users who hold manage-roles.
- Gatekeeper lookup: add `PERM_VIEW_PPI` so PPI (IP, MAC, HostID) is not exposed to everyone with user lookup.
- Separate Knowledge Base document editing from grid policy editing permissions.

### Fixed

- Gatekeeper lookup showed “Unknown User” for some hypergrid paths after Robust enrichment; linkage of IP/MAC/HostID to names and UUIDs restored (includes HG lookup hotfix).
- Password reset via token could fail internally; expired or superseded tokens are cleaned up more reliably.
- Registration “Required Reading” listed non-policy documents; only binding policies that do not require login are shown.
- Manage Regions: permission checks now use `check_bit` consistently.
- RBAC when all portal bits are removed from a user; redundant RBAC checks skipped for in-world admin Robust tiers (0, 200) per policy.
- Online HUD no longer relies on legacy `is_admin` / userlevel checks alone; visibility follows RBAC (including region-owner scenarios).
- **Policy agreement:** agreeing to an updated policy version **only** restores Robust user level from the policy-decline lock tier. Staff and admins (normal positive levels) are no longer reset to 0/1 when recording agreement.
- **Texture gallery worker:** cache cleanup uses configurable retention again (see Added); fixes unintended aggressive deletion when retention was hard-coded shorter than documented defaults.

### Added

- Policy decline flow: configurable Robust lock tier (`policy_decline_user_level`); users can still log in to read policies and agree or decline.
- Who may see which regions on the online HUD respects region config (e.g. public listing toggle), not legacy listable-region settings.
- Configurable portal background image via settings (theming without editing packaged CSS).
- **Settings schema:** `selectable` field type with comma-separated `options`; validated on save (e.g. **Region Owner/Estate Manager Controls** as a dropdown: `no` / `owners` / `owners_managers`).
- **`texture_cache_retention_days`** setting (default 30); `scripts/worker.py` cleanup honors it for JPG cache files under `texture_cache_path`.
- Ban creation collects associated account identifiers and notes for review and escalation.
- Portal version string shown in the UI (`app/version.py`; RPM-friendly).
- Region owners / estate managers (optional): start/stop/restart and HUD visibility via region-control permission, without full region management—tiered by `region_owner_control_level`.
- Robust **systemd unit name** setting for optional service restart after MAC ban sync.
- This changelog as the canonical release history; legacy roadmap retired (planned work tracked in GitHub issues).

### Changed

- Gatekeeper lookup: named results sorted; “Valid Region Host IPs” replaced by Region DNS mappings with warnings when a region hostname has no mapping.
- Regions list UI: clearer enabled/disabled presentation.
- Policy admin: minor/major bump preview shows the resulting version strings accurately.
- Grid connectivity settings clarified further (`domainName`, Robust host/ports/protocol, derived public/private URLs).
- Ban management UI and Gatekeeper-oriented display names on bans.
- User management and helpdesk ticket handling refactored to reduce inappropriate reliance on raw IP fields where Robust identifies users.

### Dependencies

- `urllib3` updated (Dependabot security/maintenance track).

---

## [0.10.0]

_range approximates roadmap “Completed (v0.9.4 – v0.10.0)”._

### Added

- Role-based access control (RBAC): assign portal permissions to non-grid-admin users via dedicated UI; extensible for future permissions.
- Bootstrap path for grid owners: users at userlevel 250+ with no RBAC row receive Super Admin until RBAC is assigned (recovery / first admin).
- Profile page shows current email; admins can change user email and issue forced password resets.
- Audit trail in the database for portal changes, with review UI for high admins.
- Settings: “no reset to default” settings; per-field auto-save with inline success/error instead of a global “Save All”; clearer default vs overridden indicators.

### Changed

- Clarify and split grid connectivity settings (`domainName`, robust host/ports, protocols, derived public/private Robust URLs) instead of overloading `DOMAIN`.

---

## [0.9.4]

_range approximates roadmap “Completed (v0.9.2 – v0.9.4)”._

### Security

- Dependency updates for known vulnerabilities.
- Tighter sudoers layout via dedicated `pariah_workers` include instead of inline spec echoes.

### Fixed

- `check_mariadb.py` missing from RPM install.
- Migration: `region_configs.is_active` column.
- Config file group ownership so OpenSim can run worker services.
- Systemd unit path for RPM (`/usr/lib/systemd/system/`).
- Policy bouncer firing when no policies exist; default `global_policy_version` semantics.
- Splash/policy handling when global policy version is unset.
- Region controls: sudo failures after permission tightening.
- CSS path theming overwritten on upgrade (configurable location).
- Change-email flow database error.
- Hypergrid users incorrectly offered user level changes in lookup.
- User password change reported success when Robust update failed; URL/config/method corrected.
- IAR generation failure (`NoneType` path).
- Variable label/description fixes (`allow_ticket_deletion`, `region_host_ips`).
- Settings save wrote defaults into DB; only persist overrides and show default values clearly.

### Added

- Splash/welcome screen content for viewers.
- Helpdesk: filter closed/withdrawn tickets.
- Texture/photo review for admins; texture gallery improvements (orphan handling, search by name, skip non-display types, hash UX).
- Region configurations: disable/re-enable/delete workflow.
- Gatekeeper cross-reference: multi-match buttons for exact search; grid-from info on UUIDs; display last-seen timestamps.
- User display name changes for admins.
- `%license` in spec; assorted packaging fixes.

### Changed

- Main content width/CSS centralization sweep.
- Gatekeeper cross-reference and listing behaviors.

---

## [0.9.2]

_range approximates roadmap “Completed (v0.9.0 – v0.9.2)”._

### Added

- RPM packaging pipeline for openSUSE/RHEL.
- Unix socket deployment for Gunicorn.
- GitHub Actions for CI and releases.
- Database migration engine (`migrate.py`).
- Webhook/settings UI improvements (discoverable variables, grouped blocks).
- Expanded testing direction (integration/smoke coverage).

### Fixed

- Registration form regression (submit affordance messaging).
- Helpdesk layout (half-width submit, ticket view height).
- Grid branding link targets home/base URL correctly.

### Changed

- Default values pulled from migrations vs hard-coded defaults where appropriate.
- Bans/warnings behavior verified against firewall and Robust.

---

## Earlier history

Items from roadmap “v0.9.0 – v0.9.2” also referenced foundational verification (bans, user promotion, etc.). For detail prior to this changelog, see git history and archived roadmap commits.
