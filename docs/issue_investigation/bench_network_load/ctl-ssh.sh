#!/bin/bash
# one ssh to the bench board: args = remote command string; output with address/host redacted
ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=15 -o LogLevel=ERROR root@${BENCH:?the bench board address} "$@" 2>&1 | sed 's/[0-9]*\.[0-9]*\.[0-9]*\.[0-9]*/<addr>/g; s/<hostname>/<host>/g'
