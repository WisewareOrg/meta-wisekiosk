#!/usr/bin/env bash
# What the kiosk's browser is doing, inferred from TCP state alone.
#
#   tools/kiosk-tcp-state.sh <kiosk-address> [port]
#
# Run on the machine serving the page: a socket table holds only that host's own sockets, so
# from a third machine it reports no connections.
#
#   no connections                        browser not running, or not attempting
#   1, ending FIN_WAIT_2 / TIME_WAIT      fetched the HTML only -- scripts never
#                                         ran, so a parse failure or an ignored
#                                         module
#   3, then closed                        fetched HTML and JS, but the scripts
#                                         did not execute -- CSP, or an early
#                                         throw
#   1 ESTABLISHED, sustained              rendering, one multiplexed socket.
#                                         The healthy state
#
# "1" appears twice with opposite meanings: a single connection that closes is failure, one that
# stays established is success.
set -uo pipefail

ADDR=${1:?usage: kiosk-tcp-state.sh <kiosk-address> [port]}
PORT=${2:-8080}

# ss and netstat spell states differently (ESTAB / ESTABLISHED, FIN-WAIT-2 / FIN_WAIT2); both are
# canonicalised below to the spelling in the table above.
if command -v ss > /dev/null; then
    engine="ss"
    rows=$(ss -tan 2>/dev/null)
    statecol=1
elif command -v netstat > /dev/null; then
    engine="netstat"
    rows=$(netstat -an 2>/dev/null | grep '^tcp')
    statecol=6
else
    echo "neither ss (iproute2) nor netstat (net-tools) is installed on this host" >&2
    exit 2
fi

# Rows count when the local port is PORT and the peer address is the kiosk. Column 4 is the local
# address and column 5 the peer in both engines; statecol carries the state column.
out=$(printf '%s\n' "$rows" | awk -v sc="$statecol" -v addr="$ADDR" -v port="$PORT" '
    $1 == "State" { next }
    NF >= 5 {
        lp = $4; sub(/.*:/, "", lp)
        pa = $5; sub(/:[^:]*$/, "", pa); gsub(/[][]/, "", pa)
        if (lp == port && pa == addr) print $sc
    }' \
    | sed -e 's/-/_/g' \
          -e 's/^ESTAB$/ESTABLISHED/' \
          -e 's/^FIN_WAIT\([12]\)$/FIN_WAIT_\1/' \
          -e 's/^SYN_RECV$/SYN_RECEIVED/' \
    | sort | uniq -c)

echo "$ADDR:$PORT  $(date '+%H:%M:%S')  [$engine]"
if [ -z "$out" ]; then
    echo "  no connections"
else
    printf '%s\n' "$out" | sed 's/^/  /'
fi

# Exits 0 with no verdict; one sample shows no persistence, so run it twice, seconds apart.
