"""Style-Bert-VITS2 TTS engine."""

from __future__ import annotations

import logging
import os
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


_sudachi_tokenizer: Any = None
_sudachi_mode: Any = None


def _get_sudachi() -> tuple[Any, Any] | None:
    """Lazily create a sudachipy tokenizer. Returns None if unavailable."""
    global _sudachi_tokenizer, _sudachi_mode
    if _sudachi_tokenizer is None:
        try:
            from sudachipy import dictionary
            from sudachipy import tokenizer as _tok
            _sudachi_tokenizer = dictionary.Dictionary().create()
            _sudachi_mode = _tok.Tokenizer.SplitMode.C
        except Exception as exc:
            logger.warning("sudachipy unavailable, skipping reading conversion: %s", exc)
            return None
    return _sudachi_tokenizer, _sudachi_mode


def _is_latin_word(s: str) -> bool:
    """True if every char is ASCII and at least one is a latin letter."""
    if not s:
        return False
    has_alpha = False
    for c in s:
        if not c.isascii():
            return False
        if c.isalpha():
            has_alpha = True
    return has_alpha


def _to_reading(text: str) -> str:
    """Convert *only* latin (English) tokens to katakana via sudachipy.

    The rest of the text (kanji/kana/punctuation/numbers) is kept as-is so
    SBV2's native Japanese prosody survives. Pure-ASCII alphabetic tokens
    like "hello", "AI", "GPT" get replaced with their katakana reading.
    Falls back to the original text when sudachipy is unavailable.
    """
    result = _get_sudachi()
    if result is None:
        return text
    tok, mode = result
    parts: list[str] = []
    try:
        for m in tok.tokenize(text, mode):
            surface = m.surface()
            if _is_latin_word(surface):
                reading = m.reading_form()
                parts.append(reading if reading else surface)
            else:
                parts.append(surface)
    except Exception as exc:
        logger.warning("sudachipy tokenization failed, using original text: %s", exc)
        return text
    return "".join(parts)


class SBV2Engine:
    """Style-Bert-VITS2 TTS engine (local HTTP API)."""

    def __init__(
        self,
        url: str = "http://localhost:5000",
        model_id: int = 0,
        model_name: str | None = None,
        speaker_id: int = 0,
        style: str = "Neutral",
        style_weight: float = 5.0,
        length: float = 1.0,
        language: str = "JP",
    ) -> None:
        self._url = url.rstrip("/")
        self._model_id = model_id
        self._model_name = model_name
        self._speaker_id = speaker_id
        self._style = style
        self._style_weight = style_weight
        self._length = length
        self._language = language
        self._use_reading = os.getenv(
            "SBV2_USE_SUDACHI_READING", "true"
        ).lower() in {"1", "true", "yes", "on"}

    @property
    def engine_name(self) -> str:
        return "sbv2"

    def is_available(self) -> bool:
        """Check if SBV2 server is running."""
        try:
            req = urllib.request.Request(f"{self._url}/models/info", method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                resp.read()
            return True
        except Exception:
            return False

    def synthesize(self, text: str, **kwargs: Any) -> tuple[bytes, str]:
        """Synthesize text using Style-Bert-VITS2 API.

        Kwargs:
            model_name: Override model name (takes priority over model_id).
            model_id: Override model ID.
            speaker_id: Override speaker ID.
            style: Override style name.
            style_weight: Override style weight.
            length: Override speech rate (1.0 = normal).
            language: Override language (JP, EN, ZH).

        Returns:
            Tuple of (wav_bytes, 'wav').
        """
        language = kwargs.get("language", self._language)
        if self._use_reading and language == "JP":
            text = _to_reading(text)
        params: dict[str, Any] = {"text": text}

        # Explicit model_id override takes priority over model_name
        if "model_id" in kwargs:
            params["model_id"] = kwargs["model_id"]
        else:
            model_name = kwargs.get("model_name", self._model_name)
            if model_name:
                params["model_name"] = model_name
            else:
                params["model_id"] = self._model_id

        params["speaker_id"] = kwargs.get("speaker_id", self._speaker_id)
        params["style"] = kwargs.get("style", self._style)
        params["style_weight"] = kwargs.get("style_weight", self._style_weight)
        params["length"] = kwargs.get("length", self._length)
        params["language"] = kwargs.get("language", self._language)

        if "sdp_ratio" in kwargs:
            params["sdp_ratio"] = kwargs["sdp_ratio"]
        if "noise" in kwargs:
            params["noise"] = kwargs["noise"]
        if "noisew" in kwargs:
            params["noisew"] = kwargs["noisew"]

        query = urllib.parse.urlencode(params)
        req = urllib.request.Request(
            f"{self._url}/voice?{query}",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            wav_bytes = resp.read()

        return wav_bytes, "wav"
