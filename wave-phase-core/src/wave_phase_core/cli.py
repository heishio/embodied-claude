# -*- coding: utf-8 -*-
"""wave_recall CLI - Bipartite (word+sentence) wave recall.

Single wave propagation on a graph containing both word and sentence nodes.
Word-word edges from pair cos, word-sentence edges from membership. Query
lemmas are injected sequentially so the interference pattern carries order
information (phase-precession analogue on the recall side).

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

from .constants import FUNC_WORDS, PAIR_WINDOW, ECHO_WEIGHT, ECHO_ENERGY_CAP, load_echo, save_echo
from .tokenize import tokenize_sent

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, ".claude", "session-wave-v2.db")
FRESH_THRESHOLD_MAX = 0.5
DEGREE_LEAK_RATE = 0.001
SENT_WORD_WEIGHT = 0.3


def load_graph():
    conn = sqlite3.connect(DB, timeout=3)
    aud, vis = {}, {}
    for r in conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute("SELECT word_a,word_b,cos_a,cos_v,count,plasticity FROM session_pairs"):
        pairs[(r[0], r[1])] = {'cos_a': r[2], 'cos_v': r[3], 'count': r[4], 'plasticity': r[5] or 1.0}
    sents = conn.execute(
        "SELECT id, text, lemmas, plasticity FROM lt_sentences ORDER BY id"
    ).fetchall()
    conn.close()
    return aud, vis, pairs, sents


def bipartite_wave(query_lemmas, aud, vis, pairs, sents,
                   reach_threshold=0.005, echo_u=None):
    """Single wave on word+sentence bipartite graph."""
    # Word nodes: 0..W-1
    all_words = list(aud.keys())
    W = len(all_words)
    word_idx = {w: i for i, w in enumerate(all_words)}

    # Parse sentences → sentence nodes: W..W+S-1
    sent_data = []
    ids = [s[0] for s in sents]
    if not ids:
        return [], [], []
    min_id, max_id = min(ids), max(ids)
    id_range = max(max_id - min_id, 1)
    for sid, text, lemmas_str, plast in sents:
        if not lemmas_str:
            continue
        content = [l for l in lemmas_str.split(",")
                   if l not in FUNC_WORDS and len(l) >= 2 and l in word_idx]
        if len(content) < 2:
            continue
        norm_id = (sid - min_id) / id_range
        sent_data.append((sid, text, content, norm_id, plast or 0.01))

    S = len(sent_data)
    N = W + S

    # Build edges
    edges = []

    # Word-word edges
    for (a, b), ps in pairs.items():
        if ps['count'] < 1 or a not in word_idx or b not in word_idx:
            continue
        cos_s = max(0.0, (ps['cos_a'] + ps['cos_v']) / 2)
        w = cos_s
        fresh = max(ps.get('plasticity', 1.0), 0.01)
        thr = (1 - fresh) * FRESH_THRESHOLD_MAX
        if cos_s < thr:
            continue
        if w > 0.001:
            edges.append((word_idx[a], word_idx[b], w))

    # Sentence-word edges
    for si, (sid, text, content, norm_id, plast) in enumerate(sent_data):
        sent_node = W + si
        n_c = len(content)
        w = SENT_WORD_WEIGHT / max(math.sqrt(n_c), 1)
        for word in content:
            edges.append((sent_node, word_idx[word], w))

    if not edges:
        return [], [], []

    # Sparse Laplacian
    degree = np.zeros(N)
    for i, j, w in edges:
        degree[i] += w; degree[j] += w
    degree = np.maximum(degree, 0.01)
    di = 1.0 / np.sqrt(degree)
    rs, cs, vs = [], [], []
    for i, j, w in edges:
        nw = w * di[i] * di[j]
        rs += [i, j]; cs += [j, i]; vs += [nw, nw]
    A = sp.csr_matrix((vs, (rs, cs)), shape=(N, N))
    dA = np.asarray(A.sum(axis=1)).flatten()
    L = sp.diags(dA) - A

    # Sequential query injection: seed query words one-by-one so order
    # affects the interference pattern on the bipartite graph.
    valid_q = [q for q in query_lemmas if q in word_idx]
    if not valid_q:
        return [], [], []

    # Echo as background recharge (word nodes only, pad to N)
    u_echo = np.zeros(N)
    if echo_u is not None:
        echo_full = np.zeros(N)
        echo_full[:W] = echo_u[:W] if len(echo_u) >= W else echo_u
        echo_l2 = np.linalg.norm(echo_full)
        if echo_l2 > 0.001:
            u_echo = np.maximum(echo_full / echo_l2, 0) * ECHO_WEIGHT

    leak = 1.0 / (1 + degree * DEGREE_LEAK_RATE)
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
    # Final relaxation to settle sentence-node activations
    for step in range(8):
        f = -0.3 * (L @ x) + 0.05 * (u_echo - x)
        v = v * 0.8 - 0.3 * x * 0.1 + f
        x = np.clip(x + v, -1, 3)
        x *= leak

    # Word activations (for center output)
    word_act = {}
    for i in range(W):
        if x[i] > 0.001:
            word_act[all_words[i]] = float(x[i])

    # Sentence activations
    sent_scored = []
    for si in range(S):
        act = float(x[W + si])
        if act > reach_threshold:
            sid, text, content, norm_id, plast = sent_data[si]
            sent_scored.append((sid, text, act, norm_id, si))
    sent_scored.sort(key=lambda r: -r[2])

    return word_act, sent_scored, sent_data


def recall(query_text, mode="broad"):
    """mode: broad (wide topic), focus (tight), zoom (temporal anchor)"""
    aud, vis, pairs, sents = load_graph()

    toks = tokenize_sent(query_text)
    if not toks:
        return "No tokens from query."
    query_lemmas = [t['lemma'] for t in toks if t['lemma'] not in FUNC_WORDS]
    if not query_lemmas:
        query_lemmas = [t['lemma'] for t in toks][:3]

    reach = {"broad": 0.0005, "focus": 0.0015, "zoom": 0.0008}.get(mode, 0.0008)

    # Load echo from DB (CoT: previous step's echo persists)
    all_words = list(aud.keys())
    word_idx = {w: i for i, w in enumerate(all_words)}
    conn = sqlite3.connect(DB, timeout=3)
    echo = load_echo(conn, word_idx)

    word_act, sent_scored, sent_data = bipartite_wave(
        query_lemmas, aud, vis, pairs, sents,
        reach_threshold=reach, echo_u=echo)

    if not word_act:
        conn.close()
        return "No activation from query."

    # Update echo: blend current activation for next CoT step
    W = len(all_words)
    current_act = np.zeros(W)
    for w, z in word_act.items():
        if w in word_idx:
            current_act[word_idx[w]] = z
    for q in query_lemmas:
        if q in word_idx:
            current_act[word_idx[q]] = 0.5
    # Accumulate (CoT steps build on each other)
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
    activated_sids = {sid for sid, _, _, _, _ in sent_scored[:5]}

    for sid, text, act, norm_id, si in sent_scored[:3]:
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
            _, btxt, bcontent, _, _ = sent_data[ni]
            # Include if any content word is activated, or if it's the hit itself
            topic_hit = any(word_act.get(l, 0) > 0.002 for l in bcontent)
            if topic_hit or ni == si:
                block_lines.append(btxt)
        if block_lines:
            blocks.append(block_lines)

    # Format output
    lines = []
    lines.append(f"[wave-recall] q={query_lemmas[:4]} center={center_words[:4]} sents={len(sent_scored)}")
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
