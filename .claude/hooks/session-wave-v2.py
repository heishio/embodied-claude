#!/usr/bin/env python
"""session-wave-v2.py - Pool-based wave recall with freshness decay.

Architecture:
  Step 1: Input query → wave_recall on session sentences (freshness-weighted edges)
          → collect activated words → build session pool (~30-50 sentences)
  Step 2: Pool keywords → search LT memory (recall_index) → expand pool
  Step 3: Final wave_recall on pool → top 3 sentences to prompt

  Pool management:
    - Local freshness: newer sentences have stronger edges
    - Abruptness detection: if pool activation is low → rebuild pool
    - Natural decay: old pool entries drop off over time

  Also outputs [memory-hint] (replaces recall-lite).
"""
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
import math

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import scipy.sparse as sp

# ── Paths ──
HOME = os.path.expanduser("~")
SESSION_DB = os.path.join(HOME, ".claude", "session-wave-v2.db")
MEMORY_DB = os.path.join(HOME, ".claude", "memories", "memory.db")
POOL_FILE = os.path.join(HOME, ".claude", "wave-pool.json")

# ── wave_phase_core imports ──
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'wave-phase-core', 'src'))
try:
    from wave_phase_core import (
        audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain,
        tokenize_sent, FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR,
        plasticity_log_scale, ECHO_WEIGHT, ECHO_ENERGY_CAP,
        load_echo, save_echo, load_sent_echo, save_sent_echo,
    )
    from wave_phase_core.phase import to_reading_text, _extract_accent, _hl_pattern
    from wave_phase_core.cli import bipartite_wave
except ImportError:
    sys.exit(0)

try:
    import pyopenjtalk
    HAS_G2P = True
except ImportError:
    HAS_G2P = False

# ── Constants ──
POOL_MAX = 80
POOL_SESSION_MAX = 40
POOL_LT_MAX = 40
FRESHNESS_DECAY = 0.15  # exp(-decay * age): age=10 → 0.22, age=20 → 0.05
ABRUPT_THRESHOLD = 0.005  # pool activation below this → rebuild
FRESH_THRESHOLD_MAX = 0.5  # old memories need cos > this to respond
DEGREE_LEAK_RATE = 0.001   # high-degree nodes saturate faster
TIMEOUT_SEC = 13
ECHO_TOPIC_THRESHOLD = 0.1         # cos(echo, current) below this → topic switch
ECHO_BLEND_PREV = 0.7              # normal: prev-echo decay
ECHO_BLEND_CURRENT = 0.3           # normal: current activation injection
ECHO_BLEND_PREV_SWITCH = 0.3       # on topic switch: shrink past
ECHO_BLEND_CURRENT_SWITCH = 0.7    # on topic switch: emphasize current
# Hybrid learn (phase-precession + gamma-sync analogy)
SEQ_PULL = 0.40            # sequential x_aud → aud pull weight
KUR_PULL = 0.10            # kuramoto output → aud pull weight
CARRY_DECAY = 0.3          # inter-sentence carry-wave decay
LEARN_DEGREE_LEAK = 0.005  # build_L leak for learning dynamics (stronger than recall)
MORA_ENDS = {'a', 'i', 'u', 'e', 'o', 'A', 'I', 'U', 'E', 'O', 'N', 'cl'}

# ── Speaker detection ──
GO2RTC_SNAPSHOT = "http://localhost:1984/api/frame.jpeg?src=tapo_cam"
VISION_SERVER = "http://127.0.0.1:8100"


def get_speaker_tag():
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen(f"{VISION_SERVER}/status", timeout=1)
    except (urllib.error.URLError, OSError):
        return None
    try:
        resp = urllib.request.urlopen(GO2RTC_SNAPSHOT, timeout=2)
        jpeg_data = resp.read()
    except (urllib.error.URLError, OSError):
        return None
    if len(jpeg_data) < 1000:
        return None
    snap_dir = os.path.join(tempfile.gettempdir(), "session-wave-v2")
    os.makedirs(snap_dir, exist_ok=True)
    snap_path = os.path.join(snap_dir, "snap.jpg").replace("\\", "/")
    with open(snap_path, "wb") as f:
        f.write(jpeg_data)
    try:
        payload = json.dumps({"path": snap_path}).encode("utf-8")
        req = urllib.request.Request(
            f"{VISION_SERVER}/detect", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=3)
        result = json.loads(resp.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None
    persons = result.get("persons")
    if persons:
        for p in persons:
            m = p.get("match")
            if m and m.get("delta_sim", 0) > 0.5:
                return m["tag"]
    match = result.get("match")
    if match and match.get("delta_sim", 0) > 0.5:
        return match["tag"]
    return None


# ── DB ──
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
        CREATE TABLE IF NOT EXISTS session_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            plasticity REAL DEFAULT 1.0);
        CREATE TABLE IF NOT EXISTS lt_sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT, speaker TEXT, timestamp REAL, lemmas TEXT,
            plasticity REAL DEFAULT 0.5);
        CREATE TABLE IF NOT EXISTS echo_state (
            word TEXT PRIMARY KEY, activation REAL);
    """)
    # Add energy column if missing (migration)
    try:
        conn.execute("SELECT energy FROM session_pairs LIMIT 1")
    except Exception:
        try:
            conn.execute("ALTER TABLE session_pairs ADD COLUMN energy REAL DEFAULT 0.0")
        except Exception:
            pass
    # Add temporal sketch columns if missing (migration)
    for col in ("mean_f", "var_f", "mean_id", "var_id"):
        try:
            conn.execute(f"SELECT {col} FROM session_pairs LIMIT 1")
        except Exception:
            try:
                conn.execute(f"ALTER TABLE session_pairs ADD COLUMN {col} REAL")
            except Exception:
                pass


def load_state(conn):
    aud, vis = {}, {}
    for r in conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute("SELECT word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity,energy,mean_f,var_f,mean_id,var_id FROM session_pairs"):
        pairs[(r[0], r[1])] = {
            'cos_a': r[2] if r[2] is not None else 0.0,
            'cos_v': r[3] if r[3] is not None else 0.0,
            'signed_a': r[4] if r[4] is not None else 0.0,
            'signed_v': r[5] if r[5] is not None else 0.0,
            'count': r[6] or 0,
            'plasticity': r[7] or 1.0,
            'energy': r[8] or 0.0,
            'mean_f': r[9], 'var_f': r[10],
            'mean_id': r[11], 'var_id': r[12],
        }
    return aud, vis, pairs


def save_state(conn, aud, vis, pairs):
    for w in aud:
        conn.execute("INSERT OR REPLACE INTO session_words VALUES(?,?,?)", (w, aud[w], vis[w]))
    for (a, b), ps in pairs.items():
        conn.execute("INSERT OR REPLACE INTO session_pairs(word_a,word_b,cos_a,cos_v,signed_a,signed_v,count,plasticity,energy,mean_f,var_f,mean_id,var_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (a, b, ps['cos_a'], ps['cos_v'], ps['signed_a'], ps['signed_v'], ps['count'], ps.get('plasticity', 1.0), ps.get('energy', 0.0), ps.get('mean_f'), ps.get('var_f'), ps.get('mean_id'), ps.get('var_id')))
    conn.commit()


# ── Learning (hybrid: phase-precession + gamma-sync) ──
# Sequential injection (theta-precession analogue) + carry-wave + kuramoto
# pair sync (gamma-binding analogue). See wave_phase_changelog for the
# ablation that selected seq0.40 + kur0.10 + pair=kuramoto.
def _get_phonemes(word):
    """Phoneme list + HL pattern for a word. Returns ([], []) on failure."""
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
    """Build sparse Laplacian for learning dynamics from current pairs."""
    edges = []
    for (a, b), ps in pairs.items():
        if ps['count'] < 1 or a not in word_idx or b not in word_idx:
            continue
        w = max(0.0, (ps['cos_a'] + ps['cos_v']) / 2) + ps['count'] / 200.0
        if w > 0.001:
            edges.append((word_idx[a], word_idx[b], w))
    if not edges:
        # Bootstrap: weak seed edges so first pass can start
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
    """Hybrid sequential+kuramoto learn. Returns updated carry state (x/v).

    Precondition: caller has already registered new words into aud/vis/word_idx
    and expanded x/v vectors to match, AND built L/leak against this expanded
    word_idx. Failing that, L@x will shape-mismatch.
    """
    words = [t['lemma'] for t in toks]
    surfaces = [t['surface'] for t in toks]
    n = len(words)
    if n < 2:
        return x_aud, v_aud, x_vis, v_vis

    # Sequential injection (phoneme-by-phoneme audio, one-shot visual)
    for word, surface in zip(words, surfaces):
        if word not in word_idx:
            continue
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

    # Kuramoto output (used for pair cos and partial aud/vis drift)
    new_a = kuramoto_chain(np.array([aud[l] for l in words]))
    new_v = kuramoto_chain(np.array([vis[l] for l in words]))

    # Blended long-term phase update: seq pull (ctx) + kura pull (BCM-like)
    for wi, word in enumerate(words):
        wid = word_idx[word]
        aud[word] += ETA * SEQ_PULL * (float(x_aud[wid]) - aud[word])
        vis[word] += ETA * SEQ_PULL * (float(x_vis[wid]) - vis[word])
        aud[word] += ETA * KUR_PULL * (new_a[wi] - aud[word])
        vis[word] += ETA * KUR_PULL * (new_v[wi] - vis[word])

    # Pair cos/signed from kuramoto output (gamma-sync binding)
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


# ── Wave recall (sparse, sequential query injection) ──
def wave_recall_sparse(query_lemmas, aud, vis, pairs, freshness_weight=True, top_k=30, accumulate_energy=False, temporal_anchor=None, temporal_mode='plasticity', echo_u=None):
    all_words = list(aud.keys())
    if not all_words: return []
    N = len(all_words)
    idx = {w: i for i, w in enumerate(all_words)}
    edges = []
    edge_pair_keys = []
    for (a, b), ps in pairs.items():
        if ps['count'] < 1 or a not in idx or b not in idx: continue
        cos_strength = max(0.0, (ps['cos_a'] + ps['cos_v']) / 2)
        w = cos_strength
        if freshness_weight:
            fresh = max(ps.get('plasticity', 1.0), 0.01)
            threshold = (1 - fresh) * FRESH_THRESHOLD_MAX
            if cos_strength < threshold:
                continue
        # Temporal edge modulation via sketch
        if temporal_anchor is not None:
            if temporal_mode == 'id' and ps.get('mean_id') is not None:
                spread = max(math.sqrt(ps['var_id']) if ps.get('var_id') else 0.03, 0.03)
                tw = math.exp(-((ps['mean_id'] - temporal_anchor) / spread) ** 2)
                w *= tw
            elif temporal_mode == 'plasticity' and ps.get('mean_f') is not None:
                spread = max(math.sqrt(ps['var_f']) if ps.get('var_f') else 0.03, 0.03)
                tw = math.exp(-((ps['mean_f'] - temporal_anchor) / spread) ** 2)
                w *= tw
        if w > 0.001:
            edges.append((idx[a], idx[b], w))
            edge_pair_keys.append((a, b))
    if not edges: return []
    degree = np.zeros(N)
    for i, j, w in edges: degree[i] += w; degree[j] += w
    degree = np.maximum(degree, 0.01)
    di = 1.0 / np.sqrt(degree)
    rs, cs, vs = [], [], []
    for i, j, w in edges:
        nw = w * di[i] * di[j]
        rs += [i, j]; cs += [j, i]; vs += [nw, nw]
    A = sp.csr_matrix((vs, (rs, cs)), shape=(N, N))
    dA = np.asarray(A.sum(axis=1)).flatten()
    L = sp.diags(dA) - A
    # Sequential query injection: seed query words one-by-one so order affects
    # the interference pattern (phase-precession analogue on the recall side).
    valid_q = [q for q in query_lemmas if q in idx]
    if not valid_q:
        return []
    # Echo (context persistence) is added as a background recharge signal.
    u_echo = np.zeros(N)
    if echo_u is not None and len(echo_u) == N:
        echo_l2 = np.linalg.norm(echo_u)
        if echo_l2 > 0.001:
            u_echo = np.maximum(echo_u / echo_l2, 0) * ECHO_WEIGHT
    # Vectorized edge arrays for energy accumulation
    ei_i = np.array([e[0] for e in edges])
    ei_j = np.array([e[1] for e in edges])
    ei_w = np.array([e[2] for e in edges])
    edge_energy = np.zeros(len(edges))
    # Degree saturation: high-degree nodes leak activation each step
    leak = 1.0 / (1 + degree * DEGREE_LEAK_RATE)
    x = u_echo * 0.3; v = np.zeros(N)
    STEPS_PER_INJECT = 4
    for q in valid_q:
        x[idx[q]] += 0.3
        for _ in range(STEPS_PER_INJECT):
            f = -0.3 * (L @ x) + 0.05 * (u_echo - x)
            v = v * 0.8 - 0.3 * x * 0.1 + f
            x = np.clip(x + v, -1, 3)
            x *= leak
            edge_energy += np.abs(x[ei_i] * x[ei_j]) * ei_w
    # Final relaxation
    for step in range(8):
        f = -0.3 * (L @ x) + 0.05 * (u_echo - x)
        v = v * 0.8 - 0.3 * x * 0.1 + f
        x = np.clip(x + v, -1, 3)
        x *= leak
        edge_energy += np.abs(x[ei_i] * x[ei_j]) * ei_w
    # Accumulate energy into pairs (side-effect for consolidate LTP)
    if accumulate_energy:
        for ei, key in enumerate(edge_pair_keys):
            if key in pairs:
                pairs[key]['energy'] = pairs[key].get('energy', 0.0) + float(edge_energy[ei])
    inv = {v: k for k, v in idx.items()}
    act = [(inv[i], float(x[i])) for i in range(N)
           if inv[i] not in query_lemmas and inv[i] not in FUNC_WORDS]
    act.sort(key=lambda r: -r[1])
    return act[:top_k]


# ── Pool management ──
def load_pool():
    if os.path.exists(POOL_FILE):
        try:
            with open(POOL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception: pass
    return {"session_sids": [], "lt_sids": [], "keywords": [], "last_update": 0}


def save_pool(pool):
    with open(POOL_FILE, 'w', encoding='utf-8') as f:
        json.dump(pool, f, ensure_ascii=False)


def build_pool(query_lemmas, conn, aud, vis, pairs):
    """Step 1+2: Build pool from session + LT sentences."""
    pool = {"session_sids": [], "lt_sids": [], "keywords": list(query_lemmas), "last_update": time.time()}

    # Step 1: Wave recall on session sentences
    activated = wave_recall_sparse(query_lemmas, aud, vis, pairs, freshness_weight=True, top_k=30)
    activated_words = [w for w, z in activated if z > 0.005]

    # Score session sentences
    act_map = {w: z for w, z in activated}
    sess_rows = conn.execute("SELECT id, text, speaker, lemmas, plasticity FROM session_sentences ORDER BY id DESC LIMIT 200").fetchall()
    n_sess = len(sess_rows)
    scored = []
    for i, (sid, text, spk, lemmas_str, fresh) in enumerate(sess_rows):
        if not lemmas_str: continue
        lemmas = lemmas_str.split(",")
        content = [l for l in lemmas if l not in FUNC_WORDS]
        if not content: continue
        # Local freshness: position-based decay (newest=index 0)
        local_f = math.exp(-FRESHNESS_DECAY * i)
        score = sum(max(0, act_map.get(l, 0)) for l in content) / len(content)
        score *= local_f
        if fresh is not None: score *= max(fresh, 0.01)
        scored.append((sid, text, spk, score))
    scored.sort(key=lambda r: -r[3])
    pool["session_sids"] = [s[0] for s in scored[:POOL_SESSION_MAX]]

    # Step 2: LT search via recall_index
    all_keywords = list(set(query_lemmas + activated_words[:10]))
    pool["keywords"] = all_keywords[:15]
    if os.path.exists(MEMORY_DB):
        try:
            mem = sqlite3.connect(MEMORY_DB, timeout=2)
            has_idx = False
            try:
                mem.execute("SELECT 1 FROM recall_index LIMIT 1")
                has_idx = True
            except Exception: pass
            if has_idx:
                lt_scores = {}
                lt_previews = {}
                for kw in all_keywords[:8]:
                    rows = mem.execute(
                        "SELECT target_type, target_id, similarity, content_preview "
                        "FROM recall_index WHERE word=? ORDER BY similarity DESC LIMIT 5", (kw,)
                    ).fetchall()
                    for tt, tid, sim, prev in rows:
                        key = (tt, tid)
                        lt_scores[key] = lt_scores.get(key, 0) + sim
                        if prev and key not in lt_previews:
                            lt_previews[key] = prev
                ranked_lt = sorted(lt_scores.items(), key=lambda r: -r[1])[:POOL_LT_MAX]
                pool["lt_sids"] = [k for k, _ in ranked_lt]
                # Also build memory-hint output
                if ranked_lt:
                    total = len(lt_scores)
                    samples = [lt_previews.get(k, "")[:30] for k, _ in ranked_lt[:4] if lt_previews.get(k)]
                    sample_str = " / ".join(samples)
                    words_str = ",".join(all_keywords[:8])
                    pool["memory_hint"] = f"[memory-hint] [{words_str}] ({total}件, 例: {sample_str})" if sample_str else f"[memory-hint] [{words_str}] ({total}件)"
            mem.close()
        except Exception: pass
    return pool


def score_pool_sentences(query_lemmas, pool, conn, aud, vis, pairs, accumulate_energy=False, echo_u=None):
    """Step 3: Semantic wave → temporal zoom → re-seed."""
    # Collect pool sentences with freshness (session + LT)
    pool_sents = []
    if pool["session_sids"]:
        placeholders = ",".join("?" * len(pool["session_sids"]))
        rows = conn.execute(
            f"SELECT id, text, speaker, lemmas, plasticity FROM session_sentences WHERE id IN ({placeholders})",
            pool["session_sids"]).fetchall()
        pool_sents.extend([('s', *r) for r in rows])  # tag source
    # Include all LT sentences (freshness decay is the natural filter)
    lt_rows = conn.execute(
        "SELECT id, text, speaker, lemmas, plasticity FROM lt_sentences"
    ).fetchall()
    pool_sents.extend([('lt', *r) for r in lt_rows])
    if not pool_sents:
        return [], 0.0

    # Parse all sentence data once
    sent_data = []  # (src_sid, text, spk, content_lemmas, fresh)
    for src, sid, text, spk, lemmas_str, fresh in pool_sents:
        if not lemmas_str: continue
        lemmas = lemmas_str.split(",")
        content = [l for l in lemmas if l not in FUNC_WORDS]
        if len(content) < 2: continue
        f = fresh if fresh is not None else 1.0
        sent_data.append((f"{src}:{sid}", text, spk, content, f))
    if not sent_data:
        return [], 0.0

    def _score_by_activation(act_map):
        scored = []
        for src_sid, text, spk, content, fresh in sent_data:
            reached = [max(0, act_map.get(l, 0)) for l in content]
            reach_above = [z for z in reached if z > 0.005]
            if not reach_above: continue
            reach_ratio = len(reach_above) / len(content)
            mean_z = sum(reached) / len(content)
            score = mean_z * reach_ratio
            scored.append((src_sid, text, spk, score, fresh, content))
        scored.sort(key=lambda r: -r[3])
        return scored

    # Pass 1: Semantic wave recall (energy only on this pass)
    # Preserve order from query_lemmas (sequential injection needs it)
    seen = set(); all_query = []
    for q in list(query_lemmas) + list(pool.get("keywords", []))[:5]:
        if q not in seen:
            seen.add(q); all_query.append(q)
    activated = wave_recall_sparse(all_query[:8], aud, vis, pairs,
                                   freshness_weight=True, top_k=50,
                                   accumulate_energy=accumulate_energy,
                                   echo_u=echo_u)
    if not activated:
        return [], 0.0
    scored = _score_by_activation({w: z for w, z in activated})
    if not scored:
        return [], 0.0

    # Detect anchor: strongest hit that's been consolidated at least once
    # Convert to log scale to match sketch's temporal coordinate
    anchor_fresh = None
    for _, _, _, sc, fresh, _ in scored:
        if fresh < 0.9 and sc > 0:
            anchor_fresh = plasticity_log_scale(fresh)
            break

    if anchor_fresh is not None:
        # B-plan: temporal edge modulation via sketch (re-run wave with anchor)
        activated2 = wave_recall_sparse(all_query[:8], aud, vis, pairs,
                                        freshness_weight=True, top_k=50,
                                        temporal_anchor=anchor_fresh,
                                        echo_u=echo_u)
        if activated2:
            scored2 = _score_by_activation({w: z for w, z in activated2})
            if scored2:
                scored = scored2
        final = [(src_sid, text, spk, sc) for src_sid, text, spk, sc, _, _ in scored]
    else:
        final = [(src_sid, text, spk, sc) for src_sid, text, spk, sc, _, _ in scored]

    pool_activation = np.mean([s[3] for s in final[:5]]) if final else 0.0
    return final[:3], pool_activation


# ── Main ──
def main():
    t0 = time.time()
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="ignore")
        data = json.loads(raw) if raw else {}
    except Exception:
        sys.exit(0)
    prompt = data.get("prompt", "")
    if not prompt or len(prompt) < 2: sys.exit(0)
    if os.environ.get("CLAUDE_AUTONOMOUS"): sys.exit(0)
    prompt = re.sub(r"<system-reminder>.*?</system-reminder>", "", prompt, flags=re.DOTALL)
    prompt = prompt.encode("utf-8", errors="ignore").decode("utf-8").strip()
    if not prompt: sys.exit(0)

    speaker = get_speaker_tag() or "unknown"
    sents = [s.strip() for s in re.split(r'[。！？\n\.]+', prompt) if len(s.strip()) > 1]
    if not sents: sys.exit(0)

    conn = sqlite3.connect(SESSION_DB, timeout=3)
    init_db(conn)
    aud, vis, pairs = load_state(conn)

    # Build word_idx for sequential learning dynamics
    word_idx = {w: i for i, w in enumerate(aud.keys())}
    W = len(word_idx)
    x_aud = np.zeros(W); v_aud = np.zeros(W)
    x_vis = np.zeros(W); v_vis = np.zeros(W)

    # Learn input (hybrid: sequential + carry-wave + kuramoto pair sync)
    all_query_lemmas = []
    current_sids = []
    for sent_text in sents:
        toks = tokenize_sent(sent_text)
        if not toks: continue
        if speaker != "unknown":
            sp_tok = {'lemma': speaker, 'surface': speaker, 'reading': speaker, 'pos': '名詞'}
            if speaker not in aud:
                aud[speaker] = audio_phase_accent(speaker)
                vis[speaker] = visual_phase(speaker)
            toks = [sp_tok] + toks
        # Register new words BEFORE build_L so L/leak/x_v shapes stay aligned
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
            # Inter-sentence carry decay
            x_aud *= CARRY_DECAY; v_aud *= CARRY_DECAY
            x_vis *= CARRY_DECAY; v_vis *= CARRY_DECAY
        for t in toks:
            if t.get('pos') == '名詞' and t['lemma'] not in FUNC_WORDS:
                if len(t['lemma']) >= 1 and t['lemma'] != speaker:
                    all_query_lemmas.append(t['lemma'])
        lemmas_str = ",".join(t['lemma'] for t in toks)
        conn.execute("INSERT INTO session_sentences(text,speaker,timestamp,lemmas,plasticity) VALUES(?,?,?,?,1.0)",
                     (sent_text, speaker, time.time(), lemmas_str))
        current_sids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    save_state(conn, aud, vis, pairs)

    if not all_query_lemmas:
        conn.close()
        sys.exit(0)
    query = list(dict.fromkeys(all_query_lemmas))[:6]
    n_sess = conn.execute("SELECT COUNT(*) FROM session_sentences").fetchone()[0]
    if n_sess < 3:
        conn.close()
        sys.exit(0)
    if time.time() - t0 > TIMEOUT_SEC - 3:
        conn.close()
        sys.exit(0)

    # Load echo (context persistence from previous turns)
    all_words = list(aud.keys())
    word_idx = {w: i for i, w in enumerate(all_words)}
    echo = load_echo(conn, word_idx)

    # Pool management
    pool = load_pool()
    need_rebuild = False
    if not pool["session_sids"]:
        need_rebuild = True
    elif time.time() - pool.get("last_update", 0) > 300:  # stale after 5 min
        need_rebuild = True

    if not need_rebuild:
        # Check abruptness: quick activation test on current pool
        top, activation = score_pool_sentences(query, pool, conn, aud, vis, pairs, echo_u=echo)
        if activation < ABRUPT_THRESHOLD:
            need_rebuild = True

    if need_rebuild and time.time() - t0 < TIMEOUT_SEC - 3:
        pool = build_pool(query, conn, aud, vis, pairs)
        save_pool(pool)

    # Final recall from pool (energy accumulation only here)
    if time.time() - t0 < TIMEOUT_SEC - 2:
        top, activation = score_pool_sentences(query, pool, conn, aud, vis, pairs, accumulate_energy=True, echo_u=echo)
        save_state(conn, aud, vis, pairs)  # persist accumulated energy
        # Exclude current message
        exclude = set(f"s:{sid}" for sid in current_sids)
        top = [(s, t, sp, sc) for s, t, sp, sc in top if s not in exclude]

        # Recall output (QUIET mode - uncomment to enable prompt injection)
        # Enables associative recall fragments in Claude's context.
        # if top:
        #     lines = [f"  [{sp}] {t[:50]} ({sc:.1f})" for _, t, sp, sc in top[:3]]
        #     print(f"[session-wave] q={query[:3]}\n" + "\n".join(lines))

    # Update echo: working-memory bipartite wave on session_sentences only.
    # Query source = シオの新入力 + クオの直前応答 (cached by stop-log.py).
    # Both word_act and sent_act are persisted as the new echo.
    if time.time() - t0 < TIMEOUT_SEC - 1:
        claude_last = ""
        cache_path = os.path.join(HOME, ".claude", "claude-last-message.txt")
        try:
            if os.path.exists(cache_path):
                with open(cache_path, encoding='utf-8') as f:
                    claude_last = f.read()[:2000]
        except Exception:
            pass

        claude_say = ""
        say_cache = os.path.join(HOME, ".claude", "claude-last-say.txt")
        try:
            if os.path.exists(say_cache):
                with open(say_cache, encoding='utf-8') as f:
                    claude_say = f.read()[:1000]
        except Exception:
            pass

        combined_text = (prompt or "") + " " + claude_last + " " + claude_say
        combined_toks = tokenize_sent(combined_text)
        combined_lemmas = [t['lemma'] for t in combined_toks
                           if t['lemma'] not in FUNC_WORDS
                           and len(t['lemma']) >= 2
                           and t['lemma'] in word_idx]
        combined_lemmas = list(dict.fromkeys(combined_lemmas))[:12]

        # session_sentences only (no LT) — short-term working memory.
        # Attach scope='session' so bipartite_wave distinguishes the
        # sentence namespace from lt_sentences when sent_echo is used.
        session_sents_raw = conn.execute(
            "SELECT id, text, lemmas, plasticity FROM session_sentences "
            "WHERE plasticity > 0.01 ORDER BY id DESC LIMIT 200").fetchall()
        session_sents = [(r[0], r[1], r[2], r[3] or 1.0, 'session')
                         for r in session_sents_raw]
        session_sids = [s[0] for s in session_sents]
        sent_idx = {sid: i for i, sid in enumerate(session_sids)}

        # Narrow aud/pairs to the lemma subset appearing in this pool —
        # prevents LT-only vocabulary from dragging the session wave.
        pool_lemmas = set(combined_lemmas)
        for _, _, lemmas_str, _, _ in session_sents:
            if not lemmas_str:
                continue
            for l in lemmas_str.split(','):
                if l and l in aud:
                    pool_lemmas.add(l)
        aud_sub = {w: aud[w] for w in pool_lemmas if w in aud}
        vis_sub = {w: vis[w] for w in pool_lemmas if w in vis}
        pairs_sub = {(a, b): v for (a, b), v in pairs.items()
                     if a in pool_lemmas and b in pool_lemmas}

        # Previous sentence echo (working memory persistence, scope='session')
        prev_sent_echo_vec = load_sent_echo(conn, sent_idx, scope='session')
        prev_sent_echo = {('session', sid): float(prev_sent_echo_vec[sent_idx[sid]])
                          for sid in session_sids
                          if abs(prev_sent_echo_vec[sent_idx[sid]]) > 0.001}

        if combined_lemmas and session_sents:
            try:
                word_act, sent_scored, _ = bipartite_wave(
                    combined_lemmas, aud_sub, vis_sub, pairs_sub, session_sents,
                    reach_threshold=0.005,
                    echo_u=None, sent_echo_u=prev_sent_echo)

                # Build new word activation against the *full* word space
                # (so the saved word echo stays consistent with all_words).
                current_act = np.zeros(len(all_words))
                for w, z in word_act.items():
                    if w in word_idx:
                        current_act[word_idx[w]] = z
                for q in combined_lemmas:
                    if q in word_idx:
                        current_act[word_idx[q]] = 0.5

                # Topic switch detection: when triggered, shift the blend
                # ratio toward the current activation so new topics surface
                # faster (without hard-resetting the echo).
                topic_switch_detected = False
                echo_norm = np.linalg.norm(echo)
                current_norm = np.linalg.norm(current_act)
                if echo_norm > 0.01 and current_norm > 0.01:
                    cos_sim_topic = float(np.dot(echo, current_act)
                                           / (echo_norm * current_norm))
                    if cos_sim_topic < ECHO_TOPIC_THRESHOLD:
                        topic_switch_detected = True

                if topic_switch_detected:
                    blend_prev = ECHO_BLEND_PREV_SWITCH
                    blend_curr = ECHO_BLEND_CURRENT_SWITCH
                else:
                    blend_prev = ECHO_BLEND_PREV
                    blend_curr = ECHO_BLEND_CURRENT

                # Always-blend (wave superposition with adaptive ratio).
                echo = echo * blend_prev + current_act * blend_curr

                new_sent_echo_vec = prev_sent_echo_vec * blend_prev
                for row in sent_scored[:20]:
                    # sent_scored rows are (sid, text, act, norm_id, si, scope)
                    sid = row[0]
                    act = row[2]
                    if sid in sent_idx:
                        new_sent_echo_vec[sent_idx[sid]] += float(act) * blend_curr

                # Cap energies
                echo_l2 = np.linalg.norm(echo)
                if echo_l2 > ECHO_ENERGY_CAP:
                    echo *= ECHO_ENERGY_CAP / echo_l2
                sent_echo_l2 = np.linalg.norm(new_sent_echo_vec)
                if sent_echo_l2 > ECHO_ENERGY_CAP:
                    new_sent_echo_vec *= ECHO_ENERGY_CAP / sent_echo_l2

                save_echo(conn, echo, all_words)
                save_sent_echo(conn, new_sent_echo_vec, session_sids,
                               scope='session')
            except Exception as e:
                import traceback
                sys.stderr.write(
                    f"[session-wave-v2] working-memory wave failed: {e}\n"
                    f"{traceback.format_exc()}\n")

    # Memory hint output (uncomment to enable)
    # if pool.get("memory_hint"):
    #     print(pool["memory_hint"])

    conn.close()


if __name__ == "__main__":
    main()
