from datetime import date

import pytest
import requests

from src import map_handler as mh
from src.story_manager import Story


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._b = status, body
    def json(self):
        if self._b is None:
            raise ValueError
        return self._b


# ---------------------------------------------------------------- geometry
SEA = {"Arabian Sea": (15, 70), "Bay of Bengal": (15, 86), "off Kerala": (9.9, 75.6), "Lakshadweep": (10.6, 72.0), "Andaman": (11.6, 93.0), "south of Sri Lanka": (5.7, 80.6), "Palk Strait": (9.8, 79.6)}
LAND = {"Bengaluru": (12.97, 77.59), "Delhi": (28.6, 77.2), "Jaipur": (26.9, 75.8), "Nagpur": (21.1, 79.1), "Colombo": (6.93, 79.86), "Kandy": (7.29, 80.63), "Ahmedabad": (23.03, 72.58)}


@pytest.mark.parametrize("name", SEA)
def test_sea_points_are_not_land(name):
    assert not mh.is_land(*SEA[name])


@pytest.mark.parametrize("name", LAND)
def test_land_points_are_land(name):
    assert mh.is_land(*LAND[name])


def test_marine_or_coastal_filter():
    assert mh.is_marine_or_coastal(*SEA["Arabian Sea"])
    assert not mh.is_marine_or_coastal(*LAND["Jaipur"])  # far inland
    assert not mh.is_marine_or_coastal(*LAND["Nagpur"])
    assert mh.is_marine_or_coastal(19.7, 85.3)  # Chilika lagoon is whitelisted
    assert mh.is_marine_or_coastal(21.9, 88.6)  # Sundarbans delta
    assert mh.distance_to_coast_km(9.97, 76.24) < 1  # Kochi sits on the coastline


def test_grid_points_are_sea_only_and_unique():
    pts = mh.grid_points()
    assert 30 < len(pts) < 120 and len(set(pts)) == len(pts)
    assert not any(mh.is_land(*p) for p in pts)


def test_box_wkt_is_counter_clockwise_and_closed():
    wkt = mh.box_wkt((5.0, 66.0, 23.6, 89.0))
    assert wkt == "POLYGON((66 5,89 5,89 23.6,66 23.6,66 5))"


def test_compass_and_units():
    assert [mh.compass(d) for d in (0, 90, 180, 270, 359, 45, None)] == ["N", "E", "S", "W", "N", "NE", "–"]
    assert mh.kmh_to_knots(10) == pytest.approx(5.4, abs=0.01) and mh.kmh_to_knots(None) is None
    assert mh.weather_text(95) == "Thunderstorm" and mh.weather_text(None) == "–" and "Code" in mh.weather_text(7)


# ---------------------------------------------------------------- currents
def test_parse_marine_batch_handles_list_dict_and_nulls():
    coords = [(10.0, 72.0), (12.0, 80.0), (14.0, 75.0)]
    payload = [
        {"current": {"ocean_current_velocity": 1.2, "ocean_current_direction": 90, "sea_surface_temperature": 28.5}},
        {"current": {"ocean_current_velocity": None, "ocean_current_direction": None}},  # land / no coverage
        {"error": True},
    ]
    cells = mh.parse_marine_batch(payload, coords)
    assert len(cells) == 1 and cells[0].lat == 10.0 and cells[0].speed_kmh == 1.2 and cells[0].sst == 28.5
    single = mh.parse_marine_batch({"current": {"ocean_current_velocity": 0.4, "ocean_current_direction": 10}}, [(1, 2)])
    assert single[0].direction == 10 and single[0].sst is None


def test_fetch_current_grid_batches_and_tolerates_partial_failure(monkeypatch):
    calls = []
    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params)
        if len(calls) == 1:
            return Resp(500)
        n = len(params["latitude"].split(","))
        return Resp(200, [{"current": {"ocean_current_velocity": 1.0, "ocean_current_direction": 180}}] * n)
    monkeypatch.setattr(requests, "get", fake_get)
    cells = mh.fetch_current_grid(batch_size=20)
    assert len(calls) >= 2 and cells and all(c.speed_kmh == 1.0 for c in cells)
    assert "ocean_current_velocity" in calls[0]["current"] and calls[0]["latitude"].count(",") == 19


def test_fetch_current_grid_all_fail(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(500))
    with pytest.raises(mh.DataSourceError, match="HTTP 500"):
        mh.fetch_current_grid()


def test_http_errors_become_friendly(monkeypatch):
    def timeout(*a, **k): raise requests.Timeout()
    monkeypatch.setattr(requests, "get", timeout)
    with pytest.raises(mh.DataSourceError, match="too long"):
        mh.fetch_current_grid()
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(429))
    with pytest.raises(mh.DataSourceError, match="busy"):
        mh.fetch_current_grid()
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(200, None))
    with pytest.raises(mh.DataSourceError, match="unreadable"):
        mh.fetch_current_grid()


def test_current_at():
    cells = [mh.CurrentCell(10, 72, 1, 90), mh.CurrentCell(20, 88, 2, 0)]
    assert mh.current_at(cells, 10.5, 72.5).speed_kmh == 1
    assert mh.current_at(cells, 0, 0) is None


def test_current_color_bands():
    assert [mh.current_color(v) for v in (0.1, 0.5, 1.5, 3)] == ["#2B8CBE", "#2E9E6B", "#E0A800", "#D9534F"]


# ---------------------------------------------------------------- weather
MARINE_JSON = {"current": {"time": "2026-10-13T12:00", "wave_height": 2.8, "wave_period": 8.1, "wave_direction": 230, "swell_wave_height": 1.5, "sea_surface_temperature": 29.1, "ocean_current_velocity": 1.1, "ocean_current_direction": 45}}
FORECAST_JSON = {"current": {"time": "2026-10-13T12:00", "temperature_2m": 30.2, "precipitation": 0.0, "weather_code": 3, "cloud_cover": 80, "pressure_msl": 1008.2, "wind_speed_10m": 22.0, "wind_direction_10m": 250, "wind_gusts_10m": 33.0}}


def test_fetch_marine_weather(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, MARINE_JSON if "marine" in url else FORECAST_JSON))
    mw = mh.fetch_marine_weather(15.3, 73.3)
    assert (mw.wave_height, mw.sea_temp, mw.current_kmh, mw.wind_kmh, mw.gust_kmh, mw.weather_code) == (2.8, 29.1, 1.1, 22.0, 33.0, 3)
    assert mw.errors == []
    adv = mh.assess_conditions(mw)
    assert adv.level == "caution" and "Waves 2.8 m" in adv.reasons


def test_fetch_marine_weather_partial_and_total_failure(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, **k: Resp(200, MARINE_JSON) if "marine" in url else Resp(500))
    mw = mh.fetch_marine_weather(15, 73)
    assert mw.wave_height == 2.8 and len(mw.errors) == 1 and mw.errors[0].startswith("Weather")
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(500))
    with pytest.raises(mh.DataSourceError):
        mh.fetch_marine_weather(15, 73)


@pytest.mark.parametrize("kw,level", [
    (dict(wave_height=1.0, gust_kmh=20, weather_code=1), "ok"),
    (dict(wave_height=2.5), "caution"), (dict(wave_height=4.0), "danger"),
    (dict(gust_kmh=40), "caution"), (dict(gust_kmh=60), "danger"),
    (dict(weather_code=95), "danger"), (dict(weather_code=65), "caution"), (dict(), "unknown"),
])
def test_assess_conditions(kw, level):
    assert mh.assess_conditions(mh.MarineWeather(0, 0, **kw)).level == level


# ---------------------------------------------------------------- GBIF sightings
GBIF_RECORD = {
    "key": 5938052503, "scientificName": "Physeter macrocephalus Linnaeus, 1758", "species": "Physeter macrocephalus",
    "decimalLatitude": 12.560781, "decimalLongitude": 92.932591, "coordinateUncertaintyInMeters": 31081.0,
    "eventDate": "2026-01-02T17:44", "license": "http://creativecommons.org/licenses/by-nc/4.0/legalcode", "vitality": "dead",
    "occurrenceStatus": "PRESENT", "basisOfRecord": "HUMAN_OBSERVATION", "datasetName": "iNaturalist research-grade observations",
    "media": [{"type": "StillImage", "identifier": "https://inaturalist-open-data.s3.amazonaws.com/photos/604812137/original.jpg"}],
}


def test_parse_gbif_results():
    out = mh.parse_gbif_results({"results": [GBIF_RECORD, {"key": 1}, {"key": 2, "decimalLatitude": 1, "decimalLongitude": 2, "occurrenceStatus": "ABSENT"}, "junk"]}, "whale")
    assert len(out) == 1
    s = out[0]
    assert s.group == "whale" and s.species == "Physeter macrocephalus" and s.date == "2026-01-02" and s.vitality == "dead"
    assert s.record_url == "https://www.gbif.org/occurrence/5938052503" and s.image_url.startswith("https://")
    assert s.age_days(date(2026, 1, 12)) == 10 and mh.license_name(s.license) == "CC BY-NC"
    assert mh.parse_gbif_results(None, "fish") == [] and mh.parse_gbif_results({"results": None}, "fish") == []


def test_unsafe_image_urls_are_dropped():
    bad = {**GBIF_RECORD, "media": [{"identifier": "javascript:alert(1)"}, {"identifier": "http://insecure/x.jpg"}, {"identifier": "https://ok/x.jpg\"onerror=\""}]}
    assert mh.parse_gbif_results({"results": [bad]}, "whale")[0].image_url == ""


def test_fetch_sightings_queries_both_boxes_and_filters_inland_fish(monkeypatch):
    seen = []
    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append(params)
        if params["scientificName"] == "Actinopterygii":
            inland = {**GBIF_RECORD, "key": 7, "decimalLatitude": 26.9, "decimalLongitude": 75.8}  # Jaipur
            coast = {**GBIF_RECORD, "key": 8, "decimalLatitude": 15.3, "decimalLongitude": 73.3}
            return Resp(200, {"results": [inland, coast]})
        return Resp(200, {"results": [{**GBIF_RECORD, "key": 100 + len(seen)}]})
    monkeypatch.setattr(requests, "get", fake_get)
    res = mh.fetch_sightings(today=date(2026, 10, 13))
    assert {p["scientificName"] for p in seen} == {"Cetacea", "Elasmobranchii", "Actinopterygii"}
    assert all(p["geometry"].startswith("POLYGON((") and p["hasCoordinate"] == "true" and p["occurrenceStatus"] == "PRESENT" for p in seen)
    assert [s.id for s in res["fish"]] == ["8"]  # inland freshwater record dropped, duplicate ids merged
    assert res["whale"] and res["shark"]


def test_fetch_sightings_failure_modes(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(503))
    with pytest.raises(mh.DataSourceError):
        mh.fetch_sightings()
    monkeypatch.setattr(requests, "get", lambda *a, **k: Resp(200, {"results": []}))
    assert mh.fetch_sightings(("whale",)) == {"whale": []}  # a genuine "none seen" is not an error


# ---------------------------------------------------------------- folium map
def _story(**kw):
    base = dict(id="s1", title='<script>alert(1)</script> "quoted"', text="x" * 20, category="species", lat=13.0, lng=80.0, language="en", state="Tamil Nadu")
    return Story(**{**base, **kw})


def test_build_map_renders_all_layers_and_escapes_html():
    sight = mh.parse_gbif_results({"results": [{**GBIF_RECORD, "species": "<b>Whale</b>"}]}, "whale")
    m = mh.build_map([_story(), _story(id="s2", lat=None, lng=None)], currents=[mh.CurrentCell(10, 72, 2.2, 90, 28.0)],
                     sightings={"whale": sight}, hotspots=True, today=date(2026, 1, 3))
    html = m.get_root().render()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>Whale</b>" not in html
    assert "Ocean currents" in html and "Reference areas" in html and "Fisher stories" in html and "Arabian Sea" in html
    assert html.count("L.circleMarker") >= 1 + len(mh.HOTSPOTS)  # 1 story + hotspots
    assert "rotate(90deg)" in html


def test_build_map_basemaps_and_empty():
    assert "openstreetmap" in mh.build_map([], basemap="osm").get_root().render().lower()
    plain = mh.build_map([], basemap="coastline").get_root().render()
    assert "tile.openstreetmap" not in plain and "L.polyline" in plain  # offline coastline only


def test_attribution_and_safety_texts():
    assert "Open-Meteo" in mh.ATTRIBUTION and "GBIF" in mh.ATTRIBUTION and "1554" in mh.EMERGENCY_NOTE
    assert mh.is_offline() is True  # conftest sets SAGARKATHA_OFFLINE=1
