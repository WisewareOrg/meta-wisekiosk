#!/bin/bash
# run remote-read.sh on the bench board; caller wraps this in the bench flock
host=$1
ssh=(ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
echo "== host epoch before: $(date +%s.%N)"
"${ssh[@]}" "$host" sh -s < "$(dirname "$0")/remote-read.sh"
rc=$?
echo "== host epoch after: $(date +%s.%N) rc=$rc"
