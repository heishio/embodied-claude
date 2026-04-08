#!/usr/bin/env python
"""diary-wave.py - PostToolUse hook for mcp__memory__diary.

When a diary entry is saved, learn its content into the wave phase graph
(session-wave-v2.db) and store the memory_id for linkage.
"""
import json
import os
import re
import sqlite3
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np

HOME = os.path.expanduser("~")
SESSION_DB = os.path.join(HOME, ".claude", "session-wave-v2.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'wave-phase-core', 'src'))
try:
    from wave_phase_core import (
        audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain,
        tokenize_sent, FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR,
    )
except ImportError:
    sys.exit(0)


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_words (
            word TEXT PRIMARY KEY, aud_phase REAL, vis_phase REAL);
        CREATE TABLE IF NOT EXISTS session_pairs (
            word_a TEXT, word_b TEXT,
            cos_a REAL, cos_v REAL, signed_a REAL, signed_v REAL,
            count INTEGER DEFAULT 0, avg_freshness REAL DEFAULT 1.0,
            PRIMARY KEY (word_a, word_b));
        CREATE TABLE IF NOT EXISTS session_chain (
            word_prev TEXT, word_next TEXT, count INTEGER DEFAULT 1,
            PRIMARY KEY (word_prev, word_next));
        CREATE TABLE IF NOT EXISTS lt_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            freshness REAL DEFAULT 0.5, memory_id TEXT);
    """)
    # Add memory_id column if missing
    try:
        conn.execute("SELECT memory_id FROM lt_sentences LIMIT 1")
    except Exception:
        try:
            conn.execute("ALTER TABLE lt_sentences ADD COLUMN memory_id TEXT")
        except Exception:
            pass


def load_state(conn):
    aud, vis = {}, {}
    for r in conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute("SELECT word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,avg_freshness FROM session_pairs"):
        pairs[(r[0], r[1])] = {'cos_a':r[2],'cos_v':r[3],'signed_a':r[4],'signed_v':r[5],'count':r[6],'avg_freshness':r[7] or 1.0}
    chain = {}
    for r in conn.execute("SELECT word_prev, word_next, count FROM session_chain"):
        chain[(r[0], r[1])] = r[2]
    return aud, vis, pairs, chain


def save_state(conn, aud, vis, pairs, chain):
    for w in aud:
        conn.execute("INSERT OR REPLACE INTO session_words VALUES(?,?,?)", (w, aud[w], vis[w]))
    for (a, b), ps in pairs.items():
        conn.execute("INSERT OR REPLACE INTO session_pairs(word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,avg_freshness) VALUES(?,?,?,?,?,?,?,?)",
                     (a, b, ps['cos_a'], ps['cos_v'], ps['signed_a'], ps['signed_v'], ps['count'], ps.get('avg_freshness', 1.0)))
    for (a, b), cnt in chain.items():
        conn.execute("INSERT OR REPLACE INTO session_chain VALUES(?,?,?)", (a, b, cnt))
    conn.commit()


def learn_sentence(toks, aud, vis, pairs, chain):
    lems = [t['lemma'] for t in toks]
    n = len(lems)
    if n < 2: return
    for t in toks:
        l = t['lemma']
        if l not in aud:
            aud[l] = audio_phase_accent(l)
            vis[l] = visual_phase(t['surface'])
    new_a = kuramoto_chain(np.array([aud[l] for l in lems]))
    new_v = kuramoto_chain(np.array([vis[l] for l in lems]))
    for i, l in enumerate(lems):
        aud[l] += ETA * (new_a[i] - aud[l])
        vis[l] += ETA * (new_v[i] - vis[l])
    for i in range(n):
        for j in range(i+1, min(n, i+PAIR_WINDOW)):
            key = tuple(sorted([lems[i], lems[j]]))
            da = float(wrap_pi(new_a[j] - new_a[i]))
            dv = float(wrap_pi(new_v[j] - new_v[i]))
            ca = float(np.cos(da)); cv = float(np.cos(dv))
            if key not in pairs:
                pairs[key] = {'cos_a':ca,'cos_v':cv,'signed_a':da,'signed_v':dv,'count':0,'avg_freshness':1.0}
            ps = pairs[key]
            ps['cos_a'] = (1-ETA_PAIR)*ps['cos_a'] + ETA_PAIR*ca
            ps['cos_v'] = (1-ETA_PAIR)*ps['cos_v'] + ETA_PAIR*cv
            ps['signed_a'] = (1-ETA_PAIR)*ps['signed_a'] + ETA_PAIR*da
            ps['signed_v'] = (1-ETA_PAIR)*ps['signed_v'] + ETA_PAIR*dv
            ps['count'] += 1
    for i in range(n-1):
        ck = (lems[i], lems[i+1])
        chain[ck] = chain.get(ck, 0) + 1


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="ignore")
        data = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)

    # Extract diary content and memory_id
    tool_input = data.get("tool_input", {})
    content = tool_input.get("content", "")
    if not content or len(content) < 5:
        sys.exit(0)

    # Extract memory_id from tool_response
    memory_id = None
    tool_response = data.get("tool_response", [])
    if isinstance(tool_response, list):
        for item in tool_response:
            if isinstance(item, dict) and item.get("text"):
                m = re.search(r'ID:\s*([a-f0-9-]+)', item["text"])
                if m:
                    memory_id = m.group(1)
                    break
    elif isinstance(tool_response, str):
        m = re.search(r'ID:\s*([a-f0-9-]+)', tool_response)
        if m:
            memory_id = m.group(1)

    # Learn into wave graph
    conn = sqlite3.connect(SESSION_DB, timeout=3)
    init_db(conn)
    aud, vis, pairs, chain = load_state(conn)

    sents = [s.strip() for s in re.split(r'[。！？\n\.]+', content) if len(s.strip()) > 2]
    import time
    for sent_text in sents:
        sent_text = re.sub(r'[#*`\-|>]', '', sent_text).strip()
        if len(sent_text) < 3: continue
        try:
            toks = tokenize_sent(sent_text)
        except Exception:
            continue
        if not toks: continue
        learn_sentence(toks, aud, vis, pairs, chain)
        lemmas_str = ",".join(t['lemma'] for t in toks)
        conn.execute(
            "INSERT INTO lt_sentences(text,speaker,timestamp,lemmas,freshness,memory_id) VALUES(?,?,?,?,?,?)",
            (sent_text[:200], 'diary', time.time(), lemmas_str, 1.0, memory_id)
        )

    save_state(conn, aud, vis, pairs, chain)
    conn.close()


if __name__ == "__main__":
    main()
