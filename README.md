# OS-Pariah
An OpenSimulator administration and user portal.

[![Automated Tests](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml) [![openSUSE RPM Build](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/release-rpm.yml/badge.svg)](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/release-rpm.yml)

## Overview
The OS Pariah Portal is the living core of the OS-Pariah environment.  Building on the strong groundwork of the OS-Pariah Installation and System platform, the Portal gives a fundamentally user-focused platform giving users and administrators a functional and supportive platform for all parts of an active and thriving OpenSimulator Grid.

The following basic assumptions are in place:
- The OpenSimulator setup is Grid (not standalone)
- Users should be respected and not treated like a lesser group because they are not part of the grid staff
- Security, privacy, respect, and functionality should be core values of any Grid and or community.
- Python 3.13 is available at `/usr/bin/python3.13` (Leap 16: `python313` from OSS; Leap 15.6: see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))
- The web server is Nginx.  Apache or other webserver packages could well work, but you are on your own with them

OS Pariah is an enterprise-grade portal built for scale and stability. Because it heavily integrates with native OS-level process management (like systemd, firewalld, and screen), the portal backend requires a Linux environment (Currently only openSUSE is officially supported for reliability reasons — Leap **16** preferred; Leap **15.6** is supported only with a local Python 3.13. Technically, there is no known reason why a Ubuntu, CentOS, or other Linux variant wouldn't work assuming a manual install, but your mileage may vary.). Windows Server is not supported for the portal installation.

## Functionality

Pariah was built to be enterprise-grade, capable of handling high-traffic OpenSimulator grids without buckling or exposing the host OS to vulnerabilities.

* **Advanced user management:** From registration, to promotion, to warnings and bans, Pariah is ready for it all
* **User can self-update:** Users can change their own passwords or email addresses.  They can even backup their own inventory.
* **Gatekeeper Cross-Referencing:** Collecting all user connection information allows for quick insight into user issues and grid safety concerns.
* **Policy, Rules, and Documentation:** Pariah tracks user's acceptance of system policies, keeping everyone up to date while allowing administrators to easily edit and publish documentation.
* **Dynamic Helpdesk System:** Guests and members alike have a central location to get the help they need.  Administrators can get updates on Discord or Matrix.  Abuse is limited by Cloudflare&copy;'s Turnstyle&trade; CAPTCHA system.
* **System and Region Configuration:** All of the various parts of running a grid are accessible to users and administrators in Pariah's centralized system.
* **Viewer Welcome/Splash page:** A dynamic page for users of the grid when they are logging in. (Set the Welcome page in Robust.ini to point to https://portal.example.com/comms/splash)
* **Role Based Access Control:** Functions of the Pariah Portal are assignable reguardless of a users in-world permissions.  Grid-wide God powers are not required to access functionality in the portal

## Philosophical Reasoning
For all the various reasons that one thing or another was chosen, or to learn more about the industry best practices that were intended to be followed, refer to [Philosophy](PHILOSOPHY.md).

## Installation

Before installing or upgrading, check the [Compatibility Matrix](COMPATIBILITY.md) to ensure your grid's OpenSimulator version is supported.

> **Do not install v1.0.1.** That release is withdrawn (#61): `/etc/os_pariah` ownership broke `opensim` workers. Prefer **v1.0.0** until **v1.1.0** is published, or go straight to **v1.1.0**.

**Full install and first-boot guide:** [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)  
**Day-to-day operations (workers, upgrades, troubleshooting):** [docs/OPERATIONS.md](docs/OPERATIONS.md)  
**End-user help (once the portal is running):** `/manual.html`

### Quick start (RPM)

1. Import the Pariah ecosystem PGP key (below) if you want to verify signed releases.
2. Ensure Python 3.13 is on the host (`/usr/bin/python3.13`). On Leap 16: `sudo zypper install python313 python313-devel`. On Leap 15.6, follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#python-313-on-leap-156).
3. Install the RPM:
   ```bash
   sudo zypper install ./os-pariah-portal-*.rpm
   ```
4. Edit `/etc/os_pariah/os-pariah.conf` with your MariaDB credentials (portal + Robust read-only). Leave `SECRET_KEY` unset — it is auto-generated into `/etc/os_pariah/secrets` on first start.
5. Start the portal:
   ```bash
   sudo systemctl enable --now pariah
   sudo nginx -t && sudo systemctl reload nginx
   ```

Manual (unsupported) installs are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

### PGP signing key

To verify the RPM, add this public key to your rpm keyring (`rpm --import <file>`). This is the signing key for the Pariah ecosystem:

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
mDMEaczq4RYJKwYBBAHaRw8BAQdAk33PRQWPrSBVPWowoeYunQPP82t8qkBbl+a9
GWBJF9+0HkpqIEthbHQgPGpqYW5kdGthbHRAZ21haWwuY29tPoiTBBMWCgA7FiEE
7WH3aBWPsIvqEdDqgoSdDkW0ATQFAmnM6uECGwMFCwkIBwICIgIGFQoJCAsCBBYC
AwECHgcCF4AACgkQgoSdDkW0ATSAQwEAkr+VpdxRsRq3w5wWWZEj++pjfrAOFknj
R6ujsCE9lqYBANr43plIvWNh5XOKpThFpJY3VtLd5lR4aD6BpWJeP6cEuDgEaczq
4RIKKwYBBAGXVQEFAQEHQLvb4DWe6M73W2PN8flODiV8Mq71DKdN7RlLZLmEmKxo
AwEIB4h4BBgWCgAgFiEE7WH3aBWPsIvqEdDqgoSdDkW0ATQFAmnM6uECGwwACgkQ
goSdDkW0ATRrsQD/TE5LQlgpUiWRh8i/P7irqMD7JMziH9MakUYteFvmW0UBAP+f
iyWwmFIxjnomhjqAiESjJXAFw/6jC1zb8jIxfTcD
=UiGf
-----END PGP PUBLIC KEY BLOCK-----
```

## Contributing

Linting and formatting use **Ruff** (see `pyproject.toml`). The local gate mirrors CI (`ruff` + `pytest`) and adds `pip-audit` for known dependency advisories:

```bash
source venv/bin/activate          # Windows: venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
python3 scripts/check_local.py
```

Recommended: `pre-commit install` so every commit runs Ruff auto-fix/format, then `scripts/check_local.py` (lint/format check, pytest, pip-audit). Needs network access for `pip-audit`. Skip once with `git commit --no-verify` only when you intentionally need to bypass the gate.
