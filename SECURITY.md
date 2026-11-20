# Security Policy

## Supported Versions

Only the **latest release on `main`** receives security fixes. Please upgrade to the newest
release before reporting, and see the [Compatibility Matrix](COMPATIBILITY.md) for supported
OpenSimulator versions.

## Reporting a Vulnerability

**Do not open a public Issue for a suspected vulnerability.**

Use GitHub's **Private Vulnerability Reporting**:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** (this creates a private Security Advisory draft).
3. Describe what you found, how to reproduce it, and the impact.

You can also reach the maintainer by direct message if you cannot use GitHub's reporting
form. Please give a reasonable window to ship a fix before any public disclosure.

(Maintainers: keep **Settings → Code security → Private vulnerability reporting** enabled.)

## Deployment hardening notes

- The installed code tree (`/opt/os-pariah`) is `root:root`; only upload/runtime directories (ticket uploads live in `/var/lib/os-pariah/uploads/tickets`, `0750`, not nginx-served)
  are owned by the `os-pariah` service user.
- `sudoers` grants for the `os-pariah` user are limited to the firewall/Robust sync scripts (`/etc/sudoers.d/os-pariah-worker`),
  `systemctl start os-pariah-worker-iar.service`, and OpenSim/Robust unit control.
- OIDC sign-in is disabled until clients are registered; see [docs/OPERATIONS.md](docs/OPERATIONS.md).

Thank you for showing responsibility to the greater community!
