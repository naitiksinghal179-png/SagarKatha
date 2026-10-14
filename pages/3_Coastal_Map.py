"""Coastal map: story pins + live ocean currents + whale/shark/fish sightings + sea report."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from src.map_handler import (
    ATTRIBUTION,
    BASEMAP_NOTE,
    BASEMAPS,
    EMERGENCY_NOTE,
    GROUPS,
    DataSourceError,
    assess_conditions,
    build_map,
    compass,
    current_at,
    fetch_current_grid,
    fetch_marine_weather,
    fetch_sightings,
    is_offline,
    kmh_to_knots,
    weather_text,
)
from src.story_manager import CATEGORIES, REGIONS
from src.ui import get_manager, page_header, sample_notice

page_header("Coastal map & ocean", "Fisher stories, ocean currents and wildlife sightings on one map.", "🗺️")
manager = get_manager()
stories = manager.all_stories()
offline = is_offline()


@st.cache_data(ttl=1800, show_spinner=False)
def load_currents():
    return fetch_current_grid()


@st.cache_data(ttl=600, show_spinner=False)
def load_sightings(groups: tuple[str, ...]):
    return fetch_sightings(groups)


@st.cache_data(ttl=600, show_spinner=False)
def load_weather(lat: float, lng: float):
    return fetch_marine_weather(lat, lng)


with st.container(border=True):
    c1, c2 = st.columns([1, 2])
    basemap = c1.selectbox("Base map", list(BASEMAPS), format_func=BASEMAPS.get)
    layers = c2.multiselect(
        "Layers",
        ["Fisher stories", "Ocean currents", "Whales & dolphins", "Sharks & rays", "Fish sightings", "Reference areas"],
        default=["Fisher stories", "Ocean currents", "Whales & dolphins", "Sharks & rays", "Fish sightings"],
        help="Currents and sightings come from live public data; they need an internet connection.",
    )
    min_cur = st.slider("Show currents faster than (km/h)", 0.0, 3.0, 0.0, 0.5, disabled="Ocean currents" not in layers)
st.caption(BASEMAP_NOTE)

cells, sightings, notes = [], None, []
if offline:
    st.info("Offline mode (`SAGARKATHA_OFFLINE=1`): live ocean and sighting data are switched off.", icon="📴")
else:
    if "Ocean currents" in layers:
        with st.spinner("Loading ocean currents…"):
            try:
                cells = load_currents()
            except DataSourceError as exc:
                notes.append(f"Ocean currents unavailable: {exc}")
    wanted = tuple(k for k, lbl in (("whale", "Whales & dolphins"), ("shark", "Sharks & rays"), ("fish", "Fish sightings")) if lbl in layers)
    if wanted:
        with st.spinner("Loading recent sightings…"):
            try:
                sightings = load_sightings(wanted)
            except DataSourceError as exc:
                notes.append(f"Sightings unavailable: {exc}")
for msg in notes:
    st.warning(msg + " Showing the rest of the map.", icon="⚠️")

fmap = build_map(
    stories, basemap=basemap, show_stories="Fisher stories" in layers, currents=cells, min_current_kmh=min_cur,
    sightings=sightings, hotspots="Reference areas" in layers,
)
st_folium(fmap, height=560, use_container_width=True, returned_objects=[], key="coastal_map")
sample_notice()

if sightings:
    total = sum(len(v) for v in sightings.values())
    st.markdown(f"**{total} recent sightings** · " + " · ".join(f"{GROUPS[k]['emoji']} {len(v)}" for k, v in sightings.items()))
    st.caption(
        "These are observations that people reported to GBIF / iNaturalist – **not live tracking** and not a count of animals. "
        "Positions of protected species can be deliberately blurred by the observers' platform."
    )
    rows = [
        {"": GROUPS[s.group]["emoji"], "Species": s.species, "Scientific name": s.scientific_name, "Date": s.date, "Record": s.record_url}
        for items in sightings.values() for s in items[:100]
    ]
    rows.sort(key=lambda r: r["Date"], reverse=True)
    with st.expander("Latest sightings (table)"):
        st.dataframe(pd.DataFrame(rows[:60]), hide_index=True, width="stretch",
                     column_config={"Record": st.column_config.LinkColumn("GBIF record", display_text="open")})

# ------------------------------------------------------------------ sea report
st.subheader("Sea & weather report")
region_id = st.selectbox("Choose a coast", [r.id for r in REGIONS], format_func=lambda i: next(r.name for r in REGIONS if r.id == i), key="rep_region")
region = next(r for r in REGIONS if r.id == region_id)
if offline:
    st.caption("Switched off in offline mode.")
else:
    try:
        with st.spinner("Fetching the latest sea state…"):
            mw = load_weather(region.sea_lat, region.sea_lng)
        adv = assess_conditions(mw)
        {"ok": st.success, "caution": st.warning, "danger": st.error, "unknown": st.info}[adv.level](
            f"**{region.name}** – {adv.label}" + (" · " + ", ".join(adv.reasons) if adv.reasons else "")
        )
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Wave height", "–" if mw.wave_height is None else f"{mw.wave_height:.1f} m", None if mw.wave_period is None else f"{mw.wave_period:.0f} s period", delta_color="off")
        m2.metric("Wind", "–" if mw.wind_kmh is None else f"{mw.wind_kmh:.0f} km/h {compass(mw.wind_dir)}", None if mw.gust_kmh is None else f"gusts {mw.gust_kmh:.0f}", delta_color="off")
        m3.metric("Sea temperature", "–" if mw.sea_temp is None else f"{mw.sea_temp:.1f} °C")
        kn = kmh_to_knots(mw.current_kmh)
        m4.metric("Ocean current", "–" if mw.current_kmh is None else f"{mw.current_kmh:.1f} km/h → {compass(mw.current_dir)}", None if kn is None else f"{kn:.1f} knots", delta_color="off")
        st.caption(f"Sky: {weather_text(mw.weather_code)} · Air {'–' if mw.air_temp is None else f'{mw.air_temp:.0f} °C'} · observed/forecast time {mw.time or '–'} (IST)")
        for e in mw.errors:
            st.caption("⚠ " + e)
        near = current_at(cells, region.sea_lat, region.sea_lng) if cells else None
        if near and mw.current_kmh is None:
            st.caption(f"Nearest grid current: {near.speed_kmh:.1f} km/h → {compass(near.direction)}")
    except DataSourceError as exc:
        st.warning(f"Could not load the sea report: {exc}")
st.error(EMERGENCY_NOTE, icon="🚨")
st.caption(ATTRIBUTION)

with st.expander("Stories by topic on this map"):
    counts = {}
    for s in stories:
        if s.has_location:
            counts[s.category] = counts.get(s.category, 0) + 1
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        c = CATEGORIES.get(k, CATEGORIES["other"])
        st.markdown(f"<span style='color:{c['color']}'>●</span> {c['icon']} {c['label']} — {v}", unsafe_allow_html=True)
