"""Speech-to-text providers for story recordings.

The app works with **no API key at all**: the contributor simply types or edits
the transcript ("manual" provider).  When keys are configured in the
environment, a *Transcribe* button appears:

==========  =====================================  ===================================
provider    needs                                  notes
==========  =====================================  ===================================
manual      nothing                                always available
sarvam      ``SARVAM_API_KEY``                     Indian-language ASR; all 22
                                                   scheduled languages + English are
                                                   listed in Sarvam's documentation.
                                                   The REST endpoint is meant for short
                                                   clips (≈30 s); longer audio needs
                                                   Sarvam's batch API.
openai      ``OPENAI_API_KEY``                     Whisper; supports about 15 of our
                                                   languages (see ``LANGUAGES``).
==========  =====================================  ===================================

Audio is sent to the chosen provider **only** when the contributor presses the
button.  Machine transcripts can be wrong, especially for coastal dialects, so
the UI always shows the result in an editable box.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import requests

from src.audio_handler import FORMATS, detect_format, wav_duration
from src.story_manager import LANGUAGES

SARVAM_URL = os.getenv("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/") + "/speech-to-text"
OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
SARVAM_MAX_SECONDS = 30
TIMEOUT = 90


class TranscriptionError(RuntimeError):
    """Friendly, user-displayable failure (never contains API keys)."""


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    provider: str
    language: str  # code requested (or detected when the provider reports it)


PROVIDER_LABELS = {
    "manual": "Type it myself",
    "sarvam": "Sarvam AI (Indian languages)",
    "openai": "OpenAI Whisper",
}


def available_providers() -> list[str]:
    """Providers usable right now (``manual`` is always first)."""
    out = ["manual"]
    if os.getenv("SARVAM_API_KEY"):
        out.append("sarvam")
    if os.getenv("OPENAI_API_KEY"):
        out.append("openai")
    return out


def supports(provider: str, language: str) -> bool:
    """Does ``provider`` accept this language code?"""
    lang = LANGUAGES.get(language)
    if provider == "manual":
        return True
    if not lang:
        return False
    if provider == "sarvam":
        return bool(lang["sarvam"])
    if provider == "openai":
        return bool(lang["whisper"])
    return False


def transcribe(
    audio: bytes,
    language: str,
    provider: str,
    *,
    filename: str = "recording",
    session: Optional[requests.Session] = None,
) -> TranscriptionResult:
    """Transcribe ``audio`` with ``provider``; raises :class:`TranscriptionError`."""
    if provider == "manual":
        return TranscriptionResult("", "manual", language)
    if provider not in ("sarvam", "openai"):
        raise TranscriptionError(f"Unknown transcription provider: {provider}")
    if provider not in available_providers():
        raise TranscriptionError(f"{PROVIDER_LABELS[provider]} is not configured (missing API key).")
    if not supports(provider, language):
        raise TranscriptionError(
            f"{PROVIDER_LABELS[provider]} does not support {LANGUAGES.get(language, {}).get('name', language)}. "
            "Please type the transcript instead."
        )
    fmt = detect_format(audio)
    if fmt is None:
        raise TranscriptionError("The recording is not a recognised audio file.")
    name = os.path.splitext(os.path.basename(filename) or "recording")[0] + FORMATS[fmt][0]
    mime = FORMATS[fmt][1]
    http = session or requests
    try:
        if provider == "sarvam":
            return _sarvam(http, audio, language, name, mime, fmt)
        return _openai(http, audio, language, name, mime)
    except requests.Timeout as exc:
        raise TranscriptionError("The transcription service took too long. Try a shorter clip.") from exc
    except requests.RequestException as exc:
        raise TranscriptionError("Could not reach the transcription service. Check the internet connection.") from exc


# --------------------------------------------------------------------------- #


def _http_error(resp: requests.Response, who: str) -> TranscriptionError:
    code = resp.status_code
    if code in (401, 403):
        return TranscriptionError(f"{who} rejected the API key (HTTP {code}). Check your .env file.")
    if code == 429:
        return TranscriptionError(f"{who} rate limit reached. Please wait a minute and try again.")
    if code == 413:
        return TranscriptionError("The recording is too large for the transcription service.")
    if code in (400, 422):
        return TranscriptionError(f"{who} could not process this audio (HTTP {code}). Try WAV or a shorter clip.")
    return TranscriptionError(f"{who} returned an error (HTTP {code}).")


def _sarvam(http, audio: bytes, language: str, name: str, mime: str, fmt: str) -> TranscriptionResult:
    duration = wav_duration(audio) if fmt == "wav" else None
    if duration is not None and duration > SARVAM_MAX_SECONDS:
        raise TranscriptionError(
            f"Sarvam's quick API handles clips up to about {SARVAM_MAX_SECONDS} seconds "
            f"(this one is {duration:.0f} s). Record in shorter parts, or type the transcript."
        )
    data = {"language_code": LANGUAGES[language]["sarvam"]}
    model = os.getenv("SARVAM_STT_MODEL")
    if model:
        data["model"] = model
    resp = http.post(
        SARVAM_URL,
        headers={"api-subscription-key": os.environ["SARVAM_API_KEY"]},
        files={"file": (name, audio, mime)},
        data=data,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise _http_error(resp, "Sarvam")
    try:
        body = resp.json()
    except ValueError as exc:
        raise TranscriptionError("Sarvam returned an unreadable response.") from exc
    text = (body.get("transcript") or "").strip()
    if not text:
        raise TranscriptionError("No speech was recognised. Speak closer to the microphone or type the transcript.")
    return TranscriptionResult(text, "sarvam", language)


def _openai(http, audio: bytes, language: str, name: str, mime: str) -> TranscriptionResult:
    data = {"model": os.getenv("OPENAI_STT_MODEL", "whisper-1")}
    code = LANGUAGES[language]["whisper"]
    if code:
        data["language"] = code
    resp = http.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
        files={"file": (name, audio, mime)},
        data=data,
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise _http_error(resp, "OpenAI")
    try:
        text = (resp.json().get("text") or "").strip()
    except ValueError as exc:
        raise TranscriptionError("OpenAI returned an unreadable response.") from exc
    if not text:
        raise TranscriptionError("No speech was recognised. Speak closer to the microphone or type the transcript.")
    return TranscriptionResult(text, "openai", language)
