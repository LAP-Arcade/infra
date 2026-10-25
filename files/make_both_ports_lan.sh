#!/bin/sh
# usage: make_both_ports_lan.sh {0|1}
#   1 = port 0 (WAN jack) joins the LAN VLAN -> both ethernet ports are LAN
#   0 = vanilla: port 0 is the WAN uplink
# Mode is written to /etc/config/network, so netifd reapplies it on every boot.

set -e

vlan_sect() {
	i=0
	while v=$(uci -q get "network.@switch_vlan[$i].vlan"); do
		[ "$v" = "$1" ] && { echo "@switch_vlan[$i]"; return 0; }
		i=$((i + 1))
	done
	return 1
}

case "$1" in
1) LP="0 1 6t"; WP="6t"   ; DISABLE=1 ;;
0) LP="1 6t"  ; WP="0 6t" ; DISABLE=0 ;;
*) echo "usage: ${0##*/} {0|1}" >&2; exit 1 ;;
esac

L=$(vlan_sect 1) || { echo "vlan 1 section missing" >&2; exit 1; }
W=$(vlan_sect 2) || { echo "vlan 2 section missing" >&2; exit 1; }

if [ "$(uci -q get "network.$L.ports")" = "$LP" ] && [ "$(uci -q get "network.$W.ports")" = "$WP" ]; then
	logger -t portmode "both_ports_lan=$1 already active, nothing to do"
	exit 0
fi

uci set "network.$L.ports=$LP"
uci set "network.$W.ports=$WP"

if [ "$DISABLE" = 1 ]; then
	# eth0.2 keeps no physical port in this mode; leaving wan enabled would retry DHCP forever.
	uci set network.wan.disabled='1'
	uci set network.wan6.disabled='1'
else
	uci -q delete network.wan.disabled || true
	uci -q delete network.wan6.disabled || true
fi

uci commit network
/etc/init.d/network reload
logger -t portmode "both_ports_lan=$1 applied"
