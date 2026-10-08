#!/bin/bash
set -u
cd /home/tjwise/meta-wisekiosk-185-s2
D=docs/issue_investigation/wpe_evaluation
OUTDIR=/tmp/claude-1000/-home-tjwise-meta-wisekiosk/76635847-5247-4809-8402-e1fe41739c68/scratchpad/s3

mkdir -p "$OUTDIR"

for i in 1 2 3; do
  echo "=== S3 smoothness run $i starting $(date -u +%FT%TZ) ==="
  "$D/run-smoothness.sh" 'root@<BENCH_ADDRESS>' S3-32b670c "$OUTDIR/s3-smoothness-run$i.txt"
  echo "=== S3 smoothness run $i exit=$? done $(date -u +%FT%TZ) ==="
done

echo "=== S3 soak starting $(date -u +%FT%TZ) ==="
"$D/run-soak.sh" 'root@<BENCH_ADDRESS>' S3-32b670c "$OUTDIR/s3-soak.txt"
echo "=== S3 soak exit=$? done $(date -u +%FT%TZ) ==="

echo "=== S3 time-to-page starting $(date -u +%FT%TZ) ==="
"$D/run-time-to-page.sh" 'root@<BENCH_ADDRESS>' S3-32b670c "$OUTDIR/s3-ttp.txt"
echo "=== S3 time-to-page exit=$? done $(date -u +%FT%TZ) ==="

echo ALL_S3_DONE
