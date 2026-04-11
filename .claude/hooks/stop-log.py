#!/usr/bin/env python
"""stop-log.py - Stopフックの中身をログに出力"""
import json
import sys
import os

log_path = os.path.join(os.path.expanduser("~"), ".claude", "stop-hook-log.jsonl")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

try:
    raw = sys.stdin.buffer.read().decode("utf-8", errors="ignore")
    if not raw:
        sys.exit(0)
    data = json.loads(raw)
except Exception as e:
    with open(log_path, "a", encoding="utf-8") as f:
        f.write("ERROR: " + str(e) + "\n")
    sys.exit(0)

with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "keys": list(data.keys()),
        "last_assistant_message": data.get("last_assistant_message", "")[:500],
        "full_keys_dump": {k: str(v)[:200] for k, v in data.items()},
    }, ensure_ascii=False) + "\n")

# Cache last assistant message for session-wave-v2 working memory
last_msg = data.get("last_assistant_message", "")
if last_msg:
    cache_path = os.path.join(os.path.expanduser("~"), ".claude", "claude-last-message.txt")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(last_msg)
    except Exception:
        pass
