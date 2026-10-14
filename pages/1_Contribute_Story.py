"""Contribute a story: consent → record or upload → transcript → place → save."""

from __future__ import annotations

import os

import streamlit as st

from src.audio_handler import UPLOAD_TYPES, AudioError, delete_audio, format_duration, save_audio, validate_audio
from src.story_manager import (
    CATEGORIES,
    LANGUAGES,
    PRECISIONS,
    REGIONS,
    TEXT_MAX,
    StoryValidationError,
    contains_pii,
    language_label,
    moderation_enabled,
)
from src.transcription import PROVIDER_LABELS, TranscriptionError, available_providers, supports, transcribe
from src.ui import get_manager, page_header

page_header("Contribute a story", "A story, a sign you read in the sea, a fishing method, a tale – in your own words.", "🎙️")
manager = get_manager()
st.session_state.setdefault("nonce", 0)
n = st.session_state["nonce"]  # changing it resets every widget after a successful save

done = st.session_state.get("saved")
if done:
    st.success("Thank you! Your story was saved." + (" It will appear after a moderator approves it." if done["pending"] else ""))
    st.warning(
        "**Keep this withdraw code.** It is the only way to delete your story later, and it is shown only once.",
        icon="🔑",
    )
    st.code(done["code"], language=None)
    st.caption(f"Story id: {done['id']}")
    if st.button("Add another story"):
        st.session_state["nonce"] += 1
        st.session_state.pop("saved", None)
        st.rerun()
    st.stop()

# ---------------------------------------------------------------- 1. consent
st.subheader("1 · Your consent")
with st.container(border=True):
    st.markdown(
        "- Your story will be shown **publicly** in the SagarKatha library (after review, if moderation is on).\n"
        "- **Do not** include phone numbers, addresses, ID numbers or other people's private details. "
        "Phone numbers and e-mail addresses are removed automatically; names are not.\n"
        "- You choose how precisely the place is shown. The exact spot is never stored unless you pick *Exact*.\n"
        "- You can delete your story later with a withdraw code.\n"
        "- Recording someone else? Get their permission first. Under 18? Ask a parent or guardian."
    )
    consent_public = st.checkbox("I am the narrator, or I have the narrator's permission, and I agree to share this story publicly.", key=f"c1_{n}")
    consent_research = st.checkbox("(Optional) Researchers may also use this story for non-commercial study of ocean knowledge and language.", key=f"c2_{n}")

# ------------------------------------------------------------------ 2. audio
st.subheader("2 · Record or upload (optional)")
st.caption("Use your phone or computer microphone – your browser will ask for permission – or upload a file. You can also skip this and just type.")
col_rec, col_up = st.columns(2)
with col_rec:
    recorded = st.audio_input("Record with the microphone", key=f"rec_{n}")
with col_up:
    uploaded = st.file_uploader("…or upload an audio file", type=UPLOAD_TYPES, key=f"up_{n}")
audio_bytes, audio_name = (None, "")
if recorded is not None:
    audio_bytes, audio_name = recorded.getvalue(), "recording.wav"
elif uploaded is not None:
    audio_bytes, audio_name = uploaded.getvalue(), uploaded.name
audio_ok = False
if audio_bytes:
    try:
        fmt, dur = validate_audio(audio_bytes, audio_name)
        st.audio(audio_bytes)
        st.caption(f"{fmt.upper()} · {format_duration(dur)} · {len(audio_bytes) / 1024:.0f} KB")
        audio_ok = True
    except AudioError as exc:
        st.error(str(exc))
audio_public = False
if audio_ok:
    audio_public = st.checkbox("Let visitors listen to my recording (otherwise only the text is public)", value=True, key=f"ap_{n}")

# ------------------------------------------------------------------ 3. story
st.subheader("3 · The story")
language = st.selectbox("Language of the story", list(LANGUAGES), index=list(LANGUAGES).index("hi"), format_func=language_label, key=f"lang_{n}")
dialect = st.text_input("Dialect or community name (optional)", placeholder="e.g. Agri Koli, Mangalorean Konkani, Tulu", max_chars=60, key=f"dia_{n}")

providers = [p for p in available_providers() if p != "manual"]
if audio_ok and providers:
    usable = [p for p in providers if supports(p, language)]
    if usable:
        c1, c2 = st.columns([2, 1])
        prov = c1.selectbox("Transcribe automatically with", usable, format_func=PROVIDER_LABELS.get, key=f"prov_{n}")
        if c2.button("Transcribe", width="stretch", key=f"tr_{n}"):
            with st.spinner("Listening…"):
                try:
                    res = transcribe(audio_bytes, language, prov, filename=audio_name)
                    st.session_state[f"text_{n}"] = res.text
                    st.session_state[f"tsrc_{n}"] = res.provider
                except TranscriptionError as exc:
                    st.error(str(exc))
        st.caption("Your audio is sent to the chosen provider only when you press the button. Machine transcripts can be wrong – please check and fix them.")
    else:
        st.caption(f"Automatic transcription is not available for {LANGUAGES[language]['name']}. Please type the story.")
elif audio_ok:
    st.caption("No speech-to-text key is configured, so please type what you said. (Admins: see `.env.example`.)")

title = st.text_input("Title", max_chars=120, key=f"title_{n}")
text = st.text_area(f"Story text (up to {TEXT_MAX} characters)", height=200, max_chars=TEXT_MAX, key=f"text_{n}")
if text and contains_pii(text):
    st.warning("This looks like it contains a phone number, e-mail or ID number. It will be removed when you save.", icon="⚠️")
summary_en = ""
if language != "en":
    summary_en = st.text_area("English summary (optional, helps others find your story)", height=80, max_chars=500, key=f"sum_{n}")

c1, c2 = st.columns(2)
cat_choice = c1.selectbox(
    "Topic", ["auto"] + list(CATEGORIES),
    format_func=lambda k: "✨ Choose for me" if k == "auto" else f"{CATEGORIES[k]['icon']} {CATEGORIES[k]['label']}", key=f"cat_{n}",
)
species = c2.text_input("Fish or sea life mentioned (comma separated)", key=f"sp_{n}")
tags = st.text_input("Tags (comma separated)", placeholder="monsoon, net, dawn", key=f"tags_{n}")

use_ai = False
if os.getenv("ANTHROPIC_API_KEY") and cat_choice == "auto":
    use_ai = st.checkbox("Let an AI suggest the topic (sends the text, without phone numbers, to the AI provider)", key=f"ai_{n}")

# ------------------------------------------------------------------ 4. place
st.subheader("4 · Where is it from?")
region_ids = [""] + [r.id for r in REGIONS]
region = st.selectbox("Coastal region", region_ids, format_func=lambda i: "I'd rather not say" if not i else next(r.name + " – " + r.state for r in REGIONS if r.id == i), key=f"reg_{n}")
use_point = st.checkbox("I want to mark a more specific spot on the map", key=f"pt_{n}")
lat = lng = None
precision = "region" if region else "approx"
if use_point:
    p1, p2 = st.columns(2)
    default = next((r for r in REGIONS if r.id == region), REGIONS[4])
    lat = p1.number_input("Latitude", 4.0, 25.0, float(default.lat), 0.01, format="%.4f", key=f"lat_{n}")
    lng = p2.number_input("Longitude", 65.0, 98.0, float(default.lng), 0.01, format="%.4f", key=f"lng_{n}")
    precision = st.radio("How precisely should the place be shown?", list(PRECISIONS), index=1, format_func=PRECISIONS.get, horizontal=True, key=f"prec_{n}")
    st.caption("Approximate = rounded to about 5 km before saving. Safer for fishing grounds you do not want to give away.")

# ------------------------------------------------------------------ 5. you
st.subheader("5 · About you (optional)")
narrator = st.text_input("Your name or nickname", max_chars=60, key=f"nar_{n}")
show_name = st.checkbox("Show my name next to the story (otherwise it says 'Anonymous')", disabled=not narrator.strip(), key=f"show_{n}")
role = st.text_input("Role (e.g. fisher, boat owner, elder, student)", max_chars=40, key=f"role_{n}")

st.divider()
if st.button("Save my story", type="primary", disabled=not consent_public):
    saved_audio = None
    try:
        if audio_ok:
            saved_audio = save_audio(audio_bytes, audio_name)
        story, code = manager.create_story(
            title=title, text=text, language=language, category=cat_choice, consent_public=consent_public,
            consent_research=consent_research, dialect=dialect, region=region, lat=lat, lng=lng, precision=precision,
            species=species, tags=tags, narrator=narrator, show_name=show_name, narrator_role=role,
            audio_file=saved_audio.filename if saved_audio else "", audio_public=audio_public,
            transcript_source=st.session_state.get(f"tsrc_{n}", "typed"), summary_en=summary_en, use_ai=use_ai,
        )
        st.session_state["saved"] = {"code": code, "id": story.id, "pending": story.status == "pending"}
        st.rerun()
    except StoryValidationError as exc:
        if saved_audio:
            delete_audio(saved_audio.filename)
        for p in exc.problems:
            st.error(p)
    except AudioError as exc:
        st.error(str(exc))
if not consent_public:
    st.caption("Tick the consent box above to enable saving.")
