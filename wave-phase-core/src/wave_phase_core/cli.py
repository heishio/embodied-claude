# -*- coding: utf-8 -*-
"""wave_recall CLI - two-phase bipartite wave recall.

Phase 1 (impulse scan): fast impulse propagation over the full
  (session + LT) bipartite graph to pick the top-K relevant LT
  sentences for this query.
Phase 2 (oscillatory drive): oscillatory-drive wave on a subgraph
  composed of session sents + selected LT sents + their content
  words. Per-node ω² comes from freq-rank to provide selective
  frequency filtering (HORN-inspired).

The `bipartite_wave` helper remains impulse-only and is used by
session-wave-v2.py's working-memory echo update. The `recall()`
entry point (called via `python -m wave_phase_core.cli`) uses the
two-phase pipeline.

Usage: python -m wave_phase_core.cli [--mode broad|focus|zoom] "query text"
"""
import sys
import os
import math
import sqlite3
import numpy as np
import scipy.sparse as sp

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from .constants import (
    FUNC_WORDS, SPEAKER_TOKENS, ECHO_WEIGHT, ECHO_ENERGY_CAP,
    load_echo, save_echo, load_sent_echo,
)
from .tokenize import tokenize_sent

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, ".claude", "session-wave-v2.db")

FRESH_THRESHOLD_MAX = 0.5
DEGREE_LEAK_RATE = 0.001
SENT_WORD_WEIGHT = 0.3

# Phase 2 oscillatory drive parameters
DRIVE_ITERS = 80
DRIVE_GAIN = 0.08
DRIVE_V_DECAY = 0.95
OMEGA2_LO = 0.015
OMEGA2_HI = 0.060
OMEGA2_SENT = 0.03
K_LT_DEFAULT = 5


# ─────────────────────────────────────────────
# Graph loading
# ─────────────────────────────────────────────
def load_graph():
    """Dict-form loader kept for backwards compatibility.

    Returns (aud, vis, pairs, sents) where pairs is a dict and sents is
    a list of (id, text, lemmas, plasticity, scope) tuples.
    """
    conn = sqlite3.connect(DB, timeout=3)
    aud, vis = {}, {}
    for r in conn.execute(
            "SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]
        vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute(
            "SELECT word_a,word_b,cos_a,cos_v,count,plasticity FROM session_pairs"):
        pairs[(r[0], r[1])] = {
            'cos_a': r[2], 'cos_v': r[3], 'count': r[4],
            'plasticity': r[5] or 1.0,
        }
    sents = []
    for r in conn.execute(
            "SELECT id, text, lemmas, plasticity FROM session_sentences ORDER BY id"):
        sents.append((r[0], r[1], r[2], r[3] or 1.0, 'session'))
    for r in conn.execute(
            "SELECT id, text, lemmas, plasticity FROM lt_sentences ORDER BY id"):
        sents.append((r[0], r[1], r[2], r[3] or 1.0, 'lt'))
    conn.close()
    return aud, vis, pairs, sents


def _load_graph_cached(conn):
    """Numpy-friendly loader used by the two-phase pipeline.

    Returns (aud, vis, all_words, word_idx, P, sent_cache) where
      P: dict of 6 parallel numpy arrays for the pair table
         keys: i, j, cos_a, cos_v, count, plast
      sent_cache: list of (sid, text, content_idx_np, plasticity, scope)
         with content_idx_np already FUNC/SPEAKER filtered and length >= 2.
    """
    aud, vis = {}, {}
    for r in conn.execute(
            "SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]
        vis[r[0]] = r[2]
    all_words = list(aud.keys())
    word_idx = {w: i for i, w in enumerate(all_words)}

    Pi, Pj, Pa, Pv, Pc, Pp = [], [], [], [], [], []
    for r in conn.execute(
            "SELECT word_a,word_b,cos_a,cos_v,count,plasticity FROM session_pairs"):
        a, b, ca, cv, cnt, plast = r
        if a in word_idx and b in word_idx:
            Pi.append(word_idx[a])
            Pj.append(word_idx[b])
            Pa.append(ca)
            Pv.append(cv)
            Pc.append(cnt)
            Pp.append(plast if plast is not None else 1.0)
    P = {
        'i': np.asarray(Pi, dtype=np.int64),
        'j': np.asarray(Pj, dtype=np.int64),
        'cos_a': np.asarray(Pa, dtype=np.float64),
        'cos_v': np.asarray(Pv, dtype=np.float64),
        'count': np.asarray(Pc, dtype=np.int64),
        'plast': np.asarray(Pp, dtype=np.float64),
    }

    sent_cache = []
    for scope, table in (('session', 'session_sentences'),
                         ('lt', 'lt_sentences')):
        for r in conn.execute(
                f"SELECT id, text, lemmas, plasticity FROM {table} ORDER BY id"):
            sid, text, lemmas_str, plast = r
            plast = plast if plast is not None else 1.0
            if not lemmas_str:
                continue
            content_idx = [
                word_idx[l] for l in lemmas_str.split(',')
                if l and l not in FUNC_WORDS and l not in SPEAKER_TOKENS
                and len(l) >= 2 and l in word_idx
            ]
            if len(content_idx) < 2:
                continue
            sent_cache.append((
                sid, text,
                np.asarray(content_idx, dtype=np.int64),
                plast, scope,
            ))
    return aud, vis, all_words, word_idx, P, sent_cache


# ─────────────────────────────────────────────
# Bipartite graph assembly (numpy-vectorized)
# ─────────────────────────────────────────────
def _pairs_dict_to_np(pairs, word_idx):
    """Convert dict-form pairs into numpy arrays (used by the legacy
    `bipartite_wave` entry point from session-wave-v2 hook)."""
    Pi, Pj, Pa, Pv, Pc, Pp = [], [], [], [], [], []
    for (a, b), ps in pairs.items():
        if a not in word_idx or b not in word_idx:
            continue
        Pi.append(word_idx[a])
        Pj.append(word_idx[b])
        Pa.append(ps.get('cos_a', 0.0))
        Pv.append(ps.get('cos_v', 0.0))
        Pc.append(ps.get('count', 0))
        Pp.append(ps.get('plasticity', 1.0) or 1.0)
    return {
        'i': np.asarray(Pi, dtype=np.int64),
        'j': np.asarray(Pj, dtype=np.int64),
        'cos_a': np.asarray(Pa, dtype=np.float64),
        'cos_v': np.asarray(Pv, dtype=np.float64),
        'count': np.asarray(Pc, dtype=np.int64),
        'plast': np.asarray(Pp, dtype=np.float64),
    }


def _tokenize_sent_rows(sents, word_idx):
    """Pre-tokenize legacy sent rows into the v3 sent_cache form."""
    sent_cache = []
    for row in sents:
        if len(row) == 5:
            sid, text, lemmas_str, plast, scope = row
        else:
            sid, text, lemmas_str, plast = row
            scope = 'lt'
        if not lemmas_str:
            continue
        content_idx = [
            word_idx[l] for l in lemmas_str.split(',')
            if l and l not in FUNC_WORDS and l not in SPEAKER_TOKENS
            and len(l) >= 2 and l in word_idx
        ]
        if len(content_idx) < 2:
            continue
        sent_cache.append((
            sid, text,
            np.asarray(content_idx, dtype=np.int64),
            plast or 0.01, scope,
        ))
    return sent_cache


def _build_bipartite_np(W, P, sent_cache):
    """Vectorized edge construction.

    Returns (N, W, S, edges_i, edges_j, edges_w).
    """
    # Word-word edges
    if P['i'].size:
        cos_s = np.maximum((P['cos_a'] + P['cos_v']) * 0.5, 0.0)
        fresh = np.maximum(P['plast'], 0.01)
        thr = (1 - fresh) * FRESH_THRESHOLD_MAX
        mask = (P['count'] >= 1) & (cos_s >= thr) & (cos_s > 0.001)
        ww_i = P['i'][mask]
        ww_j = P['j'][mask]
        ww_w = cos_s[mask]
    else:
        ww_i = np.empty(0, dtype=np.int64)
        ww_j = np.empty(0, dtype=np.int64)
        ww_w = np.empty(0, dtype=np.float64)

    # Sentence-word edges
    S = len(sent_cache)
    N = W + S
    if S > 0:
        lens = np.fromiter((c[2].size for c in sent_cache),
                           dtype=np.int64, count=S)
        total_sw = int(lens.sum())
        sw_i = np.empty(total_sw, dtype=np.int64)
        sw_j = np.empty(total_sw, dtype=np.int64)
        sw_w = np.empty(total_sw, dtype=np.float64)
        offset = 0
        for si, (_, _, content_idx, _, _) in enumerate(sent_cache):
            nc = content_idx.size
            if nc == 0:
                continue
            node = W + si
            w_val = SENT_WORD_WEIGHT / max(math.sqrt(nc), 1.0)
            sw_i[offset:offset + nc] = node
            sw_j[offset:offset + nc] = content_idx
            sw_w[offset:offset + nc] = w_val
            offset += nc
        edges_i = np.concatenate([ww_i, sw_i])
        edges_j = np.concatenate([ww_j, sw_j])
        edges_w = np.concatenate([ww_w, sw_w])
    else:
        edges_i = ww_i
        edges_j = ww_j
        edges_w = ww_w
    return N, W, S, edges_i, edges_j, edges_w


def _assemble_laplacian_np(N, i_arr, j_arr, w_arr):
    if i_arr.size == 0:
        return None, np.full(N, 0.01)
    degree = (np.bincount(i_arr, weights=w_arr, minlength=N)
              + np.bincount(j_arr, weights=w_arr, minlength=N))
    degree = np.maximum(degree, 0.01)
    di = 1.0 / np.sqrt(degree)
    nw = w_arr * di[i_arr] * di[j_arr]
    rs = np.concatenate([i_arr, j_arr])
    cs = np.concatenate([j_arr, i_arr])
    vs = np.concatenate([nw, nw])
    A = sp.csr_matrix((vs, (rs, cs)), shape=(N, N))
    dA = np.asarray(A.sum(axis=1)).flatten()
    L = sp.diags(dA) - A
    return L, degree


# ─────────────────────────────────────────────
# Specificity: context-entropy continuous weight
# ─────────────────────────────────────────────
def _compute_word_specificity(P, W, floor=0.05):
    """Neighbor weight entropy → specificity per word node.

    Same concept as pred_v30's compute_context_entropy / compute_specificity.
    High-entropy (function words: の,は,が) → low specificity → dampened.
    """
    weight_lists = [[] for _ in range(W)]
    n = len(P['i'])
    for k in range(n):
        w = float(P['count'][k]) * max(float(P['plast'][k]), 0.01)
        if w <= 0:
            continue
        i, j = int(P['i'][k]), int(P['j'][k])
        if i < W:
            weight_lists[i].append(w)
        if j < W:
            weight_lists[j].append(w)
    entropy = np.zeros(W)
    for i in range(W):
        ws = weight_lists[i]
        if len(ws) < 2:
            continue
        p = np.array(ws)
        p = p / p.sum()
        p = p[p > 1e-12]
        entropy[i] = -float(np.sum(p * np.log(p)))
    h_max = entropy.max() if entropy.max() > 0 else 1.0
    spec = floor + (1.0 - floor) * (1.0 - entropy / h_max)
    return spec


# ─────────────────────────────────────────────
# Phase 1: impulse propagation (hook-compatible)
# ─────────────────────────────────────────────
def _impulse_propagate(N, W, L, degree, word_idx, valid_q,
                       u_echo_word=None, sent_echo_map=None,
                       specificity=None):
    """Sequential impulse injection. Returns x (final activation vector)."""
    leak = 1.0 / (1 + degree * DEGREE_LEAK_RATE)
    u_echo = np.zeros(N)
    if u_echo_word is not None:
        lim = min(W, len(u_echo_word))
        u_echo[:lim] = u_echo_word[:lim]
    if sent_echo_map is not None and len(sent_echo_map) > 0:
        # sent_echo_map: array parallel to sent_cache, one float per sentence
        u_echo[W:W + len(sent_echo_map)] = sent_echo_map
    echo_l2 = np.linalg.norm(u_echo)
    if echo_l2 > 0.001:
        u_echo = np.maximum(u_echo / echo_l2, 0) * ECHO_WEIGHT
    else:
        u_echo = np.zeros(N)

    # Specificity damping: low-spec words (function words) lose energy each step
    if specificity is not None:
        spec_damp = np.ones(N)
        spec_damp[:W] = specificity
    else:
        spec_damp = None

    x = u_echo * 0.3
    v = np.zeros(N)
    STEPS_PER_INJECT = 4
    for q in valid_q:
        x[word_idx[q]] += 0.3
        for _ in range(STEPS_PER_INJECT):
            f = -0.3 * (L @ x) + 0.05 * (u_echo - x)
            v = v * 0.8 - 0.3 * x * 0.1 + f
            x = np.clip(x + v, -1, 3)
            x *= leak
            if spec_damp is not None:
                x *= spec_damp
    for _ in range(8):
        f = -0.3 * (L @ x) + 0.05 * (u_echo - x)
        v = v * 0.8 - 0.3 * x * 0.1 + f
        x = np.clip(x + v, -1, 3)
        x *= leak
        if spec_damp is not None:
            x *= spec_damp
    return x


def bipartite_wave(query_lemmas, aud, vis, pairs, sents,
                   reach_threshold=0.005, echo_u=None, sent_echo_u=None):
    """Legacy single-phase bipartite impulse wave (hook-compatible).

    This path is used by session-wave-v2.py's working-memory echo update,
    which feeds a narrowed session-only subgraph. Kept as impulse-only so
    its behavior matches prior semantics.
    """
    all_words = list(aud.keys())
    if not all_words:
        return {}, [], []
    W = len(all_words)
    word_idx = {w: i for i, w in enumerate(all_words)}
    P = _pairs_dict_to_np(pairs, word_idx)
    sent_cache = _tokenize_sent_rows(sents, word_idx)

    N, W, S, ei, ej, ew = _build_bipartite_np(W, P, sent_cache)
    if ei.size == 0:
        return {}, [], []
    L, degree = _assemble_laplacian_np(N, ei, ej, ew)

    valid_q = [q for q in query_lemmas if q in word_idx]
    if not valid_q:
        return {}, [], []

    # Map sent echo (keyed by (scope, sid)) to a parallel vector.
    sent_echo_map = None
    if sent_echo_u:
        sent_echo_map = np.zeros(S)
        for si, (sid, _, _, _, scope) in enumerate(sent_cache):
            key = (scope, sid)
            if key in sent_echo_u:
                sent_echo_map[si] = float(sent_echo_u[key])

    spec = _compute_word_specificity(P, W)
    x = _impulse_propagate(N, W, L, degree, word_idx, valid_q,
                           u_echo_word=echo_u,
                           sent_echo_map=sent_echo_map,
                           specificity=spec)

    word_act = {all_words[i]: float(x[i]) for i in range(W) if x[i] > 0.001}

    # Normalized sid range for temporal tagging downstream
    sent_ids = [sid for sid, _, _, _, _ in sent_cache]
    if sent_ids:
        min_id = min(sent_ids)
        id_range = max(max(sent_ids) - min_id, 1)
    else:
        min_id, id_range = 0, 1

    sent_scored = []
    for si, (sid, text, _, _, scope) in enumerate(sent_cache):
        act = float(x[W + si])
        if act > reach_threshold:
            norm_id = (sid - min_id) / id_range
            sent_scored.append((sid, text, act, norm_id, si, scope))
    sent_scored.sort(key=lambda r: -r[2])

    # sent_data preserves the sid/text/content/plast/scope tuple used by
    # recall() for block reconstruction. Content is kept as a string list
    # so downstream consumers can look up word_act directly.
    sent_data = [
        (sid, text,
         [all_words[i] for i in content_idx],
         (sid - min_id) / id_range, plast, scope)
        for (sid, text, content_idx, plast, scope) in sent_cache
    ]
    return word_act, sent_scored, sent_data


# ─────────────────────────────────────────────
# Phase 2 subgraph drive
# ─────────────────────────────────────────────
def _build_subgraph(all_words, word_idx, P, sent_cache, lt_selected):
    """Restrict to session sents + selected LT sents. Remap indices."""
    kept = [
        (sid, text, cidx, plast, scope)
        for (sid, text, cidx, plast, scope) in sent_cache
        if scope == 'session' or (scope == 'lt' and sid in lt_selected)
    ]

    needed = set()
    needed.update(P['i'].tolist())
    needed.update(P['j'].tolist())
    for _, _, cidx, _, _ in kept:
        needed.update(cidx.tolist())

    sorted_idx = sorted(needed)
    sub_words = [all_words[i] for i in sorted_idx]
    sub_idx = {w: i for i, w in enumerate(sub_words)}

    N_orig = len(all_words)
    old_to_new = np.full(N_orig, -1, dtype=np.int64)
    for new_i, old_i in enumerate(sorted_idx):
        old_to_new[old_i] = new_i

    new_pi = old_to_new[P['i']]
    new_pj = old_to_new[P['j']]
    pmask = (new_pi >= 0) & (new_pj >= 0)
    sub_P = {
        'i': new_pi[pmask],
        'j': new_pj[pmask],
        'cos_a': P['cos_a'][pmask],
        'cos_v': P['cos_v'][pmask],
        'count': P['count'][pmask],
        'plast': P['plast'][pmask],
    }

    sub_sc = []
    for sid, text, cidx, plast, scope in kept:
        new_cidx = old_to_new[cidx]
        new_cidx = new_cidx[new_cidx >= 0]
        if new_cidx.size < 2:
            continue
        sub_sc.append((sid, text, new_cidx, plast, scope))
    return sub_words, sub_idx, sub_P, sub_sc


def _subgraph_omega2(sub_P, N_sub):
    """Per-node ω² from freq rank on the subgraph."""
    if N_sub <= 0 or sub_P['i'].size == 0:
        return np.full(max(N_sub, 1), OMEGA2_SENT)
    freq = (np.bincount(sub_P['i'],
                        weights=sub_P['count'].astype(float),
                        minlength=N_sub)
            + np.bincount(sub_P['j'],
                          weights=sub_P['count'].astype(float),
                          minlength=N_sub))
    order = np.argsort(freq)
    rnk = np.empty(N_sub, dtype=np.float64)
    rnk[order] = np.arange(N_sub) / max(N_sub - 1, 1)
    return OMEGA2_LO + (1 - rnk) * (OMEGA2_HI - OMEGA2_LO)


MODE_REACH = {"broad": 0.0005, "focus": 0.0015, "zoom": 0.0008}


def _drive_subgraph(query_lemmas, sub_words, sub_idx, sub_P, sub_sc,
                    omega2_word, reach_threshold=0.0005):
    W = len(sub_words)
    N, W, S, ei, ej, ew = _build_bipartite_np(W, sub_P, sub_sc)
    if ei.size == 0:
        return {}, []
    L, degree = _assemble_laplacian_np(N, ei, ej, ew)

    om2 = np.full(N, OMEGA2_SENT)
    if omega2_word is not None and len(omega2_word) == W:
        om2[:W] = omega2_word
    om2[W:] = OMEGA2_SENT
    omega_nodes = np.sqrt(np.maximum(om2, 1e-6))

    valid_q = [q for q in query_lemmas if q in sub_idx]
    if not valid_q:
        return {}, []
    u_seed = np.zeros(N)
    for q in valid_q:
        u_seed[sub_idx[q]] = 1.0
    q_set = set(valid_q)

    x = np.zeros(N)
    v = np.zeros(N)
    energy = np.zeros(N)
    for step in range(DRIVE_ITERS):
        drive = u_seed * np.cos(omega_nodes * step)
        f = -0.3 * (L @ x) - om2 * x + DRIVE_GAIN * drive
        v = v * DRIVE_V_DECAY + f
        x = np.clip(x + v, -5, 5)
        energy += x ** 2

    # Suppress structural hub bias with sqrt(degree).
    energy = energy / np.sqrt(degree)

    word_act = {}
    for i in range(W):
        w = sub_words[i]
        if w in FUNC_WORDS or w in SPEAKER_TOKENS or w in q_set:
            continue
        if energy[i] > 0:
            word_act[w] = float(energy[i])
    if word_act:
        mx = max(word_act.values())
        if mx > 0:
            word_act = {w: a / mx for w, a in word_act.items() if a / mx > 0.001}

    sent_scored = []
    for si in range(S):
        e = float(energy[W + si])
        if e > 0:
            sid, text, _, _, scope = sub_sc[si]
            sent_scored.append((sid, text, e, scope))
    if sent_scored:
        mx = max(r[2] for r in sent_scored)
        if mx > 0:
            sent_scored = [
                (sid, text, act / mx, scope)
                for (sid, text, act, scope) in sent_scored
                if (act / mx) > reach_threshold
            ]
    sent_scored.sort(key=lambda r: -r[2])
    return word_act, sent_scored


def _two_phase_recall(query_lemmas, all_words, word_idx, P, sent_cache,
                      k_lt=K_LT_DEFAULT, echo_u=None, sent_echo_u=None,
                      reach_threshold=0.0005):
    """Run Phase 1 impulse → pick top-K LT → Phase 2 drive on subgraph."""
    # Phase 1
    W = len(all_words)
    N, W, S, ei, ej, ew = _build_bipartite_np(W, P, sent_cache)
    if ei.size == 0:
        return {}, [], []
    L1, degree1 = _assemble_laplacian_np(N, ei, ej, ew)
    valid_q = [q for q in query_lemmas if q in word_idx]
    if not valid_q:
        return {}, [], []
    sent_echo_map = None
    if sent_echo_u:
        sent_echo_map = np.zeros(S)
        for si, (sid, _, _, _, scope) in enumerate(sent_cache):
            key = (scope, sid)
            if key in sent_echo_u:
                sent_echo_map[si] = float(sent_echo_u[key])
    spec = _compute_word_specificity(P, W)
    x = _impulse_propagate(N, W, L1, degree1, word_idx, valid_q,
                           u_echo_word=echo_u,
                           sent_echo_map=sent_echo_map,
                           specificity=spec)

    lt_hits = []
    for si in range(S):
        act = float(x[W + si])
        if act <= 1e-6:
            continue
        sid, _, _, _, scope = sent_cache[si]
        if scope == 'lt':
            lt_hits.append((sid, act))
    lt_hits.sort(key=lambda r: -r[1])
    lt_selected = {sid for sid, _ in lt_hits[:k_lt]}

    # Phase 2
    sub_words, sub_idx, sub_P, sub_sc = _build_subgraph(
        all_words, word_idx, P, sent_cache, lt_selected)
    sub_omega2 = _subgraph_omega2(sub_P, len(sub_words))
    word_act, sent_scored_raw = _drive_subgraph(
        query_lemmas, sub_words, sub_idx, sub_P, sub_sc, sub_omega2,
        reach_threshold=reach_threshold)

    # Sent metadata for recall()'s block reconstruction. Content is
    # expanded to word strings so downstream lookups (word_act dict) work.
    if sub_sc:
        sids = [row[0] for row in sub_sc]
        min_id = min(sids)
        id_range = max(max(sids) - min_id, 1)
    else:
        min_id, id_range = 0, 1
    sent_data = [
        (sid, text,
         [sub_words[i] for i in cidx],
         (sid - min_id) / id_range, plast, scope)
        for (sid, text, cidx, plast, scope) in sub_sc
    ]
    # Key by (scope, sid): session_sentences.id and lt_sentences.id can
    # collide numerically, so scope is required to disambiguate.
    sid_to_si = {(row[4], row[0]): i for i, row in enumerate(sub_sc)}
    sent_scored = []
    for sid, text, act, scope in sent_scored_raw:
        si = sid_to_si.get((scope, sid), 0)
        norm_id = (sid - min_id) / id_range if sub_sc else 0.0
        sent_scored.append((sid, text, act, norm_id, si, scope))
    return word_act, sent_scored, sent_data


# ─────────────────────────────────────────────
# Top-level recall
# ─────────────────────────────────────────────
def recall(query_text, mode="broad"):
    """mode: broad (wide topic), focus (tight), zoom (temporal anchor)"""
    conn = sqlite3.connect(DB, timeout=3)
    aud, vis, all_words, word_idx, P, sent_cache = _load_graph_cached(conn)

    toks = tokenize_sent(query_text)
    if not toks:
        conn.close()
        return "No tokens from query."
    query_lemmas = [t['lemma'] for t in toks if t['lemma'] not in FUNC_WORDS]
    if not query_lemmas:
        query_lemmas = [t['lemma'] for t in toks][:3]

    echo = load_echo(conn, word_idx)

    # Sent echo from both scopes (keyed by (scope, sid))
    sess_ids = [row[0] for row in sent_cache if row[4] == 'session']
    lt_ids = [row[0] for row in sent_cache if row[4] == 'lt']
    sess_idx_map = {sid: i for i, sid in enumerate(sess_ids)}
    lt_idx_map = {sid: i for i, sid in enumerate(lt_ids)}
    sess_echo_vec = load_sent_echo(conn, sess_idx_map, scope='session')
    lt_echo_vec = load_sent_echo(conn, lt_idx_map, scope='lt')
    sent_echo_dict = {}
    for sid in sess_ids:
        v = sess_echo_vec[sess_idx_map[sid]]
        if abs(v) > 0.001:
            sent_echo_dict[('session', sid)] = float(v)
    for sid in lt_ids:
        v = lt_echo_vec[lt_idx_map[sid]]
        if abs(v) > 0.001:
            sent_echo_dict[('lt', sid)] = float(v)

    reach = MODE_REACH.get(mode, MODE_REACH["broad"])
    word_act, sent_scored, sent_data = _two_phase_recall(
        query_lemmas, all_words, word_idx, P, sent_cache,
        k_lt=K_LT_DEFAULT, echo_u=echo, sent_echo_u=sent_echo_dict,
        reach_threshold=reach,
    )

    if not word_act:
        conn.close()
        return "No activation from query."

    # Update word echo for CoT chaining
    current_act = np.zeros(len(all_words))
    for w, z in word_act.items():
        if w in word_idx:
            current_act[word_idx[w]] = z
    for q in query_lemmas:
        if q in word_idx:
            current_act[word_idx[q]] = 0.5
    echo_norm = np.linalg.norm(echo)
    if echo_norm > 0.01:
        echo = echo * 0.5 + current_act * 0.5
    else:
        echo = current_act.copy()
    echo_l2 = np.linalg.norm(echo)
    if echo_l2 > ECHO_ENERGY_CAP:
        echo *= ECHO_ENERGY_CAP / echo_l2
    save_echo(conn, echo, all_words)
    conn.close()

    # Center words
    center = sorted(
        [(w, z) for w, z in word_act.items()
         if w not in FUNC_WORDS and w not in set(query_lemmas) and z > 0.003],
        key=lambda r: -r[1]
    )[:5]
    center_words = [w for w, _ in center]

    # Block reconstruction from top sentence hits
    NEIGHBOR = 4
    blocks = []
    used_indices = set()
    for sid, text, act, norm_id, si, scope in sent_scored[:3]:
        if si in used_indices:
            continue
        block_indices = []
        for offset in range(-NEIGHBOR, NEIGHBOR + 1):
            ni = si + offset
            if 0 <= ni < len(sent_data) and ni not in used_indices:
                block_indices.append(ni)
                used_indices.add(ni)
        block_lines = []
        for ni in sorted(block_indices):
            _, btxt, bcontent, _, _, _ = sent_data[ni]
            topic_hit = any(word_act.get(l, 0) > 0.002 for l in bcontent)
            if topic_hit or ni == si:
                block_lines.append(btxt)
        if block_lines:
            blocks.append(block_lines)

    lines = [f"[wave-recall] q={query_lemmas[:4]} center={center_words[:4]} sents={len(sent_scored)}"]
    for i, block in enumerate(blocks):
        lines.append(f"  --- block {i+1} ---")
        for bl in block:
            lines.append(f"  {bl}")
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print('Usage: python -m wave_phase_core.cli [--mode broad|focus|zoom] "query text"')
        sys.exit(1)
    args = sys.argv[1:]
    mode = "broad"
    if args[0].startswith("--mode"):
        if "=" in args[0]:
            mode = args[0].split("=")[1]
            args = args[1:]
        elif len(args) > 1:
            mode = args[1]
            args = args[2:]
    query = " ".join(args)
    print(recall(query, mode=mode))


if __name__ == "__main__":
    main()
