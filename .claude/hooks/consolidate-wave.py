#!/usr/bin/env python
"""consolidate-wave.py - SessionEnd hook for wave phase consolidation.

Performs:
  1. session_sentences → lt_sentences migration
  2. LTD: all pairs avg_freshness *= 0.92 (floor 0.01)
  3. LTP: energy-proportional freshness boost (wave co-activation)
  4. Reset energy counters and pool
"""
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
import numpy as np

sys.path.insert(0, "C:/tmp/wave_phase_lab")
try:
    from reading_session_v2 import FUNC_WORDS, PAIR_WINDOW
except ImportError:
    FUNC_WORDS = set()
    PAIR_WINDOW = 5

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

HOME = os.path.expanduser("~")
SESSION_DB = os.path.join(HOME, ".claude", "session-wave-v2.db")
POOL_FILE = os.path.join(HOME, ".claude", "wave-pool.json")

# LTP/LTD parameters
LTD_FACTOR = 0.92       # global freshness decay per consolidation
LTD_FLOOR = 0.01        # minimum freshness (never fully forgotten)
LTP_BETA = 0.005        # energy → freshness conversion rate
LTP_CAP = 0.2           # max freshness boost per consolidation


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_words (
            word TEXT PRIMARY KEY, aud_phase REAL, vis_phase REAL);
        CREATE TABLE IF NOT EXISTS session_pairs (
            word_a TEXT, word_b TEXT,
            cos_a REAL, cos_v REAL, signed_a REAL, signed_v REAL,
            count INTEGER DEFAULT 0, avg_freshness REAL DEFAULT 1.0,
            energy REAL DEFAULT 0.0,
            mean_f REAL, var_f REAL,
            PRIMARY KEY (word_a, word_b));
        CREATE TABLE IF NOT EXISTS session_chain (
            word_prev TEXT, word_next TEXT, count INTEGER DEFAULT 1,
            PRIMARY KEY (word_prev, word_next));
        CREATE TABLE IF NOT EXISTS session_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            freshness REAL DEFAULT 1.0);
        CREATE TABLE IF NOT EXISTS lt_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            freshness REAL DEFAULT 0.5, memory_id TEXT);
    """)
    # Add energy column if missing (migration)
    try:
        conn.execute("SELECT energy FROM session_pairs LIMIT 1")
    except Exception:
        try:
            conn.execute("ALTER TABLE session_pairs ADD COLUMN energy REAL DEFAULT 0.0")
        except Exception:
            pass
    # Add memory_id column if missing
    try:
        conn.execute("SELECT memory_id FROM lt_sentences LIMIT 1")
    except Exception:
        try:
            conn.execute("ALTER TABLE lt_sentences ADD COLUMN memory_id TEXT")
        except Exception:
            pass
    # Add temporal sketch columns if missing
    for col in ("mean_f", "var_f"):
        try:
            conn.execute(f"SELECT {col} FROM session_pairs LIMIT 1")
        except Exception:
            try:
                conn.execute(f"ALTER TABLE session_pairs ADD COLUMN {col} REAL")
            except Exception:
                pass


def main():
    if not os.path.exists(SESSION_DB):
        print("[consolidate-wave] no session DB, skip")
        return

    conn = sqlite3.connect(SESSION_DB, timeout=5)
    init_db(conn)

    # 1. Migrate session_sentences → lt_sentences
    sess_rows = conn.execute(
        "SELECT text, speaker, timestamp, lemmas, freshness FROM session_sentences"
    ).fetchall()
    migrated = 0
    for text, speaker, ts, lemmas, fresh in sess_rows:
        conn.execute(
            "INSERT INTO lt_sentences(text,speaker,timestamp,lemmas,freshness) VALUES(?,?,?,?,?)",
            (text, speaker, ts, lemmas, fresh)
        )
        migrated += 1
    conn.execute("DELETE FROM session_sentences")

    # 2. LTD: global freshness decay
    conn.execute(
        "UPDATE session_pairs SET avg_freshness = MAX(avg_freshness * ?, ?)",
        (LTD_FACTOR, LTD_FLOOR)
    )

    # 3. LTP: energy-proportional freshness boost
    energized = conn.execute(
        "SELECT word_a, word_b, avg_freshness, energy FROM session_pairs WHERE energy > 0"
    ).fetchall()
    ltp_count = 0
    for a, b, fresh, energy in energized:
        boost = min(energy * LTP_BETA, LTP_CAP)
        new_fresh = min(fresh + boost, 1.0)
        conn.execute(
            "UPDATE session_pairs SET avg_freshness=? WHERE word_a=? AND word_b=?",
            (new_fresh, a, b)
        )
        ltp_count += 1

    # 4. Reset all energy counters
    conn.execute("UPDATE session_pairs SET energy = 0")

    # 5. Rebuild temporal sketch (mean_f, var_f per pair)
    pair_set = set(
        (r[0], r[1]) for r in conn.execute("SELECT word_a, word_b FROM session_pairs")
    )
    pair_freshness = defaultdict(list)
    lt_all = conn.execute("SELECT lemmas, freshness FROM lt_sentences").fetchall()
    for lemmas_str, fresh in lt_all:
        if not lemmas_str or fresh is None:
            continue
        lems = lemmas_str.split(",")
        content = [l for l in lems if l not in FUNC_WORDS]
        n = len(content)
        for i in range(n):
            for j in range(i + 1, min(n, i + PAIR_WINDOW)):
                key = tuple(sorted([content[i], content[j]]))
                if key in pair_set:
                    pair_freshness[key].append(fresh)
    # Clear stale sketches first, then write fresh ones
    conn.execute("UPDATE session_pairs SET mean_f=NULL, var_f=NULL")
    sketch_count = 0
    for key, fs in pair_freshness.items():
        a = np.array(fs)
        mean_f = float(a.mean())
        var_f = float(a.var()) if len(a) > 1 else 0.01
        conn.execute(
            "UPDATE session_pairs SET mean_f=?, var_f=? WHERE word_a=? AND word_b=?",
            (mean_f, var_f, key[0], key[1])
        )
        sketch_count += 1

    conn.commit()

    # Stats
    total_pairs = conn.execute("SELECT COUNT(*) FROM session_pairs").fetchone()[0]
    lt_total = conn.execute("SELECT COUNT(*) FROM lt_sentences").fetchone()[0]
    avg_fresh = conn.execute("SELECT AVG(avg_freshness) FROM session_pairs").fetchone()[0] or 0

    conn.close()

    # 5. Reset pool
    if os.path.exists(POOL_FILE):
        try:
            os.remove(POOL_FILE)
        except Exception:
            pass

    print(f"[consolidate-wave] migrated={migrated} LTD={total_pairs}pairs(avg_f={avg_fresh:.3f}) LTP={ltp_count}pairs sketch={sketch_count} lt_total={lt_total}")


if __name__ == "__main__":
    main()
