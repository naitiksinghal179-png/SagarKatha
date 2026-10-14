"""Shared fixtures: every test works in a temp data dir and never touches the network."""

import os
import struct
import wave
import io

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGARKATHA_OFFLINE", "1")
    monkeypatch.delenv("ADMIN_PASSCODE", raising=False)
    for k in ("SARVAM_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    yield


def make_wav(seconds: float = 1.0, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<h", 0) * int(rate * seconds))
    return buf.getvalue()


@pytest.fixture
def wav_bytes():
    return make_wav()
