# Solution overview

**SagarKatha (सागरकथा)** – "stories of the sea" – is a web app where coastal people record what they know about the sea, in their own language, and where anyone can search it, hear it, and see it on a map next to live ocean data.

Built for the **Viksit Bharat Young Leaders Dialogue (VBYLD) 2027**. It fits the *Hack for Social Cause* and *Design for Bharat* tracks; check the current track list and rules on the MY Bharat portal before submitting.

## What is built (and tested)

| Area | What it does | Where |
|---|---|---|
| **Contribute** | Consent first → record with the microphone *or* upload audio *or* just type → optional automatic transcript → topic, tags, place, privacy level → save. A one-time **withdraw code** is shown. | `pages/1_Contribute_Story.py` |
| **Topic sorting** | Every story is classified into a topic (fish & sea life, currents & tides, weather, changes over time, technique, folklore). Offline keyword classifier by default; an optional AI call if a key is set. The model's answer can only pick from the fixed list. | `src/story_manager.py` |
| **Library** | Search that works in every script (Devanagari, Tamil, Malayalam, Bengali, Odia …), filters, folktale quizzes, a live report with charts, CSV / JSON export, withdraw, moderator queue. | `pages/2_Story_Library.py`, `src/search.py` |
| **Coastal map** | Story pins on an offline-capable coastline map; optional **live ocean-current arrows** (Open-Meteo), **whale / shark / fish sightings** (GBIF), reference hotspots, and a per-coast **sea & weather report** with a traffic-light rating. | `pages/3_Coastal_Map.py`, `src/map_handler.py` |
| **Dialect glossary** | 68 draft words for fish, boats, nets, tides and communities across 10 languages, with a "compare one concept across languages" view. Every entry is marked *needs review*. | `pages/4_Dialect_Glossary.py`, `data/dialect_glossary.csv` |
| **22 languages** | Stories and glossary accept all 22 scheduled languages, English and "other / local dialect". Speech-to-text via Sarvam covers all 22 + English; Whisper covers about 15. | `src/story_manager.py`, `src/transcription.py` |
| **Privacy by design** | Consent gate, location blurring before saving, phone / e-mail / ID redaction, anonymous by default, hashed withdraw codes, moderation, safe exports. | see [consent_and_privacy.md](consent_and_privacy.md) |

## What is *not* built yet

Being honest about this matters more than a long feature list:

- **Images and video uploads.** Audio only for now.
- **User accounts / login.** Withdraw codes replace accounts in this prototype.
- **App interface in 22 languages.** Story content is multilingual; the interface text is English. (A PWA prototype with a translated interface was built earlier; it is not part of this repository.)
- **Offline-first mobile experience.** It is a normal web app; recording needs a network connection to reach the server.
- **Production database.** Stories are stored in a JSON file. See [system_architecture.md](system_architecture.md) for the upgrade path.
- **Verified translations / glossary.** All sample translations and glossary words were drafted with AI assistance and need review by native speakers.
- **Live animal tracking.** Sightings are volunteered observations, not tracking.
- **Official warnings.** The sea rating is indicative only; INCOIS / IMD advisories and the Coast Guard (1554) are the authority.

## How it compares to the usual approach

- Not a survey form: the contributor stays in control (consent, precision, withdrawal).
- Not a black-box AI: the classifier, redaction and search are small, readable and unit-tested (100+ tests).
- Not a map of pretty dots: the map puts people's stories next to ocean currents and sightings, so patterns can be asked about ("do sardine stories cluster where the current is strong?").

## Suggested success measures for a pilot

1. Number of consented stories from at least three coastal districts, in at least three languages.
2. Share of stories where the contributor kept the default (approximate) location.
3. Transcript word-error rate on a small set of hand-corrected recordings per dialect.
4. Glossary words confirmed by native speakers.
5. Time for a first-time contributor to save a story (target: under 5 minutes).

## Roadmap

1. Pilot with one fishing cooperative; fix what real users stumble on.
2. Postgres + PostGIS, private object storage, phone-OTP login, role-based moderation.
3. Image and short-video uploads with EXIF stripping.
4. Interface localisation, starting with Hindi, Marathi, Gujarati, Malayalam, Tamil, Bengali, Odia.
5. Offline-first client (PWA) that queues recordings until the network returns.
6. Community review workflow for the glossary.
