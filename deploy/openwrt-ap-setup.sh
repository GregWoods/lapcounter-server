#!/bin/sh
#
# Configure a Google WiFi (Gale) puck running OpenWrt as the standalone,
# offline access point for a lapcounter race meet.
#
# Idempotent: safe to re-run. Does NOT touch dropbear / authorized_keys,
# and does NOT change the LAN IP away from 192.168.8.1.
#
# Usage (from the repo root). `-O` is required: Windows OpenSSH scp defaults to
# SFTP, which dropbear does not provide.
#   scp -O deploy/openwrt-ap-setup.sh root@192.168.8.1:/tmp/
#   ssh root@192.168.8.1 "sed -i 's/\r$//' /tmp/openwrt-ap-setup.sh && sh /tmp/openwrt-ap-setup.sh"
#
set -e

PI_IP="192.168.8.3"
PI_MAC="B8:27:EB:B7:5B:58"    # Pi 3A+ has no Ethernet - this is the wlan0 MAC
ROUTER_IP="192.168.8.1"
SSID="Scalextric"
WIFI_KEY="racenight2026"
# The captive portal is served BY THIS ROUTER, not by the Pi. The Pi is a 3A+
# with 424MB of RAM running eight containers; the puck is otherwise idle, so the
# portal lives here and port 80 on the Pi stays free.
PORTAL_URL="http://${ROUTER_IP}/index.html"

# The captive-portal DNS hijack resolves EVERY name to this router, which also
# breaks apt/docker/apk on anything using it as a resolver.
#
# THIS IS NOW AUTOMATIC: plug the WAN cable in -> build mode; unplug it -> race
# mode. See deploy/openwrt/{portal-mode,99-portal-mode,portal-mode-boot} and the
# "Automatic, driven by the WAN cable" section of race-network-setup.md.
#
# HIJACK below only sets the state at the moment this script runs; the next WAN
# transition (or a reboot) will override it. For a deliberate manual override use
# `portal-mode on|off|status` instead.
#     HIJACK=0 sh openwrt-ap-setup.sh     # build mode  - real DNS via WAN
#     sh openwrt-ap-setup.sh              # race mode   - portal active
HIJACK="${HIJACK:-1}"

echo "==> Purging home-router leftovers"
# 18 static reservations on 10.0.1.x imported from the home router. Harmful
# here: expandhosts=1 turns them into DNS records, so lapcounter-server.lan
# would resolve to 10.0.1.13 - a black hole on this network.
# NB: `uci -q delete` still exits non-zero when the target doesn't exist (-q only
# silences the message), so every standalone delete needs `|| true` under `set -e`.
# The `while` loops below rely on exactly that non-zero exit to terminate.
while uci -q delete dhcp.@host[0]; do :; done
uci -q delete network.lan.multipath || true  # leftover from a multipath/mwan experiment
uci set system.@system[0].hostname='lapcounter-ap'
uci set system.@system[0].zonename='Europe/London'
uci set system.@system[0].timezone='GMT0BST,M3.5.0/1,M10.5.0/2'

echo "==> LAN (asserting, not changing)"
uci set network.lan.proto='static'
uci set network.lan.ipaddr="${ROUTER_IP}"
uci set network.lan.netmask='255.255.255.0'

echo "==> DHCP"
uci set dhcp.lan.start='50'
uci set dhcp.lan.limit='200'      # pool .50-.249; the Pi's reserved .3 sits outside it
uci set dhcp.lan.leasetime='4h'
# RFC 8910: modern iOS/Android open this URL directly on join.
uci -q delete dhcp.lan.dhcp_option || true
uci add_list dhcp.lan.dhcp_option="114,${PORTAL_URL}"

echo "==> Static lease for the Pi"
# A reservation beats Pi-side static config: it survives a reimage, keeps all
# addressing in one place, and means the SD-card image needs no IP settings.
uci add dhcp host >/dev/null
uci set dhcp.@host[-1].name='lapcounter'
uci set dhcp.@host[-1].mac="${PI_MAC}"
uci set dhcp.@host[-1].ip="${PI_IP}"

echo "==> Disabling IPv6"
# The captive portal depends on OS connectivity probes failing over to our
# portal page. `address=/#/<ipv4>` only answers A queries - AAAA leaks upstream,
# so a dual-stack phone probes over IPv6, fails, and never shows the portal.
# This is an offline appliance; IPv6 buys nothing and breaks the hijack.
uci set dhcp.@dnsmasq[0].filter_aaaa='1'
uci set dhcp.lan.dhcpv6='disabled'
uci set dhcp.lan.ra='disabled'
uci -q delete dhcp.lan.ra_flags || true
uci -q delete dhcp.lan.ra_preference || true
uci -q delete network.lan.ip6assign || true
uci -q delete network.globals.ula_prefix || true

echo "==> Wireless"
uci set wireless.radio0.disabled='0'
uci set wireless.radio0.country='GB'
uci set wireless.radio0.channel='6'
uci set wireless.radio0.htmode='HT20'
uci set wireless.radio1.disabled='0'
uci set wireless.radio1.country='GB'
uci set wireless.radio1.channel='44'      # non-DFS (U-NII-1). Never use 52-140: a
uci set wireless.radio1.htmode='VHT80'    # radar hit silently drops every client.

# Drop the 'ndtest' AP and rebuild both bands from scratch.
while uci -q delete wireless.@wifi-iface[0]; do :; done
for r in 0 1; do
    uci set wireless.ap${r}=wifi-iface
    uci set wireless.ap${r}.device="radio${r}"
    uci set wireless.ap${r}.mode='ap'
    uci set wireless.ap${r}.network='lan'
    uci set wireless.ap${r}.ssid="${SSID}"
    uci set wireless.ap${r}.encryption='psk2'
    uci set wireless.ap${r}.key="${WIFI_KEY}"
    # MUST stay 0: the Pi is a 3A+ with no Ethernet, so it joins as a *wireless*
    # client. Client isolation blocks wireless-to-wireless traffic, which would
    # stop every phone from reaching the Pi. Only safe to enable if the Pi is
    # ever moved onto a wired port.
    uci set wireless.ap${r}.isolate='0'
done

echo "==> Captive portal web server (uhttpd)"
# Move LuCI off port 80 -> http://192.168.8.1:8080 , freeing :80 for the portal.
uci set uhttpd.main.listen_http='0.0.0.0:8080'
uci set uhttpd.main.listen_https='0.0.0.0:8443'
# Dedicated portal instance. error_page points at a CGI that 302s, so EVERY
# unknown URL (i.e. every OS probe URL) redirects to the landing page.
uci set uhttpd.portal=uhttpd
uci set uhttpd.portal.home='/www-portal'
uci set uhttpd.portal.error_page='/cgi-bin/portal'
uci set uhttpd.portal.cgi_prefix='/cgi-bin'
uci set uhttpd.portal.index_page='index.html'
uci -q delete uhttpd.portal.listen_http || true
uci add_list uhttpd.portal.listen_http="0.0.0.0:80"
uci set uhttpd.portal.max_requests='10'
uci set uhttpd.portal.script_timeout='10'
uci commit uhttpd

echo "==> DNS hijack (captive portal): HIJACK=${HIJACK}"
# Resolve EVERY name to the ROUTER so the OS connectivity probes hit the portal.
# Always removed first so HIJACK=0 genuinely turns it off.
uci -q del_list dhcp.@dnsmasq[0].address="/#/${ROUTER_IP}" || true
uci -q del_list dhcp.@dnsmasq[0].address="/#/${PI_IP}" || true
if [ "${HIJACK}" = "1" ]; then
    uci add_list dhcp.@dnsmasq[0].address="/#/${ROUTER_IP}"
fi
# Friendly name for humans typing it, and for the docs.
while uci -q delete dhcp.@domain[0]; do :; done
uci add dhcp domain >/dev/null
uci set dhcp.@domain[-1].name='race'
uci set dhcp.@domain[-1].ip="${PI_IP}"

echo "==> Committing"
uci commit system
uci commit network
uci commit dhcp
uci commit wireless

/etc/init.d/system reload
wifi reload
/etc/init.d/dnsmasq restart
[ -x /www-portal/cgi-bin/portal ] || chmod +x /www-portal/cgi-bin/portal 2>/dev/null || true
/etc/init.d/uhttpd restart

echo "==> Done. Verifying:"
sleep 3
echo "--- wifi ---"
iwinfo 2>/dev/null | grep -E 'ESSID|Channel|Mode' || true
echo "--- dhcp reservations (should be ONLY the Pi) ---"
uci show dhcp | grep '@host' || echo "  (none)"
echo "--- dns hijack ---"
uci -q get dhcp.@dnsmasq[0].address || echo "  (off - build mode)"
