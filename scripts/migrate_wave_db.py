# -*- coding: utf-8 -*-
"""migrate_wave_db.py - Migration + memory import for session-wave-v2.db.

Commands:
  python scripts/migrate_wave_db.py              # schema migration only
  python scripts/migrate_wave_db.py --import      # schema + import memories from memory.db
  python scripts/migrate_wave_db.py --db PATH     # custom DB path
"""
import os
import re
import sqlite3
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add wave-phase-core to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'wave-phase-core', 'src'))

DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".claude", "session-wave-v2.db")
MEMORY_DB = os.path.join(os.path.expanduser("~"), ".claude", "memories", "memory.db")


def has_column(conn, table, col):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    return col in cols


def migrate(db_path):
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}, creating new.")

    conn = sqlite3.connect(db_path)
    changes = []

    # 1. WAL mode
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    if mode != "wal":
        conn.execute("PRAGMA journal_mode=WAL")
        changes.append("journal_mode -> WAL")

    # 2. Ensure tables exist
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS session_words (
            word TEXT PRIMARY KEY, aud_phase REAL, vis_phase REAL);
        CREATE TABLE IF NOT EXISTS session_pairs (
            word_a TEXT, word_b TEXT,
            cos_a REAL, cos_v REAL, signed_a REAL, signed_v REAL,
            count INTEGER DEFAULT 0, plasticity REAL DEFAULT 1.0,
            energy REAL DEFAULT 0.0,
            mean_f REAL, var_f REAL,
            mean_id REAL, var_id REAL,
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

    # 3. Column renames: freshness -> plasticity (SQLite 3.25+)
    for table in ("session_pairs", "session_sentences", "lt_sentences"):
        old_col = "avg_freshness" if table == "session_pairs" else "freshness"
        if has_column(conn, table, old_col) and not has_column(conn, table, "plasticity"):
            conn.execute(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO plasticity")
            changes.append(f"{table}: {old_col} -> plasticity")

    # 4. Add missing columns
    for col, default in [("energy", "0.0"), ("mean_f", "NULL"), ("var_f", "NULL"), ("mean_id", "NULL"), ("var_id", "NULL")]:
        if not has_column(conn, "session_pairs", col):
            conn.execute(f"ALTER TABLE session_pairs ADD COLUMN {col} REAL DEFAULT {default}")
            changes.append(f"session_pairs: +{col}")

    if not has_column(conn, "lt_sentences", "memory_id"):
        conn.execute("ALTER TABLE lt_sentences ADD COLUMN memory_id TEXT")
        changes.append("lt_sentences: +memory_id")

    conn.commit()

    # Stats
    pairs = conn.execute("SELECT COUNT(*) FROM session_pairs").fetchone()[0]
    lt = conn.execute("SELECT COUNT(*) FROM lt_sentences").fetchone()[0]
    avg_p = conn.execute("SELECT AVG(plasticity) FROM session_pairs").fetchone()[0] or 0
    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]

    conn.close()

    if changes:
        print(f"Migrations applied: {', '.join(changes)}")
    else:
        print("No migrations needed.")
    print(f"DB: {db_path}")
    print(f"  pairs={pairs} lt_sentences={lt} avg_plasticity={avg_p:.3f} journal={journal}")
    return db_path


def import_memories(db_path, memory_db=MEMORY_DB):
    """Import all memories from memory.db into wave graph (non-destructive)."""
    try:
        import numpy as np
        from wave_phase_core import (
            audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain,
            tokenize_sent, FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR,
        )
    except ImportError as e:
        print(f"Error: {e}")
        print("Install: numpy, scipy, sudachipy, sudachidict-core, pyopenjtalk")
        sys.exit(1)

    if not os.path.exists(memory_db):
        print(f"Memory DB not found: {memory_db}")
        return

    print(f"Loading diary from {memory_db}...")
    mem_conn = sqlite3.connect(memory_db)
    rows = mem_conn.execute(
        "SELECT id, content, freshness, timestamp FROM memories ORDER BY freshness DESC"
    ).fetchall()
    mem_conn.close()
    print(f"  {len(rows)} memories loaded")

    sess_conn = sqlite3.connect(db_path)

    # Load existing state
    aud, vis = {}, {}
    for r in sess_conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in sess_conn.execute("SELECT word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity FROM session_pairs"):
        pairs[(r[0], r[1])] = {
            'cos_a': r[2], 'cos_v': r[3], 'signed_a': r[4], 'signed_v': r[5],
            'count': r[6], 'plasticity': r[7] or 1.0
        }
    chain = {}
    for r in sess_conn.execute("SELECT word_prev, word_next, count FROM session_chain"):
        chain[(r[0], r[1])] = r[2]

    # Check existing memory_ids to avoid duplicates
    existing_mids = set()
    for r in sess_conn.execute("SELECT memory_id FROM lt_sentences WHERE memory_id IS NOT NULL"):
        existing_mids.add(r[0])

    print(f"  existing: {len(aud)} words, {len(pairs)} pairs, {len(existing_mids)} imported memories")

    t0 = time.time()
    total_sents = 0
    skipped_dup = 0

    for mid, content, freshness, ts in rows:
        if not content or len(content) < 5:
            continue
        if mid in existing_mids:
            skipped_dup += 1
            continue

        sents = [s.strip() for s in re.split(r'[。！？\n\.]+', content) if len(s.strip()) > 2]
        for sent_text in sents:
            sent_text = re.sub(r'[#*`\-|>]', '', sent_text).strip()
            if len(sent_text) < 3:
                continue
            try:
                toks = tokenize_sent(sent_text)
            except Exception:
                continue
            if not toks:
                continue

            # Learn into graph
            lems = [t['lemma'] for t in toks]
            n = len(lems)
            if n < 2:
                continue
            fw = max(0.1, freshness)
            eta = ETA * fw
            eta_pair = ETA_PAIR * fw
            for t in toks:
                l = t['lemma']
                if l not in aud:
                    aud[l] = audio_phase_accent(l)
                    vis[l] = visual_phase(t['surface'])
            new_a = kuramoto_chain(np.array([aud[l] for l in lems]))
            new_v = kuramoto_chain(np.array([vis[l] for l in lems]))
            for i, l in enumerate(lems):
                aud[l] += eta * (new_a[i] - aud[l])
                vis[l] += eta * (new_v[i] - vis[l])
            for i in range(n):
                for j in range(i + 1, min(n, i + PAIR_WINDOW)):
                    key = tuple(sorted([lems[i], lems[j]]))
                    da = float(wrap_pi(new_a[j] - new_a[i]))
                    dv = float(wrap_pi(new_v[j] - new_v[i]))
                    ca = float(np.cos(da)); cv = float(np.cos(dv))
                    if key not in pairs:
                        pairs[key] = {'cos_a': ca, 'cos_v': cv, 'signed_a': da, 'signed_v': dv, 'count': 0, 'plasticity': 1.0}
                    ps = pairs[key]
                    ps['cos_a'] = (1 - eta_pair) * ps['cos_a'] + eta_pair * ca
                    ps['cos_v'] = (1 - eta_pair) * ps['cos_v'] + eta_pair * cv
                    ps['signed_a'] = (1 - eta_pair) * ps['signed_a'] + eta_pair * da
                    ps['signed_v'] = (1 - eta_pair) * ps['signed_v'] + eta_pair * dv
                    ps['count'] += 1
                    old_p = ps.get('plasticity', fw)
                    ps['plasticity'] = old_p * 0.9 + fw * 0.1
            for i in range(n - 1):
                ck = (lems[i], lems[i + 1])
                chain[ck] = chain.get(ck, 0) + 1

            lemmas_str = ",".join(t['lemma'] for t in toks)
            sess_conn.execute(
                "INSERT INTO lt_sentences (text, speaker, timestamp, lemmas, plasticity, memory_id) VALUES (?, ?, ?, ?, ?, ?)",
                (sent_text[:200], 'LT', ts or 0, lemmas_str, freshness, mid)
            )
            total_sents += 1

        if total_sents % 500 == 0 and total_sents > 0:
            print(f"  ... {total_sents} sentences ({time.time()-t0:.1f}s)")

    # Save state
    for w in aud:
        sess_conn.execute("INSERT OR REPLACE INTO session_words VALUES (?, ?, ?)", (w, aud[w], vis[w]))
    for (a, b), ps in pairs.items():
        sess_conn.execute(
            "INSERT OR REPLACE INTO session_pairs (word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity) VALUES (?,?,?,?,?,?,?,?)",
            (a, b, ps['cos_a'], ps['cos_v'], ps['signed_a'], ps['signed_v'], ps['count'], ps.get('plasticity', 1.0))
        )
    for (a, b), cnt in chain.items():
        sess_conn.execute("INSERT OR REPLACE INTO session_chain VALUES (?, ?, ?)", (a, b, cnt))
    sess_conn.commit()
    sess_conn.close()

    elapsed = time.time() - t0
    print(f"\nImport complete!")
    print(f"  new sentences: {total_sents} (skipped {skipped_dup} duplicates)")
    print(f"  vocab: {len(aud)} words, pairs: {len(pairs)}, chain: {len(chain)}")
    print(f"  elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    db = DEFAULT_DB
    do_import = False
    args = sys.argv[1:]
    while args:
        if args[0] == "--db" and len(args) > 1:
            db = args[1]
            args = args[2:]
        elif args[0] == "--import":
            do_import = True
            args = args[1:]
        else:
            args = args[1:]

    db = migrate(db)
    if do_import:
        print()
        import_memories(db)
