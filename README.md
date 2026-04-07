# OS-Pariah
An OpenSimulator administration and user portal.

[![Automated Tests](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml) [![Latest RPM Build](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/release-rpm.yml/badge.svg)](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/release-rpm.yml)

## Overview
The OS Pariah Portal is the living core of the OS-Pariah environment.  Building on the strong groundwork of the OS-Pariah Installation and System platform, the Portal gives a fundamentally user-focused platform giving users and administrators a functional and supportive platform for all parts of an active and thriving OpenSimulator Grid.

The following basic assumptions are in place:
- The OpenSimulator setup is Grid (not standalone)
- Users should be respected and not treated like a lesser group because they are not part of the grid staff
- Security, privacy, respect, and functionality should be core values of any Grid and or community.
- Python 3.12 is available (the code MIGHT be compatible with later versions, but it is untested)
- The web browser is Nginx.  Apache or other webserver packages could well work, but you are on your own with them

While this application is almost entirely platform agnostic, as of right now, it is only supported in a unix environment and still has a few dependencies on the OS-Pariah Installation project.  A midterm goal is to roll those dependencies into the code to allow it to be truly standalone.  This MOSTLY affects the region controls at this time.  YMMV

## Functionality

Pariah was built to be enterprise-grade, capable of handling high-traffic OpenSimulator grids without buckling or exposing the host OS to vulnerabilities.

* **Advanced user management:** From registration, to promotion, to warnings and bans, Pariah is ready for it all
* **Gatekeeper Cross-Referencing:** Collecting all user connection information allows for quick insight into user issues and grid safety concerns.
* **Policy, Rules, and Documentation:** Pariah tracks user's acceptance of system policies, keeping everyone up to date while allowing administrators to easily edit and publish documentation.
* **Dynamic Helpdesk System:** Guests and members alike have a central location to get the help they need.  Administrators can get updates on Discord or Matrix.  Abuse is limited by Cloudflare&copy;'s Turnstyle&trade; CAPTCHA system.
* **System and Region Configuration:** All of the various parts of running a grid are accessible to users and administrators in Pariah's centralized system.
* **Viewer Welcome/Splash page:** a dynamic page for users of the grid when they are logging in.

## Philosophical Reasoning
For all the various reasons that one thing or another was chosen, or to learn more about the industry best practices that were intended to be followed, refer to [Philosophy](PHILOSOPHY.md).

## Installation

Before installing or upgrading, please check the [Compatibility Matrix](COMPATIBILITY.md) file to ensure your grid's version of OpenSimulator is supported.

### Package Installation

Install the RPM.  Note: This is only tested on openSUSE 15.6 right now per the OS-Pariah Installation project

To verify the RPM, add this public key to your rpm key ring (save to a file, then rpm --import <file>).  Please note - the is the signing key for the Pariah ecosystem:

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

### Manual Installation (Not recommended or supported.  But it should work!)

In our testing, the following commands were run as the opensim user from Pariah Installation.  This allowed us to use Git to update to the latest develop release for testing.  YMMV

- Create a pariah user to run the portal.  Assign the home directory to be your installation base.
- Create the SUDO rules required for Pariah.  Something like:
  - ```echo "pariah ALL=(ALL) NOPASSWD: /bin/systemctl start pariah-worker-iar.service, /bin/systemctl stop pariah-worker-iar.service, /bin/systemctl restart pariah-worker-iar.service, /opt/os_pariah/venv/bin/python /opt/os_pariah/scripts/sync_firewall.py, /opt/os_pariah/venv/bin/python /opt/os_pariah/scripts/sync_robust.py" | sudo tee /etc/sudoers.d/pariah_worker```
  - ```sudo chmod 0440 /etc/sudoers.d/pariah_worker```
- Create the Pariah Gallery Cache directory for image review: ```sudo mkdir -p /home/opensim/FSAssets/pariahcache```
  - IMPORTANT: If your FSAssets path is different than the default, or you aren't using the default fsassets table in the robust database, you must update this to where it will be located and update the default value in the Admin - Settings menu of the Portal UI.
- Clone the GitHub repository into /opt/os_pariah
- Edit ```.env_example``` with your DB credentials and save it as either ```.env``` or the standard /etc/os_pariah/os-pariah.conf
- Create the virtual environment inside /opt/os_pariah: ```cd /opt/os_pariah; python3.12 -m venv venv```
- Activate the Virtual environment in your shell: ```source /opt/os_pariah/venv/bin/activate```
- Install requirements into the virtual environment: ```/opt/os_pariah/venv/bin/pip -r requirements.txt```
- Run database migrations: ```/opt/os_pariah/venv/bin/python migrate.py```
- Install and activate the Systemd services and the Nginx vhost configuration from the /opt/os_pariah/packaging directory
  - ```sudo cp /opt/os_pariah/packaging/OS-Pariah.conf /etc/nginx/vhosts.d/```
  - ```sudo cp /opt/os_pariah/packaging/*.service /opt/os_pariah/packaging/*.timer /etc/systemd/system/```
  - ```sudo systemctl daemon-reload```
- Test and restart the Nginx Web Service
  - ```sudo nginx -t```
  - ```sudo systemctl restart nginx.service```
- Enable and start the portal: ```sudo systemctl enable --now pariah```
