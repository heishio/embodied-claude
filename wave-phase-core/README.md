# wave-phase-core

Stable subset of the wave-phase recall system. Extracted from `reading_session_v2.py` (experiment lab).

## Structure

```
src/wave_phase_core/
  __init__.py      # re-exports all public API
  constants.py     # FUNC_WORDS, PAIR_WINDOW, ETA, ETA_PAIR, KURAMOTO_K/STEPS
  tokenize.py      # tokenize_sent (sudachipy)
  phase.py         # audio_phase_accent, visual_phase, wrap_pi, kuramoto_chain
  cli.py           # wave_recall CLI (broad/focus/zoom modes)
  __main__.py      # python -m wave_phase_core.cli entry point
```

## Dependencies

- numpy
- scipy
- sudachipy + sudachidict-core
- pyopenjtalk (for audio_phase_accent)

## Usage

### As a library (from hooks)

```python
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'wave-phase-core', 'src'))
from wave_phase_core import tokenize_sent, FUNC_WORDS, audio_phase_accent, visual_phase
```

### As a CLI

```bash
PYTHONPATH=wave-phase-core/src python -m wave_phase_core.cli "query text"
PYTHONPATH=wave-phase-core/src python -m wave_phase_core.cli --mode=focus "query text"
```

### From MCP (memory-mcp)

Registered as `wave_recall` tool. Calls `python -m wave_phase_core.cli` via subprocess.

## Relationship to reading_session_v2.py

The experimental lab file (`reading_session_v2.py`) is maintained separately. This package contains only the stable, production-ready subset. Lab changes should be ported intentionally.
