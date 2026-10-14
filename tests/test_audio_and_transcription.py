import pytest
import requests

from src import transcription as tr
from src.audio_handler import AudioError, delete_audio, detect_format, read_audio, save_audio, validate_audio, wav_duration, format_duration, audio_path
from tests.conftest import make_wav


def test_detect_format():
    assert detect_format(make_wav()) == "wav"
    assert detect_format(b"OggS" + b"\0" * 20) == "ogg"
    assert detect_format(b"\x1a\x45\xdf\xa3" + b"\0" * 20) == "webm"
    assert detect_format(b"fLaC" + b"\0" * 20) == "flac"
    assert detect_format(b"\0\0\0\x20ftypM4A " + b"\0" * 20) == "m4a"
    assert detect_format(b"ID3" + b"\0" * 20) == "mp3"
    assert detect_format(b"\xff\xfb\x90\x00" + b"\0" * 20) == "mp3"
    assert detect_format(b"MZ\x90\x00" + b"\0" * 300) is None  # an .exe


def test_validate_rejects_bad_files():
    with pytest.raises(AudioError):
        validate_audio(b"")
    with pytest.raises(AudioError):
        validate_audio(b"not audio at all" * 40, "x.mp3")
    with pytest.raises(AudioError, match="named .mp3"):
        validate_audio(make_wav(), "evil.mp3")  # extension lies about contents
    with pytest.raises(AudioError, match="too large"):
        validate_audio(b"RIFF" + b"\0" * (26 * 1024 * 1024))
    assert validate_audio(make_wav(2.0), "ok.wav") == ("wav", pytest.approx(2.0))
    with pytest.raises(AudioError, match="damaged"):
        validate_audio(b"RIFF\x00\x00\x00\x00WAVEjunk" + b"\0" * 300)


def test_save_read_delete(tmp_path):
    info = save_audio(make_wav(), "../../etc/passwd.wav", tmp_path)
    assert info.format == "wav" and "/" not in info.filename and info.filename.endswith(".wav")
    assert (tmp_path / info.filename).exists() and len(info.sha256) == 64
    assert read_audio(info.filename, tmp_path)[1] == "audio/wav"
    assert audio_path("../secret.wav", tmp_path) is None  # only server-generated names resolve
    assert delete_audio(info.filename, tmp_path) is True
    assert delete_audio(info.filename, tmp_path) is False


def test_helpers():
    assert wav_duration(make_wav(1.5)) == pytest.approx(1.5)
    assert wav_duration(b"nope") is None
    assert format_duration(75) == "1:15" and format_duration(None) == "unknown length"


# ---------------------------------------------------------------- transcription
class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body if body is not None else {}
    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


def test_providers_follow_environment(monkeypatch):
    assert tr.available_providers() == ["manual"]
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert tr.available_providers() == ["manual", "sarvam", "openai"]


def test_language_support():
    assert tr.supports("sarvam", "or") and tr.supports("sarvam", "brx") and tr.supports("sarvam", "mni")
    assert tr.supports("openai", "hi") and not tr.supports("openai", "or") and not tr.supports("openai", "other")
    assert tr.supports("manual", "other")


def test_sarvam_request_and_response(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "secret-key")
    seen = {}
    def fake_post(url, headers=None, files=None, data=None, timeout=None):
        seen.update(url=url, headers=headers, data=data, files=files)
        return FakeResp(200, {"transcript": " नमस्ते समुद्र ", "language_code": "hi-IN"})
    monkeypatch.setattr(requests, "post", fake_post)
    res = tr.transcribe(make_wav(), "hi", "sarvam", filename="a.wav")
    assert res.text == "नमस्ते समुद्र" and res.provider == "sarvam"
    assert seen["url"].endswith("/speech-to-text") and seen["headers"] == {"api-subscription-key": "secret-key"}
    assert seen["data"]["language_code"] == "hi-IN" and seen["files"]["file"][2] == "audio/wav"


def test_odia_uses_sarvams_od_code(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    seen = {}
    monkeypatch.setattr(requests, "post", lambda *a, **k: (seen.update(k["data"]) or FakeResp(200, {"transcript": "ଓଡ଼ିଆ"})))
    tr.transcribe(make_wav(), "or", "sarvam")
    assert seen["language_code"] == "od-IN"


def test_sarvam_rejects_long_clips_before_upload(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("should not call the API"))
    with pytest.raises(tr.TranscriptionError, match="30 seconds"):
        tr.transcribe(make_wav(45, rate=4000), "hi", "sarvam")


def test_openai_request_and_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    seen = {}
    monkeypatch.setattr(requests, "post", lambda url, **k: (seen.update(url=url, **k) or FakeResp(200, {"text": "hello sea"})))
    assert tr.transcribe(make_wav(), "en", "openai").text == "hello sea"
    assert seen["data"] == {"model": "whisper-1", "language": "en"} and seen["headers"]["Authorization"] == "Bearer k"


@pytest.mark.parametrize("status,needle", [(401, "API key"), (429, "rate limit"), (413, "too large"), (422, "could not process"), (500, "HTTP 500")])
def test_http_errors_are_friendly_and_never_leak_keys(monkeypatch, status, needle):
    monkeypatch.setenv("SARVAM_API_KEY", "super-secret")
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResp(status))
    with pytest.raises(tr.TranscriptionError, match=needle) as e:
        tr.transcribe(make_wav(), "hi", "sarvam")
    assert "super-secret" not in str(e.value)


def test_network_failures(monkeypatch):
    monkeypatch.setenv("SARVAM_API_KEY", "k")
    def timeout(*a, **k): raise requests.Timeout()
    def down(*a, **k): raise requests.ConnectionError()
    monkeypatch.setattr(requests, "post", timeout)
    with pytest.raises(tr.TranscriptionError, match="too long"):
        tr.transcribe(make_wav(), "hi", "sarvam")
    monkeypatch.setattr(requests, "post", down)
    with pytest.raises(tr.TranscriptionError, match="Could not reach"):
        tr.transcribe(make_wav(), "hi", "sarvam")


def test_guard_rails(monkeypatch):
    assert tr.transcribe(b"", "hi", "manual").text == ""
    with pytest.raises(tr.TranscriptionError, match="not configured"):
        tr.transcribe(make_wav(), "hi", "sarvam")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    with pytest.raises(tr.TranscriptionError, match="does not support"):
        tr.transcribe(make_wav(), "or", "openai")
    with pytest.raises(tr.TranscriptionError, match="Unknown"):
        tr.transcribe(make_wav(), "hi", "bogus")
    with pytest.raises(tr.TranscriptionError, match="not a recognised"):
        tr.transcribe(b"x" * 500, "hi", "openai")
