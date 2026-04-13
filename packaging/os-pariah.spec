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
mkdir -p %{buildroot}/etc/systemd/system
mkdir -p %{buildroot}/etc/nginx/vhosts.d
mkdir -p %{buildroot}/var/log/os_pariah

# Copy application files
cp -r app scripts migrations wsgi.py worker.py check_mariadb.py migrate.py requirements.txt %{buildroot}/opt/os_pariah/

# Install the default blank config template
cp .env.example %{buildroot}/etc/os_pariah/os-pariah.conf

# Install the systemd services
cp packaging/pariah.service %{buildroot}/etc/systemd/system/
cp packaging/pariah-worker-iar.service %{buildroot}/etc/systemd/system/
cp packaging/pariah-worker-log.service %{buildroot}/etc/systemd/system/
cp packaging/pariah-worker-log.timer %{buildroot}/etc/systemd/system/

# Add the Nginx and gunicorn files
cp packaging/OS-Pariah.conf %{buildroot}/etc/nginx/vhosts.d/

%post
# Add sudo permissions for pariah user
echo "pariah ALL=(ALL) NOPASSWD: /bin/systemctl start pariah-worker-iar.service, /bin/systemctl stop pariah-worker-iar.service, /bin/systemctl restart pariah-worker-iar.service, /opt/os_pariah/venv/bin/python /opt/os_pariah/scripts/sync_firewall.py, /opt/os_pariah/venv/bin/python /opt/os_pariah/scripts/sync_robust.py, /bin/systemctl start opensim@*.service, /bin/systemctl stop opensim@*.service, /bin/systemctl restart opensim@*.service, /bin/systemctl enable opensim@*.service, /bin/systemctl disable opensim@*.service" > /etc/sudoers.d/pariah_worker
echo "pariah ALL=(opensim) NOPASSWD: /usr/bin/screen -p 0 -S OpenSim-* -X stuff *" >> /etc/sudoers.d/pariah_worker
chmod 0440 /etc/sudoers.d/pariah_worker

# This runs AFTER the files are copied to the server.
echo "Building Python 3.12 Virtual Environment..."
/usr/bin/python3.12 -m venv /opt/os_pariah/venv

echo "Installing Python Dependencies..."
/opt/os_pariah/venv/bin/pip install --upgrade pip
/opt/os_pariah/venv/bin/pip install -r /opt/os_pariah/requirements.txt

# Lock down permissions
chown -R pariah:pariah /opt/os_pariah /var/log/os_pariah /etc/os_pariah
chmod 640 /etc/os_pariah/os-pariah.conf

# Configure the FSAssets Texture Cache Directory
echo "Configuring FSAssets Texture Cache..."
mkdir -p /home/opensim/FSAssets/pariahcache
chown pariah:pariah /home/opensim/FSAssets/pariahcache

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

# Safely generate the dummy SSL certificate using a temporary config file
cat << 'EOF' > /tmp/pariah-openssl.cnf
[dn]
CN=pariahhost
[req]
distinguished_name = dn
[EXT]
subjectAltName=DNS:pariahhost
keyUsage=digitalSignature
extendedKeyUsage=serverAuth
EOF

openssl req -x509 -out /etc/nginx/dummy.crt -keyout /etc/nginx/dummy.key \
    -newkey rsa:2048 -nodes -sha256 -subj '/CN=pariahhost' \
    -extensions EXT -config /tmp/pariah-openssl.cnf

# Clean up the temp file
rm -f /tmp/pariah-openssl.cnf

echo "========================================================="
echo "OS Pariah Portal Installed Successfully!"
echo "1. Edit /etc/os_pariah/os-pariah.conf with your DB credentials."
echo "2. Run database migrations: sudo su - pariah -s /bin/bash -c '/opt/os_pariah/venv/bin/python migrate.py'"
echo "3. Start the portal: sudo systemctl enable --now pariah"
echo "4. IMPORTANT: If your FSAssets path differs from the default,"
echo "   update the cache path in the Portal UI (System & Backend)."
echo "========================================================="

%files
# We claim ownership of these directories and files
/opt/os_pariah/
/etc/systemd/system/pariah.service
/etc/systemd/system/pariah-worker-iar.service
/etc/systemd/system/pariah-worker-log.service
/etc/systemd/system/pariah-worker-log.timer
/etc/nginx/vhosts.d/OS-Pariah.conf
%config(noreplace) /etc/os_pariah/os-pariah.conf
%attr(0755, pariah, pariah) /var/log/os_pariah/