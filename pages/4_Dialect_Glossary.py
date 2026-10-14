"""Dialect glossary: the same sea-word in different languages and coasts."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.search import glossary_concepts, glossary_languages, load_glossary, same_concept, search_glossary
from src.story_manager import CATEGORIES, LANGUAGES, language_label
from src.ui import page_header

page_header("Dialect glossary", "How fishers name the same fish, boat or tide along different coasts.", "🔤")

entries = load_glossary()
if not entries:
    st.error("The glossary file `data/dialect_glossary.csv` is missing or empty.")
    st.stop()

st.warning(
    "**Draft word list.** Every entry is marked *needs review* until a native speaker from the coast confirms the word, "
    "its spelling and where it is used. Please correct us.",
    icon="📝",
)

q = st.text_input("Search a word, meaning or language", placeholder="sardine, net, बोंबील, வலை, tide …", key="g_q")
c1, c2, c3 = st.columns(3)
language = c1.selectbox("Language", [""] + glossary_languages(entries), format_func=lambda c: "All languages" if not c else language_label(c))
concept = c2.selectbox("Concept", [""] + glossary_concepts(entries), format_func=lambda c: "All concepts" if not c else c.replace("_", " ").title())
category = c3.selectbox("Type", [""] + sorted({e["category"] for e in entries}), format_func=lambda k: "All types" if not k else CATEGORIES.get(k, CATEGORIES["other"])["label"])

results = search_glossary(entries, q, language=language or None, category=category or None, concept=concept or None)
st.caption(f"{len(results)} of {len(entries)} words")

df = pd.DataFrame(
    [
        {
            "Word": e["term"],
            "Sounds like": e["transliteration"],
            "Language": LANGUAGES.get(e["language"], {"name": e["language"]})["name"],
            "Where": e["dialect_region"],
            "Meaning": e["meaning_en"],
            "Note": e["usage_note"],
            "Status": e["status"].replace("_", " "),
        }
        for e in results
    ]
)
st.dataframe(df, hide_index=True, width="stretch")

st.subheader("Compare one concept across languages")
pick = st.selectbox("Concept to compare", glossary_concepts(entries), format_func=lambda c: c.replace("_", " ").title(), key="g_cmp")
group = [e for e in entries if e["concept"] == pick]
if group:
    cols = st.columns(min(4, len(group)))
    for i, e in enumerate(sorted(group, key=lambda e: (e["language"], e["term"]))):
        with cols[i % len(cols)].container(border=True):
            st.markdown(f"### {e['term']}")
            st.caption(f"{e['transliteration']} · {LANGUAGES.get(e['language'], {'name': e['language']})['name']}")
            st.write(e["dialect_region"])

st.download_button("⬇ Download glossary (CSV)", pd.DataFrame(entries).to_csv(index=False), "sagarkatha_glossary.csv", "text/csv")
st.caption("Open the CSV in Excel via *Data → From Text/CSV* and choose UTF-8 so the scripts display correctly. Want to add words? See `docs/user_journey.md`.")
