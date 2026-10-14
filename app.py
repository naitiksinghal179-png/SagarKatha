"""SagarKatha (सागरकथा) – home page and navigation.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

try:  # optional: read a local .env file
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv not installed – environment variables still work
    pass

from src.story_manager import SCHEDULED_LANGUAGE_CODES, summarize
from src.ui import (
    APP_NAME,
    APP_NATIVE,
    EMERGENCY,
    TAGLINE,
    get_manager,
    inject_css,
    language_names_line,
    render_sidebar,
    sample_notice,
)

st.set_page_config(page_title=f"{APP_NAME} – {TAGLINE}", page_icon="🌊", layout="wide")


def home() -> None:
    inject_css()
    render_sidebar()
    manager = get_manager()
    stories = manager.all_stories()
    stats = summarize(stories)

    st.markdown(
        f"<div class='sk-hero'><h1>🌊 {APP_NAME} · {APP_NATIVE}</h1>"
        f"<p>{TAGLINE}. India's fishers know the sea in a way no instrument does – "
        "which fish come when, how the water and sky behave, the tales that keep people safe. "
        "SagarKatha helps them record it in their own language, so it is not lost.</p></div>",
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Stories in the archive", stats["total"])
    c2.metric("Languages", stats["languages"])
    c3.metric("Pinned on the map", stats["with_location"])
    c4.metric("Contributed by users", stats["user_contributed"])
    sample_notice()

    st.subheader("How it works")
    a, b, c = st.columns(3)
    with a:
        st.markdown("#### 1 · Speak or type")
        st.write("Record a short story with your phone's microphone or write it down – in any of the 22 scheduled languages or a local dialect.")
    with b:
        st.markdown("#### 2 · Keep it safe")
        st.write("You give consent first, choose how precisely the place is shown, and can withdraw your story at any time.")
    with c:
        st.markdown("#### 3 · Share and learn")
        st.write("Stories are sorted into topics, searchable, pinned on a coastal map next to live ocean currents, and collected into a dialect glossary.")

    st.subheader("Start here")
    n1, n2, n3, n4 = st.columns(4)
    n1.page_link("pages/1_Contribute_Story.py", label="Contribute a story", icon="🎙️")
    n2.page_link("pages/2_Story_Library.py", label="Story library", icon="📚")
    n3.page_link("pages/3_Coastal_Map.py", label="Coastal map & ocean", icon="🗺️")
    n4.page_link("pages/4_Dialect_Glossary.py", label="Dialect glossary", icon="🔤")

    with st.expander(f"All {len(SCHEDULED_LANGUAGE_CODES)} scheduled languages are supported for stories"):
        st.write(language_names_line())
        st.caption(
            "Story text and the glossary work in every scheduled language, plus English and 'other / local dialect'. "
            "Automatic speech-to-text covers fewer languages (see the Contribute page). The app interface itself is currently in English."
        )
    st.info(EMERGENCY + " Ocean advice on this site is indicative only – follow INCOIS / IMD advisories.", icon="🚨")


pages = [
    st.Page(home, title="Home", icon="🌊", default=True),
    st.Page("pages/1_Contribute_Story.py", title="Contribute a story", icon="🎙️", url_path="contribute"),
    st.Page("pages/2_Story_Library.py", title="Story library", icon="📚", url_path="library"),
    st.Page("pages/3_Coastal_Map.py", title="Coastal map & ocean", icon="🗺️", url_path="map"),
    st.Page("pages/4_Dialect_Glossary.py", title="Dialect glossary", icon="🔤", url_path="glossary"),
]
st.navigation(pages).run()
