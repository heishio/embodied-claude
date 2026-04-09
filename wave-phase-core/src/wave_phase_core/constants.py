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


FUNC_WORDS = {
    'は', 'が', 'を', 'に', 'の', 'と', 'で', 'も', 'て', 'た', 'し',
    'する', 'いる', 'ある', 'だ', 'れる', 'られる', 'ない', 'この', 'その',
    'よう', 'こと', 'それ', 'これ', 'よる', 'おく', 'いう', 'なる', 'せる',
    'ば', 'ず', 'なり', 'より', 'から', 'まで', 'ため', 'けれ', 'ても', 'か',
    'ね', 'よ', 'な', 'や', 'ぞ', 'ぜ', 'って', 'ます', 'ました',
}
