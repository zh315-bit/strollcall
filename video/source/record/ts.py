"""Prefix each line of stdin with its wall-clock time (for replaying the real terminal output in A3)."""
import json, sys, time
for line in sys.stdin:
    print(json.dumps({"t": time.time(), "line": line.rstrip("\n")}), flush=True)
