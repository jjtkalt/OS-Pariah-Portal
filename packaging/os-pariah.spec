#
# spec file for package os-pariah
#

Name:           os-pariah
Version:        1.2.4
Release:        %{?build_number}%{!?build_number:1}%{?dist}
Summary:        OS-Pariah - OpenSim CMS and Grid Management

License:        GNU-GPLv3
URL:            https://github.com/jjtkalt/OS-Pariah-Portal
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64
# Pure Python / config packaging — no ELF to strip. Skip empty debuginfo/debugsource.
%global debug_package %{nil}

# File require so Leap 16's python313 *or* a local/altinstall of 3.13 on Leap 15.6
# (symlink /usr/bin/python3.13) can satisfy the dependency. See docs/DEPLOYMENT.md.
Requires:       /usr/bin/python3.13
Requires:       nginx
Requires:       mariadb
Requires:       sudo
Requires:       screen
Requires(pre):  shadow
Recommends:     python313
Recommends:     python313-devel
Provides:       user(os-pariah)
Provides:       group(os-pariah)
Provides:       group(opensim)

%description
A high-performance, Flask-based CMS, Support Portal, and Grid Management interface for OpenSimulator.

Runtime requires Python 3.13. On openSUSE Leap 16, install python313 from OSS.
On Leap 15.6 (no stock 3.13), provide /usr/bin/python3.13 before installing —
see docs/DEPLOYMENT.md § "Python 3.13 on Leap 15.6".

%prep
%setup -q

%pre
# This runs BEFORE the files are copied.

#We create the secure 'os-pariah' user.
%{_sbindir}/groupadd -r os-pariah 2> /dev/null || :
%{_sbindir}/useradd -r -g os-pariah -d /opt/os-pariah -s /sbin/false \
    -c "OS-Pariah Daemon User" os-pariah || :

# Workers (User=opensim) and runtime dirs use the opensim group; create it if the
#   OpenSim host account has not been provisioned yet so chown below cannot fail.
%{_sbindir}/groupadd -r opensim 2> /dev/null || :

if [ ! -x /usr/bin/python3.13 ]; then
    echo "=========================================================" >&2
    echo "ERROR: /usr/bin/python3.13 is required for os-pariah." >&2
    echo "" >&2
    echo "  Leap 16:  sudo zypper install python313 python313-devel" >&2
    echo "  Leap 15.6: no stock Python 3.13 — upgrade to Leap 16, or" >&2
    echo "             install 3.13 locally (docs/DEPLOYMENT.md)." >&2
    echo "=========================================================" >&2
    exit 1
fi

%install
# This tells the RPM builder where to put everything on the target server.
mkdir -p %{buildroot}/opt/os-pariah
mkdir -p %{buildroot}/etc/os-pariah
mkdir -p %{buildroot}/etc/sudoers.d
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/etc/nginx/vhosts.d
mkdir -p %{buildroot}/etc/nginx/conf.d
mkdir -p %{buildroot}/var/log/os-pariah
mkdir -p %{buildroot}/var/lib/os-pariah/uploads/tickets
mkdir -p %{buildroot}/home/opensim/FSAssets/os-pariah-cache
mkdir -p %{buildroot}/home/opensim/Backups/downloads
mkdir -p %{buildroot}/home/opensim/Backups/portal

# Copy application files
cp -r app scripts migrations wsgi.py requirements.txt %{buildroot}/opt/os-pariah/
mkdir -p %{buildroot}/opt/os-pariah/packaging/inworld
cp -r packaging/inworld/* %{buildroot}/opt/os-pariah/packaging/inworld/

# Install the default blank config template
cp .env.example %{buildroot}/etc/os-pariah/os-pariah.conf

# Setup OS-Pariah worker's limited sudo privileges.
cp packaging/os-pariah-worker.sudo %{buildroot}/etc/sudoers.d/os-pariah-worker
chmod 0440 %{buildroot}/etc/sudoers.d/os-pariah-worker

# Install the systemd services
cp packaging/os-pariah.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-iar.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-iar.timer %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-log.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-log.timer %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-calendar.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-worker-calendar.timer %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-cloudflare-ip.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-cloudflare-ip.timer %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-backup.service %{buildroot}/usr/lib/systemd/system/
cp packaging/os-pariah-backup.timer %{buildroot}/usr/lib/systemd/system/

# Add the Nginx files (Please install certbot, don't use dummy certs!)
cp packaging/os-pariah.conf %{buildroot}/etc/nginx/vhosts.d/
cp packaging/os-pariah-cloudflare-ip.conf %{buildroot}/etc/nginx/conf.d/
cp packaging/dummy-os-pariah.crt packaging/dummy-os-pariah.key %{buildroot}/etc/nginx/

%post
# This runs AFTER the files are copied to the server.
echo "Building Python 3.13 Virtual Environment..."
# --clear recreates the venv so upgrades from python312 (or an older 3.13 tree) land clean.
/usr/bin/python3.13 -m venv --clear /opt/os-pariah/venv

echo "Installing Python Dependencies..."
/opt/os-pariah/venv/bin/pip install --upgrade pip
/opt/os-pariah/venv/bin/pip install --require-hashes -r /opt/os-pariah/requirements.txt

# Lock down permissions.
# The application tree (code, scripts, venv) is root-owned and not writable by the
# service account, so a compromised portal process cannot rewrite code that is
# later run via sudo (sync_firewall.py / sync_robust.py) or by User=opensim workers.
# sync_requirements.py runs as root via ExecStartPre=+ in os-pariah.service.
chown -R root:root /opt/os-pariah
chmod -R go-w /opt/os-pariah
# Private ticket attachments live outside the code tree and outside nginx /static/
# (Flask serves them only after an ownership/staff check).
mkdir -p /var/lib/os-pariah/uploads/tickets
chown -R os-pariah:os-pariah /var/lib/os-pariah
chmod 0750 /var/lib/os-pariah
chmod 0750 /var/lib/os-pariah/uploads /var/lib/os-pariah/uploads/tickets
# Shared with User=opensim workers (texture JPG cache cleanup, worker logs)
chown -R os-pariah:opensim /var/log/os-pariah /home/opensim/FSAssets/os-pariah-cache
chmod 0770 /var/log/os-pariah
chmod 0775 /home/opensim/FSAssets/os-pariah-cache
# Portal self-backup tree (DB dumps + conf + ticket uploads); not root-only.
mkdir -p /home/opensim/Backups/portal
chown os-pariah:opensim /home/opensim/Backups/portal
chmod 0750 /home/opensim/Backups/portal

# Sudoers drop-ins must be 0440 root:root or sudo ignores/rejects them.
chown root:root /etc/sudoers.d/os-pariah-worker
chmod 0440 /etc/sudoers.d/os-pariah-worker

# Ensure the os-pariah user can create /etc/os-pariah/secrets on first start (ADR-013).
# Directory group must be opensim so worker units (User=opensim) can traverse and
# read os-pariah.conf (0640 os-pariah:opensim). Secrets remain 0600 os-pariah-only.
chown os-pariah:opensim /etc/os-pariah
chmod 0750 /etc/os-pariah

# Reload systemd so it sees the new service files
systemctl daemon-reload

# Drop pre-rename Cloudflare conf so conf.d/*.conf does not load duplicates.
if [ -f /etc/nginx/conf.d/cloudflare-real-ip.conf ]; then
    rm -f /etc/nginx/conf.d/cloudflare-real-ip.conf
fi

nginx -t && systemctl reload nginx.service || echo "Need to manually fix and start Nginx"

echo "========================================================="
echo "OS-Pariah Installed Successfully!"
echo "1. Edit /etc/os-pariah/os-pariah.conf with your DB credentials."
echo "   (MariaDB database name stays os_pariah; set OS_PARIAH_DB_* variables.)"
echo "2. Start the portal: sudo systemctl enable --now os-pariah"
echo ""
echo "IMPORTANT: If your FSAssets path differs from the default, update the cache path in the Portal UI (System & Backend)."
echo "========================================================="

%files
# We claim ownership of these directories and files
%defattr(-, root, root, -)
/opt/os-pariah/
%dir %attr(0750, os-pariah, os-pariah) /var/lib/os-pariah/
%dir %attr(0750, os-pariah, os-pariah) /var/lib/os-pariah/uploads/
%dir %attr(0750, os-pariah, os-pariah) /var/lib/os-pariah/uploads/tickets/
%dir %attr(0775, os-pariah, opensim) /home/opensim/FSAssets/os-pariah-cache/
%attr(0775, os-pariah, opensim) /home/opensim/Backups/downloads/
%dir %attr(0750, os-pariah, opensim) /home/opensim/Backups/portal/
%dir %attr(0770, os-pariah, opensim) /var/log/os-pariah/
/usr/lib/systemd/system/os-pariah.service
/usr/lib/systemd/system/os-pariah-worker-iar.service
/usr/lib/systemd/system/os-pariah-worker-iar.timer
/usr/lib/systemd/system/os-pariah-worker-log.service
/usr/lib/systemd/system/os-pariah-worker-log.timer
/usr/lib/systemd/system/os-pariah-worker-calendar.service
/usr/lib/systemd/system/os-pariah-worker-calendar.timer
/usr/lib/systemd/system/os-pariah-cloudflare-ip.service
/usr/lib/systemd/system/os-pariah-cloudflare-ip.timer
/usr/lib/systemd/system/os-pariah-backup.service
/usr/lib/systemd/system/os-pariah-backup.timer
%doc packaging/inworld/README.md
%config(noreplace) /etc/nginx/vhosts.d/os-pariah.conf
%config(noreplace) /etc/nginx/conf.d/os-pariah-cloudflare-ip.conf
/etc/nginx/dummy-os-pariah.crt
/etc/nginx/dummy-os-pariah.key
%attr(0440, root, root) /etc/sudoers.d/os-pariah-worker
%dir %attr(0750, os-pariah, opensim) /etc/os-pariah/
%config(noreplace) %attr(0640, os-pariah, opensim) /etc/os-pariah/os-pariah.conf
%doc README.md
%doc CHANGELOG.md
%doc COMPATIBILITY.md
%doc docs/DEPLOYMENT.md
%doc docs/OPERATIONS.md
%doc docs/NAMING.md
%doc docs/ROADMAP.md
%license LICENSE
