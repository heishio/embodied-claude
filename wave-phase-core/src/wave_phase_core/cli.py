# -*- coding: utf-8 -*-
"""wave_recall CLI - Wave-based recall with topic extraction.

Usage: python -m wave_phase_core.cli [--mode broad|focus|zoom] "query text"
"""
import sys
import os
import sqlite3
import numpy as np
import scipy.sparse as sp

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from .constants import FUNC_WORDS, PAIR_WINDOW
from .tokenize import tokenize_sent

HOME = os.path.expanduser("~")
DB = os.path.join(HOME, ".claude", "session-wave-v2.db")
FRESH_THRESHOLD_MAX = 0.5
DEGREE_LEAK_RATE = 0.001


def load_graph():
    conn = sqlite3.connect(DB, timeout=3)
    aud, vis = {}, {}
    for r in conn.execute("SELECT word, aud_phase, vis_phase FROM session_words"):
        aud[r[0]] = r[1]; vis[r[0]] = r[2]
    pairs = {}
    for r in conn.execute("SELECT word_a,word_b,cos_a,cos_v,count,plasticity FROM session_pairs"):
        pairs[(r[0], r[1])] = {'cos_a': r[2], 'cos_v': r[3], 'count': r[4], 'plasticity': r[5] or 1.0}
    chain = {}
    for r in conn.execute("SELECT word_prev, word_next, count FROM session_chain"):
        chain[(r[0], r[1])] = r[2]
    sents = conn.execute(
        "SELECT id, text, lemmas, plasticity FROM lt_sentences ORDER BY id"
    ).fetchall()
    conn.close()
    return aud, vis, pairs, chain, sents


def wave_propagate(query_lemmas, aud, vis, pairs, chain):
    all_words = list(aud.keys())
    N = len(all_words)
    idx = {w: i for i, w in enumerate(all_words)}
    edges = []
    for (a, b), ps in pairs.items():
        if ps['count'] < 1 or a not in idx or b not in idx:
            continue
        cos_s = max(0.0, (ps['cos_a'] + ps['cos_v']) / 2)
        ch = chain.get((a, b), 0) + chain.get((b, a), 0)
        w = cos_s + ch / 30.0
        fresh = max(ps.get('plasticity', 1.0), 0.01)
        thr = (1 - fresh) * FRESH_THRESHOLD_MAX
        if cos_s < thr:
            continue
        if w > 0.001:
            edges.append((idx[a], idx[b], w))
    if not edges:
        return {}
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
    u = np.zeros(N)
    for q in query_lemmas:
        if q in idx:
            u[idx[q]] = 1.0
    if u.sum() == 0:
        return {}
    leak = 1.0 / (1 + degree * DEGREE_LEAK_RATE)
    x = u * 0.3
    v = np.zeros(N)
    for step in range(15):
        f = -0.3 * (L @ x)
        if step % 5 == 0:
            f += 0.05 * (u - x)
        v = v * 0.8 - 0.3 * x * 0.1 + f
        x = np.clip(x + v, -1, 3)
        x *= leak
    inv = {v: k for k, v in idx.items()}
    return {inv[i]: float(x[i]) for i in range(N)}


def recall(query_text, mode="broad"):
    """mode: broad (wide topic), focus (tight), zoom (temporal anchor)"""
    aud, vis, pairs, chain, sents = load_graph()

    toks = tokenize_sent(query_text)
    if not toks:
        return "No tokens from query."
    query_lemmas = [t['lemma'] for t in toks if t['lemma'] not in FUNC_WORDS]
    if not query_lemmas:
        query_lemmas = [t['lemma'] for t in toks][:3]

    reach = {"broad": 0.005, "focus": 0.015, "zoom": 0.008}.get(mode, 0.008)

    act1 = wave_propagate(query_lemmas, aud, vis, pairs, chain)
    if not act1:
        return "No activation from query."

    center = sorted(
        [(w, z) for w, z in act1.items() if w not in FUNC_WORDS and w not in set(query_lemmas) and z > 0.005],
        key=lambda r: -r[1]
    )[:5]
    center_words = [w for w, _ in center]

    requery = list(set(query_lemmas + center_words))[:8]
    act2 = wave_propagate(requery, aud, vis, pairs, chain)
    if not act2:
        return "No activation from re-query."

    in_topic = {w for w, z in act2.items() if z > reach and w not in FUNC_WORDS}

    scored_sents = []
    for idx_s, (sid, text, lemmas_str, plast) in enumerate(sents):
        if not lemmas_str:
            continue
        lems = lemmas_str.split(",")
        content = [l for l in lems if l not in FUNC_WORDS and len(l) >= 2]
        if not content:
            continue
        overlap = sum(1 for l in content if l in in_topic)
        if overlap < 2:
            continue
        wave_score = sum(act2.get(l, 0) for l in content) / len(content)
        scored_sents.append((sid, text, wave_score, overlap / len(content), plast or 0.01, idx_s))

    scored_sents.sort(key=lambda r: -(r[2] * r[3]))

    content_topic = {w for w in in_topic if len(w) >= 2}
    fwd = {}
    for (p, n), c in chain.items():
        if p in content_topic and n in content_topic and c >= 2:
            if p not in fwd or c > chain.get((p, fwd[p]), 0):
                fwd[p] = n
    all_nexts = set(fwd.values())
    starts = sorted([w for w in fwd if w not in all_nexts], key=lambda w: -act2.get(w, 0))[:3]
    if not starts and fwd:
        starts = sorted(fwd.keys(), key=lambda w: -act2.get(w, 0))[:3]
    used = set()
    sequences = []
    for start in starts:
        seq = [start]
        used.add(start)
        cur = start
        while cur in fwd and fwd[cur] not in used:
            cur = fwd[cur]
            seq.append(cur)
            used.add(cur)
        if len(seq) >= 2:
            sequences.append(seq)

    NEIGHBOR = 4
    blocks = []
    used_indices = set()
    for sid, text, ws, ov, pl, idx_s in scored_sents[:3]:
        if idx_s in used_indices:
            continue
        block_indices = []
        for offset in range(-NEIGHBOR, NEIGHBOR + 1):
            ni = idx_s + offset
            if 0 <= ni < len(sents) and ni not in used_indices:
                block_indices.append(ni)
                used_indices.add(ni)
        block_lines = []
        for ni in sorted(block_indices):
            _, btxt, blems, bpl = sents[ni]
            if not blems:
                continue
            bcontent = [l for l in blems.split(",") if l not in FUNC_WORDS]
            topic_hit = any(l in in_topic for l in bcontent)
            if topic_hit or ni == idx_s:
                block_lines.append(btxt)
        if block_lines:
            blocks.append(block_lines)

    lines = []
    lines.append(f"[wave-recall] q={query_lemmas[:4]} center={center_words[:4]} topic={len(in_topic)}words")
    if sequences:
        for seq in sequences[:3]:
            lines.append(f"  chain: {'→'.join(seq)}")
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
