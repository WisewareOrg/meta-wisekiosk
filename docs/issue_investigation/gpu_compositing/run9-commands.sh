#!/bin/sh
# Run 9 -- #100 gpu-compositing, W6 recovery.
# Source session: 9253304a-ddb2-4c2c-827e-a05b0942ac7b
# Transcript: main transcript + subagent agent-adeb77092a2242020.jsonl
# Judgement (owner ruling 2026-09-28: best effort, pick the attempt matching the recorded number):
# Confidence: HIGH
# Two attempts of the identical command exist: line 6478 was REJECTED by the user/system (tool use declined) and never produced output; line 6623 is the verbatim retry and DID run (background task b4y08la3w). The retry's output (still readable in the committed hang-after-raw.txt) carries ROT0 and BT308/287s = 1.073/s, matching the README's cited 'ROT 97 -> 0' and '1.07/s' exactly -- picked on that match, not by position.

# --- main transcript line 6478  2026-09-22T05:54:59Z --- REJECTED, never ran (user declined the tool use) ---

# --- main line 6478  2026-09-22T05:54:59.392Z ---
/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/run-phase.sh /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p4_a.js 300 2>&1 | tee /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/hang-after-raw.txt

# --- main transcript line 6623  2026-09-22T06:14:43Z --- retry of the above, SUCCEEDED (background task b4y08la3w) ---

# --- main line 6623  2026-09-22T06:14:43.609Z ---
/tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/run-phase.sh /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/p4_a.js 300 2>&1 | tee /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad/hang-after-raw.txt

# --- adeb77092a2242020 line 134  2026-09-22T06:21:56.112Z ---
cd /tmp/claude-1000/-home-tjwise-meta-wisekiosk/9253304a-ddb2-4c2c-827e-a05b0942ac7b/scratchpad && python3 parse4.py hang-after-raw.txt "AFTER — fixed bundle (remount removed)" 2>&1
