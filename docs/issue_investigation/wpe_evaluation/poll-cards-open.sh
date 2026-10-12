#!/bin/bash
# poll-cards-open.sh <ssh-target> <outpath> -- take one read-only screenshot and report its
# settle mean. Used to find when all 4 park cards show live data again (owner ruling on #185,
# 2026-10-04: S3 smoothness/soak must match the baseline's all-cards-open-with-data state).
set -u
T=${1:?ssh-target}; OUT=${2:?outpath}
/home/tjwise/meta-wisekiosk-185-s2/tools/kiosk-screenshot.sh "$T" "$OUT"
