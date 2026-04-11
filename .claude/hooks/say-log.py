#!/usr/bin/env python
"""say-log.py - PostToolUse for say: log spoken text"""
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
        f.write(json.dumps({"error": str(e), "source": "say-log"}, ensure_ascii=False) + "\n")
    sys.exit(0)

tool_input = data.get("tool_input", {})
tool_name = data.get("tool_name", "")
# tool_input may arrive as either a dict or a JSON-encoded string (observed on
# some Windows hook invocations).  Handle both to avoid silently dropping text.
if isinstance(tool_input, str):
    try:
        tool_input = json.loads(tool_input)
    except Exception:
        tool_input = {}
text = tool_input.get("text", "") if isinstance(tool_input, dict) else ""

with open(log_path, "a", encoding="utf-8") as f:
    f.write(json.dumps({
        "source": "say",
        "tool_name": tool_name,
        "text": text,
        "keys": list(data.keys()),
    }, ensure_ascii=False) + "\n")

# Cache last say text for session-wave-v2 working memory
if text:
    cache_path = os.path.join(os.path.expanduser("~"), ".claude", "claude-last-say.txt")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass
