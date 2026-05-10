# Changelog

All notable changes to OS Pariah Portal are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html) where practical. Release history was migrated from the former `ROADMAP.md` completed sections; future release notes should be appended here.

## [Unreleased]

### Known issues

- None recorded at migration from the roadmap. Track new findings as GitHub issues or append here before tagging a release.

---

## [0.10.1]

_range approximates roadmap “Completed (v0.10.0 – v0.10.1)”._

### Security

- Restrict who can change their own permissions (manage roles); allow only when the account is already Super Admin.
- Reserve destructive permissions (e.g. purge assets, delete grid users, assign Super Admin) for Super Admins only, not merely holders of manage-roles.
- Add `PERM_VIEW_PPI` so PPI (IP, MAC, HostID) is not exposed to everyone with user lookup; gate PPI behind explicit permission.
- Separate Knowledge Base document editing from policy-editing permissions.

### Fixed

- Gatekeeper lookup showed “Unknown User” for hypergrid records after robust info was included; IP/MAC/HostID linkage to names and UUIDs restored.
- Password reset via token could fail with an internal error.
- Expired or superseded password reset tokens were not cleaned up reliably.
- Registration page listed non-policy documents as “Required Reading”; only binding, login-not-required policies are shown.
- Manage Regions page permission checks did not use `check_bit` consistently.
- RBAC table and user level handling when all RBAC perms are removed; skip redundant RBAC checks for in-world admin user levels (0, 200) per policy.
- Online HUD still used legacy `is_admin` / userlevel logic; now driven by RBAC-style permission (e.g. who may view online users).

### Added

- Policy bouncer: users who decline current policies can be locked to a configurable user level while still able to log in and accept policies; restoration to normal levels on agreement.
- Region visibility for online HUD driven from region config (public listing toggle) instead of only `listable_regions`-style settings.
- Configurable CSS background image via settings (avoid editing packaged CSS for theming).
- Settings can support selectable options.
- Ban creation collects associated account identifiers and notes for review and escalation.
- Portal version visible in the UI (supports RPM workflow writing `app/version.py`).
- Region owners and estate managers: optional start/stop/restart and HUD list visibility via `Perm_Region_Control`, without full region management (tiers: off / owners / owners+managers).

### Changed

- Gatekeeper lookup: sort named results for easier scanning.
- Replace redundant “Valid Region Host IPs” with Region DNS mappings; warn when region host names lack mapping entries.
- Regions list UI: simplify status presentation (enabled/disabled vs duplicated labels).
- Policy admin: minor/major bump preview shows the actual resulting version numbers.
- Settings and DNA-related grid URL variables reworked (domain vs login URI, robust host/ports/protocol and derived URLs).

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
