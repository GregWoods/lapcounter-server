#!/bin/bash
#
# Lap Counter first-boot provisioning. Runs once, via lapcounter-firstboot.service.
#
# Does the things that cannot be baked into the image because they depend on the
# operator's choices or on a running kernel:
#   1. reads /boot/firmware/lapcounter.conf (editable from Windows/macOS)
#   2. configures WiFi as a CLIENT of the puck, with a static address
#   3. loads the pre-baked Docker images (no internet required)
#   4. starts the stack and seeds the database
#
# Idempotent: a sentinel file stops it re-running. Safe to re-arm by deleting
# /var/lib/lapcounter/firstboot-done and rebooting.
set -uo pipefail

BOOTDIR=/boot/firmware
CONF="$BOOTDIR/lapcounter.conf"
STATE=/var/lib/lapcounter
SENTINEL="$STATE/firstboot-done"
STACK=/opt/lapcounter
IMAGES="$STACK/images.tar.zst"
LOG=/var/log/lapcounter-firstboot.log

exec > >(tee -a "$LOG") 2>&1
echo "=== lapcounter first boot: $(date -Is) ==="

[ -e "$SENTINEL" ] && { echo "already provisioned; nothing to do"; exit 0; }
mkdir -p "$STATE"

# ---------------------------------------------------------------- 1. config
# Defaults match deploy/race-network-setup.md. The address pair is NOT
# configurable - see lapcounter.conf.example for why.
WIFI_SSID="Scalextric"
WIFI_PSK="racenight2026"
WIFI_COUNTRY="GB"
HOSTNAME="lapcounter-server"
DB_PASSWORD="lap"
SEED_SAMPLE_DATA="yes"
PI_IP="192.168.8.3"
ROUTER_IP="192.168.8.1"

if [ -f "$CONF" ]; then
    echo "--> reading $CONF"
    # Tolerate CRLF: the file is edited on Windows more often than not.
    sed -i 's/\r$//' "$CONF" 2>/dev/null || true
    # shellcheck disable=SC1090
    . "$CONF"
else
    echo "--> no $CONF found; using defaults"
fi

# ---------------------------------------------------------------- 2. identity
if [ "$(hostname)" != "$HOSTNAME" ]; then
    echo "--> hostname: $HOSTNAME"
    hostnamectl set-hostname "$HOSTNAME" || true
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$HOSTNAME/" /etc/hosts || true
fi

# ---------------------------------------------------------------- 3. wifi
# Without a regulatory domain the radio stays rfkill-blocked and nothing
# associates, no matter how correct the credentials are.
echo "--> wifi country: $WIFI_COUNTRY"
raspi-config nonint do_wifi_country "$WIFI_COUNTRY" || true
rfkill unblock wifi || true

echo "--> wifi client profile for '$WIFI_SSID', static $PI_IP"
nmcli connection delete lapcounter-wifi >/dev/null 2>&1 || true
nmcli connection add type wifi ifname wlan0 con-name lapcounter-wifi ssid "$WIFI_SSID" || true
nmcli connection modify lapcounter-wifi \
    wifi-sec.key-mgmt wpa-psk \
    wifi-sec.psk "$WIFI_PSK" \
    ipv4.method manual \
    ipv4.addresses "$PI_IP/24" \
    ipv4.gateway "$ROUTER_IP" \
    ipv4.dns "$ROUTER_IP" \
    ipv6.method disabled \
    connection.autoconnect yes \
    connection.autoconnect-priority 100 \
    802-11-wireless.powersave 2 || true

# powersave 2 = disabled. This is not cosmetic: the Pi is the server every phone
# talks to, and WiFi powersave adds hundreds of ms of latency, which makes the
# live MQTT leaderboard look broken.
nmcli connection up lapcounter-wifi || echo "!! wifi did not come up; check SSID/PSK in $CONF"

# ---------------------------------------------------------------- 4. images
# Pre-baked so first boot needs no internet. Loading takes a few minutes on a
# Pi 3A+; the tarball is removed afterwards to give the card its ~2GB back.
if [ -f "$IMAGES" ]; then
    echo "--> loading Docker images (this takes several minutes)"
    systemctl start docker || true
    if zstd -dc "$IMAGES" | docker load; then
        rm -f "$IMAGES"
        echo "--> images loaded; tarball removed"
    else
        echo "!! docker load FAILED - leaving $IMAGES in place for retry"
    fi
else
    echo "--> no $IMAGES (already loaded, or an internet-install image)"
fi

# ---------------------------------------------------------------- 5. stack
echo "--> starting the stack"
if [ "$DB_PASSWORD" != "lap" ]; then
    sed -i "s/^\( *POSTGRES_PASSWORD:\).*/\1 $DB_PASSWORD/; s/\(DB_PASSWORD=\).*/\1$DB_PASSWORD/" \
        "$STACK/compose.yaml"
fi

systemctl enable --now docker || true
( cd "$STACK" && docker compose up -d ) || echo "!! compose up failed"

# ---------------------------------------------------------------- 6. seed
# The API creates no tables at startup, so a fresh volume needs the schema.
if [ "$SEED_SAMPLE_DATA" = "yes" ] && [ -f "$STACK/database/schema.sql" ]; then
    echo "--> waiting for postgres"
    for _ in $(seq 1 60); do
        docker exec database pg_isready -U lap >/dev/null 2>&1 && break
        sleep 2
    done
    if docker exec database psql -U lap -d lapcounter_server -c '\dt' 2>/dev/null | grep -q drivers; then
        echo "--> database already populated; skipping seed"
    else
        echo "--> seeding schema + sample data"
        docker exec -i database psql -U lap -d lapcounter_server < "$STACK/database/schema.sql"
        docker exec -i database psql -U lap -d lapcounter_server < "$STACK/database/sampledata.sql"
    fi
fi

touch "$SENTINEL"
echo "=== first boot complete: $(date -Is) ==="
echo "App:    http://$PI_IP:8087/"
echo "Portal: http://$ROUTER_IP/  (served by the puck)"
