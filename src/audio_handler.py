"""Validation and safe storage for recorded / uploaded audio.

Everything here is standard-library only.  Uploaded files are untrusted, so:

* the format is detected from the file's **magic bytes** – the extension and the
  browser-supplied MIME type are never trusted;
* files are stored under a random name inside one directory (no path traversal,
  no overwriting, the original file name is discarded);
* size and (for WAV) duration are capped.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.story_manager import DATA_DIR

AUDIO_DIR = Path(os.getenv("SAGARKATHA_AUDIO_DIR", DATA_DIR / "uploads" / "audio"))

MAX_BYTES = int(os.getenv("SAGARKATHA_MAX_AUDIO_MB", "25")) * 1024 * 1024
MAX_SECONDS = 600  # 10 minutes – longer recordings should be split into parts
MIN_BYTES = 256

#: format key -> (file extension, MIME type)
FORMATS: dict[str, tuple[str, str]] = {
    "wav": (".wav", "audio/wav"),
    "mp3": (".mp3", "audio/mpeg"),
    "ogg": (".ogg", "audio/ogg"),
    "webm": (".webm", "audio/webm"),
    "m4a": (".m4a", "audio/mp4"),
    "flac": (".flac", "audio/flac"),
}

#: file extensions the uploader widget should offer
UPLOAD_TYPES = ["wav", "mp3", "ogg", "webm", "m4a", "mp4", "flac"]

_STORED_NAME = re.compile(r"^[0-9a-f]{32}\.(wav|mp3|ogg|webm|m4a|flac)$")


class AudioError(ValueError):
    """The audio file was rejected; the message is safe to show to the user."""


@dataclass(frozen=True)
class AudioInfo:
    filename: str  # stored file name (not a path)
    format: str
    mime: str
    size: int
    sha256: str
    duration: Optional[float]  # seconds, only known for WAV


def detect_format(data: bytes) -> Optional[str]:
    """Identify the audio container from its leading bytes. ``None`` if unknown."""
    head = data[:16]
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    if head[:4] == b"OggS":
        return "ogg"
    if head[:4] == b"\x1a\x45\xdf\xa3":  # EBML header: WebM / Matroska
        return "webm"
    if head[:4] == b"fLaC":
        return "flac"
    if head[4:8] == b"ftyp":  # ISO base media: m4a / mp4 audio
        return "m4a"
    if head[:3] == b"ID3" or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
        return "mp3"
    return None


def wav_duration(data: bytes) -> Optional[float]:
    """Duration in seconds for PCM WAV data, else ``None``."""
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            frames, rate = w.getnframes(), w.getframerate()
            return frames / float(rate) if rate else None
    except (wave.Error, EOFError):
        return None


def validate_audio(data: bytes, original_name: str = "") -> tuple[str, Optional[float]]:
    """Check an upload and return ``(format, duration_seconds_or_None)``.

    Raises :class:`AudioError` with a friendly message otherwise.
    """
    if not data or len(data) < MIN_BYTES:
        raise AudioError("The recording is empty or too short. Please record again.")
    if len(data) > MAX_BYTES:
        raise AudioError(f"The file is too large (limit {MAX_BYTES // (1024 * 1024)} MB). Try a shorter recording.")
    fmt = detect_format(data)
    if fmt is None:
        raise AudioError("This does not look like an audio file. Use WAV, MP3, OGG, WebM, M4A or FLAC.")
    ext = Path(original_name).suffix.lower().lstrip(".") if original_name else ""
    if ext in FORMATS and ext != fmt and not (ext == "mp4" and fmt == "m4a"):
        raise AudioError(f"The file is named .{ext} but its contents are {fmt.upper()}. Please re-export it.")
    duration = wav_duration(data) if fmt == "wav" else None
    if fmt == "wav" and duration is None:
        raise AudioError("The WAV file is damaged and cannot be read.")
    if duration is not None and duration > MAX_SECONDS:
        raise AudioError(f"The recording is longer than {MAX_SECONDS // 60} minutes. Please split it into parts.")
    return fmt, duration


def save_audio(data: bytes, original_name: str = "", dest_dir: Optional[Path | str] = None) -> AudioInfo:
    """Validate and store audio; returns metadata with the *stored* file name."""
    fmt, duration = validate_audio(data, original_name)
    ext, mime = FORMATS[fmt]
    folder = Path(dest_dir) if dest_dir else AUDIO_DIR
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + ext
    path = folder / name
    # "x" mode: never overwrite an existing file
    with open(path, "xb") as fh:
        fh.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - not supported on every filesystem
        pass
    return AudioInfo(name, fmt, mime, len(data), hashlib.sha256(data).hexdigest(), duration)


def audio_path(filename: str, dest_dir: Optional[Path | str] = None) -> Optional[Path]:
    """Resolve a stored file name to a path, or ``None`` if it is not a valid stored name."""
    if not filename or not _STORED_NAME.match(filename):
        return None
    p = (Path(dest_dir) if dest_dir else AUDIO_DIR) / filename
    return p if p.is_file() else None


def read_audio(filename: str, dest_dir: Optional[Path | str] = None) -> Optional[tuple[bytes, str]]:
    """Return ``(bytes, mime)`` for a stored file, or ``None``."""
    p = audio_path(filename, dest_dir)
    if p is None:
        return None
    fmt = detect_format(p.read_bytes()[:16]) or p.suffix.lstrip(".")
    return p.read_bytes(), FORMATS.get(fmt, (".bin", "application/octet-stream"))[1]


def delete_audio(filename: str, dest_dir: Optional[Path | str] = None) -> bool:
    """Delete a stored recording. Returns ``True`` if a file was removed."""
    p = audio_path(filename, dest_dir)
    if p is None:
        return False
    p.unlink()
    return True


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "unknown length"
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}:{s:02d}"
