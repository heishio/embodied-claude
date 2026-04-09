"""wave_phase_core - Stable subset of wave-phase recall system."""
from .constants import FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR, KURAMOTO_K, KURAMOTO_STEPS, LTD_FLOOR, plasticity_log_scale
from .phase import audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain
from .tokenize import tokenize_sent
