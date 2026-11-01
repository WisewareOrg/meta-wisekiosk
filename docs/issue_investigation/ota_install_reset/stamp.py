#!/usr/bin/env python3
"""Prefix each stdin line with the host's receive time (epoch seconds)."""
import sys, time
for line in iter(sys.stdin.readline, ""):
    sys.stdout.write(f"{time.time():.6f} {line}")
    sys.stdout.flush()
