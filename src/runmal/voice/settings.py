"""Voice settings store (ADR-0005/0006): the user's backend defaults.

TTS and STT are multi-backend and user-selectable. The selections
live in ``voice_settings.json`` in the data dir (``RUNMAL_DATA_DIR``),
persisted exactly like the S513 route store: a versioned JSON
document with sorted keys, tolerant load, and defaults that point at
the default-shipped backends. Selections are validated against the
registries (``KNOWN_TTS_BACKENDS`` / ``KNOWN_STT_BACKENDS``); an
unknown stored key falls back to the default — it is never an error,
so a legacy or hand-edited file can never brick the voice page.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from runmal.voice.backends import (
    DEFAULT_TTS_BACKEND,
    KNOWN_TTS_BACKENDS,
)
from runmal.voice.stt_backends import (
    DEFAULT_STT_BACKEND,
    KNOWN_STT_BACKENDS,
)

SETTINGS_VERSION = 1
SETTINGS_FILENAME = "voice_settings.json"


def settings_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / SETTINGS_FILENAME


@dataclass
class VoiceSettings:
    """The user's voice-backend selections, persisted as JSON."""

    tts_backend: str = DEFAULT_TTS_BACKEND
    stt_backend: str = DEFAULT_STT_BACKEND

    def __post_init__(self) -> None:
        if self.tts_backend not in KNOWN_TTS_BACKENDS:
            self.tts_backend = DEFAULT_TTS_BACKEND
        if self.stt_backend not in KNOWN_STT_BACKENDS:
            self.stt_backend = DEFAULT_STT_BACKEND

    def set_tts_backend(self, key: str) -> None:
        if key not in KNOWN_TTS_BACKENDS:
            raise ValueError(f"unknown TTS backend: {key!r}")
        self.tts_backend = key

    def set_stt_backend(self, key: str) -> None:
        if key not in KNOWN_STT_BACKENDS:
            raise ValueError(f"unknown STT backend: {key!r}")
        self.stt_backend = key

    # ------------------------------------------------------------ persist

    def to_dict(self) -> dict:
        return {"version": SETTINGS_VERSION,
                "tts_backend": self.tts_backend,
                "stt_backend": self.stt_backend}

    @classmethod
    def from_dict(cls, data: dict) -> VoiceSettings:
        return cls(tts_backend=str(data.get("tts_backend") or DEFAULT_TTS_BACKEND),
                   stt_backend=str(data.get("stt_backend") or DEFAULT_STT_BACKEND))

    def save(self, path: Path | None = None) -> None:
        target = path or settings_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))

    @classmethod
    def load(cls, path: Path | None = None) -> VoiceSettings:
        target = path or settings_path()
        if not target.exists():
            return cls()
        try:
            return cls.from_dict(json.loads(target.read_text()))
        except (ValueError, TypeError, OSError):
            return cls()  # corrupt settings never brick the voice page
