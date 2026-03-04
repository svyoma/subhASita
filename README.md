# subhāṣita-darpaṇaḥ — Sanskrit Wisdom Explorer

A Flask web application for browsing, searching, and exploring Sanskrit *subhāṣita* (wise sayings) from classical texts. Features Devanāgarī/IAST display, cross-text similarity, shared pāda detection, and per-verse author attribution.

> Vibe-coded with Claude · by [Vyom](https://github.com/svyoma)

---

## Features

- **16,000+ verses** from six classical Sanskrit anthologies
- **Devanāgarī ↔ IAST toggle** (keyboard: `T`)
- **Full-text search** across all texts with simplified diacritic matching
- **Per-verse attribution** — poets identified in anthology texts (Vidyākara's *Ratnakoṣa* etc.)
- **Cross-text verse linking** — same verse appearing in multiple texts shown as cross-references
- **Shared pāda detection** — quarter-verses that recur across the corpus (multi-word pādas only)
- **TF-IDF cosine similarity** — semantically related verses in the sidebar (hyphens ignored)
- **Concordance** — find every occurrence of any word
- **Meter browser** — filter by pāda count (2-pāda, 4-pāda, 6-pāda …)
- **Insights page** — corpus statistics, attribution distribution, meter charts
- **Flashcard mode** — blur the second half of a verse for memorisation practice
- **Bookmarks / Favorites page** — saved in browser localStorage, no account needed
- **Share button** — native share sheet on mobile, clipboard fallback on desktop
- **PWA support** — installable as a home-screen app on iOS/Android

### Accessibility

- **Skip-to-content** link for keyboard users
- **Accessibility panel** (⊕ icon in navbar):
  - Font size: Small / Normal / Large / Extra Large
  - Dark mode
  - High contrast mode
  - Reduce motion
  - Script toggle (Devanāgarī / IAST)
- **ARIA labels** on all interactive elements
- Full keyboard navigation with shortcuts:
  - `T` — toggle script
  - `/` — focus search
  - `F` — toggle bookmark
  - `J` / `K` — next / prev verse

### Mobile

- Offcanvas filter sidebar on Browse page
- Fixed bottom action bar (prev / bookmark / share / next) on verse pages
- 44 px minimum touch targets
- Safe-area padding for notched phones

---

## Texts Included

| # | Title | Author | Verses | Format |
|---|-------|--------|--------|--------|
| 1 | *Mahāsubhāṣitasaṅgrahaḥ* | Anthology | 9,952 | A |
| 2 | *Saduktikarṇāmṛtam* | Śrīdharadāsa | 2,352 | B |
| 3 | *Subhāṣitāvaliḥ* | Anthology | 1,034 | A |
| 4 | *Subhāṣitaratnakoṣa* | Vidyākara | 1,734 | C (GRETIL) |
| 5 | *Śatakatraya* | Bhartṛhari | 321 | C (GRETIL) |
| 6 | *Darpadalana* | Kṣemendra | 596 | C (GRETIL) |

---

## Credits & Data Sources

Raw text data is sourced from **Vishwas Vasuki**'s Sanskrit raw e-text repository:

> **https://github.com/sanskrit/raw_etexts**

No copyright infringement intended. All texts are from publicly available corpus files in the GRETIL (Göttingen Register of Electronic Texts in Indian Languages) tradition. The original Sanskrit texts are in the public domain.

---

## Requirements

- Python 3.11+
- Dependencies in `requirements.txt`:

```
flask
aksharamukha
indic-transliteration
scikit-learn
numpy
```

Install:

```bash
pip install -r requirements.txt
```

---

## Local Development

```bash
git clone <your-repo-url>
cd similarity

pip install -r requirements.txt

python app.py
# -> http://127.0.0.1:5000
```

On first run the app will:
1. Parse all `Devanagari_IAST_*.txt` files in the project directory
2. Build the SQLite database (`subhashita.db`)
3. Compute exact pāda-match pairs
4. Assign cross-text verse groups
5. Compute TF-IDF cosine similarity (takes ~2–3 min for the full corpus)

Subsequent runs skip all pre-computation (idempotent).

---

## Rebuilding the Database

After modifying parsers, text files, or similarity logic:

```bash
# Stop the running server first
rm -f subhashita.db
python app.py
# Wait for "Ready." then Ctrl-C to stop
```

> **Required after these changes:** attribution parsing fix, shared-pāda filter, hyphen-normalisation in similarity.

---

## Adding New Text Files

Place files matching `Devanagari_IAST_*.txt` in the project root. The parser auto-detects one of three formats:

| Format | Identifier | Example files |
|--------|-----------|--------------|
| **A** | `NNNN-P text` pāda lines | *mahāsubhāṣitasaṅgrahaḥ*, *subhāṣitāvaliḥ* |
| **B** | Free verse ending `\|\|N\|\|` | *saduktikarṇāmṛtam* |
| **C** | GRETIL `.. abbrev_X.Y ..` markers | *ratnakoṣa*, *śatakatraya*, *darpadalana* |

Add a `+++` metadata header to the file for title/author:

```
+++
title = "My Sanskrit Text"
author = "Author Name"
+++
```

---

## Verse Display Format

Verses are formatted with traditional Sanskrit dandas, one pāda per line:

```
pāda 1
pāda 2 ।
pāda 3
pāda 4 ॥
```

For 2-pāda verses:

```
pāda 1 ।
pāda 2 ॥
```

---

## Vercel Deployment

### 1. Pre-build the database locally

```bash
rm -f subhashita.db
python app.py
# Wait for "Ready." — this takes 2–3 minutes
# Then Ctrl-C to stop
```

### 2. Commit the database

```bash
git add subhashita.db
git commit -m "Add pre-built database for Vercel deployment"
git push
```

> **Note:** If `subhashita.db` exceeds 100 MB, use [Git LFS](https://git-lfs.github.com/):
> ```bash
> git lfs install
> git lfs track "*.db"
> git add .gitattributes subhashita.db
> ```

### 3. Deploy

Connect your GitHub repository to [Vercel](https://vercel.com) for automatic deployments, or use the CLI:

```bash
npm i -g vercel
vercel login
vercel --prod
```

The included `vercel.json` configures the Python WSGI runtime. The app automatically copies `subhashita.db` to `/tmp/` on cold start to satisfy Vercel's read-only filesystem requirement.

> **Important:** At runtime on Vercel, the app is read-only — no new text files will be parsed and no similarity indexes will be rebuilt. Always pre-build locally before deploying.

---

## Project Structure

```
similarity/
├── app.py                  Flask routes and startup init
├── db.py                   SQLite access layer
├── parse.py                Text file parsers (Format A / B / C)
├── similarity_engine.py    TF-IDF + exact pāda-hash pre-computation
├── transliterate.py        IAST → Devanāgarī (aksharamukha + fallback)
├── requirements.txt
├── vercel.json
├── subhashita.db           Pre-built SQLite database (generated)
├── Devanagari_IAST_*.txt   Source text files
├── static/
│   ├── css/style.css
│   ├── js/app.js
│   ├── manifest.json       PWA manifest
│   └── icons/icon.svg      PWA icon
└── templates/
    ├── base.html           Navbar, accessibility panel, footer
    ├── index.html          Home — verse of the day, stats
    ├── browse.html         Search & filter with mobile offcanvas
    ├── verse.html          Verse detail, shared pādas, similar verses
    ├── favorites.html      Bookmarked verses (localStorage)
    ├── shared_padas.html   Cross-corpus pāda recurrence
    ├── concordance.html    Word concordance
    ├── insights.html       Statistics & charts
    └── sources.html        Text sources
```

---

## License

Application code: MIT License.

Sanskrit text content: sourced from the [Sanskrit raw e-texts repository](https://github.com/sanskrit/raw_etexts) by Vishwas Vasuki. The original texts are classical Sanskrit literature in the public domain.
