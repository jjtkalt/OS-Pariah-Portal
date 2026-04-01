#OS-Pariah Philosophy
So many of the ideas, best practices, and choices of OS Pariah were made by the Original Author because of various experiences had over the the span of their career.  Having started in UNIX administration in the late 1980s and am early adopter of Linux and a strong believer that it was the only sustainable high-end server Operating System for ongoing use, they have had a long time to build completely unreasonable expectations of stability, reliability, and functionality.

Sadly, not all of those can be applied to OpenSimulator because of the very nature of the development and evolution.  And yet, that fails to distract them.

## OpenSUSE and SUSE Linux Enterprise Server
### File System Layout

## OS Pariah Installation
### OpenSimulator
#### NGC Tanquility
#### IAR Password Patch
#### Shared Binaries
#### Modular ini files
#### Split Asset Services
### Nginx Web and Reverse Proxy
### PHPMyAdmin
### The OpenSim User
### The Splash Page
### Non-containerized/Non-virtualized

## Portal (This project)

### Basic Tenants

* **Rule #1 (No Guessing / Single Source of Truth):** If data exists in two places, it is broken. Configuration values, user levels, and ban data must flow from a single, verifiable source to prevent split-brain architecture.
* **The Principle of Least Privilege:** A web portal should never have `root` access to the host machine. OS-level changes must be handled by dedicated, localized scripts triggered securely.
* **Automate the Administration:** Grid owners should spend their time building communities, not manually editing `.ini` files or grepping log files. The portal must act as a force multiplier that distills complex server management into a few clicks.
* **Test to Trust:** Code that is not mathematically proven to work by an automated test suite is code that will eventually break in production. Every critical path must be verifiable.
* **Dual MariaDB Connection Pooling:** Implemented `PooledDB` for both the Pariah CMS database and the OpenSim Robust database. This ensures thread-safe, high-concurrency database access while preventing memory leaks and connection drops (`InvalidConnection`).
* **Single Source of Truth (SSOT) Configuration:** Eradicated "split-brain" configurations by moving all portal settings into a dynamic, database-driven `KNOWN_SETTINGS` schema. Settings are automatically injected globally into all Jinja templates and cached for performance.
* **Gunicorn "Worker Storm" Prevention:** Solved the pre-fork concurrency issue using Linux native `fcntl` file locking. This ensures that when multiple web workers boot simultaneously, only one worker is allowed to trigger system-level background processes, keeping systemd logs clean and CPU usage low.
* **Automated RPM Deployment:** Engineered a comprehensive `.spec` file that automatically handles user creation (`pariah` user), directory permissions, Nginx routing, systemd service installation, and surgical `sudoers` rule injection for secure background script execution.
* **Rate Limiting & Proxy Security:** Configured Nginx `limit_req_zone` to prevent brute-force and DDoS attacks, while properly forwarding `X-Real-IP` headers so the portal can accurately track and ban malicious actors.

### Python
### OS Authentication Bridge
### Ticket System
### Registration Page
### Rental System
### Patreon/PayPal/Venmo
### Gatekeeper Logs & Ban Records

We designed one of the most advanced, multi-layered ban systems currently available in the OpenSimulator ecosystem.

**Defense in Depth:** Banning an account in the database is not enough. A true grid defense requires synchronized enforcement at the Database, Application, and the Network levels.

* **Gatekeeper Cross-Referencing:** Leveraged nightly worker scripts to scrape and parse OpenSim Gatekeeper logs, allowing Admins to instantly cross-reference Alt accounts using usernames, IPs, and hardware information.
* **Cascading Severity Tiers:** Replaced the standard binary ban system with a highly granular, configurable tier system:
    * Account Ban
    * IP Ban
    * Hardware Ban
    * Host Ban
* **OS-Level Network Enforcement (Firewalld):** Created a bridge between the web database and the host OS. 
    * Uses highly efficient hash tables to instantly drop traffic.
    * Uses advanced string-matching algorithms to drop packets on the OpenSim login port.
* **Surgical Robust Configuration Injection:** Safely injects bans into Robust's configuration.
* **Secure Boundary Crossing:** The web application never requires `root` access. Instead, it asynchronously triggers highly restricted, dedicated scripts firewall and Robust configurations.

### Name Changes
### Partner System
