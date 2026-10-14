# User journeys

The people below are **illustrative personas**, not real individuals or research findings. Replace them with what you learn from real users.

## 1. Contributor – "Ravi", a boat owner on the Konkan coast

| Step | What Ravi does | What the app does |
|---|---|---|
| 1 | Opens the site on his phone | Home explains the purpose; emergency number is always visible. |
| 2 | Opens **Contribute a story** | Plain-language consent box; Save stays disabled until he agrees. |
| 3 | Taps the microphone and speaks for ~20 s in Marathi, or types | Audio is checked; if a Sarvam key is configured, a *Transcribe* button offers a draft he can correct. |
| 4 | Picks language and *Koli* as dialect, adds a title | Topic is suggested automatically ("Choose for me") or he picks one. |
| 5 | Chooses **Mumbai & Konkan**; marks a spot but keeps **Approximate** | The pin is rounded to ~5 km *before* saving. |
| 6 | Keeps his name hidden | Story shows "Anonymous". |
| 7 | Presses **Save my story** | A one-time **withdraw code** is shown: *write it down*. If moderation is on, the story waits for approval. |

*Edge cases handled:* wrong file type, empty / too-long recordings, a phone number typed into the story (removed automatically), nothing typed, consent not ticked.

## 2. Reader – "Meera", a student

1. Opens **Story library**, searches `sardine`, then `ചാകര` – both find stories (the second via its script, the first also via English summaries of non-English stories).
2. Filters to *Folktale & belief*, opens "Bonbibi, Lady of the Forest", expands **Test yourself**.
3. Opens **Dialect glossary**, compares how *sardine* is named in Malayalam, Tamil, Kannada and Marathi.

## 3. Researcher – "Dr. Iyer"

1. Filters the library by region and topic; the **Report** tab shows counts by topic and language.
2. Opens the **Coastal map**, turns on ocean currents and sightings, and notes where "changes over time" stories cluster.
3. Downloads **CSV / JSON** – public fields only; names appear only where narrators allowed it.
4. Filters the export on the `research_consent` column: only stories whose narrators ticked *researchers may use* are intended for study. Sample stories are `false`.

## 4. Withdrawing a story

Library → *Withdraw / moderate* → enter story id and code → the story and its recording are deleted. Lost code? In the prototype only an administrator can remove the story by editing the data file.

## 5. Moderator

With `ADMIN_PASSCODE` set, new stories are `pending`. The moderator opens *Library → Withdraw / moderate*, enters the passcode, and approves or rejects each one. Reject anything with private details, abuse or commercial spam.

## 6. Adding glossary words (community workflow)

1. Open `data/dialect_glossary.csv`.
2. Add a row: `id`, the word in its own script, a plain-Latin `transliteration`, language code (see `LANGUAGES` in `src/story_manager.py`), where it is used, a shared `concept` key (e.g. `sardine`), a category, the English meaning, an optional note.
3. Leave `status` as `needs_review`; change it to `verified` only after a native speaker from that coast has confirmed it.
4. Run `pytest` – the glossary test checks ids, required columns and language codes.
5. Open a pull request.
