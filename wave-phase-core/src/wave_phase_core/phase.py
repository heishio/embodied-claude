"""Phase computation: audio (accent), visual (char-type), Kuramoto chain."""
import re

import numpy as np
import pyopenjtalk
import sudachipy

from .constants import KURAMOTO_K, KURAMOTO_STEPS

_tok = sudachipy.Dictionary().create()
_GOLDEN = (1 + np.sqrt(5)) / 2
_MORA_ENDS = {'a', 'i', 'u', 'e', 'o', 'A', 'I', 'U', 'E', 'O', 'N', 'cl'}


def _is_latin_word(s: str) -> bool:
    if not s:
        return False
    ha = False
    for c in s:
        if not c.isascii():
            return False
        if c.isalpha():
            ha = True
    return ha


def to_reading_text(text: str) -> str:
    """sudachi: latin words -> katakana reading, others as surface."""
    parts = []
    for m in _tok.tokenize(text, sudachipy.Tokenizer.SplitMode.C):
        pos0 = m.part_of_speech()[0]
        if pos0 in ("補助記号", "空白"):
            parts.append(m.surface())
        elif _is_latin_word(m.surface()):
            parts.append(m.reading_form() or m.surface())
        else:
            parts.append(m.surface())
    return "".join(parts)


def _extract_accent(text: str) -> tuple[int, int]:
    try:
        labels = pyopenjtalk.extract_fullcontext(text)
    except Exception:
        return (0, 0)
    if not labels:
        return (0, 0)
    for label in labels:
        m = re.search(r'/F:(\d+)_(\d+)', label)
        if m:
            return int(m.group(1)), int(m.group(2))
    return (0, 0)


def _hl_pattern(n_mora: int, accent: int) -> list[str]:
    if n_mora <= 0:
        return []
    if accent == 0:
        return ['L'] + ['H'] * (n_mora - 1)
    if accent == 1:
        return ['H'] + ['L'] * (n_mora - 1)
    return ['L'] + ['H'] * (accent - 1) + ['L'] * (n_mora - accent)


def audio_phase_accent(word: str) -> float:
    """Phoneme list + pitch-accent H/L -> scalar phase."""
    prepared = to_reading_text(word)
    try:
        phons = pyopenjtalk.g2p(prepared).split(' ')
    except Exception:
        phons = []
    if not phons or phons == ['']:
        return 0.0
    n_mora, accent = _extract_accent(prepared)
    hl = _hl_pattern(n_mora, accent)
    mi = 0
    h = 0.0
    for i, ph in enumerate(phons):
        hv = hl[mi] if mi < len(hl) else 'L'
        val = sum(ord(c) * 17 for c in ph) + (500 if hv == 'H' else 0)
        h += val * _GOLDEN ** (i + 1)
        if ph in _MORA_ENDS:
            mi += 1
    return float((h % (2 * np.pi)) - np.pi)


def visual_phase(surface: str) -> float:
    """Unicode char-type biased phase."""
    if not surface:
        return 0.0
    h = 0.0
    for i, ch in enumerate(surface):
        b = 0.8 if '\u4e00' <= ch <= '\u9fff' else (
            0.0 if '\u3040' <= ch <= '\u309f' else (
                0.3 if '\u30a0' <= ch <= '\u30ff' else (
                    -0.5 if ch.isascii() and ch.isalpha() else 0.0)))
        h += (ord(ch) + b * 1000) * _GOLDEN ** (i + 1)
    return float((h % (2 * np.pi)) - np.pi)


def wrap_pi(x: float) -> float:
    return (x + np.pi) % (2 * np.pi) - np.pi


def kuramoto_chain(phases: np.ndarray, K: float = KURAMOTO_K,
                    steps: int = KURAMOTO_STEPS) -> np.ndarray:
    phi = np.array(phases, dtype=float)
    n = len(phi)
    if n < 2:
        return phi
    for _ in range(steps):
        dphi = np.zeros(n)
        for i in range(n):
            if i > 0:
                dphi[i] += K * np.sin(phi[i - 1] - phi[i])
            if i < n - 1:
                dphi[i] += K * np.sin(phi[i + 1] - phi[i])
        phi += dphi
    return phi
