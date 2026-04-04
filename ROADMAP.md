# OS Pariah Portal Roadmap

Welcome to the OS Pariah Portal roadmap! This document outlines the planned features, architectural improvements, and community suggestions we are working on. 

So many things to do, so many ways to forget! This is a living document. Priorities can shift based on community feedback, upstream OpenSimulator changes, and developer bandwidth.

## Known Bugs (v0.9.0 (to get our of Release candidate))
*Focus: Things that need to be fixed and should already work!  Seed for the issues list.*

## 🚧 Short-Term (v0.9.1 - v0.9.x)
*Focus: Polish, bug fixes, and expanding core administrator tools.*

* **[ ] Verify Bans/warnings:** Do bans actually ban they way they should (update firewalld, set banned MAC in robust, set userlevel to banned).  Need testing and review.
* **[ ] Helpdesk ticket sort:** Logged in users and admins should have a filter option to view closed or withdrawn tickets.
* **[ ] Region.ini Information:** All regional information should be kept in the portal database.  No region specific ini files should be needed for regions
* **[ ] Robust.ini Information:** Should we configure the Robust instance(s) via the portal? Pro: centralized. Con: no real way to parse the needed parts.
* **[ ] Region Configurations:** A region should be disabled to save the configuration.  A disabled region should be able to be reactivated at a later point.  Only a disabled region should be able to be completely deleted from the database.
* **[ ] Splash/Welcome Screen:** For the welcome screen in the viewers, we should generate a basic page with current announcements, grids stats, etc.
* **[ ] Full UI, including CSS, Sweep:** review all CSS and inline style to make sure it makes sense and is centralized in the css file for easy theming.  (AI suggested the sweep, especially on .group and .card)
* **[ ] Texture/Photo viewer:** Admins of a certain userlevel should be able to review a users texture and photo inventory for safety and grid security.

## 🚀 Mid-Term (v1.0.0 Release Candidate)
*Focus: Enterprise readiness, onboarding, and major feature additions.*

* **[ ] Default values evaluation:** We should update 'default values' in the code and pull them out of the seeded values set during the first migration.
* **[ ] User control:** User levels set or changed within the UI.  EG: Promoting a new Admin.
* **[ ] Settings drive functions** Some variables, if not set, should deactivate the functionality in the portal. (Example: If there is no discord webhook URL, the app should skip the attempt to post to discord.  Or, if there is no smtp server defined, do not use email based options. (Of course, smtp might not be something we want to run without, so, this might need reconsideration))

## 🔮 Future / Under Consideration
*Focus: Big ideas, complex integrations, and "nice-to-have" features that require significant architectural planning.*

* **[ ] Web-Based Setup Wizard:** A graphical first-run installer to securely collect database credentials, generate system secrets, and run initial migrations without requiring terminal access.

## ✅ Recently Completed (v0.9.x)
* **[x] RPM Packaging:** Fully automated build pipeline for openSUSE/RHEL.
* **[x] Socket Architecture:** Transitioned Gunicorn to high-performance Unix domain sockets.
* **[x] Automated CI/CD:** Implemented GitHub Actions for testing and release builds.
* **[x] Database Migration Engine:** Version-controlled schema updates via `migrate.py`.
* **[x] Registration Form:** The form down not have the latest update that tells users why the submit button isn't available (regression)
* **[x] Helpdesk submit ticket:** Only using half the screen instead of stretching out like the other pages (CSS issue).  View ticket height is also limited.
* **[x] Grid name tag:** Upper left corner tag/logo should take users to home page, not refresh the one we are on.
* **[x] Home menu:** The Home menu item should take us to the base URL of the portal
* **[x] Webhook UI Configuration:** Update the settings page in the Admin Dashboard. It should include a selectable list of every variable in the portal that isn't already defined so we aren't guessing variable names.  Items that are related, should be set together as a block.
* **[x] Testing suite expansion** Tests should be created to test all parts of the functionality of the portal.  Does it allow users to login correctly and assign them the correct right, does it send the right calls to Robust to create/change/lock users, can a guest open a helpdesk ticket, do the notifications to discord/matrix/email go correctly, can a user register, can a registration be verified, can a verified registration be approved and rejected, can an IAR be created on demand, can a region be started or stopped, can settings be updated, can announcements be created, can policies be created and updates, does the bouncer get triggered correctly, etc?  A smoke test should give a strong sense of continuing functionality.  Do we need to update the test to do a basic install of OpenSim with robust and a single region so we can test all this, or can we "fake" the responses without invalidating the tests?
