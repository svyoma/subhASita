# subhāṣita Explorer — Feature Ideas

A living list of potential enhancements, roughly grouped by theme.

---

## 1. Text & Data Enrichment

### 1.1 Meter Identification
Automatically identify the Sanskrit metre (chandas) of each verse — anuṣṭubh, śārdūlavikrīḍita, mandākrāntā, etc. — using syllable-counting heuristics or a dedicated chandas library. Display as a badge on the verse page and as a filterable facet in Browse.

### 1.2 Expanded Source Cross-References
The saduktikarṇāmṛtam and subhāṣitaratnakoṣaḥ contain source abbreviations (su.ra., śā.pa., skmsa.u.ka. …). Currently stored and expanded on display. Future: resolve each reference to a verse in the DB if that work is also loaded, turning source citations into clickable cross-links.

### 1.3 Additional Text Sources
Load more anthologies from Vishwas Vasuki's raw_etexts repo:
- *Śārṅgadhara-paddhati* (largest Sanskrit anthology, ~4,500 verses)
- *Sūkti-muktāvalī* (~2,380 verses)
- *Subhāṣita-ratnabhāṇḍāgāram*
- Individual poet collections: *Amaruśataka*, *Bhartṛhari* (already loaded as śatakatrayam), *Bāṇabhaṭṭa*, etc.

### 1.4 Devanāgarī Display of Composer Names
Currently attributions are stored in IAST. Render them in Devanāgarī using the existing `to_devanagari()` transliterator when the Devanāgarī script mode is active.

### 1.5 Word-by-Word Gloss (Anvaya)
For selected verses, store or generate a word-by-word gloss (anvaya order + translation notes). Could be manually curated or linked from external Sanskrit dictionaries (Monier-Williams, Apte).

---

## 2. Search & Discovery

### 2.1 Full-Text Search with Ranking
Replace the current LIKE-based search with SQLite FTS5 (full-text search) for faster, relevance-ranked results. Support phrase queries, prefix wildcards, and proximity operators.

### 2.2 Sandhi-Aware Search
Break user queries across sandhi boundaries before searching so that searching `rājā` also finds `rājāpi`, `tato rājā`, etc. Use the `indic_transliteration` library for basic sandhi splitting.

### 2.3 Script-Flexible Input
Let users type in Devanāgarī, IAST, Harvard-Kyoto (HK), SLP1, or ITRANS in the search box, normalising all to IAST before querying. Currently only IAST/simplified is supported.

### 2.4 Semantic / Vector Search
Embed verse texts with a multilingual sentence-transformer and store embeddings in a vector index (e.g., sqlite-vss, Chroma, or FAISS). Provide a "find verses with similar meaning" feature beyond the current TF-IDF similarity.

### 2.5 Advanced Filters in Browse
- Filter by metre (once metre detection is added)
- Filter by century / period (requires manual metadata)
- Filter by number of cross-text occurrences (verse_group_id present)
- Exclude verses with no attribution

### 2.6 Concordance Enhancements
The existing concordance page shows all verses containing a word. Add:
- Collocates: which words most frequently appear near the query word
- KWIC (keyword-in-context) view sorted by left/right context
- Lemma support (search for a root and find all inflected forms)

---

## 3. Reading & Learning

### 3.1 Verse of the Day
Display a different verse each day (seeded by date). Already partially implemented via `get_random_verse(seed=today_int)`. Add a dedicated landing-page section and an email/RSS subscription option.

### 3.2 Spaced Repetition / Memorisation Mode
Expand the existing flashcard mode into a full spaced-repetition system (SM-2 algorithm). Track which verses the user has reviewed, when to review next, and their self-reported recall score — all stored in `localStorage` or an optional user account.

### 3.3 Audio Pronunciation
Embed or link to audio recordings of verses for correct Sanskrit pronunciation and metre. Could start with TTS (Google/Azure Sanskrit TTS) and replace with human recordings over time.

### 3.4 Verse Collections / Reading Lists
Let users create named collections (beyond single bookmarks). Each collection is a named list of verse IDs stored in `localStorage` or a server-side user table. Share collections as URLs.

### 3.5 Progress Tracking
Track which verses a user has read, bookmarked, or memorised. Show per-text reading progress ("you've read 47 of 321 verses in śatakatrayam").

---

## 4. Social & Collaboration

### 4.1 User Annotations
Allow logged-in users to add notes, translations, or corrections to individual verses. Store in a `annotations` table linked to `verse_id`. Show community annotations below the verse text.

### 4.2 Crowdsourced Translations
Invite contributors to submit English/Hindi/regional language translations. Moderated queue → approved translations displayed under verses.

### 4.3 Corrections / Errata Reporting
A simple "Report error" button that logs the verse ID and a user comment for the admin to review — useful for fixing misattributions or OCR errors in the source files.

---

## 5. Visualisation & Analytics

### 5.1 Author Network Graph
Visualise which authors appear in multiple anthologies (shared attribution nodes). An interactive force-directed graph showing poets, anthologies, and the verses linking them.

### 5.2 Thematic Clustering
Apply LDA or k-means on verse TF-IDF vectors to suggest additional topic clusters beyond the hand-curated `auto_tags`. Display a tag-cloud per cluster.

### 5.3 Timeline of Poets
For poets with known dates (Kālidāsa, Bhartṛhari, Āmaru, etc.), render a timeline showing when they lived, how many verses are attributed to them, and which anthologies include them.

### 5.4 Shared-Pāda Network
The existing Shared Pādas page shows individual shared pādas. Extend it to a graph view: nodes = verse groups sharing ≥2 pādas, edges = number of shared pādas. Reveals transmission and adaptation patterns across anthologies.

---

## 6. Technical / Infrastructure

### 6.1 User Accounts (optional)
Optional account system (OAuth via Google/GitHub) to persist favourites, collections, annotations, and review history server-side rather than just `localStorage`. Keeps features working across devices.

### 6.2 REST API
Expose a read-only JSON API for the entire corpus:
- `GET /api/verse/<id>` (already exists)
- `GET /api/search?q=...&text_id=...`
- `GET /api/random`
- `GET /api/texts`
This enables third-party integrations, mobile apps, and Anki deck generation.

### 6.3 Anki Deck Export
Generate an Anki `.apkg` deck from bookmarked verses (or a whole text), with Devanāgarī on the front and IAST + attribution on the back.

### 6.4 Incremental DB Rebuild
Currently the DB must be fully rebuilt when parser logic changes. Add a per-text checksum (hash of source file) to `build_state` so only changed files are re-parsed on startup — useful as the corpus grows.

### 6.5 Full Vercel Edge Deployment
Move the similarity computation and heavy pandas/sklearn code to a build step, storing all similarity data in the committed DB. The runtime Flask app would then be read-only and suitable for Vercel's serverless environment without timeouts.

### 6.6 OpenGraph / Twitter Cards
Add proper OpenGraph meta tags to verse pages so sharing a verse URL on social media renders a preview card with the Devanāgarī text and attribution.

---

## 7. Accessibility & Internationalisation

### 7.1 Screen-Reader Optimisation
Add `aria-label` attributes to all verse text blocks with a plain-Roman transliteration for screen readers that cannot render Devanāgarī or IAST diacritics correctly.

### 7.2 Hindi / Vernacular Interface
Offer the UI in Hindi or other Indian languages alongside English, using Flask-Babel or a simple string-table approach.

### 7.3 High-Contrast & Large-Print Themes
Extend the existing accessibility panel with pre-defined themes (sepia, night, high-contrast) stored in CSS custom properties and toggled via `localStorage`.

---

*Last updated: 2026-03-09*
