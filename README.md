# OS-Pariah
An OpenSimulator administration and user portal.

[![Automated Tests](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml/badge.svg)](https://github.com/jjtkalt/OS-Pariah-Portal/actions/workflows/ci-tests.yml)

## Overview
The OS Pariah Portal is the living core of the OS-Pariah environment.  Building on the strong groundwork of the OS-Pariah Installation and System platform, the Portal gives a fundamentally user-focused platform giving users and administrators a functional and supportive platform for all parts of an active and thriving OpenSimulator Grid.

The following basic assumptions are in place:
- The OpenSimulator setup is Grid (not standalone)
- Users should be respected and not treated like a lesser group because they are not part of the grid staff
- Security, privacy, respect, and functionality should be core values of any Grid and or community.
- Python 3.12 is available (the code MIGHT be compatible with later versions, but it is untested)
- The web browser is Nginx.  Apache or other webserver packages could well work, but you are on your own with them

While this application is almost entirely platform agnostic, as of right now, it is only supported in a unix environment and still has a few dependencies on the OS-Pariah Installation project.  A midterm goal is to roll those dependencies into the code to allow it to be truly standalone.  This MOSTLY affects the region controls at this time.  YMMV

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

### Manual Installation

- Create a pariah user to run the portal.  Assign the home directory to be your installation base.
- Install and activate the Systemd services and the Nginx vhost configuration
- Edit .env_example with your DB credentials and save it as .env
- Create the virtual environment: python3.12 -m venv venv
- Activate the Virtual environment in your shell: 'source venv/bin/activate'
- Install requirements into the virtual environment: 'venv/bin/pip -r requirements.txt'
- Run database migrations: 'venv/bin/python migrate.py'
- Start the portal: 'sudo systemctl enable --now pariah'
