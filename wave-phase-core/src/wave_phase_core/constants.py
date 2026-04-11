"""Constants for wave-phase system."""
import math

ETA = 0.1
ETA_PAIR = 0.05
PAIR_WINDOW = 4
KURAMOTO_K = 0.1
KURAMOTO_STEPS = 5

LTD_FLOOR = 0.01
_LOG_RANGE = math.log(1.0 / LTD_FLOOR)  # log(100) ≈ 4.605


def plasticity_log_scale(p: float) -> float:
    """Map plasticity [LTD_FLOOR, 1.0] -> [0.0, 1.0] in log space.

    Spreads the dense low-plasticity region for better temporal resolution.
    0.01->0.0, 0.1->0.5, 1.0->1.0
    """
    return math.log(max(p, LTD_FLOOR) / LTD_FLOOR) / _LOG_RANGE


ECHO_WEIGHT = 0.15  # background recharge intensity (was 0.3 — softened for ふんわり影響)
ECHO_ENERGY_CAP = 5.0


def load_echo(conn, word_idx):
    """Load echo state vector from DB."""
    import numpy as np
    N = len(word_idx)
    echo = np.zeros(N)
    try:
        for r in conn.execute("SELECT word, activation FROM echo_state"):
            if r[0] in word_idx:
                echo[word_idx[r[0]]] = r[1]
    except Exception:
        pass
    return echo


def save_echo(conn, echo, all_words):
    """Save echo state vector to DB (only significant entries)."""
    import numpy as np
    conn.execute("DELETE FROM echo_state")
    nz = np.nonzero(np.abs(echo) > 0.001)[0]
    for i in nz:
        conn.execute("INSERT INTO echo_state VALUES(?,?)", (all_words[i], float(echo[i])))
    conn.commit()


def _ensure_sent_echo_schema(conn):
    """Ensure sent_echo_state exists with (scope, sent_id) composite key.
    Scope values: 'session' | 'lt'. This prevents id collision between
    session_sentences and lt_sentences which can share numeric IDs.
    """
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sent_echo_state'")
    if cur.fetchone() is None:
        conn.execute("CREATE TABLE sent_echo_state ("
                     "scope TEXT NOT NULL, "
                     "sent_id INTEGER NOT NULL, "
                     "activation REAL, "
                     "updated_at REAL, "
                     "PRIMARY KEY (scope, sent_id))")
        return
    # Migrate old (sent_id PK only) schema
    cols = [r[1] for r in conn.execute("PRAGMA table_info(sent_echo_state)")]
    if 'scope' not in cols:
        conn.execute("DROP TABLE sent_echo_state")
        conn.execute("CREATE TABLE sent_echo_state ("
                     "scope TEXT NOT NULL, "
                     "sent_id INTEGER NOT NULL, "
                     "activation REAL, "
                     "updated_at REAL, "
                     "PRIMARY KEY (scope, sent_id))")


def load_sent_echo(conn, sent_idx, scope='session'):
    """Load sentence echo for a given scope.
    sent_idx: dict[sid] -> i.  Returns np vector of size len(sent_idx).
    """
    import numpy as np
    N = len(sent_idx)
    echo = np.zeros(N)
    try:
        _ensure_sent_echo_schema(conn)
        cur = conn.execute(
            "SELECT sent_id, activation FROM sent_echo_state WHERE scope=?",
            (scope,))
        for sid, act in cur.fetchall():
            if sid in sent_idx:
                echo[sent_idx[sid]] = act
    except Exception:
        pass
    return echo


def save_sent_echo(conn, echo, sent_ids, scope='session'):
    """Save sentence echo for a given scope.
    sent_ids[i] = sid for echo index i.
    """
    import numpy as np
    import time as _time
    _ensure_sent_echo_schema(conn)
    conn.execute("DELETE FROM sent_echo_state WHERE scope=?", (scope,))
    nz = np.nonzero(np.abs(echo) > 0.001)[0]
    now = _time.time()
    for i in nz:
        conn.execute("INSERT INTO sent_echo_state VALUES(?,?,?,?)",
                     (scope, int(sent_ids[i]), float(echo[i]), now))
    conn.commit()


FUNC_WORDS = {
    'は', 'が', 'を', 'に', 'の', 'と', 'で', 'も', 'て', 'た', 'し',
    'する', 'いる', 'ある', 'だ', 'れる', 'られる', 'ない', 'この', 'その',
    'よう', 'こと', 'それ', 'これ', 'よる', 'おく', 'いう', 'なる', 'せる',
    'ば', 'ず', 'なり', 'より', 'から', 'まで', 'ため', 'けれ', 'ても', 'か',
    'ね', 'よ', 'な', 'や', 'ぞ', 'ぜ', 'って', 'ます', 'ました',
}

# Speaker tokens are injected by session-wave-v2.py into sentence lemmas as a
# cheap "who said it" label. Without a real speaker modality they end up as
# super-hub nodes that drag recall toward the speaker themselves. Strip them
# from content-word counting in wave_recall until multi-modal speaker cues are
# in place.
SPEAKER_TOKENS = {'シオ', 'クオ'}
