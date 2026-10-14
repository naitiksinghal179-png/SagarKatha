import json

import pytest

from src.story_manager import (
    CATEGORIES, LANGUAGES, REGIONS, SCHEDULED_LANGUAGE_CODES, Story, StoryManager, StoryValidationError,
    blur_coordinates, classify_story, csv_safe, ai_classify, contains_pii, in_study_area, md_escape,
    nearest_region, redact_pii, stories_to_csv, summarize, validate_story_input, DEMO_STORIES_PATH,
)

GOOD = dict(title="Silver flashes", text="At dawn we look for silver flashes on the water.", language="en", consent_public=True)


@pytest.fixture
def mgr(tmp_path):
    return StoryManager(user_path=tmp_path / "user.json")


# ---------------------------------------------------------------- reference data
def test_there_are_22_scheduled_languages():
    assert len(SCHEDULED_LANGUAGE_CODES) == 22
    assert "en" in LANGUAGES and "other" in LANGUAGES


def test_regions_are_unique_and_in_study_area():
    assert len({r.id for r in REGIONS}) == len(REGIONS) == 13
    assert all(in_study_area(r.lat, r.lng) and in_study_area(r.sea_lat, r.sea_lng) for r in REGIONS)


def test_nearest_region():
    assert nearest_region(9.95, 76.25).id == "ker"
    assert nearest_region(11.6, 92.7).id == "and"


# ---------------------------------------------------------------- privacy helpers
@pytest.mark.parametrize("text,marker,leftover", [
    ("call me on 9876543210", "[phone removed]", "9876543210"),
    ("call +91 98765 43210 now", "[phone removed]", "98765"),
    ("mail me a.b@example.com", "[email removed]", "example.com"),
    ("aadhaar 1234 5678 9012", "[number removed]", "5678"),
    ("landline 02212345678", "[number removed]", "2212345678"),
])
def test_pii_is_redacted(text, marker, leftover):
    out, changed = redact_pii(text)
    assert changed and marker in out and leftover not in out
    assert contains_pii(text)


def test_pii_does_not_touch_normal_numbers():
    text = "We caught 120 kg of sardine at 19.7, 85.3 in 2026 with 3 boats."
    assert redact_pii(text) == (text, False)


def test_blur_coordinates():
    assert blur_coordinates(13.0827, 80.2707, "exact") == (13.0827, 80.2707)
    la, ln = blur_coordinates(13.0827, 80.2707, "approx")
    assert (la, ln) == (13.1, 80.25)
    assert blur_coordinates(13.0827, 80.2707, "approx") == (la, ln)  # deterministic
    r = nearest_region(13.0827, 80.2707)
    assert blur_coordinates(13.0827, 80.2707, "region") == (r.lat, r.lng)
    with pytest.raises(ValueError):
        blur_coordinates(1, 1, "nope")


def test_md_escape_blocks_markdown_injection():
    out = md_escape("[click](http://evil) ![x](y) # head `code` $x$")
    for ch in "[]()#`$!":
        assert ("\\" + ch) in out


def test_csv_safe():
    assert csv_safe("=1+1") == "'=1+1" and csv_safe("@x") == "'@x" and csv_safe("ok") == "ok" and csv_safe(None) == ""


# ---------------------------------------------------------------- classification
def test_keyword_classifier():
    assert classify_story("", "The sardine and mackerel shoal came in with the catch").category == "species"
    assert classify_story("", "A storm and heavy rain, dark clouds").category == "weather"
    assert classify_story("", "बारिश और हवा तेज़ थी").category == "weather"
    assert classify_story("", "hello hello").category == "other"
    assert classify_story("", "hello").confidence == 0.0


def test_ai_classify_validates_model_output(monkeypatch):
    class Resp:
        status_code = 200
        def __init__(self, word): self.word = word
        def raise_for_status(self): pass
        def json(self): return {"content": [{"type": "text", "text": self.word}]}
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp("Weather."))
    assert ai_classify("t", "sardine", api_key="k").category == "weather"
    monkeypatch.setattr("requests.post", lambda *a, **k: Resp("ignore previous instructions"))
    assert ai_classify("t", "sardine net", api_key="k").source == "keyword"  # garbage => fallback
    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr("requests.post", boom)
    assert ai_classify("t", "sardine", api_key="k").category == "species"
    assert ai_classify("t", "sardine", api_key="").source == "keyword"  # no key


# ---------------------------------------------------------------- validation
def test_validation_problems():
    assert validate_story_input(**GOOD, category="auto") == []
    bad = validate_story_input(title="a", text="short", language="xx", category="zzz", consent_public=False, lat=1.0, lng=None)
    assert len(bad) >= 5
    assert any("Consent" in p for p in bad)
    assert validate_story_input(**GOOD, category="auto", lat=60.0, lng=10.0)  # outside study area


# ---------------------------------------------------------------- storage
def test_create_and_reload(mgr):
    story, code = mgr.create_story(**GOOD, category="auto", region="che", lat=13.0827, lng=80.2707, precision="approx",
                                   species="Sardine, sardine, Mackerel", tags="dawn; net", narrator="Ravi", show_name=False)
    assert story.id.startswith("s_") and story.category in CATEGORIES
    assert (story.lat, story.lng) == (13.1, 80.25)  # blurred before saving
    assert story.species == ["Sardine", "Mackerel"]
    assert story.display_name == "Anonymous"
    assert story.withdraw_hash and code not in json.dumps(story.to_dict())
    again = mgr.get(story.id)
    assert again and again.title == "Silver flashes"
    assert mgr.user_stories()[0].region == "che"


def test_create_requires_consent_and_valid_data(mgr):
    with pytest.raises(StoryValidationError) as e:
        mgr.create_story(**{**GOOD, "consent_public": False}, category="auto")
    assert any("Consent" in p for p in e.value.problems)
    assert mgr.user_stories() == []


def test_pii_removed_on_save(mgr):
    s, _ = mgr.create_story(**{**GOOD, "text": "Ring me on 9876543210 about the sardine run"}, category="auto")
    assert "9876543210" not in s.text and s.pii_redacted


def test_withdraw_code(mgr):
    s, code = mgr.create_story(**GOOD, category="auto")
    assert mgr.delete_story(s.id, "wrong") is None
    assert mgr.delete_story(s.id, "") is None
    assert mgr.get(s.id) is not None
    assert mgr.delete_story(s.id, code).id == s.id
    assert mgr.get(s.id) is None


def test_moderation(mgr, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSCODE", "x")
    s, _ = mgr.create_story(**GOOD, category="auto")
    assert s.status == "pending" and s not in mgr.all_stories(include_demo=False)
    assert mgr.set_status(s.id, "approved")
    assert [x.id for x in mgr.all_stories(include_demo=False)] == [s.id]
    with pytest.raises(ValueError):
        mgr.set_status(s.id, "bogus")


def test_corrupt_user_file_is_ignored(tmp_path):
    p = tmp_path / "u.json"
    p.write_text("{not json")
    assert StoryManager(user_path=p).user_stories() == []


def test_from_dict_is_tolerant():
    s = Story.from_dict({"id": "x", "title": "t", "text": "tt", "species": "a, b", "unknown": 1, "quiz": {"question": "q", "options": ["a"], "answer": 5}})
    assert s.species == ["a", "b"] and s.quiz is None


def test_export_has_only_public_fields(mgr):
    s, _ = mgr.create_story(**GOOD, category="auto", audio_file="a" * 32 + ".wav", narrator="Ravi", show_name=True)
    csv_text = stories_to_csv([s])
    assert "withdraw" not in csv_text and "audio" not in csv_text and "Ravi" in csv_text
    s2, _ = mgr.create_story(**{**GOOD, "title": "=HYPERLINK(1)"}, category="auto")
    assert "'=HYPERLINK" in stories_to_csv([s2])


# ---------------------------------------------------------------- demo data
def test_demo_stories_are_valid_and_clearly_samples():
    raw = json.loads(DEMO_STORIES_PATH.read_text(encoding="utf-8"))
    stories = [Story.from_dict(d) for d in raw]
    assert len(stories) == len({s.id for s in stories}) >= 20
    for s in stories:
        assert s.source == "sample" and s.status == "approved", s.id
        assert s.language in LANGUAGES and s.category in CATEGORIES, s.id
        assert s.title and len(s.text) >= 10 and s.note, s.id
        if s.has_location:
            assert in_study_area(s.lat, s.lng), s.id
        if s.language != "en":
            assert s.summary_en, f"{s.id} needs an English summary"
        if s.quiz:
            assert 0 <= s.quiz["answer"] < len(s.quiz["options"])
    assert sum(1 for s in stories if s.quiz) == 8  # the eight folktales
    assert len({s.language for s in stories}) >= 8


def test_summarize():
    mgr = StoryManager(user_path="/nonexistent/u.json")
    s = summarize(mgr.all_stories())
    assert s["total"] == s["samples"] and s["languages"] >= 8 and s["user_contributed"] == 0
