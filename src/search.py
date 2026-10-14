"""Search for the Story Library and the Dialect Glossary.

Pure Python, no dependencies.  Two details matter for Indian languages:

* **Tokenisation.**  ``\\w`` in Python's ``re`` module does *not* match
  combining marks, so a Devanagari word such as ``मछली`` would be cut into
  pieces at every vowel sign.  :func:`tokenize` therefore keeps letters,
  combining marks and digits together (Unicode categories ``L*``, ``M*``,
  ``N*``).
* **Normalisation.**  Text is NFKC-normalised and case-folded; the zero-width
  (non-)joiners that people type inconsistently are removed.

Ranking is a small BM25 implementation with field weights (title > tags/species
> place > body).  Prefix matching lets ``sardin`` find ``sardines``.
"""

from __future__ import annotations

import csv
import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from src.story_manager import LANGUAGES, REGION_BY_ID, Story

# --------------------------------------------------------------------------- #
# Text processing
# --------------------------------------------------------------------------- #

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))


def _fold_latin_diacritics(text: str) -> str:
    """``bombīl`` -> ``bombil``: strip accents from *Latin* letters only.

    Combining marks that follow Indic letters (vowel signs, viramas) are kept –
    removing them would change the word.
    """
    out: list[str] = []
    last_latin = False
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn" and last_latin:
            continue
        out.append(ch)
        last_latin = ch.isascii() and ch.isalpha()
    return unicodedata.normalize("NFC", "".join(out))


def normalize(text: str) -> str:
    """NFKC + drop zero-width characters + casefold + fold Latin accents.

    Transliterations such as ``bombīl`` or ``sālai`` therefore match what people
    type on a plain keyboard (``bombil``, ``salai``).
    """
    text = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH).casefold()
    return _fold_latin_diacritics(text)


def tokenize(text: str) -> list[str]:
    """Split into word tokens, keeping Indic combining marks inside words."""
    tokens: list[str] = []
    buf: list[str] = []
    for ch in normalize(text):
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "M", "N"):
            buf.append(ch)
        elif buf:
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return tokens


# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #

FIELD_WEIGHTS = {"title": 3.0, "tags": 2.0, "place": 1.5, "text": 1.0}
_K1, _B = 1.4, 0.75
_PREFIX_MIN = 3  # query terms shorter than this must match whole tokens
_PREFIX_FACTOR = 0.6


@dataclass
class SearchHit:
    story: Story
    score: float
    matched: list[str] = field(default_factory=list)


def _story_fields(s: Story) -> dict[str, list[str]]:
    place = " ".join(
        filter(None, [s.state, s.dialect, REGION_BY_ID[s.region].name if s.region in REGION_BY_ID else ""])
    )
    return {
        "title": tokenize(s.title),
        "tags": tokenize(" ".join(s.tags + s.species)),
        "place": tokenize(place),
        "text": tokenize(f"{s.text} {s.summary_en}"),
    }


def _tf(term: str, tokens: Sequence[str]) -> float:
    exact = sum(1 for t in tokens if t == term)
    if len(term) >= _PREFIX_MIN:
        prefix = sum(1 for t in tokens if t != term and t.startswith(term))
        return exact + _PREFIX_FACTOR * prefix
    return float(exact)


def _rank(docs: Sequence[dict[str, list[str]]], query_terms: Sequence[str]) -> list[tuple[float, list[str]]]:
    """BM25F-style scores for every document. Returns ``[(score, matched_terms), ...]``."""
    n = len(docs)
    lengths = [sum(len(v) for v in d.values()) or 1 for d in docs]
    avg = sum(lengths) / n if n else 1.0
    # document frequency per query term
    df = {t: sum(1 for d in docs if any(_tf(t, toks) > 0 for toks in d.values())) for t in query_terms}
    results: list[tuple[float, list[str]]] = []
    for d, length in zip(docs, lengths):
        score, matched = 0.0, []
        for t in query_terms:
            tf = sum(FIELD_WEIGHTS.get(name, 1.0) * _tf(t, toks) for name, toks in d.items())
            if tf <= 0:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * (tf * (_K1 + 1)) / (tf + _K1 * (1 - _B + _B * length / avg))
            matched.append(t)
        results.append((score, matched))
    return results


# --------------------------------------------------------------------------- #
# Story search
# --------------------------------------------------------------------------- #


def filter_stories(
    stories: Iterable[Story],
    *,
    language: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
    state: Optional[str] = None,
    source: Optional[str] = None,
) -> list[Story]:
    """Exact-match filters; ``None`` / empty means "any"."""
    out = []
    for s in stories:
        if language and s.language != language:
            continue
        if region and s.region != region:
            continue
        if category and s.category != category:
            continue
        if state and s.state != state:
            continue
        if source and s.source != source:
            continue
        out.append(s)
    return out


def search_stories(
    stories: Iterable[Story],
    query: str = "",
    *,
    language: Optional[str] = None,
    region: Optional[str] = None,
    category: Optional[str] = None,
    state: Optional[str] = None,
    source: Optional[str] = None,
    match_all: bool = False,
) -> list[SearchHit]:
    """Search + filter. With no query, returns every filtered story (newest first).

    ``match_all=True`` requires every query term to match (AND); the default is
    OR with ranking, which is friendlier for short multilingual queries.
    """
    pool = filter_stories(stories, language=language, region=region, category=category, state=state, source=source)
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        pool = sorted(pool, key=lambda s: (s.created_at, s.id), reverse=True)
        return [SearchHit(s, 0.0, []) for s in pool]
    ranked = _rank([_story_fields(s) for s in pool], terms)
    hits = [
        SearchHit(s, round(score, 4), matched)
        for s, (score, matched) in zip(pool, ranked)
        if score > 0 and (not match_all or len(matched) == len(terms))
    ]
    hits.sort(key=lambda h: (-h.score, h.story.created_at, h.story.id))
    return hits


# --------------------------------------------------------------------------- #
# Dialect glossary
# --------------------------------------------------------------------------- #

GLOSSARY_COLUMNS = (
    "id", "term", "transliteration", "language", "dialect_region", "concept",
    "category", "meaning_en", "usage_note", "status",
)
GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "data" / "dialect_glossary.csv"


def load_glossary(path: Optional[Path | str] = None) -> list[dict[str, str]]:
    """Read the glossary CSV (UTF-8, with or without BOM). Missing file => empty list."""
    p = Path(path) if path else GLOSSARY_PATH
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = [{k: (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(fh)]
    return [r for r in rows if r.get("term")]


def _glossary_fields(e: Mapping[str, str]) -> dict[str, list[str]]:
    lang = LANGUAGES.get(e.get("language", ""), {}).get("name", e.get("language", ""))
    return {
        "title": tokenize(f'{e.get("term", "")} {e.get("transliteration", "")}'),
        "tags": tokenize(f'{e.get("concept", "")} {e.get("meaning_en", "")}'),
        "place": tokenize(f'{lang} {e.get("dialect_region", "")}'),
        "text": tokenize(e.get("usage_note", "")),
    }


def search_glossary(
    entries: Iterable[Mapping[str, str]],
    query: str = "",
    *,
    language: Optional[str] = None,
    category: Optional[str] = None,
    concept: Optional[str] = None,
) -> list[dict[str, str]]:
    """Rank glossary entries by term / transliteration / meaning; supports filters."""
    pool = [
        dict(e)
        for e in entries
        if (not language or e.get("language") == language)
        and (not category or e.get("category") == category)
        and (not concept or e.get("concept") == concept)
    ]
    terms = list(dict.fromkeys(tokenize(query)))
    if not terms:
        return sorted(pool, key=lambda e: (e.get("concept", ""), e.get("language", ""), normalize(e.get("term", ""))))
    ranked = _rank([_glossary_fields(e) for e in pool], terms)
    scored = [(score, e) for e, (score, _m) in zip(pool, ranked) if score > 0]
    scored.sort(key=lambda p: (-p[0], normalize(p[1].get("term", ""))))
    return [e for _s, e in scored]


def same_concept(entries: Iterable[Mapping[str, str]], entry: Mapping[str, str]) -> list[dict[str, str]]:
    """Other glossary words for the same concept (e.g. *sardine* in other languages / dialects)."""
    concept = entry.get("concept", "")
    if not concept:
        return []
    return [dict(e) for e in entries if e.get("concept") == concept and e.get("id") != entry.get("id")]


def glossary_concepts(entries: Iterable[Mapping[str, str]]) -> list[str]:
    return sorted({e.get("concept", "") for e in entries if e.get("concept")})


def glossary_languages(entries: Iterable[Mapping[str, str]]) -> list[str]:
    return sorted({e.get("language", "") for e in entries if e.get("language")})


def validate_glossary(entries: Iterable[Mapping[str, Any]]) -> list[str]:
    """Data-quality check used by the tests and the contributor guide."""
    problems: list[str] = []
    seen: set[str] = set()
    for i, e in enumerate(entries, start=2):  # row 1 is the header
        eid = e.get("id", "")
        if not eid:
            problems.append(f"row {i}: missing id")
        elif eid in seen:
            problems.append(f"row {i}: duplicate id {eid}")
        seen.add(eid)
        for col in ("term", "language", "concept", "meaning_en", "status"):
            if not e.get(col):
                problems.append(f"row {i} ({eid}): missing {col}")
        if e.get("language") and e["language"] not in LANGUAGES:
            problems.append(f"row {i} ({eid}): unknown language code {e['language']!r}")
    return problems
