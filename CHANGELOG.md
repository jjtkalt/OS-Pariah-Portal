# Changelog

All notable changes to OS Pariah Portal are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where practical. Release history was migrated from the former `ROADMAP.md` completed sections; future release notes should be appended here.

## [Unreleased]

### Known issues

- None recorded. Track new findings as GitHub issues or append here before tagging a release.

---

## [1.0.1] – 2026-07-20

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
