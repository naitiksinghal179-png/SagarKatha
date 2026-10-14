from src.search import (
    glossary_concepts, load_glossary, normalize, same_concept, search_glossary, search_stories, tokenize, validate_glossary,
)
from src.story_manager import StoryManager, Story


def S(i, title, text, **kw):
    return Story(id=i, title=title, text=text, created_at=kw.pop("created_at", "2026-01-01"), **kw)


STORIES = [
    S("a", "Sardine shoals at dawn", "We circle the shoal with a ring net.", language="en", category="technique", tags=["dawn"]),
    S("b", "Monsoon winds", "The wind swings north-east before the storm.", language="en", category="weather", region="che"),
    S("c", "बोंबील अब दूर जाने लगी है", "मानसून में बोंबील किनारे के पास आती थी।", language="hi", category="change", summary_en="Bombil moved offshore"),
    S("d", "ചാകര", "മഴക്കാലത്ത് കടൽ കലങ്ങി ശാന്തമാകും. മത്തി കരയോട് അടുത്ത് വരും.", language="ml", category="species", summary_en="Chakara brings sardines close"),
]


def test_tokenizer_keeps_indic_words_whole():
    assert tokenize("मछली-पकड़ना, ചാകര! sardines.") == ["मछली", "पकड़ना", "ചാകര", "sardines"]
    assert tokenize("") == [] and tokenize("  ,, ") == []


def test_normalisation():
    assert normalize("Bombīl") == "bombil" == normalize("BOMBIL")
    assert normalize("a​b") == "ab"  # zero-width removed
    assert normalize("किनारे") == "किनारे"  # Indic vowel signs are preserved, not stripped


def test_ranking_and_prefix():
    r = search_stories(STORIES, "sardin")
    assert [h.story.id for h in r][:2] == ["a", "d"]  # prefix match + English summary of the Malayalam story
    assert search_stories(STORIES, "shoal")[0].story.id == "a"


def test_search_in_indian_scripts():
    assert [h.story.id for h in search_stories(STORIES, "बोंबील")] == ["c"]
    assert [h.story.id for h in search_stories(STORIES, "ചാകര")] == ["d"]
    assert [h.story.id for h in search_stories(STORIES, "bombil")] == ["c"]  # via English summary


def test_filters_and_empty_query():
    assert {h.story.id for h in search_stories(STORIES, "")} == {"a", "b", "c", "d"}
    assert [h.story.id for h in search_stories(STORIES, "", language="hi")] == ["c"]
    assert [h.story.id for h in search_stories(STORIES, "wind", category="weather", region="che")] == ["b"]
    assert search_stories(STORIES, "wind", language="ml") == []
    assert search_stories(STORIES, "zzzzqq") == []


def test_match_all():
    assert [h.story.id for h in search_stories(STORIES, "ring net dawn", match_all=True)] == ["a"]
    assert search_stories(STORIES, "ring storm", match_all=True) == []


def test_empty_query_orders_newest_first():
    items = [S("old", "x", "xx", created_at="2020"), S("new", "y", "yy", created_at="2026")]
    assert [h.story.id for h in search_stories(items, "")] == ["new", "old"]


def test_demo_data_is_searchable():
    stories = StoryManager(user_path="/nonexistent/u.json").all_stories()
    assert search_stories(stories, "Bonbibi")
    assert search_stories(stories, "chakara")
    assert search_stories(stories, "बोंबील")  # Marathi/Hindi sample stories are found


# ---------------------------------------------------------------- glossary
def test_glossary_file_is_valid():
    entries = load_glossary()
    assert len(entries) >= 50
    assert validate_glossary(entries) == []
    assert all(e["status"] == "needs_review" for e in entries)  # nothing is claimed as verified


def test_glossary_search_and_concepts():
    g = load_glossary()
    assert {"sardine", "net", "boat", "high_tide"} <= set(glossary_concepts(g))
    terms = [e["term"] for e in search_glossary(g, "sardine")]
    assert "മത്തി" in terms and "சாளை" in terms
    assert [e["term"] for e in search_glossary(g, "salai")] == ["சாளை"]  # accent-folded transliteration
    assert [e["term"] for e in search_glossary(g, "வலை")] == ["வலை"]
    assert search_glossary(g, "", language="ml") and all(e["language"] == "ml" for e in search_glossary(g, "", language="ml"))
    assert search_glossary(g, "nothing-matches-this") == []


def test_same_concept():
    g = load_glossary()
    sardine = next(e for e in g if e["transliteration"] == "mathi")
    others = same_concept(g, sardine)
    assert others and all(o["concept"] == "sardine" and o["id"] != sardine["id"] for o in others)


def test_validate_glossary_catches_problems():
    bad = [{"id": "1", "term": "x", "language": "zz", "concept": "c", "meaning_en": "m", "status": "s"}, {"id": "1", "term": "", "language": "hi", "concept": "", "meaning_en": "", "status": ""}]
    problems = validate_glossary(bad)
    assert any("unknown language" in p for p in problems) and any("duplicate" in p for p in problems) and any("missing" in p for p in problems)
