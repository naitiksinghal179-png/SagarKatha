"""Map, ocean-current, marine-weather and wildlife-sighting helpers.

Data sources (all free, no API key):

* **Open-Meteo Marine API** – ocean current speed/direction, waves, sea-surface
  temperature (https://open-meteo.com, CC BY 4.0, free for non-commercial use).
* **Open-Meteo Forecast API** – wind, gusts, rain, weather code.
* **GBIF occurrence API** – volunteered sightings of whales/dolphins, sharks/rays
  and fish, many of them iNaturalist photos (https://www.gbif.org).  These are
  *observations by people*, **not live animal tracking**.

Every network function has a timeout, raises :class:`DataSourceError` with a
friendly message, and is covered by tests with mocked responses.  Nothing in
this module imports Streamlit; ``folium`` is imported lazily inside
:func:`build_map`.

⚠ The sea-condition ratings are *indicative only*.  Fishers must follow INCOIS /
IMD advisories and the Coast Guard (toll-free **1554** for emergencies at sea).
"""

from __future__ import annotations

import html
import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional, Sequence

import requests

from src.story_manager import (
    CATEGORIES,
    LANGUAGES,
    REGIONS,
    Story,
    category_label,
)

USER_AGENT = "SagarKatha/0.1 (open-source; github.com/naitiksinghal179-png/SagarKatha)"
MARINE_URL = "https://marine-api.open-meteo.com/v1/marine"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GBIF_URL = "https://api.gbif.org/v1/occurrence/search"
REQUEST_TIMEOUT = 20

ATTRIBUTION = (
    "Ocean and weather data: [Open-Meteo](https://open-meteo.com/) (CC BY 4.0; non-commercial use). "
    "Sightings: [GBIF](https://www.gbif.org/) and its contributors, mostly iNaturalist observers – "
    "each record keeps its own licence."
)
EMERGENCY_NOTE = (
    "Indicative only – not an official warning. Follow INCOIS / IMD advisories and your fisheries department. "
    "Emergency at sea: Indian Coast Guard toll-free **1554**."
)


class DataSourceError(RuntimeError):
    """A live-data request failed. The message is safe to show to the user."""


def is_offline() -> bool:
    """``SAGARKATHA_OFFLINE=1`` disables every live-data call (demos, tests, no network)."""
    return os.getenv("SAGARKATHA_OFFLINE", "").strip().lower() in ("1", "true", "yes", "on")


# --------------------------------------------------------------------------- #
# Geography (coarse – for orientation and filtering only, not for navigation)
# --------------------------------------------------------------------------- #

#: Indian mainland coast, Kutch → Sundarbans, as (lat, lng) with land always on the left.
COAST: list[tuple[float, float]] = [
    (23.97, 68.18), (23.73, 68.53), (23.22, 68.72), (22.83, 69.35), (22.84, 69.70), (23.00, 70.22),
    (22.95, 70.45), (22.50, 70.05), (22.43, 69.83), (22.47, 69.07), (22.24, 68.97), (21.64, 69.60),
    (21.25, 69.97), (20.91, 70.37), (20.71, 71.00), (20.90, 71.50), (21.08, 71.77), (21.77, 72.15),
    (22.20, 72.40), (22.30, 72.60), (21.70, 72.60), (21.10, 72.65), (20.40, 72.83), (19.35, 72.80),
    (18.95, 72.82), (18.64, 72.87), (17.80, 73.10), (16.99, 73.28), (16.06, 73.46), (15.50, 73.80),
    (14.80, 74.10), (14.28, 74.44), (13.62, 74.68), (12.87, 74.84), (11.87, 75.37), (11.25, 75.77),
    (10.77, 75.92), (9.97, 76.24), (9.49, 76.32), (8.88, 76.59), (8.48, 76.95), (8.08, 77.55),
    (8.37, 78.06), (8.76, 78.20), (9.28, 79.31), (9.74, 79.02), (10.28, 79.87), (10.77, 79.84),
    (11.14, 79.85), (11.75, 79.77), (11.93, 79.83), (12.62, 80.20), (13.08, 80.29), (13.42, 80.32),
    (14.25, 80.12), (15.50, 80.05), (15.90, 80.47), (16.17, 81.14), (16.95, 82.24), (17.69, 83.22),
    (18.33, 84.12), (19.26, 84.90), (19.80, 85.83), (20.30, 86.67), (20.78, 87.00), (21.50, 87.00),
    (21.62, 87.55), (21.65, 88.05), (21.80, 88.90),
]
#: Sri Lanka outline (closed ring).
LANKA: list[tuple[float, float]] = [
    (9.83, 80.23), (9.27, 80.82), (8.57, 81.23), (7.72, 81.70), (6.84, 81.84), (6.35, 81.40),
    (6.12, 81.12), (5.93, 80.59), (6.03, 80.22), (6.93, 79.84), (7.58, 79.79), (8.03, 79.83),
    (9.00, 79.92), (9.70, 79.85),
]
#: Indian land mass: the coast plus a closing path through the north (land mask only).
INDIA_LAND: list[tuple[float, float]] = COAST + [(35.0, 88.9), (35.0, 68.18)]

#: Sea labels for the offline basemap: (text, lat, lng)
SEA_LABELS = [("Arabian Sea", 15.8, 66.8), ("Bay of Bengal", 14.0, 87.8), ("Indian Ocean", 4.8, 79.0), ("Andaman Sea", 10.0, 96.0)]

# Study boxes (lat_min, lng_min, lat_max, lng_max) – kept away from Bangladesh/Myanmar/Pakistan land.
BOX_MAINLAND = (5.0, 66.0, 23.6, 89.0)
BOX_ISLANDS = (5.5, 91.0, 14.5, 94.5)
STUDY_BOXES = (BOX_MAINLAND, BOX_ISLANDS)

# Brackish lagoons / deltas that lie further than the coast tolerance from our coarse coastline.
WATER_BODIES = (
    (19.40, 85.05, 19.95, 85.65),  # Chilika
    (13.30, 79.75, 13.75, 80.20),  # Pulicat
    (9.45, 76.20, 10.20, 76.50),  # Vembanad / Kochi backwaters
    (21.50, 88.00, 22.35, 89.00),  # Sundarbans
)


def point_in_polygon(lat: float, lng: float, poly: Sequence[tuple[float, float]]) -> bool:
    """Ray-casting test; ``poly`` is a list of ``(lat, lng)``."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _segment_km(lat: float, lng: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from a point to a segment using a local equirectangular projection."""
    kx = 111.32 * math.cos(math.radians(lat))
    ky = 110.57
    px, py = 0.0, 0.0
    ax, ay = (a[1] - lng) * kx, (a[0] - lat) * ky
    bx, by = (b[1] - lng) * kx, (b[0] - lat) * ky
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def distance_to_coast_km(lat: float, lng: float) -> float:
    """Distance to the nearest coastline segment (mainland or Sri Lanka)."""
    best = float("inf")
    for ring, closed in ((COAST, False), (LANKA, True)):
        pts = ring + [ring[0]] if closed else ring
        for a, b in zip(pts, pts[1:]):
            best = min(best, _segment_km(lat, lng, a, b))
    return best


def is_land(lat: float, lng: float) -> bool:
    """Inside the Indian land mass or Sri Lanka (coarse polygon)."""
    return point_in_polygon(lat, lng, INDIA_LAND) or point_in_polygon(lat, lng, LANKA)


def in_water_body(lat: float, lng: float) -> bool:
    return any(a <= lat <= c and b <= lng <= d for a, b, c, d in WATER_BODIES)


def is_marine_or_coastal(lat: float, lng: float, tolerance_km: float = 30.0) -> bool:
    """Keep a point if it is at sea, within ``tolerance_km`` of the coast, or in a known lagoon/delta."""
    if not is_land(lat, lng):
        return True
    return in_water_body(lat, lng) or distance_to_coast_km(lat, lng) <= tolerance_km


def box_wkt(box: tuple[float, float, float, float]) -> str:
    """Counter-clockwise WKT polygon (GBIF requires CCW exterior rings)."""
    lat0, lng0, lat1, lng1 = box
    ring = [(lng0, lat0), (lng1, lat0), (lng1, lat1), (lng0, lat1), (lng0, lat0)]
    return "POLYGON((" + ",".join(f"{x:g} {y:g}" for x, y in ring) + "))"


# --------------------------------------------------------------------------- #
# Small unit helpers
# --------------------------------------------------------------------------- #

_COMPASS = ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW")


def compass(degrees: Optional[float]) -> str:
    if degrees is None:
        return "–"
    return _COMPASS[int((degrees % 360) / 22.5 + 0.5) % 16]


def kmh_to_knots(kmh: Optional[float]) -> Optional[float]:
    return None if kmh is None else kmh * 0.539957


_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light rain showers", 81: "Rain showers", 82: "Violent rain showers", 85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


def weather_text(code: Optional[int]) -> str:
    return "–" if code is None else _WMO.get(int(code), f"Code {int(code)}")


def _num(value: Any) -> Optional[float]:
    """float or None – tolerant of missing / non-numeric JSON values."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _get_json(url: str, params: dict[str, Any], timeout: float = REQUEST_TIMEOUT) -> Any:
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    except requests.Timeout as exc:
        raise DataSourceError("The data service took too long to answer.") from exc
    except requests.RequestException as exc:
        raise DataSourceError("Could not reach the data service. Check the internet connection.") from exc
    if resp.status_code == 429:
        raise DataSourceError("The data service is busy (rate limit). Please try again in a few minutes.")
    if resp.status_code != 200:
        raise DataSourceError(f"The data service returned an error (HTTP {resp.status_code}).")
    try:
        return resp.json()
    except ValueError as exc:
        raise DataSourceError("The data service returned an unreadable answer.") from exc


# --------------------------------------------------------------------------- #
# Ocean currents (grid)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CurrentCell:
    lat: float
    lng: float
    speed_kmh: float
    direction: Optional[float]  # degrees the water flows TOWARDS (0 = north)
    sst: Optional[float] = None

    @property
    def speed_knots(self) -> float:
        return self.speed_kmh * 0.539957


def current_color(speed_kmh: float) -> str:
    """Arrow colour by speed (km/h)."""
    if speed_kmh >= 3:
        return "#D9534F"
    if speed_kmh >= 1.5:
        return "#E0A800"
    if speed_kmh >= 0.5:
        return "#2E9E6B"
    return "#2B8CBE"


def grid_points(step: float = 2.5) -> list[tuple[float, float]]:
    """Sea points on a regular grid over the study boxes (land cells are skipped)."""
    pts: list[tuple[float, float]] = []
    seen: set[tuple[float, float]] = set()
    for lat0, lng0, lat1, lng1 in STUDY_BOXES:
        n_lat = int((lat1 - lat0) / step) + 1
        n_lng = int((lng1 - lng0) / step) + 1
        for i in range(n_lat):
            for j in range(n_lng):
                p = (round(lat0 + i * step, 3), round(lng0 + j * step, 3))
                if p in seen or is_land(*p):
                    continue
                seen.add(p)
                pts.append(p)
    return pts


def parse_marine_batch(payload: Any, coords: Sequence[tuple[float, float]]) -> list[CurrentCell]:
    """Turn an Open-Meteo multi-location marine response into :class:`CurrentCell` objects.

    The API returns a JSON object for one location and a list for several.
    Cells without current data (land / no coverage) have ``null`` values and are skipped.
    """
    items = payload if isinstance(payload, list) else [payload]
    cells: list[CurrentCell] = []
    for (lat, lng), item in zip(coords, items):
        cur = item.get("current") if isinstance(item, dict) else None
        if not isinstance(cur, dict):
            continue
        speed = _num(cur.get("ocean_current_velocity"))
        if speed is None:
            continue
        cells.append(CurrentCell(lat, lng, speed, _num(cur.get("ocean_current_direction")), _num(cur.get("sea_surface_temperature"))))
    return cells


def fetch_current_grid(step: float = 2.5, batch_size: int = 40) -> list[CurrentCell]:
    """Current speed/direction + SST on a coarse grid. Partial failures are tolerated."""
    pts = grid_points(step)
    cells: list[CurrentCell] = []
    errors: list[str] = []
    for i in range(0, len(pts), batch_size):
        chunk = pts[i : i + batch_size]
        params = {
            "latitude": ",".join(f"{p[0]:g}" for p in chunk),
            "longitude": ",".join(f"{p[1]:g}" for p in chunk),
            "current": "ocean_current_velocity,ocean_current_direction,sea_surface_temperature",
        }
        try:
            cells.extend(parse_marine_batch(_get_json(MARINE_URL, params), chunk))
        except DataSourceError as exc:
            errors.append(str(exc))
    if not cells:
        raise DataSourceError(errors[0] if errors else "No ocean-current data was returned.")
    return cells


def current_at(cells: Sequence[CurrentCell], lat: float, lng: float, max_deg: float = 3.2) -> Optional[CurrentCell]:
    """Nearest grid cell within ``max_deg`` degrees (≈350 km), else ``None``."""
    best, best_d = None, max_deg**2
    for c in cells:
        d = (c.lat - lat) ** 2 + (c.lng - lng) ** 2
        if d < best_d:
            best, best_d = c, d
    return best


# --------------------------------------------------------------------------- #
# Marine weather for one place
# --------------------------------------------------------------------------- #


@dataclass
class MarineWeather:
    lat: float
    lng: float
    time: str = ""
    wave_height: Optional[float] = None  # m
    wave_period: Optional[float] = None  # s
    wave_direction: Optional[float] = None  # degrees, direction waves come FROM
    swell_height: Optional[float] = None  # m
    sea_temp: Optional[float] = None  # °C
    current_kmh: Optional[float] = None
    current_dir: Optional[float] = None  # degrees TOWARDS
    wind_kmh: Optional[float] = None
    gust_kmh: Optional[float] = None
    wind_dir: Optional[float] = None  # degrees FROM
    weather_code: Optional[int] = None
    rain_mm: Optional[float] = None
    cloud_pct: Optional[float] = None
    pressure_hpa: Optional[float] = None
    air_temp: Optional[float] = None
    errors: list[str] = field(default_factory=list)


def parse_marine_current(payload: Any, mw: MarineWeather) -> None:
    cur = (payload or {}).get("current") or {}
    mw.time = mw.time or str(cur.get("time") or "")
    mw.wave_height = _num(cur.get("wave_height"))
    mw.wave_period = _num(cur.get("wave_period"))
    mw.wave_direction = _num(cur.get("wave_direction"))
    mw.swell_height = _num(cur.get("swell_wave_height"))
    mw.sea_temp = _num(cur.get("sea_surface_temperature"))
    mw.current_kmh = _num(cur.get("ocean_current_velocity"))
    mw.current_dir = _num(cur.get("ocean_current_direction"))


def parse_forecast_current(payload: Any, mw: MarineWeather) -> None:
    cur = (payload or {}).get("current") or {}
    mw.time = str(cur.get("time") or mw.time)
    mw.air_temp = _num(cur.get("temperature_2m"))
    mw.rain_mm = _num(cur.get("precipitation"))
    code = _num(cur.get("weather_code"))
    mw.weather_code = None if code is None else int(code)
    mw.cloud_pct = _num(cur.get("cloud_cover"))
    mw.pressure_hpa = _num(cur.get("pressure_msl"))
    mw.wind_kmh = _num(cur.get("wind_speed_10m"))
    mw.wind_dir = _num(cur.get("wind_direction_10m"))
    mw.gust_kmh = _num(cur.get("wind_gusts_10m"))


def fetch_marine_weather(lat: float, lng: float) -> MarineWeather:
    """Current sea state + weather at a point.  Raises only if *both* requests fail."""
    mw = MarineWeather(lat=lat, lng=lng)
    base = {"latitude": f"{lat:g}", "longitude": f"{lng:g}", "timezone": "Asia/Kolkata"}
    try:
        parse_marine_current(
            _get_json(
                MARINE_URL,
                {**base, "current": "wave_height,wave_period,wave_direction,swell_wave_height,sea_surface_temperature,ocean_current_velocity,ocean_current_direction"},
            ),
            mw,
        )
    except DataSourceError as exc:
        mw.errors.append(f"Sea state: {exc}")
    try:
        parse_forecast_current(
            _get_json(
                FORECAST_URL,
                {**base, "current": "temperature_2m,precipitation,weather_code,cloud_cover,pressure_msl,wind_speed_10m,wind_direction_10m,wind_gusts_10m", "wind_speed_unit": "kmh"},
            ),
            mw,
        )
    except DataSourceError as exc:
        mw.errors.append(f"Weather: {exc}")
    if len(mw.errors) == 2:
        raise DataSourceError(mw.errors[0].split(": ", 1)[1])
    return mw


@dataclass(frozen=True)
class Advisory:
    level: str  # "ok" | "caution" | "danger" | "unknown"
    label: str
    reasons: tuple[str, ...]


_HEAVY_RAIN = {63, 65, 66, 67, 73, 75, 81, 82, 85, 86}
_THUNDER = {95, 96, 99}

# Indicative thresholds for small country boats – deliberately conservative, NOT official.
WAVE_CAUTION_M, WAVE_DANGER_M = 2.5, 4.0
GUST_CAUTION_KMH, GUST_DANGER_KMH = 40.0, 60.0


def assess_conditions(mw: MarineWeather) -> Advisory:
    """A simple traffic-light rating from waves, gusts and weather. See :data:`EMERGENCY_NOTE`."""
    reasons: list[str] = []
    level = 0  # 0 ok, 1 caution, 2 danger

    def bump(to: int, why: str) -> None:
        nonlocal level
        level = max(level, to)
        reasons.append(why)

    if mw.wave_height is not None:
        if mw.wave_height >= WAVE_DANGER_M:
            bump(2, f"Waves {mw.wave_height:.1f} m")
        elif mw.wave_height >= WAVE_CAUTION_M:
            bump(1, f"Waves {mw.wave_height:.1f} m")
    if mw.gust_kmh is not None:
        if mw.gust_kmh >= GUST_DANGER_KMH:
            bump(2, f"Wind gusts {mw.gust_kmh:.0f} km/h")
        elif mw.gust_kmh >= GUST_CAUTION_KMH:
            bump(1, f"Wind gusts {mw.gust_kmh:.0f} km/h")
    if mw.weather_code in _THUNDER:
        bump(2, "Thunderstorm")
    elif mw.weather_code in _HEAVY_RAIN:
        bump(1, "Heavy rain")
    known = any(v is not None for v in (mw.wave_height, mw.gust_kmh, mw.weather_code))
    if not known:
        return Advisory("unknown", "No data", ())
    if level == 2:
        return Advisory("danger", "Dangerous – do not go out", tuple(reasons))
    if level == 1:
        return Advisory("caution", "Caution", tuple(reasons))
    return Advisory("ok", "No strong warning signs in this data", ())


# --------------------------------------------------------------------------- #
# Wildlife sightings (GBIF)
# --------------------------------------------------------------------------- #

GROUPS: dict[str, dict[str, str]] = {
    "whale": {"label": "Whales & dolphins", "taxon": "Cetacea", "emoji": "🐋", "color": "#1D8FD1"},
    "shark": {"label": "Sharks & rays", "taxon": "Elasmobranchii", "emoji": "🦈", "color": "#D9534F"},
    "fish": {"label": "Fish", "taxon": "Actinopterygii", "emoji": "🐟", "color": "#2E9E6B"},
}


@dataclass(frozen=True)
class Sighting:
    id: str
    group: str
    species: str
    scientific_name: str
    lat: float
    lng: float
    date: str = ""
    uncertainty_m: Optional[float] = None
    license: str = ""
    image_url: str = ""
    record_url: str = ""
    dataset: str = ""
    vitality: str = ""  # GBIF "vitality" (alive / dead) when the observer recorded it
    basis: str = ""

    def age_days(self, today: Optional[date] = None) -> Optional[int]:
        try:
            d = datetime.strptime(self.date[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
        return ((today or date.today()) - d).days


def safe_https(url: Any) -> str:
    """Only plain https URLs are ever placed into HTML."""
    if isinstance(url, str) and url.startswith("https://") and not any(c in url for c in " \"'<>\\"):
        return url
    return ""


def license_name(lic: str) -> str:
    low = (lic or "").lower()
    if "publicdomain/zero" in low or "cc0" in low:
        return "CC0"
    if "by-nc-sa" in low:
        return "CC BY-NC-SA"
    if "by-nc" in low:
        return "CC BY-NC"
    if "/by-sa/" in low:
        return "CC BY-SA"
    if "/by/" in low:
        return "CC BY"
    return "see record" if lic else ""


def parse_gbif_results(payload: Any, group: str) -> list[Sighting]:
    """Convert a GBIF occurrence-search response into sightings (skips records without coordinates)."""
    out: list[Sighting] = []
    results = payload.get("results") if isinstance(payload, dict) else None
    for r in results if isinstance(results, list) else []:
        if not isinstance(r, dict):
            continue
        lat, lng = _num(r.get("decimalLatitude")), _num(r.get("decimalLongitude"))
        key = r.get("key") or r.get("gbifID")
        if lat is None or lng is None or key is None or str(r.get("occurrenceStatus", "PRESENT")).upper() == "ABSENT":
            continue
        img = ""
        for m in r.get("media") or []:
            if isinstance(m, dict) and m.get("type", "StillImage") == "StillImage":
                img = safe_https(m.get("identifier"))
                if img:
                    break
        sci = str(r.get("scientificName") or r.get("species") or "").strip()
        out.append(
            Sighting(
                id=str(key),
                group=group,
                species=str(r.get("vernacularName") or r.get("species") or sci or "Unidentified"),
                scientific_name=str(r.get("acceptedScientificName") or sci),
                lat=lat,
                lng=lng,
                date=str(r.get("eventDate") or "")[:10],
                uncertainty_m=_num(r.get("coordinateUncertaintyInMeters")),
                license=str(r.get("license") or ""),
                image_url=img,
                record_url=f"https://www.gbif.org/occurrence/{int(key)}" if str(key).isdigit() else "",
                dataset=str(r.get("datasetName") or ""),
                vitality=str(r.get("vitality") or ""),
                basis=str(r.get("basisOfRecord") or ""),
            )
        )
    return out


def _fetch_group(group: str, box: tuple[float, float, float, float], start: date, end: date, limit: int) -> list[Sighting]:
    params = {
        "scientificName": GROUPS[group]["taxon"],
        "geometry": box_wkt(box),
        "hasCoordinate": "true",
        "hasGeospatialIssue": "false",
        "occurrenceStatus": "PRESENT",
        "eventDate": f"{start.isoformat()},{end.isoformat()}",
        "limit": limit,
    }
    return parse_gbif_results(_get_json(GBIF_URL, params), group)


def filter_sightings(items: Iterable[Sighting]) -> list[Sighting]:
    """Drop duplicate records and (for fish) inland freshwater records far from the coast."""
    seen: set[str] = set()
    out: list[Sighting] = []
    for s in items:
        if s.id in seen:
            continue
        seen.add(s.id)
        if s.group == "fish" and not is_marine_or_coastal(s.lat, s.lng):
            continue
        out.append(s)
    return sorted(out, key=lambda s: s.date, reverse=True)


def fetch_sightings(
    groups: Sequence[str] = ("whale", "shark", "fish"),
    *,
    days: int = 365,
    limit: int = 300,
    today: Optional[date] = None,
) -> dict[str, list[Sighting]]:
    """Recent volunteered sightings per group (last ``days`` days; widened to 3 years if sparse).

    Raises :class:`DataSourceError` only when *every* request failed.
    """
    today = today or date.today()
    results: dict[str, list[Sighting]] = {g: [] for g in groups}
    failures: list[str] = []
    ok_requests = 0

    for window in (days, days * 3):
        need = [g for g in groups if len(results[g]) < 10]
        if not need:
            break
        jobs = [(g, box) for g in need for box in STUDY_BOXES]
        fresh: dict[str, list[Sighting]] = {g: [] for g in need}
        with ThreadPoolExecutor(max_workers=min(6, len(jobs))) as pool:
            futures = [
                (g, pool.submit(_fetch_group, g, box, today - timedelta(days=window), today, limit)) for g, box in jobs
            ]
            for g, fut in futures:
                try:
                    fresh[g].extend(fut.result())
                    ok_requests += 1
                except DataSourceError as exc:
                    failures.append(str(exc))
        for g in need:
            results[g] = filter_sightings(fresh[g])
    if ok_requests == 0 and failures:
        raise DataSourceError(failures[0])
    return results


@dataclass(frozen=True)
class Hotspot:
    group: str
    lat: float
    lng: float
    title: str
    note: str


#: Well-documented places, shown only as *reference* (never as live data).
HOTSPOTS: tuple[Hotspot, ...] = (
    Hotspot("shark", 20.9, 70.0, "Whale shark waters – Saurashtra coast",
            "Whale sharks are regularly reported off the Saurashtra coast of Gujarat. They are a protected species in India; fishers who free animals caught by accident help protect them."),
    Hotspot("whale", 5.7, 80.6, "Blue whale waters – south of Sri Lanka",
            "Blue whales are regularly seen in the deep water south of Sri Lanka, near a busy shipping route."),
    Hotspot("whale", 19.7, 85.3, "Irrawaddy dolphins – Chilika lake",
            "Chilika lake is known for a large population of Irrawaddy dolphins."),
    Hotspot("whale", 10.6, 72.5, "Dolphins – Lakshadweep", "Dolphins are commonly reported around the Lakshadweep islands."),
    Hotspot("shark", 11.8, 92.9, "Reef sharks – Andaman Islands",
            "Reef sharks are commonly seen on the coral reefs around the Andaman Islands."),
    Hotspot("fish", 10.8, 75.4, "Oil sardine and mackerel – Malabar coast",
            "The Indian oil sardine and Indian mackerel are mainstay catches off Kerala and Karnataka."),
    Hotspot("fish", 21.2, 88.4, "Hilsa – Hooghly estuary",
            "Hilsa migrate from the Bay of Bengal into the Hooghly and other estuaries."),
    Hotspot("fish", 10.6, 72.1, "Tuna – Lakshadweep", "Skipjack tuna are caught by pole-and-line fishing around Lakshadweep."),
    Hotspot("fish", 19.5, 72.5, "Bombay duck – Maharashtra and Gujarat coast",
            "Bombay duck (bombil) is a major catch off the Maharashtra and Gujarat coasts."),
)


# --------------------------------------------------------------------------- #
# Folium map
# --------------------------------------------------------------------------- #

INDIA_CENTER = (15.0, 80.0)
BASEMAPS = {
    "coastline": "Coastline only (works offline)",
    "positron": "Light online map",
    "osm": "OpenStreetMap",
}
BASEMAP_NOTE = (
    "Online base maps are drawn by third parties and may show boundaries differently from the official "
    "map of India. The coastline-only view draws no borders and is for orientation only."
)


def esc(value: Any) -> str:
    """HTML-escape any value (including quotes) for safe embedding."""
    return html.escape(str(value if value is not None else ""), quote=True)


def story_popup_html(s: Story, max_chars: int = 240) -> str:
    snippet = s.text if len(s.text) <= max_chars else s.text[: max_chars].rsplit(" ", 1)[0] + "…"
    lang = LANGUAGES.get(s.language, {}).get("name", s.language)
    sample = "<div style='color:#8a6d00;font-size:11px'>SAMPLE – illustrative, not a real recording</div>" if s.is_sample else ""
    return (
        "<div style='font-family:system-ui,sans-serif;font-size:13px;line-height:1.35;max-width:280px'>"
        f"<b>{esc(s.title)}</b><br>"
        f"<span style='color:#555'>{esc(category_label(s.category))} · {esc(lang)}</span><br>"
        f"<span style='color:#555'>{esc(s.state or s.region)}</span>{sample}"
        f"<p style='margin:6px 0 0'>{esc(snippet)}</p></div>"
    )


def sighting_popup_html(s: Sighting, today: Optional[date] = None) -> str:
    g = GROUPS[s.group]
    age = s.age_days(today)
    when = f"{esc(s.date)}" + (f" ({age} days ago)" if age is not None and age >= 0 else "")
    img = (
        f"<img src='{esc(s.image_url)}' alt='{esc(s.species)}' loading='lazy' referrerpolicy='no-referrer' "
        "style='width:100%;max-height:150px;object-fit:cover;border-radius:6px;margin-top:6px'>"
        if s.image_url
        else ""
    )
    note = "<div style='color:#b00020'>Observer noted the animal was dead (stranding).</div>" if s.vitality.lower() == "dead" else ""
    unc = f"<br>Location uncertainty: ±{s.uncertainty_m / 1000:.0f} km" if s.uncertainty_m and s.uncertainty_m >= 1000 else ""
    link = f"<br><a href='{esc(s.record_url)}' target='_blank' rel='noopener noreferrer'>GBIF record</a>" if s.record_url else ""
    return (
        "<div style='font-family:system-ui,sans-serif;font-size:13px;line-height:1.35;max-width:260px'>"
        f"<b>{g['emoji']} {esc(s.species)}</b><br><i>{esc(s.scientific_name)}</i><br>"
        f"Seen: {when}{unc}{note}<br>"
        f"<span style='color:#555'>Licence: {esc(license_name(s.license))} · volunteered observation</span>{link}{img}</div>"
    )


def arrow_html(direction: Optional[float], size: int, color: str) -> str:
    """An SVG arrow pointing the way the water flows (0° = north, clockwise)."""
    rot = 0 if direction is None else direction
    return (
        f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' style='transform:rotate({rot:.0f}deg);overflow:visible'>"
        f"<path d='M12 1 L18 17 L12 13 L6 17 Z' fill='{color}' stroke='#04202e' stroke-width='1' stroke-linejoin='round'/></svg>"
    )


def _legend_html(show_currents: bool, show_wild: bool, show_hot: bool) -> str:
    rows = []
    if show_currents:
        rows.append("<b>Ocean current</b> (arrow = flow direction)")
        for col, txt in (("#2B8CBE", "&lt; 0.5 km/h"), ("#2E9E6B", "0.5–1.5"), ("#E0A800", "1.5–3"), ("#D9534F", "&gt; 3 km/h")):
            rows.append(f"<span style='color:{col}'>&#9650;</span> {txt}")
    if show_wild:
        rows.append("<b>Sightings</b> (people's observations)")
        for g in GROUPS.values():
            rows.append(f"{g['emoji']} {esc(g['label'])}")
    if show_hot:
        rows.append("<span style='opacity:.8'>⭘ dashed = reference area, not live</span>")
    if not rows:
        return ""
    return (
        "<div style='position:fixed;bottom:22px;left:12px;z-index:9999;background:rgba(255,255,255,.93);color:#102a3a;"
        "padding:8px 10px;border-radius:8px;font:12px/1.5 system-ui,sans-serif;box-shadow:0 1px 6px rgba(0,0,0,.3);max-width:200px'>"
        + "<br>".join(rows)
        + "</div>"
    )


def build_map(
    stories: Iterable[Story] = (),
    *,
    basemap: str = "coastline",
    show_stories: bool = True,
    currents: Sequence[CurrentCell] = (),
    min_current_kmh: float = 0.0,
    sightings: Optional[dict[str, list[Sighting]]] = None,
    hotspots: bool = False,
    center: tuple[float, float] = INDIA_CENTER,
    zoom: int = 5,
    max_per_group: int = 100,
    today: Optional[date] = None,
):
    """Build a ``folium.Map`` with stories, ocean currents, sightings and reference hotspots."""
    import folium  # lazy: keeps this module importable without folium

    m = folium.Map(location=list(center), zoom_start=zoom, min_zoom=4, max_zoom=12, tiles=None, control_scale=True, prefer_canvas=True)
    if basemap == "osm":
        folium.TileLayer("OpenStreetMap", name="OpenStreetMap", control=False).add_to(m)
    elif basemap == "positron":
        folium.TileLayer("CartoDB positron", name="Light map", control=False).add_to(m)
    else:
        m.get_root().header.add_child(
            folium.Element("<style>.leaflet-container{background:#d7ebf5}.sk-empty{background:none;border:none}</style>")
        )
    # coastline is always drawn: it gives orientation even if tiles fail to load
    folium.PolyLine(COAST, color="#1B6A8A", weight=2, opacity=0.9, tooltip="Coastline (approximate)").add_to(m)
    folium.PolyLine(LANKA + [LANKA[0]], color="#1B6A8A", weight=2, opacity=0.6).add_to(m)
    for name, lat, lng in SEA_LABELS:
        folium.Marker(
            [lat, lng],
            icon=folium.DivIcon(html=f"<div style='color:#3d6b82;font:italic 600 13px system-ui;white-space:nowrap;opacity:.85'>{esc(name)}</div>", icon_size=(120, 18), class_name="sk-empty"),
            interactive=False,
        ).add_to(m)

    if currents:
        fg = folium.FeatureGroup(name="Ocean currents", show=True)
        for c in currents:
            if c.speed_kmh < min_current_kmh:
                continue
            size = int(round(16 + min(c.speed_kmh, 4) * 5))
            sst = f", sea {c.sst:.1f}°C" if c.sst is not None else ""
            tip = f"{c.speed_kmh:.1f} km/h ({c.speed_knots:.1f} kn) → {compass(c.direction)}{sst}"
            folium.Marker(
                [c.lat, c.lng],
                icon=folium.DivIcon(html=arrow_html(c.direction, size, current_color(c.speed_kmh)), icon_size=(size, size), icon_anchor=(size // 2, size // 2), class_name="sk-empty"),
                tooltip=esc(tip),
            ).add_to(fg)
        fg.add_to(m)

    show_wild = bool(sightings and any(sightings.values()))
    if sightings:
        for key, items in sightings.items():
            if key not in GROUPS or not items:
                continue
            g = GROUPS[key]
            fg = folium.FeatureGroup(name=f"{g['emoji']} {g['label']}", show=True)
            for s in items[:max_per_group]:
                fresh = (s.age_days(today) or 9999) < 7
                ring = "box-shadow:0 0 0 4px rgba(255,255,255,.55);" if fresh else ""
                icon = (
                    f"<div style='width:24px;height:24px;border-radius:50%;background:{g['color']};border:2px solid #fff;"
                    f"display:flex;align-items:center;justify-content:center;font-size:13px;{ring}'>{g['emoji']}</div>"
                )
                folium.Marker(
                    [s.lat, s.lng],
                    icon=folium.DivIcon(html=icon, icon_size=(24, 24), icon_anchor=(12, 12), class_name="sk-empty"),
                    tooltip=esc(f"{s.species} · {s.date}"),
                    popup=folium.Popup(sighting_popup_html(s, today), max_width=280),
                ).add_to(fg)
            fg.add_to(m)

    if hotspots:
        fg = folium.FeatureGroup(name="Reference areas (not live)", show=True)
        for h in HOTSPOTS:
            g = GROUPS[h.group]
            folium.CircleMarker(
                [h.lat, h.lng], radius=11, color=g["color"], weight=2, dash_array="5 5", fill=True, fill_opacity=0.12,
                tooltip=esc(h.title),
                popup=folium.Popup(
                    f"<div style='font:13px system-ui;max-width:250px'><b>{g['emoji']} {esc(h.title)}</b><br>{esc(h.note)}"
                    "<br><i style='color:#666'>Reference area – not live data.</i></div>",
                    max_width=270,
                ),
            ).add_to(fg)
        fg.add_to(m)

    if show_stories:
        fg = folium.FeatureGroup(name="Fisher stories", show=True)
        for s in stories:
            if not s.has_location:
                continue
            color = CATEGORIES.get(s.category, CATEGORIES["other"])["color"]
            folium.CircleMarker(
                [s.lat, s.lng], radius=8, color="#ffffff", weight=2, fill=True, fill_color=color, fill_opacity=0.92,
                tooltip=esc(s.title), popup=folium.Popup(story_popup_html(s), max_width=300),
            ).add_to(fg)
        fg.add_to(m)

    legend = _legend_html(bool(currents), show_wild, hotspots)
    if legend:
        m.get_root().html.add_child(folium.Element(legend))
    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    return m


def story_counts_by_region(stories: Iterable[Story]) -> list[tuple[str, int]]:
    """``[(region name, count)]`` sorted by count – used for the sidebar summary."""
    counts: dict[str, int] = {}
    names = {r.id: r.name for r in REGIONS}
    for s in stories:
        if s.region in names:
            counts[names[s.region]] = counts.get(names[s.region], 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))

