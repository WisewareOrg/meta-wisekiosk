#!/bin/bash
# run-sequence.sh <ssh-target> <run> -- the W10 invocations, one per appliance run, each the frozen
# run-appliance.sh with the recorded parameters of the reference run it repeats:
#
#   run   repeats          probe             prefix  sleep  xprop-len  capture
#   49    Run 41           p30_baseline.js   BL      600    12000      runs/run49-baseline-raw.txt
#   50    Run 26a          p7_min.js         MP      180    20000      runs/run50-hold2s-fps-raw.txt
#   51    Run 26b          p7_min.js         MP      300    30000      runs/run51-hold2s-phase-raw.txt
#   52    Run 48, 8 s arm  p31_rotcheck.js   BL      600    9000       runs/run52-rotation-8s-raw.txt
#   53    Run 48, 8 s arm  p31_rotcheck.js   BL      600    9000       runs/run53-rotation-8s-raw.txt
#
# 52 and 53 are the same method at two times of day: 52 with the park cards CLOSED (before opening),
# 53 after opening, matching Run 48's 09:25 local capture. Each run is its own run (R3).
# A screenshot of the page is taken before each run (the capture window itself is never perturbed):
# it records the park cards' state, including WiseKiosk#402 timeouts, which are recorded, not filtered.
set -u
T=${1:?target}; R=${2:?run}
W=$(dirname "$(readlink -f "$0")")
P=/home/tjwise/meta-wisekiosk/docs/issue_investigation/gpu_compositing
mkdir -p "$W/runs"
case "$R" in
  49) a=(p30_baseline.js BL 600 12000 run49-baseline-raw.txt) ;;
  50) a=(p7_min.js MP 180 20000 run50-hold2s-fps-raw.txt) ;;
  51) a=(p7_min.js MP 300 30000 run51-hold2s-phase-raw.txt) ;;
  52) a=(p31_rotcheck.js BL 600 9000 run52-rotation-8s-raw.txt) ;;
  53) a=(p31_rotcheck.js BL 600 9000 run53-rotation-8s-raw.txt) ;;
  *) echo "unknown run $R"; exit 2 ;;
esac
/home/tjwise/meta-wisekiosk/tools/kiosk-screenshot.sh "$T" "$W/runs/run$R-pre.png"
"$W/run-appliance.sh" "$T" prod "$P/${a[0]}" "${a[1]}" "${a[2]}" "${a[3]}" "$W/runs/${a[4]}"
