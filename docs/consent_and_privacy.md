# Consent and privacy

> This document describes what the software does. It is **not legal advice**. Have a lawyer review it, and agree it with the communities involved, before collecting real people's data.

## Principles

1. **Consent before collection.** Nothing can be saved until the contributor ticks the consent box. Research use is a separate, optional box.
2. **Contributor control.** Contributors choose language, topic, how precisely the place is shown, whether their name is shown, and whether the recording is playable by visitors.
3. **Collect less.** No accounts, phone numbers, e-mail addresses or exact GPS are required. Anonymous is the default.
4. **Withdrawal is real.** Each story gets a one-time withdraw code; with it the story *and its recording* are deleted.
5. **Community knowledge is not free raw material.** The CARE principles for Indigenous and community data governance (Collective benefit, Authority to control, Responsibility, Ethics) are the guide for any future research or commercial use.
6. **Honesty.** Sample content is labelled as sample everywhere. Machine translations and glossary entries are labelled as drafts.

## What is stored

| Data | Stored? | Notes |
|---|---|---|
| Story text, title, language, dialect, topic, tags | Yes | Phone numbers, e-mails and long ID-like numbers are removed automatically before saving. Names inside the text are *not* detected – contributors are told not to include them. |
| Audio recording | Optional | Random file name on the server; visitors can play it only if the contributor allowed it. |
| Location | Optional | Rounded to a ~5 km grid (default) or to the coastal region *before* saving. The exact point is stored only if the contributor chooses *Exact*. |
| Name / nickname | Optional | Shown only if the contributor ticks *Show my name*; otherwise "Anonymous". Never included in exports unless shown. |
| Consent flags and time | Yes | `consent_public`, `consent_research`, `consent_at`. |
| Withdraw code | Only its SHA-256 hash | The code is shown once and cannot be recovered. |
| IP address, cookies, analytics | Not by the app | Streamlit usage statistics are disabled in `.streamlit/config.toml`. Your hosting provider may still keep server logs. |

## Who sees what

- **Everyone:** approved stories (text, optional audio, blurred pin, name only if allowed).
- **Moderator:** pending stories.
- **Server administrator:** the data files, including recordings and consent flags.
- **Downloads (CSV / JSON):** public fields only – no audio file names, no hashes, no hidden names.

## Third parties

| Service | When | What is sent |
|---|---|---|
| Sarvam AI or OpenAI (speech-to-text) | Only if a key is configured **and** the contributor presses *Transcribe* | The audio clip and language code. |
| Anthropic API (topic suggestion) | Only if a key is configured **and** the contributor ticks the AI box | Title and text *after* PII redaction. |
| Open-Meteo, GBIF | Map and sea-report pages | Coordinates of the coast being viewed – never story content or contributor data. |
| Base-map tile servers | Only if the contributor/viewer selects an online map | The viewer's IP address and the map area (as with any web map). |

Check each provider's own terms and privacy policy before enabling it for real contributors.

## Location safety

A fishing ground is a livelihood. Rounding the pin protects it from being pinpointed; the *region-only* option protects it further. Reference areas on the map are generic and come from well-documented public knowledge, not from contributors.

## Children

The consent text asks contributors under 18 to involve a parent or guardian. The app does not verify age. For a public launch, add a proper age / guardian flow.

## Legal context (for your lawyer)

- **Digital Personal Data Protection Act, 2023** and the **DPDP Rules, 2025** (notified 14 November 2025; most consent-notice and security obligations apply 18 months after notification). They require clear, plain-language notice, a way to withdraw consent, and verifiable parental consent for children's data. Check whether a research or archiving exemption applies to you.
- **Biological Diversity Act, 2002** – knowledge associated with biological resources can carry access-and-benefit-sharing duties. Take advice before commercial or foreign use of stories about species.
- **Wild Life (Protection) Act, 1972** – do not publish exact locations of protected species. The sightings layer shows GBIF coordinates as reported; platforms may already blur protected species.
- **Copyright / moral rights** – recordings and tales belong to their narrators and communities. The licence in this repository covers the *software*; contributed stories need their own licence terms agreed with contributors.

## Security measures

See "Security controls" in [system_architecture.md](system_architecture.md). Summary: upload sniffing and size caps, random file names, escaped output, safe CSV export, hashed withdraw codes, optional moderation, secrets in environment variables.

## Known gaps before a public launch

- No accounts or per-user moderation roles.
- No malware scanning, no submission rate limit.
- Redaction cannot catch names or addresses written in words.
- Data on the server is not encrypted at rest by the app (use disk / database encryption).
- No automated retention policy – decide how long stories are kept.
- Backups, if you make them, must honour withdrawals.

## If something goes wrong

Take the app offline, remove the affected data, tell affected contributors and the relevant authority as the law requires, and record what happened.

## Contact

Add a monitored contact address for withdrawal requests and complaints before launch. (Intentionally left blank in this repository – do not publish personal contact details unless you mean to.)
