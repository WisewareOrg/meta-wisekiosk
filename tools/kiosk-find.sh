#!/usr/bin/env bash
# Find a Raspberry Pi on a LAN whose address you do not know.
#
#   tools/kiosk-find.sh 192.0.2.0/24
#
# Matches Raspberry Pi OUIs in the neighbour table. The script picks an L2 view and reports it:
#
#   windows   this host is WSL and the Windows host is on the target LAN; the sweep and the
#             neighbour table run from the Windows side.
#   local     an interface on this host is inside the CIDR; reads `ip neigh` (`arp -an` without
#             iproute2).
#   none      no L2 view of the subnet; the sweep reports only which addresses answer.
#
# Windows interop that stops answering mid-run is demoted to `none`. The sweep pings every address
# to provoke ARP, discards the replies, and reads the neighbour entries. A miss prints the whole
# neighbour table.
#
# Exit: 0 a Pi OUI found; 1 none found; 2 bad usage; 3 no L2 view.
set -uo pipefail

CIDR=${1:?usage: kiosk-find.sh <cidr>, e.g. 192.0.2.0/24}

# Raspberry Pi Trading / Raspberry Pi Foundation OUIs, oldest first.
OUIS="b8:27:eb dc:a6:32 e4:5f:01 28:cd:c1 2c:cf:67"

# Windows system directory mount point; WINDIR_MNT overrides it.
WINDIR=${WINDIR_MNT:-/mnt/c/Windows}
PS_EXE="$WINDIR/System32/WindowsPowerShell/v1.0/powershell.exe"
ARP_EXE="$WINDIR/System32/ARP.EXE"

case "$CIDR" in
    *.*.*.*/24) ;;
    *) echo "only a /24 is swept: give <a.b.c.0>/24, not $CIDR" >&2; exit 2 ;;
esac
PREFIX=${CIDR%.*/24}

# --- probes ---------------------------------------------------------------

# Run a PowerShell script read from stdin as a UTF-16LE base64 -EncodedCommand.
win_ps() {
    local enc
    enc=$(iconv -f UTF-8 -t UTF-16LE | base64 -w0) || return 1
    timeout 90 "$PS_EXE" -NoProfile -NonInteractive -EncodedCommand "$enc" 2>/dev/null | tr -d '\r'
}

# Connect and drop via bash /dev/tcp; `timeout` bounds a filtered port.
tcp_open() {
    # \$1/\$2 are the child bash's positionals, passed as arguments.
    timeout 4 bash -c "exec 3<>/dev/tcp/\$1/\$2" _ "$1" "$2" 2>/dev/null
}

# Read the banner the server volunteers.
tcp_banner() {
    timeout 5 bash -c "
        exec 3<>/dev/tcp/\$1/\$2 || exit 1
        IFS= read -r -t 3 line <&3
        printf '%s' \"\$line\"
    " _ "$1" "$2" 2>/dev/null | tr -d '\r'
}

# The same probe from the Windows side.
win_tcp_open() {
    local r
    r=$(win_ps <<PSEOF
\$c = New-Object System.Net.Sockets.TcpClient
if (\$c.ConnectAsync('$1', $2).Wait(4000) -and \$c.Connected) { Write-Output 'open' }
\$c.Close()
PSEOF
    )
    [ "$r" = "open" ]
}

# --- pick the L2 view -----------------------------------------------------

view=none
if [ -x "$PS_EXE" ] && [ -x "$ARP_EXE" ]; then
    # A returned table (an `Interface:` line) proves interop answers; retried 3 times.
    for attempt in 1 2 3; do
        probe=$(timeout 30 "$ARP_EXE" -a 2>/dev/null | tr -d '\r')
        if printf '%s' "$probe" | grep -q 'Interface:'; then
            view=windows
            break
        fi
        [ "$attempt" -lt 3 ] && sleep 5
    done
    [ "$view" = windows ] || \
        echo "warning: Windows interop is present but not answering after 3 tries -- falling back" >&2
fi
if [ "$view" = none ]; then
    # A /24 view exists iff some interface address shares the three octets.
    if ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 \
        | grep -qx "$PREFIX\.[0-9]*"; then
        view=local
    fi
fi

# Cleared only by the windows path when the sweep or the table read returns nothing.
sweep_answered=yes
table_answered=yes

echo "sweeping $PREFIX.1-254 (L2 view: $view) ..."

# --- sweep ----------------------------------------------------------------

if [ "$view" = windows ]; then
    # One asynchronous ping per address, all in flight at once.
    replies=$(win_ps <<PSEOF
\$t = foreach (\$i in 1..254) {
    (New-Object System.Net.NetworkInformation.Ping).SendPingAsync('$PREFIX.' + \$i, 1000)
}
[System.Threading.Tasks.Task]::WaitAll(\$t)
Write-Output (@(\$t | Where-Object { \$_.Result.Status -eq 'Success' }).Count)
PSEOF
    )
    case "$replies" in
        ''|*[!0-9]*)
            sweep_answered=no
            echo "warning: the Windows sweep did not report a count -- interop may have dropped mid-run" >&2 ;;
        *) echo "  $replies of 254 answered" ;;
    esac
else
    # Every ping in flight at once; each reply appends its address.
    RESPONDERS=$(mktemp)
    trap 'rm -f "$RESPONDERS"' EXIT
    for i in $(seq 1 254); do
        ( ping -c1 -W1 "$PREFIX.$i" > /dev/null 2>&1 && echo "$PREFIX.$i" >> "$RESPONDERS" ) &
    done
    wait
    echo "  $(wc -l < "$RESPONDERS") of 254 answered"
fi

# --- read the neighbour table --------------------------------------------

# Normalised to "<ip> <mac>", MACs lower-case and colon-separated.
case "$view" in
    windows)
        # An arrived table carries an `Interface:` header; no output means the call failed.
        raw=$(timeout 30 "$ARP_EXE" -a 2>/dev/null | tr -d '\r')
        case "$raw" in *Interface:*) ;; *) table_answered=no ;; esac
        table=$(printf '%s\n' "$raw" \
            | awk '$1 ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ && $2 ~ /^[0-9a-fA-F-]{17}$/ {print $1, $2}')
        source_desc="Windows ARP cache ($ARP_EXE -a)"
        ;;
    local)
        if command -v ip > /dev/null; then
            table=$(ip neigh show 2>/dev/null \
                | awk '{for (i=1;i<NF;i++) if ($i=="lladdr") print $1, $(i+1)}')
            source_desc="ip neigh"
        elif command -v arp > /dev/null; then
            table=$(arp -an 2>/dev/null \
                | awk '{ip=$2; gsub(/[()]/,"",ip); for (i=1;i<NF;i++) if ($i=="at") print ip, $(i+1)}')
            source_desc="arp -an"
        else
            echo "an interface is inside $CIDR but neither ip nor arp is installed" >&2
            exit 2
        fi
        ;;
    none)
        table=""
        source_desc="none"
        ;;
esac

table=$(printf '%s\n' "$table" | tr 'A-F' 'a-f' | tr '-' ':' \
    | grep -E "^$PREFIX\.[0-9]+ ([0-9a-f]{2}:){5}[0-9a-f]{2}$" \
    | grep -v ' ff:ff:ff:ff:ff:ff$' | sort -t. -k4 -n -u)

# --- report ---------------------------------------------------------------

# A windows run whose table read returned nothing, or whose sweep reported no count and found no
# in-range neighbour, reports "no L2 view" (exit 3).
if [ "$view" = windows ] && { [ "$table_answered" = no ] || \
    { [ "$sweep_answered" = no ] && [ -z "$table" ]; }; }; then
    if [ "$table_answered" = no ]; then
        why="the neighbour-table read returned nothing at all -- not an empty table, no table"
    else
        why="the sweep reported no count and the neighbour table came back with nothing in range"
    fi
    echo
    echo "the Windows interop this run depends on answered the opening probe and"
    echo "then stopped: $why."
    echo
    echo "This host is WSL, so those calls ARE the L2 view of $CIDR -- WSL2 sits"
    echo "behind NAT and its own neighbour table never holds a LAN peer. Nothing"
    echo "was measured. This is NOT evidence that $CIDR is empty, and a device"
    echo "sitting there right now would produce exactly this output."
    echo
    echo "the outage is usually seconds -- run it again, or run it from a host"
    echo "on that LAN."
    exit 3
fi

if [ "$view" = none ]; then
    echo
    echo "this host has no L2 view of $CIDR: no interface is inside it and no"
    echo "working Windows interop, so nothing here ever sees a MAC from that"
    echo "subnet. Reachability is all that can be measured, and it can only say"
    echo "which addresses answered -- not which of them is a Pi, and not that a"
    echo "silent address is unused."
    echo
    echo "addresses in $CIDR that answered:"
    if [ -s "$RESPONDERS" ]; then
        sort -t. -k4 -n -u "$RESPONDERS" | while read -r ip; do
            printf '  %-15s' "$ip"
            if tcp_open "$ip" 22; then
                printf ' tcp/22 open  %s' "$(tcp_banner "$ip" 22)"
            else
                printf ' tcp/22 no answer'
            fi
            printf '\n'
        done
    else
        echo "  (none -- and a host that drops ICMP answers nothing here either)"
    fi
    echo
    echo "run this from a host on that LAN to identify anything."
    exit 3
fi

pattern=$(printf '%s' "$OUIS" | tr ' ' '\n' | sed 's/^/ /' | paste -sd'|' -)
hits=$(printf '%s\n' "$table" | grep -E "$pattern") || true

if [ -z "$hits" ]; then
    echo
    echo "no Raspberry Pi OUI in $source_desc for $CIDR"
    if [ -z "$table" ]; then
        echo "  $source_desc holds no entry in that range at all -- nothing answered ARP"
    else
        echo "the whole table follows -- a newer board may carry an OUI this list predates"
        printf '%s\n' "$table" | sed 's/^/  /'
    fi
    exit 1
fi

echo
echo "Raspberry Pi OUIs in $source_desc:"
printf '%s\n' "$hits" | while read -r ip mac; do
    printf '  %-15s %s' "$ip" "$mac"
    if tcp_open "$ip" 22; then
        printf '  tcp/22 open  %s' "$(tcp_banner "$ip" 22)"
    elif [ "$view" = windows ] && win_tcp_open "$ip" 22; then
        # Reachable from Windows but not from WSL.
        printf '  tcp/22 open from Windows, not routable from WSL'
    else
        printf '  tcp/22 no answer'
    fi
    printf '\n'
done
echo
echo "an OUI says a Raspberry Pi, not which one -- confirm by logging in."
