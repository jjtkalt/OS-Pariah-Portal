# Planned enhancements → GitHub issues

This file lists **unfinished** roadmap items (Short-Term, Mid-Term, Future) in a shape you can turn into GitHub issues.

## How to use

1. Create an issue for each `###` block (title is the heading).
2. Recommended labels:
   - Always: `enhancement`
   - Exactly one horizon label:
     - `roadmap:short-term`
     - `roadmap:mid-term`
     - `roadmap:future`
3. Paste the **Description** into the issue body. Optionally prefix with `## Summary` / keep bullets as-is.

Create labels in the repo if they do not exist (GitHub: **Settings → Labels**):

| Label | Color suggestion | Meaning |
|-------|------------------|---------|
| `roadmap:short-term` | `#0E8A16` | Next minor-ish horizon |
| `roadmap:mid-term` | `#FBCA04` | Next major / broader change |
| `roadmap:future` | `#C5DEF5` | Large or exploratory |

**Example (`gh` CLI):**

```bash
gh issue create --title "Invite code for registration" --body-file - --label "enhancement" --label "roadmap:short-term" <<'EOF'
...
EOF
```

---

## Short-Term

_Status label: `roadmap:short-term` (also tag `enhancement`)._

### Regions.ini information in the portal database

**Description**

All regional information should live in the portal database so region-specific ini files are not required for regions (currently in testing / “in progress”).

---

### Invite code and sponsor linkage for registration

**Description**

Framework exists for requiring an invite code when the setting is on, but end-user flow is not implemented. When enabled, linking a user to their sponsor / voucher / inviter is missing; that relationship should appear when viewing either user.

---

### User notes shared across alts (MAC/HostID and display)

**Description**

On the lookup page, admin notes (by UUID) should logically attach to all alts of the same person (local and hypergrid). Likely link via MAC and/or HostID with lookup at display time. Update recording/display so notes store both avatar name and UUID; consider dropdown when multiple people share a home account; optionally record original MAC/HostID for audit when hardware changes.

---

### Shutdown warning when users are present in a region

**Description**

On region stop or restart, warn if users are in the region (possibly via an admin notice API method).

---

### Pariah logs under `/var/log/os_pariah`

**Description**

Write Pariah logs to `/var/log/os_pariah` (not only journald) for historical review; optionally export audit log there too.

---

### Two-factor authentication (2FA)

**Description**

Add 2FA with settings to require it for admins and/or users. “Admins” means anyone with any RBAC permission (RBAC ≠ 0).

---

### Region rental system

**Description**

Large effort: track rentals; users choose size/prims/add-ons and pay; automated setup; payment tracking with shutdown when unpaid; user notifications (due, past due, shutdown).

---

### IP geolocation capture and display

**Description**

If an IP lacks geolocation data, collect and store it for admin pattern review (account sharing hints, compromised accounts, etc.).

---

### Lookup: browse/filter full user list

**Description**

List all users with optional filters (local vs hypergrid); optional alphabetical index; names clickable for gatekeeper lookup.

---

### Move portal version display to System Configuration

**Description**

Remove version from `app/templates/base.html` footer; show version on the System Configuration page subtitle (“Manage global settings…”).

---

## Mid-Term

_Status label: `roadmap:mid-term` (also tag `enhancement`)._

### Registration appeal after rejection

**Description**

If registration is rejected, allow the applicant to appeal or supply context; admins should see prior rejection and reasons.

---

### Registration tracking: reasons and searchable history

**Description**

On rejection, store and show the reason to the user; make registration records searchable for staff with registration permission (approved and rejected).

---

### Registration tracking: clean up stub user on rejection

**Description**

When registration is rejected, remove or safely reconcile stub user rows without corrupting related data (needs design).

---

### Settings-driven feature toggles

**Description**

When optional integrations are unset (e.g. no Discord webhook URL, no SMTP), skip those code paths instead of failing or no-op noise. SMTP behavior may need policy discussion.

---

### Admin documentation (man pages / offline docs)

**Description**

Document admin workflows for operators who do not use GitHub.

---

### Partner system in the portal

**Description**

Expose partner relationships in the portal (today partner tree is API-only for in-world). May require a privileged worker script with narrow sudo, since Robust writes were previously avoided.

---

## Future

_Status label: `roadmap:future` (also tag `enhancement`)._

### OIDC / auth-bridge (non-stub)

**Description**

Replace stub OIDC/auth-bridge with real integration for Matrix, Discord, and other SSO providers.

---

### Web-based setup wizard

**Description**

First-run installer: collect DB credentials, generate secrets, run migrations without shell access.

---

### Authentication bridge and fraud detection (epic)

**Description**

Backend replacement for OpenSim-style auth plus fraud signals: policy acceptance gate on login; MAC/HostID/geo change opens a user-owned helpdesk ticket (Griefing/Abuse); configurable restriction user level during investigation.

---

### OpenSim.ini guided configuration via portal

**Description**

Seed `opensim@.service`-style flow: instances pull config from portal; import upstream `.ini` templates; admin-defined defaults with per-instance overrides; `-include` from HTTP.

---

### Robust.ini guided configuration via portal

**Description**

Similar to OpenSim.ini story for `robust@` instances, including optional separation of asset/inventory/auth services and phased rollout.

---

### Gloebit centralized money support

**Description**

Configure and deploy centralized Gloebit money handling.

---

### PoDex centralized money support

**Description**

Configure and deploy centralized PoDex money handling.

---

### Private money support

**Description**

Configure and deploy centralized private money handling.

---

### Registration avatar selection

**Description**

Allow avatar model selection during registration.

---
