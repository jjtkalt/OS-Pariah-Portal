# OS Pariah Portal Roadmap

Welcome to the OS Pariah Portal roadmap! This document outlines the planned features, architectural improvements, and community suggestions we are working on. 

So many things to do, so many ways to forget! This is a living document. Priorities can shift based on community feedback, upstream OpenSimulator changes, and developer bandwidth.

## Known Bugs (Next patch version release)
*Focus: Things that need to be fixed and should already work!  Seed for the issues list.*


## 🚧 Short-Term (Next Minor version release)
*Focus: In-line enhancements without base functionality changes.*

* **[i] Regions.ini Information:** All regional information should be kept in the portal database.  No region specific ini files should be needed for regions
* **[ ] Invite code:** We have the frame work to handle requiring an invite code, but it hasn't been implemented for users to use (if the setting is on).  We also don't yet have a way to link a user to who their "sponsor" or "Voucher" or "Inviter" was.  We need that to show up when looking at either user.
* **[ ] User notes:** on the lookup page, admins have the ability to add notes on users (via UUID).  We need these notes to link (logically) to all alts of that use, local and hypergridded.  I THINK the best way would be to do a link on MAC and/or HostID, and probably via lookup at time of display so it automatically populates to net hypergrid/local accounts from that same user.  An update to the display and recording process is needed so that any notes added against an avatar name records the name AND UUID it is originally about (maybe a need for a drop-down box?), so that in the case of multiple people connecting from the same home account, there is an indication about which user/actual-person the note is about.  It might be good to record the MAC and HostID that it was originally recorded against in case someone moves or gets a new computer and the digital trail gets murky.
* **[ ] Settings polish:** Let's do a little magic that will show on the display of the app/templates/admin/setting.py page.  If a value for a setting is currently default, let's change the (Default: <defaultvalue>) muted text to say (Already default: <defaultvalue>) and drop the "Already Default" button entirely.  But we'll keep the current behavior that if a setting is already overridden, the (Default: <defaultvalue>) shows up and then the red "Reset" button shows.  Much less distracting on the page.
* **[ ] Settings polish:** We should support "no reset to default" settings.  This would eliminate the "Reset" button on those fields (and the "Default: <value>" display, of course), while allowing the admin to make changes still if they needed to.  But much more importantly, if we DO decide to support an install wizard process in the future, these "empty but mandatory" settings would be the items that trigger that first-install experience.  The pros and cons of that idea can be researched in the future.  For now, the option will clean up those items that really should be set by the admin right and avoid accidental clicks that would revert them.  
* **[ ] Settings polish:** It would be really nice if we could eliminate the "Save All Configurations" button at the bottom of the page as it is both misleading and a point of stumble when updating these values.  Instead, it would be much better that if a setting is changed (either by the reset button or by changing the value and leaving the field), it is instantly pushed to the database.  Confirmation with a little green checkmark or a failure indicator next to the field would be the easiest to understand as a flash message would be missed since the page isn't reloaded.  Means the addition of some simple javascript and handlers.  A default "create or update a key-value pair on action" would make it all very simple and quick.  The handler would do a fast dom update to indicate the success/failure.
* **[ ] Settings polish:** Define the background image (.background {background-image: url({{ background-image }}); }) to be settable and called in base, or anywhere else a style sheet is defined.  Allows for the setting of the background via settings and not editing the CSS file.  Should probably support different images for different pages (eg: splash.html)
* **[ ] Region owners (estate?) need to be able to restart/oar their regions:** Users that own full regions should be able to see their regions.  They should be able to start/stop/restart them and pull OARs.  They should be able to move (location) or rename them.  However, they should not be able to change the size, prim limits, or other settings.
* **[ ] Shutdown warning:** On region stop or restart, a warning should be issued if users are in the region.  (admin notice API method?)
* **[ ] Admins need a way to update user emails:** An admin needs to be able to change a user's email address
* **[ ] Admins need a way to force reset passwords:** Admins should be able to set a temp auth/link so the user can change their own password. It should be sent to the user's email address
* **[ ] Audit trail:** All portal activities that cause an update should be recorded in the database for later review.  A review page should be available for high admins.
* **[ ] Variable unclear:** the variable "DOMAIN" seems to only be used in a very few locations.  It SHOULD be the first and second level domainname of the grid.  Instead, in the few places it is being used, it SEEMS to be the loginURI for the grid.  We need to fix this, and separate the public and private ports of the grid.  I think I would prefer domainName for the domain of the grid, robustHost for the hostname of where robust lives (minus domainname, obviously - and defaulting to "robust"), publicRobustPort (8002) and privateRobustPort (8003) for the ports, and robustProtocol (http).  This likely means we need a few meta-variables, handled by getDynamicConfig like publicRobust (<robustProtocol>://<robustHost>.<domainName>:<publicRobustPort>) and similar for privateRobust.   Basically, this would let us enter domainName once, and it would populate to all of the other locations that the domain would be used instead of having to type it in each time.  Avoids mistyping, and would be easier to automate into the potential setup wizard in the future.
* **[ ] Profile Page - Email:** The user's current email should be displayed so they know if they should update it or not.  (Better UX)

## 🚀 Mid-Term (Next Major version release)
*Focus: Major feature additions of compatibility changes.*

* **[ ] Registration Tracking:** If a registration is rejected, we should likely provide a reason for the user.  We probably also want to clean up the stub user from the database - that is going to take some thought to avoid corruption.
* **[ ] Use in-world region menu to be online show-able:** This would replace the need for the listable_regions setting by looking at the database of each region (a new read-only database handler would be needed to ready opensim_* region databases) and pulling the the boolean value from regionsettings.block_search.  If the value is true (1), the region would not be listable via the online api call for non-admins.  Basically, in the "online_lister" function of app/blueprints/api/routes.py, 'SELECT block_search FROM opensim_<regionname>.regionsettings' will return false for listable regions.
* **[ ] Settings drive functions** Some variables, if not set, should deactivate the functionality in the portal. (Example: If there is no discord webhook URL, the app should skip the attempt to post to discord.  Or, if there is no smtp server defined, do not use email based options. (Of course, smtp might not be something we want to run without, so, this might need reconsideration))
* **[ ] Add Doc/man entries:** Document the usage for admins that don't want to read GitHub
* **[ ] Two factor authentication:** Can we add a 2FA, mandatory for admins, optional for users?
* **[ ] Region Rental System:** Track region rentals for users.  Users should be able to rent a region (choose size and prims and add-ons for a price), and have it automatically be setup.  Payments should be tracked so if a region is not paid for, it is shutdown.  It should communicate with the user for "payment due", past due notices, and shutdown notice.  

## 🔮 Future / Under Consideration
*Focus: Big ideas, complex integrations, and "nice-to-have" features that require significant architectural planning.*

* **[ ] Partner system:** Ability for users to partner with others.  Current "Partner Tree" is API-Only for in-world use, but we will want to implement this via portal.  This has a security implication as direct Robust Database UPDATE permission would be needed, and portal has, to date, been read only.  To work around this, we might need a worker script that can be triggered with very specific sudo permission only.
* **[ ] Web-Based Setup Wizard:** A graphical first-run installer to securely collect database credentials, generate system secrets, and run initial migrations without requiring terminal access.
* **[ ] OpenSim.ini Guided Configuration:** Let's seed a simple opensim@.service that uses the service instance name to query the portal to get the entire configuration to run.  This will involve importing all of the relevant .ini files from the current OpenSim version and presenting them to a high admin with the ability set all of the settings, with explanation of each setting, to make a set of defaults.  Each region instance will override the defaults with instance specific settings (overrides - eg: opensim@Admin1 sets the chat distance to 2M instead of the default for the grid).  The results will be pulled in via http call from an -include line in the very basic common opensim.ini file.
* **[ ] Robust.ini Guided Configuration:** Let's seed a simple robust@.service that uses the service instance name to query the portal to get the entire configuration to run.  This will involve importing all of the relevant .ini files from the current Robust version and presenting them to a high admin with the ability set all of the settings, with explanation of each setting, to make a set of defaults.  Each robust instance will override the defaults with instance specific settings (overrides - eg: robust@Asset1 only starts the asset service and the HD asset services).  The selection of specialized service configuration should be via checkbox that includes all related services to this instance.  All of the asset service info not used on this instance should be pared out.  The results will be pulled in via http call from an -include line in the very basic common robust.ini file.  At time of request, it is understood that Asset and Inventory services can run separate from the main Robust instance.  It is likely that auth services (specifically user authentication) could be handled via separate process as well.  All three of these, in theory could be off loaded to third party processes and that option might need to be supported as well.  If a phased implementation of this is needed to be followed, as a first step, we will support the ability to move asset services to separate robust using configuration understandings already in place and tested.  Note, a chicken and the egg situation should happen here if the web-based setup wizard isn't active, notably, if robust isn't running, a user cannot (currently) login to the portal.
* **[ ] Protected process scripts:** the sync_firewall.py and sync_robust.py scripts are not using get_dynamic_config.  they should not have default settings, I believe. Violation of DRY  (admittedly, this might be moot, if we move the robust and opensim info into portal anyway.  let's call this low priority until we decide on that.)
* **[ ] Use Log File:** Logs for Pariah should go to the /var/log/os_pariah directory and not just the system journal for historical review if wanted.  Right now, it is easier in journal, and shouldn't normally be needed.
* **[ ] Gloebit support:** Configure and deploy centralized Gloebit money handling support
* **[ ] PoDex support:** Configure and deploy centralized PoDex money handling support
* **[ ] Private Money support:** Configure and deploy centralized private money support
* **[ ] Registration Avatar:** Avatar model selection during registration

## ✅ Recently Completed (v0.9.4 - v0.9.x)


## ✅ Completed (v0.9.2 - v0.9.4)
* **[x] Splash/Welcome Screen:** For the welcome screen in the viewers, we should generate a basic page with current announcements, grids stats, etc.
* **[x] Helpdesk ticket sort:** Logged in users and admins should have a filter option to view closed or withdrawn tickets.
* **[x] User IAR Generation:** When a user generates an IAR Backup, the download button generates an error saying the requested backup file could not be found on the server, however, that file is created and available.
* **[x] Texture/Photo viewer:** Admins of a certain userlevel should be able to review a users texture and photo inventory for safety and grid security.
* **[x] Region Configurations:** A region should be disabled to save the configuration.  A disabled region should be able to be reactivated at a later point.  Only a disabled region should be able to be completely deleted from the database.
* **[x] Full UI Sweep focusing on CSS:** review all CSS and inline style to make sure it makes sense and is centralized in the css file for easy theming.  (AI suggested the sweep, especially on .group and .card)
* **[x] System Settings:** Currently there is no ability to delete a setting and/or return it to it's default setting.  Can we add some sort of Clear/Delete/Reset button to remove a setting's entry from the setting database table?
* **[x] Region Controls:** When trying to stop/restart a region from the admin menu, sudo fails.  Probably because of the new much tighter permissions granted to pariah.
* **[x] Missing File during installation:** check_mariadb.py fails to be installed via RPM
* **[x] Database migration missing column:** in region_configs, is_active TINYINT(1) NOT NULL DEFAULT 1;
* **[x] CSS Update:** Main area should be wider and use the user's screen space
* **[x] Variable name is misleading:** allow_ticket_deletion should have a description of "Allow Super Admins to Delete Tickets" and ot reference Users.
* **[x] Permissions wrong on config file:** /etc/os_pariah/os-pariah.conf needs to be owned by group opensim or opensim cannot run worker services
* **[x] Systemd Unit file is wrong location:** RPMs should install systemd unit files to /usr/lib/systemd/system/
* **[x] Missing License File:** Need to add a %license to .spec
* **[x] Policy bouncer is bouncing where there are no policies:** The default for global_policy_version should be 0.0.  And the Policy bouncer page should not check users if the Policy version is 0.0.
* **[x] Variable name is misleading:** region_host_ips should give a hint of what it allows and what format to use for multiple IPs.
* **[x] Gatekeeper Cross-Reference:** in the case of more that one avatar found, the names listed should be shows as buttons that will do "exact username" search to make sure that information is only for that user.
* **[x] Gatekeeper Cross-Reference:** UUIDs found should show the grid-from information to differentiate between local and Hypergrid users.
* **[x] Texture Gallery:** 1-Define system/orphaned (is there a way to get more info, eg: is it hypergrid?) 2- search and "owner" should use avatar names, not uuids.  3- Mesh data and baked texture should be skipped (it can't render anyway being 3d info, as I understand it, why is it still a 0 type item?!)  4- Hash should expand (and be copyable) if pointed at.  5- Explore a bit as to why some things don't render (EG: broken links and "null")
* **[x] Last on/Last Used info in Gatekeeper Lookup:** The date_time for all gatekeeper info is not being used.  We should display it to help admins get a better idea of what evens from users happened when.  Paint a better picture!
* **[x] Security updates:** Dependency updates to address security issues.
* **[x] Sudoers file management:** Create a pariah_workers file for the sudoers.d directory instead of having the file created from echos in the .spec file.
* **[x] Region Import redirect:** When importing a region to Pariah, it should not take us to the edit screen.
* **[x] User Name Change:** Allow  high (or mid?) admins to change user's login/account name
* **[x] Setting are saving default:** When "Save All Configuration" is clicked in settings, even the default settings are saved.  Need logic to remove the option from the database if it is default, and only save the non-default options.  Also should indicate what the default setting is if it was overridden, otherwise the "Reset" button is ambiguous.
* **[x] CSS overwritten during upgrade:** the CSS file location should be settable in case users want to theme.  Otherwise, all updates are overwritten during the rpm upgrade.
* **[x] Change Email gives internal error:** Database error on attempt to chagne email.
* **[x] HyperGrid Users can't have a userlevel:** Gatekeeper lookup, user entries that are for hypergridders should NOT show the option to change their userlevel, as there is no such thing as a hypergrid admin in OpenSimulator.
* **[x] User Change Password:** When a user changes their password, it says that it worked, but no password is changed in robust.  I THINK the problem is base_url = current_app.config.get('ROBUST_PRIVATE_URL'), which isn't using the get_dymanic_config properly.  However, even if that is the case, a failed update should still show a failure, not that it worked.  Also, it is using the wrong method and namespace.
* **[x] IAR creation fail:** python[31357]: IAR generation failed: expected str, bytes or os.PathLike object, not NoneType

## ✅ Completed (v0.9.0 - v0.9.2)
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
* **[x] Default values evaluation:** We should update 'default values' in the code and pull them out of the seeded values set during the first migration.
* **[x] Verify Bans/warnings:** Do bans actually ban they way they should (update firewalld, set banned MAC in robust, set userlevel to banned).  Need testing and review.
* **[x] User control:** User levels set or changed within the UI.  EG: Promoting a new Admin.
