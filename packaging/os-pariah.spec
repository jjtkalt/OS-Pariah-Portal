#
# spec file for package os-pariah
#

Name:           os-pariah-portal
Version:        0.9.2
Release:        %{?build_number}%{!?build_number:1}%{?dist}
Summary:        OS Pariah Portal - OpenSim CMS and Grid Management

License:        MIT
URL:            https://github.com/jjtkalt/OS-Pariah-Portal
Source0:        %{name}-%{version}.tar.gz
BuildArch:      x86_64

Requires:       python312
Requires:       python312-devel
Requires:       nginx
Requires:       mariadb

%description
A high-performance, Flask-based CMS, Support Portal, and Grid Management interface for OpenSimulator.

%prep
%setup -q

%pre
# This runs BEFORE the files are copied. We create the secure 'pariah' user.
getent group pariah >/dev/null || groupadd -r pariah
getent passwd pariah >/dev/null || \
    useradd -r -g pariah -d /opt/os_pariah -s /sbin/nologin \
    -c "OS Pariah Portal Daemon User" pariah

%install
# This tells the RPM builder where to put everything on the target server.
mkdir -p %{buildroot}/opt/os_pariah
mkdir -p %{buildroot}/etc/os_pariah
mkdir -p %{buildroot}/etc/sudoers.d
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/etc/nginx/vhosts.d
mkdir -p %{buildroot}/var/log/os_pariah
mkdir -p %{buildroot}/home/opensim/FSAssets/pariahcache

# Copy application files
cp -r app scripts migrations wsgi.py requirements.txt %{buildroot}/opt/os_pariah/

# Install the default blank config template
cp .env.example %{buildroot}/etc/os_pariah/os-pariah.conf

# Setup Pariah's worker's limited sudo privileges.
cp packaging/pariah_worker.sudo %{buildroot}/etc/sudoers.d/pariah_worker

# Install the systemd services
cp packaging/pariah.service %{buildroot}/usr/lib/systemd/system/
cp packaging/pariah-worker-iar.service %{buildroot}/usr/lib/systemd/system/
cp packaging/pariah-worker-log.service %{buildroot}/usr/lib/systemd/system/
cp packaging/pariah-worker-log.timer %{buildroot}/usr/lib/systemd/system/

# Add the Nginx files (Please install certbot, don't use dummy certs!)
cp packaging/OS-Pariah.conf %{buildroot}/etc/nginx/vhosts.d/
cp packaging/dummypariah.crt packaging/dummypariah.key %{buildroot}/etc/nginx/

%post
# This runs AFTER the files are copied to the server.
echo "Building Python 3.12 Virtual Environment..."
/usr/bin/python3.12 -m venv /opt/os_pariah/venv

echo "Installing Python Dependencies..."
/opt/os_pariah/venv/bin/pip install --upgrade pip
/opt/os_pariah/venv/bin/pip install -r /opt/os_pariah/requirements.txt

# Lock down permissions
chown -R pariah:pariah /opt/os_pariah /var/log/os_pariah /var/log/pariah /home/opensim/FSAssets/pariahcache

# Initialize Firewalld Ban Hammer IPSet (If firewalld is running)
echo "Configuring firewalld rules for Pariah Ban Hammer..."
if systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --new-ipset=pariah_banned_ips --type=hash:net || true
    firewall-cmd --permanent --add-rich-rule='rule source ipset="pariah_banned_ips" drop' || true
    firewall-cmd --reload || true
else
    echo "WARNING: firewalld is not currently active."
    echo "The pariah_banned_ips ipset will need to be created manually once the firewall is started."
fi

# Reload systemd so it sees the new service files
systemctl daemon-reload

echo "========================================================="
echo "OS Pariah Portal Installed Successfully!"
echo "1. Edit /etc/os_pariah/os-pariah.conf with your DB credentials."
echo "2. Start the portal: sudo systemctl enable --now pariah"
echo ""
echo "IMPORTANT: If your FSAssets path differs from the default, update the cache path in the Portal UI (System & Backend)."
echo "========================================================="

%files
# We claim ownership of these directories and files
/opt/os_pariah/
/var/log/os_pariah/
/home/opensim/FSAssets/pariahcache
/usr/lib/systemd/system/pariah.service
/usr/lib/systemd/system/pariah-worker-iar.service
/usr/lib/systemd/system/pariah-worker-log.service
/usr/lib/systemd/system/pariah-worker-log.timer
/etc/nginx/vhosts.d/OS-Pariah.conf
/etc/nginx/dummypariah.crt
/etc/nginx/dummypariah.key
/etc/sudoers.d/pariah_worker
%config(noreplace) %attr(0640, pariah, opensim) /etc/os_pariah/os-pariah.conf
%doc README.md
%doc ROADMAP.md
%doc COMPATIBILITY.md
%license LICENSE