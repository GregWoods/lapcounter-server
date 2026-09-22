#!/bin/bash
#
# Provisioning run INSIDE the image chroot by Packer (qemu-user-static).
#
# Everything here must work without a running init system - the chroot has no
# systemd, so services can be enabled but never started. Anything needing a live
# kernel belongs in firstboot.sh instead.
#
# This is the CLIENT-mode counterpart to the superseded deploy/setup.sh, which
# configured the Pi as its own access point. Installing hostapd here would stop
# the Pi being a WiFi client and cut it off from the puck - and a 3A+ has no
# Ethernet port to recover over.
set -euxo pipefail

export DEBIAN_FRONTEND=noninteractive

# dpkg postinst scripts try to start daemons; in a chroot that fails and aborts
# the install. 101 tells them "not now".
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod +x /usr/sbin/policy-rc.d

apt-get update
apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg zstd rfkill network-manager

# --- Docker from the official repo -------------------------------------------
# Deliberately NOT get.docker.com: the convenience script tries to start the
# daemon, which cannot work in a chroot.
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=armhf signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian trixie stable" \
    > /etc/apt/sources.list.d/docker.list
apt-get update
apt-get install -y --no-install-recommends \
    docker-ce docker-ce-cli containerd.io docker-compose-plugin

usermod -aG docker pi 2>/dev/null || true

# --- services -----------------------------------------------------------------
install -m 0755 /tmp/firstboot.sh /usr/local/sbin/lapcounter-firstboot
install -m 0644 /tmp/lapcounter-firstboot.service /etc/systemd/system/
install -m 0644 /tmp/lapcounter.service /etc/systemd/system/

systemctl enable docker
systemctl enable ssh
systemctl enable lapcounter-firstboot.service
systemctl enable lapcounter.service

# --- housekeeping -------------------------------------------------------------
rm -f /usr/sbin/policy-rc.d
apt-get clean
rm -rf /var/lib/apt/lists/*

# Zeroing free space is what makes the .xz small: deleted files leave their old
# contents on disk, and random bytes do not compress. Without this the release
# artifact is several times larger.
dd if=/dev/zero of=/ZEROFILL bs=1M 2>/dev/null || true
rm -f /ZEROFILL
sync
