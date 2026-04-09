#!/usr/bin/env python
"""consolidate-wave.py - SessionEnd hook for wave phase consolidation.

Performs:
  1. session_sentences → lt_sentences migration
  2. LTD: all pairs plasticity *= 0.92 (floor 0.01)
  3. LTP: energy-proportional plasticity boost (wave co-activation)
  4. Reset energy counters and pool
"""
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'wave-phase-core', 'src'))
try:
    from wave_phase_core import FUNC_WORDS, PAIR_WINDOW, plasticity_log_scale
except ImportError:
    FUNC_WORDS = set()
    PAIR_WINDOW = 5
    import math as _math
    _LTD_FLOOR = 0.01
    _LOG_RANGE = _math.log(1.0 / _LTD_FLOOR)
    def plasticity_log_scale(p):
        return _math.log(max(p, _LTD_FLOOR) / _LTD_FLOOR) / _LOG_RANGE

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

HOME = os.path.expanduser("~")
SESSION_DB = os.path.join(HOME, ".claude", "session-wave-v2.db")
POOL_FILE = os.path.join(HOME, ".claude", "wave-pool.json")

# LTP/LTD parameters
LTD_FACTOR = 0.92       # global plasticity decay per consolidation
LTD_FLOOR = 0.01        # minimum plasticity (never fully forgotten)
LTP_BETA = 0.005        # energy → plasticity conversion rate
LTP_CAP = 0.2           # max plasticity boost per consolidation


def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_words (
            word TEXT PRIMARY KEY, aud_phase REAL, vis_phase REAL);
        CREATE TABLE IF NOT EXISTS session_pairs (
            word_a TEXT, word_b TEXT,
            cos_a REAL, cos_v REAL, signed_a REAL, signed_v REAL,
            count INTEGER DEFAULT 0, plasticity REAL DEFAULT 1.0,
            energy REAL DEFAULT 0.0,
            mean_f REAL, var_f REAL,
            PRIMARY KEY (word_a, word_b));
        CREATE TABLE IF NOT EXISTS session_chain (
            word_prev TEXT, word_next TEXT, count INTEGER DEFAULT 1,
            PRIMARY KEY (word_prev, word_next));
        CREATE TABLE IF NOT EXISTS session_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            plasticity REAL DEFAULT 1.0);
        CREATE TABLE IF NOT EXISTS lt_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            plasticity REAL DEFAULT 0.5, memory_id TEXT);
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

    # 1. Migrate session_sentences → lt_sentences (energy-based initial freshness)
    # Build pair energy map for sentence freshness estimation
    pair_energy = {}
    for r in conn.execute("SELECT word_a, word_b, energy FROM session_pairs WHERE energy > 0"):
        pair_energy[tuple(sorted([r[0], r[1]]))] = r[2]

    sess_rows = conn.execute(
        "SELECT text, speaker, timestamp, lemmas FROM session_sentences"
    ).fetchall()
    migrated = 0
    for text, speaker, ts, lemmas_str in sess_rows:
        # Estimate sentence freshness from its pairs' energy
        sent_fresh = 0.0
        if lemmas_str:
            lems = lemmas_str.split(",")
            content = [l for l in lems if l not in FUNC_WORDS]
            n = len(content)
            energies = []
            for i in range(n):
                for j in range(i + 1, min(n, i + PAIR_WINDOW)):
                    key = tuple(sorted([content[i], content[j]]))
                    e = pair_energy.get(key, 0.0)
                    if e > 0:
                        energies.append(e)
            sent_fresh = min(np.mean(energies) * LTP_BETA * 10, 1.0) if energies else 0.01
        conn.execute(
            "INSERT INTO lt_sentences(text,speaker,timestamp,lemmas,plasticity) VALUES(?,?,?,?,?)",
            (text, speaker, ts, lemmas_str, max(sent_fresh, LTD_FLOOR))
        )
        migrated += 1
    conn.execute("DELETE FROM session_sentences")

    # 2. LTP: energy-proportional freshness boost (diminishing returns)
    energized = conn.execute(
        "SELECT word_a, word_b, plasticity, energy FROM session_pairs WHERE energy > 0"
    ).fetchall()
    ltp_count = 0
    for a, b, fresh, energy in energized:
        # Low freshness recovers more easily
        recovery = (1 - fresh) if fresh < 1.0 else 0.0
        boost = min(energy * LTP_BETA * recovery, LTP_CAP)
        new_fresh = min(fresh + boost, 1.0)
        conn.execute(
            "UPDATE session_pairs SET plasticity=? WHERE word_a=? AND word_b=?",
            (new_fresh, a, b)
        )
        ltp_count += 1

    # 3. Reset all energy counters
    conn.execute("UPDATE session_pairs SET energy = 0")

    # 4. Normalize: total freshness → target_sum (finite attention resource)
    total_pairs = conn.execute("SELECT COUNT(*) FROM session_pairs").fetchone()[0]
    if total_pairs > 0:
        target_sum = total_pairs * 0.15  # base rate per pair
        current_sum = conn.execute("SELECT SUM(plasticity) FROM session_pairs").fetchone()[0] or 0
        if current_sum > target_sum and current_sum > 0:
            scale = target_sum / current_sum
            conn.execute(
                "UPDATE session_pairs SET plasticity = MAX(plasticity * ?, ?)",
                (scale, LTD_FLOOR)
            )

    # 5. Rebuild temporal sketch (mean_f, var_f per pair)
    pair_set = set(
        (r[0], r[1]) for r in conn.execute("SELECT word_a, word_b FROM session_pairs")
    )
    pair_freshness = defaultdict(list)
    lt_all = conn.execute("SELECT lemmas, plasticity FROM lt_sentences").fetchall()
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
                    pair_freshness[key].append(plasticity_log_scale(fresh))
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
    avg_fresh = conn.execute("SELECT AVG(plasticity) FROM session_pairs").fetchone()[0] or 0

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
