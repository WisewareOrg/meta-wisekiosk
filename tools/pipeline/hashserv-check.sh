#!/bin/bash
# Connects to the shared bitbake-hashserv over its unix socket.
set -euo pipefail

SOCK="$HOME/.local/share/bitbake-hashserv/hashserv.sock"

if ! python3 -c '
import socket, sys

s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.connect(sys.argv[1])
except OSError:
    sys.exit(1)
s.close()
' "$SOCK"; then
    echo "bitbake-hashserv not answering on $SOCK" >&2
    exit 1
fi
