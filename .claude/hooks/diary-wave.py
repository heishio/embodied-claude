#!/usr/bin/env python
"""diary-wave.py - PostToolUse hook for mcp__memory__diary.

When a diary entry is saved, learn its content into the wave phase graph
(session-wave-v2.db) using the same hybrid learn as session-wave-v2. Stores
the memory_id in lt_sentences for linkage.
"""
import json
import os
import re
import sqlite3
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import scipy.sparse as sp

HOME = os.path.expanduser("~")
SESSION_DB = os.path.join(HOME, ".claude", "session-wave-v2.db")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'wave-phase-core', 'src'))
try:
    from wave_phase_core import (
        audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain,
        tokenize_sent, FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR,
    )
    from wave_phase_core.phase import to_reading_text, _extract_accent, _hl_pattern
except ImportError:
    sys.exit(0)

try:
    import pyopenjtalk
    HAS_G2P = True
except ImportError:
    HAS_G2P = False

# Hybrid learn config (matches session-wave-v2.py)
SEQ_PULL = 0.40
KUR_PULL = 0.10
CARRY_DECAY = 0.3
LEARN_DEGREE_LEAK = 0.005
MORA_ENDS = {'a', 'i', 'u', 'e', 'o', 'A', 'I', 'U', 'E', 'O', 'N', 'cl'}


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
            mean_id REAL, var_id REAL,
            PRIMARY KEY (word_a, word_b));
        CREATE TABLE IF NOT EXISTS lt_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            plasticity REAL DEFAULT 0.5, memory_id TEXT);
        CREATE TABLE IF NOT EXISTS echo_state (
            word TEXT PRIMARY KEY, activation REAL);
    """)


def load_state(conn):
    aud, vis = {}, {}
    for r in conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute("SELECT word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity,energy,mean_f,var_f,mean_id,var_id FROM session_pairs"):
        pairs[(r[0], r[1])] = {
            'cos_a': r[2], 'cos_v': r[3],
            'signed_a': r[4] if r[4] is not None else 0.0,
            'signed_v': r[5] if r[5] is not None else 0.0,
            'count': r[6], 'plasticity': r[7] or 1.0,
            'energy': r[8] or 0.0,
            'mean_f': r[9], 'var_f': r[10],
            'mean_id': r[11], 'var_id': r[12],
        }
    return aud, vis, pairs


def save_state(conn, aud, vis, pairs):
    for w in aud:
        conn.execute("INSERT OR REPLACE INTO session_words VALUES(?,?,?)", (w, aud[w], vis[w]))
    for (a, b), ps in pairs.items():
        conn.execute(
            "INSERT OR REPLACE INTO session_pairs(word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity,energy,mean_f,var_f,mean_id,var_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a, b, ps['cos_a'], ps['cos_v'], ps['signed_a'], ps['signed_v'],
             ps['count'], ps.get('plasticity', 1.0), ps.get('energy', 0.0),
             ps.get('mean_f'), ps.get('var_f'), ps.get('mean_id'), ps.get('var_id')))
    conn.commit()


def _get_phonemes(word):
    if not HAS_G2P:
        return [], []
    try:
        prepared = to_reading_text(word)
        phons = pyopenjtalk.g2p(prepared).split(' ')
        if not phons or phons == ['']:
            return [], []
        n_mora, accent = _extract_accent(prepared)
        return phons, _hl_pattern(n_mora, accent)
    except Exception:
        return [], []


def build_learn_L(pairs, word_idx, W):
    edges = []
    for (a, b), ps in pairs.items():
        if ps['count'] < 1 or a not in word_idx or b not in word_idx:
            continue
        w = max(0.0, (ps['cos_a'] + ps['cos_v']) / 2) + ps['count'] / 200.0
        if w > 0.001:
            edges.append((word_idx[a], word_idx[b], w))
    if not edges:
        for i in range(min(W, 200)):
            for j in range(i + 1, min(W, i + 3)):
                edges.append((i, j, 0.01))
    degree = np.zeros(W)
    for i, j, w in edges:
        degree[i] += w; degree[j] += w
    degree = np.maximum(degree, 0.01)
    di = 1.0 / np.sqrt(degree)
    rs, cs, vs = [], [], []
    for i, j, w in edges:
        nw = w * di[i] * di[j]
        rs += [i, j]; cs += [j, i]; vs += [nw, nw]
    A = sp.csr_matrix((vs, (rs, cs)), shape=(W, W))
    dA = np.asarray(A.sum(axis=1)).flatten()
    return sp.diags(dA) - A, 1.0 / (1 + degree * LEARN_DEGREE_LEAK)


def learn_sentence(toks, aud, vis, pairs, word_idx, L, leak,
                   x_aud, v_aud, x_vis, v_vis):
    """Hybrid sequential+kuramoto learn. Matches session-wave-v2.py.

    Precondition: caller has already registered new words into aud/vis/word_idx
    and expanded x/v vectors, AND built L/leak against this expanded word_idx.
    """
    words = [t['lemma'] for t in toks]
    surfaces = [t['surface'] for t in toks]
    n = len(words)
    if n < 2:
        return x_aud, v_aud, x_vis, v_vis

    for word, surface in zip(words, surfaces):
        wid = word_idx[word]
        phons, hl = _get_phonemes(word)
        if phons:
            mi = 0
            for ph in phons:
                hv = hl[mi] if mi < len(hl) else 'L'
                energy = (sum(ord(c) * 17 for c in ph) + (500 if hv == 'H' else 0)) % 1000 / 1000.0
                x_aud[wid] += energy * 0.3
                for _ in range(2):
                    f = -0.3 * (L @ x_aud); v_aud = v_aud * 0.7 + f
                    x_aud = np.clip(x_aud + v_aud, -1, 3); x_aud *= leak * 0.95
                if ph in MORA_ENDS:
                    mi += 1
        else:
            x_aud[wid] += 0.3
            for _ in range(2):
                f = -0.3 * (L @ x_aud); v_aud = v_aud * 0.7 + f
                x_aud = np.clip(x_aud + v_aud, -1, 3); x_aud *= leak * 0.95

        x_vis[wid] += visual_phase(surface) * 0.3 + 0.3
        for _ in range(2):
            f = -0.3 * (L @ x_vis); v_vis = v_vis * 0.7 + f
            x_vis = np.clip(x_vis + v_vis, -1, 3); x_vis *= leak * 0.95

    new_a = kuramoto_chain(np.array([aud[l] for l in words]))
    new_v = kuramoto_chain(np.array([vis[l] for l in words]))

    for wi, word in enumerate(words):
        wid = word_idx[word]
        aud[word] += ETA * SEQ_PULL * (float(x_aud[wid]) - aud[word])
        vis[word] += ETA * SEQ_PULL * (float(x_vis[wid]) - vis[word])
        aud[word] += ETA * KUR_PULL * (new_a[wi] - aud[word])
        vis[word] += ETA * KUR_PULL * (new_v[wi] - vis[word])

    for i in range(n):
        for j in range(i + 1, min(n, i + PAIR_WINDOW)):
            key = tuple(sorted([words[i], words[j]]))
            da = float(wrap_pi(new_a[j] - new_a[i]))
            dv = float(wrap_pi(new_v[j] - new_v[i]))
            ca = float(np.cos(da)); cv = float(np.cos(dv))
            if key not in pairs:
                pairs[key] = {'cos_a': ca, 'cos_v': cv, 'signed_a': da, 'signed_v': dv, 'count': 0, 'plasticity': 1.0}
            ps = pairs[key]
            ps['cos_a'] = (1 - ETA_PAIR) * ps['cos_a'] + ETA_PAIR * ca
            ps['cos_v'] = (1 - ETA_PAIR) * ps['cos_v'] + ETA_PAIR * cv
            ps['signed_a'] = (1 - ETA_PAIR) * ps['signed_a'] + ETA_PAIR * da
            ps['signed_v'] = (1 - ETA_PAIR) * ps['signed_v'] + ETA_PAIR * dv
            ps['count'] += 1

    return x_aud, v_aud, x_vis, v_vis


def main():
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="ignore")
        data = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    content = tool_input.get("content", "")
    if not content or len(content) < 5:
        sys.exit(0)

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

    conn = sqlite3.connect(SESSION_DB, timeout=3)
    init_db(conn)
    aud, vis, pairs = load_state(conn)

    # Build learning state
    word_idx = {w: i for i, w in enumerate(aud.keys())}
    W = len(word_idx)
    x_aud = np.zeros(W); v_aud = np.zeros(W)
    x_vis = np.zeros(W); v_vis = np.zeros(W)

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
        # Register new words BEFORE build_L so shapes stay aligned
        for t in toks:
            w, s = t['lemma'], t['surface']
            if w not in aud:
                aud[w] = audio_phase_accent(w)
                vis[w] = visual_phase(s)
            if w not in word_idx:
                word_idx[w] = len(word_idx)
        new_W = len(word_idx)
        if new_W > len(x_aud):
            pad = new_W - len(x_aud)
            x_aud = np.concatenate([x_aud, np.zeros(pad)])
            v_aud = np.concatenate([v_aud, np.zeros(pad)])
            x_vis = np.concatenate([x_vis, np.zeros(pad)])
            v_vis = np.concatenate([v_vis, np.zeros(pad)])
        L, leak = build_learn_L(pairs, word_idx, new_W)
        if L is not None:
            x_aud, v_aud, x_vis, v_vis = learn_sentence(
                toks, aud, vis, pairs, word_idx, L, leak,
                x_aud, v_aud, x_vis, v_vis)
            x_aud *= CARRY_DECAY; v_aud *= CARRY_DECAY
            x_vis *= CARRY_DECAY; v_vis *= CARRY_DECAY
        lemmas_str = ",".join(t['lemma'] for t in toks)
        conn.execute(
            "INSERT INTO lt_sentences(text,speaker,timestamp,lemmas,plasticity,memory_id) VALUES(?,?,?,?,?,?)",
            (sent_text[:200], 'diary', time.time(), lemmas_str, 1.0, memory_id)
        )

    save_state(conn, aud, vis, pairs)
    conn.close()


if __name__ == "__main__":
    main()
