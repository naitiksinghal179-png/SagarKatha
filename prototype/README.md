# SagarKatha – first HTML prototype (v3)

`index.html` is the single-file prototype that came before the Streamlit app in the parent folder. It is kept here for reference and for demos; **the Streamlit app is the maintained version.**

Open `index.html` in a browser (no install). Needs internet for the map library, map tiles and Open-Meteo.

## What it has
Story recording and a local database (IndexedDB), a live-style map with story pins, ocean-current and weather views, folktales, a community board, reports with download/print, and a language switcher (English and Hindi built in; other languages are machine-translated on demand).

## Limits – read before showing it
- **AI features** (chatbot, translation into other languages) call `CFG.AI_URL` without any key, so they only work where such calls are provided for you (for example, inside Claude). Elsewhere they fail and the page falls back to built-in text where it can. For real use, point `CFG.AI_URL` at **your own server-side proxy**. Never put an API key in this file.
- **Data stays in the visitor's browser.** There is no shared backend, so stories from different people are not combined.
- **Weather thresholds are demo values**, not official advisories (use INCOIS / IMD). Emergency at sea: Indian Coast Guard **1554**.
- This file was recovered from the build conversation. A JavaScript syntax check passed; it has **not** been re-run in a browser against the live services since then.
- Not covered by the privacy protections described in `docs/consent_and_privacy.md`; those apply to the Streamlit app.
