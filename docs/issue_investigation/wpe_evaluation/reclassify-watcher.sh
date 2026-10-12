#!/bin/bash
# reclassify-watcher.sh -- polls orchestrate-tonight.log for each run's completion marker and
# reclassifies that run's file (t>=15s measured window, same warm-up p7_min excludes) as soon
# as it's ready, appending to the file, never overwriting the original VOID/LIVE line. Covers
# smoothness runs 1-3 and the soak.
set -u
LOG=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/logs/orchestrate-tonight.log
BURST=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/burst
OUTDIR=/home/tjwise/185-evidence/s4

for n in 1 2 3; do
	marker="smoothness run $n exit="
	echo "--- waiting for: $marker ---"
	until grep -q "$marker" "$LOG" 2>/dev/null; do sleep 10; done
	f="$OUTDIR/s4-smoothness-run$n.txt"
	if [ "$n" = 1 ]; then
		echo "run $n already reclassified earlier, skipping re-append"
		continue
	fi
	echo "reclassifying run $n: $f"
	python3 "$BURST/reclassify_cards_window.py" "$f"
done

echo "--- waiting for: soak exit= ---"
until grep -q "soak exit=" "$LOG" 2>/dev/null; do sleep 10; done
f="$OUTDIR/s4-soak.txt"
echo "reclassifying soak: $f"
python3 "$BURST/reclassify_cards_window.py" "$f"

echo RECLASSIFY_WATCHER_DONE
