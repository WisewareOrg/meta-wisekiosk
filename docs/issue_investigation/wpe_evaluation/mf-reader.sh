#!/bin/sh
# mf-reader.sh <log> <seconds> -- runs ON the board, under X.
#
# Every 30 s for <seconds>: appends "S <uptime>" and any window title carrying an MF| payload to
# <log>, then "DONE <uptime>". xwininfo -tree, as measure-surf.sh: surf is override-redirect.
LOG=$1
END=$(($(cut -d. -f1 /proc/uptime) + $2))
export DISPLAY=:0
while [ "$(cut -d. -f1 /proc/uptime)" -lt "$END" ]; do
	{
		echo "S $(cut -d' ' -f1 /proc/uptime)"
		for id in $(xwininfo -root -tree | awk '/^ +0x/ { print $1 }'); do
			xprop -len 200 -id "$id" WM_NAME
		done | grep 'MF|'
	} >> "$LOG"
	sleep 30
done
echo "DONE $(cut -d' ' -f1 /proc/uptime)" >> "$LOG"
