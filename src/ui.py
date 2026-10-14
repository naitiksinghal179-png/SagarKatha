"""Small shared Streamlit helpers (sidebar, cards, notices) used by every page.

Kept separate from the five core modules so that those stay Streamlit-free and
unit-testable.
"""

from __future__ import annotations

import streamlit as st

from src.audio_handler import read_audio
from src.story_manager import (
    CATEGORIES,
    LANGUAGES,
    REGION_BY_ID,
    SCHEDULED_LANGUAGE_CODES,
    Story,
    StoryManager,
    category_label,
    language_label,
    md_escape,
    moderation_enabled,
)

APP_NAME = "SagarKatha"
APP_NATIVE = "सागरकथा"
TAGLINE = "Stories of the sea, saved for tomorrow"
EMERGENCY = "Emergency at sea: Indian Coast Guard toll-free **1554**."

_CSS = """
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.sk-hero {padding: 1.4rem 1.6rem; border-radius: 16px;
  background: linear-gradient(135deg, #0B3C5D 0%, #1B6A8A 60%, #2B8CBE 100%); color: #fff; margin-bottom: 1rem;}
.sk-hero h1 {color: #fff; margin: 0; font-size: 2.2rem;}
.sk-hero p {margin: .3rem 0 0; opacity: .92; font-size: 1.05rem;}
.sk-badge {display:inline-block; padding: 1px 8px; border-radius: 999px; font-size: .75rem;
  background: #FFF3CD; color: #664d03; border: 1px solid #ffe69c;}
</style>
"""


@st.cache_resource
def get_manager() -> StoryManager:
    """One shared :class:`StoryManager` per server process."""
    return StoryManager()


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown(f"### 🌊 {APP_NAME}  \n**{APP_NATIVE}**")
        st.caption(TAGLINE)
        st.info(EMERGENCY, icon="🚨")
        st.caption(
            "Built for the Viksit Bharat Young Leaders Dialogue (VBYLD) 2027. "
            "Open source – see the README for licences and data sources."
        )
        if not moderation_enabled():
            st.caption("🔓 Moderation is off (no `ADMIN_PASSCODE` set) – new stories appear immediately.")


def page_header(title: str, subtitle: str = "", icon: str = "") -> None:
    inject_css()
    render_sidebar()
    st.title(f"{icon} {title}".strip())
    if subtitle:
        st.caption(subtitle)


def sample_notice() -> None:
    st.markdown(
        '<span class="sk-badge">SAMPLE DATA</span> Stories marked <i>sample</i> were written for this demo '
        "to show how the app works. They are not real fishers' recordings.",
        unsafe_allow_html=True,
    )


def md_text(text: str) -> str:
    """Escape user text for ``st.markdown`` and keep its line breaks."""
    return md_escape(text).replace("\n", "  \n")


def story_card(story: Story, *, key: str) -> None:
    """Render one story. All user-supplied text is escaped."""
    cat = CATEGORIES.get(story.category, CATEGORIES["other"])
    lang = language_label(story.language)
    region = REGION_BY_ID.get(story.region)
    place = f"{region.name}, {story.state}" if region else (story.state or "location not shared")
    with st.container(border=True):
        head = f"**{cat['icon']} {md_escape(story.title)}**"
        if story.is_sample:
            head += "  :orange-badge[sample]"
        if story.status == "pending":
            head += "  :gray-badge[awaiting review]"
        st.markdown(head)
        st.caption(f"{cat['label']} · {lang} · {place} · told by {md_escape(story.display_name)}")
        st.markdown(md_text(story.text))
        if story.summary_en:
            st.markdown(f"*English summary:* {md_text(story.summary_en)}")
        if story.lesson:
            st.markdown(f"💡 *{md_escape(story.lesson)}*")
        meta = [t for t in (story.species + story.tags) if t]
        if meta:
            st.caption("🏷️ " + " · ".join(md_escape(m) for m in meta[:10]))
        if story.dialect:
            st.caption(f"Dialect: {md_escape(story.dialect)}")
        if story.audio_file and story.audio_public:
            got = read_audio(story.audio_file)
            if got:
                st.audio(got[0], format=got[1])
        if story.note and story.is_sample:
            st.caption("ℹ️ " + md_escape(story.note))
        if story.quiz:
            _quiz(story, key)


def _quiz(story: Story, key: str) -> None:
    q = story.quiz or {}
    with st.expander("🧠 Test yourself"):
        st.write(q["question"])
        choice = st.radio("Your answer", q["options"], index=None, key=f"{key}_q", label_visibility="collapsed")
        if st.button("Check answer", key=f"{key}_b"):
            if choice is None:
                st.warning("Pick an answer first.")
            elif q["options"].index(choice) == q["answer"]:
                st.success("Correct! 🎉")
            else:
                st.error("Not quite – read the tale again and try once more.")


def language_names_line() -> str:
    return " · ".join(str(LANGUAGES[c]["native"]) for c in SCHEDULED_LANGUAGE_CODES)
