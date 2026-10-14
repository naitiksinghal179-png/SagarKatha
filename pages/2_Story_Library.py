"""Story library: search, filter, listen, test yourself, export, withdraw, moderate."""

from __future__ import annotations

import hmac
import os

import pandas as pd
import streamlit as st

from src.audio_handler import delete_audio
from src.search import search_stories
from src.story_manager import (
    CATEGORIES,
    LANGUAGES,
    REGIONS,
    language_label,
    moderation_enabled,
    stories_to_csv,
    stories_to_json,
    summarize,
)
from src.ui import get_manager, page_header, sample_notice, story_card

page_header("Story library", "Search the archive by word, language, place or topic. Works in every script – try *बोंबील*, *sardine* or *ചാകര*.", "📚")
manager = get_manager()
all_stories = manager.all_stories()
sample_notice()

with st.container(border=True):
    q = st.text_input("Search", placeholder="sardine, bombil, monsoon, ചാകര, बोंबील …", key="lib_q")
    c1, c2, c3, c4 = st.columns(4)
    lang_codes = sorted({s.language for s in all_stories})
    language = c1.selectbox("Language", [""] + lang_codes, format_func=lambda c: "All languages" if not c else language_label(c))
    region = c2.selectbox("Region", [""] + [r.id for r in REGIONS], format_func=lambda i: "All regions" if not i else next(r.name for r in REGIONS if r.id == i))
    category = c3.selectbox("Topic", [""] + list(CATEGORIES), format_func=lambda k: "All topics" if not k else f"{CATEGORIES[k]['icon']} {CATEGORIES[k]['label']}")
    source = c4.selectbox("Source", ["", "user", "sample"], format_func=lambda k: {"": "All", "user": "Contributed by users", "sample": "Sample stories"}[k])

hits = search_stories(all_stories, q, language=language or None, region=region or None, category=category or None, source=source or None)
shown = [h.story for h in hits]

tab_list, tab_stats, tab_export, tab_manage = st.tabs(["Stories", "Report", "Export", "Withdraw / moderate"])

with tab_list:
    st.caption(f"{len(shown)} of {len(all_stories)} stories")
    if not shown:
        st.info("No stories match. Try fewer filters or a different word.")
    for h in hits[:50]:
        story_card(h.story, key=f"card_{h.story.id}")
    if len(hits) > 50:
        st.caption("Showing the first 50 results – narrow the search to see more.")

with tab_stats:
    s = summarize(shown)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Stories", s["total"])
    m2.metric("Languages", s["languages"])
    m3.metric("With a map pin", s["with_location"])
    m4.metric("With audio", s["with_audio"])
    if s["total"]:
        left, right = st.columns(2)
        cat_df = pd.DataFrame({"Topic": [CATEGORIES.get(k, CATEGORIES["other"])["label"] for k in s["by_category"]], "Stories": list(s["by_category"].values())}).set_index("Topic")
        lang_df = pd.DataFrame({"Language": [LANGUAGES.get(k, {"name": k})["name"] for k in s["by_language"]], "Stories": list(s["by_language"].values())}).set_index("Language")
        left.markdown("**By topic**")
        left.bar_chart(cat_df)
        right.markdown("**By language**")
        right.bar_chart(lang_df)
    st.caption("This report counts the stories currently shown by the search and filters above.")

with tab_export:
    st.write("Downloads contain public fields only: no audio file names, no withdraw codes, and names only when the narrator chose to show them.")
    d1, d2 = st.columns(2)
    d1.download_button("⬇ CSV", stories_to_csv(shown), "sagarkatha_stories.csv", "text/csv", disabled=not shown, width="stretch")
    d2.download_button("⬇ JSON", stories_to_json(shown), "sagarkatha_stories.json", "application/json", disabled=not shown, width="stretch")

with tab_manage:
    st.markdown("#### Withdraw my story")
    st.caption("Enter the story id and the withdraw code you were given when you saved it. The story and its recording are deleted.")
    w1, w2 = st.columns(2)
    wid = w1.text_input("Story id", placeholder="s_1a2b3c4d5e", key="wd_id")
    wcode = w2.text_input("Withdraw code", type="password", key="wd_code")
    if st.button("Delete my story"):
        deleted = manager.delete_story(wid.strip(), wcode)
        if deleted:
            if deleted.audio_file:
                delete_audio(deleted.audio_file)
            st.success("Your story was deleted.")
        else:
            st.error("That id and code do not match a story.")

    st.markdown("#### Moderator")
    if not moderation_enabled():
        st.caption("Moderation is off. Set `ADMIN_PASSCODE` in the environment to review stories before they appear.")
    else:
        pw = st.text_input("Admin passcode", type="password", key="adm_pw")
        st.session_state.setdefault("adm_tries", 0)
        if pw:
            if st.session_state["adm_tries"] >= 5:
                st.error("Too many attempts in this session.")
            elif hmac.compare_digest(pw.encode(), os.environ["ADMIN_PASSCODE"].encode()):
                pending = manager.pending()
                st.write(f"{len(pending)} story(ies) waiting.")
                for p in pending:
                    story_card(p, key=f"mod_{p.id}")
                    a, b = st.columns(2)
                    if a.button("Approve", key=f"ap_{p.id}"):
                        manager.set_status(p.id, "approved")
                        st.rerun()
                    if b.button("Reject", key=f"rj_{p.id}"):
                        manager.set_status(p.id, "rejected")
                        st.rerun()
            else:
                st.session_state["adm_tries"] += 1
                st.error("Wrong passcode.")
