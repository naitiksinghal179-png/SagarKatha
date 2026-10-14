"""Run every Streamlit page headlessly and make sure none of them raises."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["app.py", "pages/1_Contribute_Story.py", "pages/2_Story_Library.py", "pages/3_Coastal_Map.py", "pages/4_Dialect_Glossary.py"]


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SAGARKATHA_DATA_DIR", str(tmp_path))
    import src.story_manager as sm, src.audio_handler as ah
    monkeypatch.setattr(sm, "USER_STORIES_PATH", tmp_path / "user_stories.json")
    monkeypatch.setattr(ah, "AUDIO_DIR", tmp_path / "audio")


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_without_exceptions(page):
    at = AppTest.from_file(str(ROOT / page), default_timeout=90).run()
    assert not at.exception, [e.value for e in at.exception]


def test_library_search_filters_results():
    at = AppTest.from_file(str(ROOT / "pages/2_Story_Library.py"), default_timeout=90).run()
    at.text_input(key="lib_q").set_value("Bonbibi").run()
    assert not at.exception
    assert any("Bonbibi" in m.value for m in at.markdown)


def test_glossary_search():
    at = AppTest.from_file(str(ROOT / "pages/4_Dialect_Glossary.py"), default_timeout=90).run()
    at.text_input(key="g_q").set_value("sardine").run()
    assert not at.exception


def test_contribute_requires_consent_then_saves():
    at = AppTest.from_file(str(ROOT / "pages/1_Contribute_Story.py"), default_timeout=90).run()
    save = next(b for b in at.button if b.label == "Save my story")
    assert save.disabled  # no consent yet
    at.checkbox(key="c1_0").check()
    at.text_input(key="title_0").set_value("Dawn shoal")
    at.text_area(key="text_0").set_value("At first light we look for silver flashes on the water and cast the net.")
    at.run()
    next(b for b in at.button if b.label == "Save my story").click().run()
    assert not at.exception and not at.error
    assert any("saved" in s.value.lower() for s in at.success)
    assert at.session_state["saved"]["code"]
