"""
Database layer for the subhāṣita explorer.
Uses SQLite with a single file `subhashita.db`.
"""

import sqlite3
import json
import os
import shutil
import hashlib
from pathlib import Path

_LOCAL_DB = Path(__file__).parent / 'subhashita.db'


def _get_db_path() -> Path:
    """Return writable DB path. On Vercel (read-only FS), copy to /tmp first."""
    if os.environ.get('VERCEL'):
        tmp = Path('/tmp/subhashita.db')
        if not tmp.exists() and _LOCAL_DB.exists():
            shutil.copy2(str(_LOCAL_DB), str(tmp))
        return tmp
    return _LOCAL_DB


DB_PATH = _get_db_path()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


# ── Schema ────────────────────────────────────────────────────────────────────

def init_schema():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS texts (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            title         TEXT    NOT NULL,
            author        TEXT,
            filename      TEXT    NOT NULL UNIQUE,
            language      TEXT    DEFAULT 'saṃskṛtam',
            domain        TEXT,
            serial_no     TEXT,
            verse_count   INTEGER DEFAULT 0,
            abbreviations TEXT    DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS verses (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            text_id           INTEGER NOT NULL REFERENCES texts(id),
            verse_num         INTEGER NOT NULL,
            verse_num_str     TEXT    NOT NULL,
            pada_count        INTEGER NOT NULL DEFAULT 2,
            full_text_iast    TEXT    NOT NULL,
            full_text_deva    TEXT    NOT NULL,
            full_text_simple  TEXT    NOT NULL,
            attribution       TEXT,
            sources           TEXT,
            chapter           TEXT,
            section           TEXT,
            auto_tags         TEXT    DEFAULT '[]',
            verse_group_id    INTEGER
        );

        CREATE TABLE IF NOT EXISTS padas (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            verse_id   INTEGER NOT NULL REFERENCES verses(id),
            pada_num   INTEGER NOT NULL,
            text_iast  TEXT    NOT NULL,
            text_deva  TEXT    NOT NULL,
            pada_hash  TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS pada_matches (
            pada1_id   INTEGER NOT NULL,
            pada2_id   INTEGER NOT NULL,
            PRIMARY KEY (pada1_id, pada2_id)
        );

        CREATE TABLE IF NOT EXISTS verse_similarity (
            verse1_id  INTEGER NOT NULL,
            verse2_id  INTEGER NOT NULL,
            similarity REAL    NOT NULL,
            PRIMARY KEY (verse1_id, verse2_id)
        );

        CREATE TABLE IF NOT EXISTS build_state (
            key   TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_verses_text_id  ON verses(text_id);
        CREATE INDEX IF NOT EXISTS idx_verses_chapter  ON verses(chapter);
        CREATE INDEX IF NOT EXISTS idx_padas_verse_id  ON padas(verse_id);
        CREATE INDEX IF NOT EXISTS idx_padas_hash      ON padas(pada_hash);
        CREATE INDEX IF NOT EXISTS idx_sim_v1          ON verse_similarity(verse1_id);
        CREATE INDEX IF NOT EXISTS idx_sim_v2          ON verse_similarity(verse2_id);
        CREATE INDEX IF NOT EXISTS idx_pada_m1         ON pada_matches(pada1_id);
        CREATE INDEX IF NOT EXISTS idx_pada_m2         ON pada_matches(pada2_id);
        CREATE INDEX IF NOT EXISTS idx_verses_group    ON verses(verse_group_id);
        """)


# ── Insert helpers ────────────────────────────────────────────────────────────

def text_already_loaded(filename: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT id FROM texts WHERE filename = ?', (filename,)
        ).fetchone()
        return row is not None


def insert_text_and_verses(metadata: dict, verses: list[dict], filename: str) -> int:
    """Insert one text file worth of data. Returns the text_id."""
    with get_conn() as conn:
        abbrevs = metadata.get('abbreviations', {})
        cur = conn.execute(
            """INSERT INTO texts (title, author, filename, language, domain, serial_no, abbreviations)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                metadata.get('title', filename),
                metadata.get('author'),
                filename,
                metadata.get('language', 'saṃskṛtam'),
                metadata.get('domain'),
                metadata.get('"serial no."') or metadata.get('serial no.'),
                json.dumps(abbrevs, ensure_ascii=False),
            )
        )
        text_id = cur.lastrowid

        for v in verses:
            cur2 = conn.execute(
                """INSERT INTO verses
                   (text_id, verse_num, verse_num_str, pada_count,
                    full_text_iast, full_text_deva, full_text_simple,
                    attribution, sources, chapter, section, auto_tags)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    text_id,
                    v['verse_num'],
                    v['verse_num_str'],
                    v['pada_count'],
                    v['full_text_iast'],
                    v['full_text_deva'],
                    v['full_text_simple'],
                    v.get('attribution'),
                    v.get('sources'),
                    v.get('chapter'),
                    v.get('section'),
                    json.dumps(v.get('auto_tags', []), ensure_ascii=False),
                )
            )
            verse_id = cur2.lastrowid

            for pi, (iast, deva) in enumerate(
                zip(v['padas_iast'], v['padas_deva']), start=1
            ):
                from parse import _normalize_pada
                norm  = _normalize_pada(iast)
                phash = hashlib.md5(norm.encode()).hexdigest()
                conn.execute(
                    """INSERT INTO padas (verse_id, pada_num, text_iast, text_deva, pada_hash)
                       VALUES (?,?,?,?,?)""",
                    (verse_id, pi, iast, deva, phash)
                )

        conn.execute(
            'UPDATE texts SET verse_count = ? WHERE id = ?',
            (len(verses), text_id)
        )
    return text_id


def get_build_state(key: str) -> str | None:
    with get_conn() as conn:
        row = conn.execute(
            'SELECT value FROM build_state WHERE key = ?', (key,)
        ).fetchone()
        return row['value'] if row else None


def set_build_state(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            'INSERT OR REPLACE INTO build_state (key, value) VALUES (?,?)',
            (key, value)
        )


# ── Query helpers ─────────────────────────────────────────────────────────────

def _expand_sources(sources_raw: str | None, abbreviations_json: str | None) -> str | None:
    """Expand abbreviations in a source reference string.

    E.g. "(su.ra. 47, śā.pa. 96)" → "(subhāṣita-ratnākara 47, śārṅgadhara-paddhati 96)"
    """
    if not sources_raw:
        return None
    try:
        abbrevs: dict = json.loads(abbreviations_json or '{}')
    except (ValueError, TypeError):
        return sources_raw
    if not abbrevs:
        return sources_raw
    result = sources_raw
    # Replace longest abbreviations first to avoid partial matches
    for abbrev in sorted(abbrevs, key=len, reverse=True):
        result = result.replace(abbrev, abbrevs[abbrev])
    return result


def get_verse(verse_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT v.*, t.title AS text_title, t.author AS text_author,
                      t.filename AS text_filename, t.abbreviations AS text_abbreviations
               FROM verses v JOIN texts t ON v.text_id = t.id
               WHERE v.id = ?""",
            (verse_id,)
        ).fetchone()
        if not row:
            return None
        verse = dict(row)
        verse['auto_tags'] = json.loads(verse['auto_tags'] or '[]')
        verse['padas'] = _get_padas(verse_id, conn)
        # Expand abbreviations in sources for display
        verse['sources_expanded'] = _expand_sources(
            verse.get('sources'), verse.get('text_abbreviations')
        )
        return verse


def _get_padas(verse_id: int, conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        'SELECT * FROM padas WHERE verse_id = ? ORDER BY pada_num',
        (verse_id,)
    ).fetchall()
    return [dict(r) for r in rows]


PER_PAGE = 20


def search_verses(query: str = '', text_id: int = None, chapter: str = None,
                  tag: str = None, pada_count: int = None,
                  page: int = 1, per_page: int = PER_PAGE) -> tuple[list, int]:
    """
    Search verses with optional filters.
    Returns (verse_rows, total_count).
    """
    from transliterate import simplify
    conditions = []
    params     = []

    if query:
        q_simple = simplify(query)
        conditions.append(
            '(v.full_text_iast LIKE ? OR v.full_text_simple LIKE ? OR v.attribution LIKE ?)'
        )
        params += [f'%{query}%', f'%{q_simple}%', f'%{query}%']

    if text_id:
        conditions.append('v.text_id = ?')
        params.append(text_id)

    if chapter:
        conditions.append('v.chapter = ?')
        params.append(chapter)

    if tag:
        conditions.append("v.auto_tags LIKE ?")
        params.append(f'%{tag}%')

    if pada_count:
        conditions.append('v.pada_count = ?')
        params.append(pada_count)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''
    offset = (page - 1) * per_page

    with get_conn() as conn:
        total = conn.execute(
            f'SELECT COUNT(*) FROM verses v {where}', params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT v.*, t.title AS text_title
                FROM verses v JOIN texts t ON v.text_id = t.id
                {where}
                ORDER BY v.text_id, v.verse_num
                LIMIT ? OFFSET ?""",
            params + [per_page, offset]
        ).fetchall()

    verses = []
    for r in rows:
        d = dict(r)
        d['auto_tags'] = json.loads(d['auto_tags'] or '[]')
        verses.append(d)

    return verses, total


def get_all_texts() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute('SELECT * FROM texts ORDER BY id').fetchall()
    return [dict(r) for r in rows]


def get_random_verse(seed: int = None) -> dict | None:
    with get_conn() as conn:
        if seed is not None:
            count = conn.execute('SELECT COUNT(*) FROM verses').fetchone()[0]
            if count == 0:
                return None
            row_id_offset = seed % count
            row = conn.execute(
                'SELECT id FROM verses ORDER BY id LIMIT 1 OFFSET ?',
                (row_id_offset,)
            ).fetchone()
        else:
            row = conn.execute(
                'SELECT id FROM verses ORDER BY RANDOM() LIMIT 1'
            ).fetchone()
        if not row:
            return None
    return get_verse(row['id'])


def get_shared_padas(min_count: int = 2, limit: int = 200) -> list[dict]:
    """Return pādas appearing in at least min_count verses.

    Single-word pādas (no space in IAST) and danda/punctuation-only
    entries are excluded — a real pāda always contains multiple words.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.pada_hash, p.text_iast, p.text_deva, COUNT(*) AS cnt,
                      GROUP_CONCAT(p.verse_id) AS verse_ids
               FROM padas p
               WHERE INSTR(p.text_iast, ' ') > 0
                 AND LENGTH(REPLACE(REPLACE(TRIM(p.text_iast), '|', ''), ' ', '')) > 3
               GROUP BY p.pada_hash
               HAVING cnt >= ?
               ORDER BY cnt DESC
               LIMIT ?""",
            (min_count, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_padas_for_verse(verse_id: int) -> list[dict]:
    """Return all pādas of a verse with their match counts.

    match_count only counts multi-word pādas (excludes single words / dandas).
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.id, p.pada_num, p.text_iast, p.text_deva,
                      p.pada_hash,
                      CASE
                        WHEN INSTR(p.text_iast, ' ') > 0
                         AND LENGTH(REPLACE(REPLACE(TRIM(p.text_iast), '|', ''), ' ', '')) > 3
                        THEN (SELECT COUNT(*) FROM padas p2
                              WHERE p2.pada_hash = p.pada_hash
                                AND p2.verse_id != p.verse_id)
                        ELSE 0
                      END AS match_count
               FROM padas p
               WHERE p.verse_id = ?
               ORDER BY p.pada_num""",
            (verse_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_verses_sharing_pada(pada_hash: str, exclude_verse_id: int = None) -> list[dict]:
    """Return all verses that share a specific pāda hash."""
    with get_conn() as conn:
        if exclude_verse_id:
            rows = conn.execute(
                """SELECT v.id, v.verse_num_str, v.full_text_iast, v.full_text_deva,
                          t.title AS text_title, p.pada_num, p.text_iast AS pada_text_iast
                   FROM padas p
                   JOIN verses v ON p.verse_id = v.id
                   JOIN texts  t ON v.text_id  = t.id
                   WHERE p.pada_hash = ? AND v.id != ?
                   ORDER BY v.id""",
                (pada_hash, exclude_verse_id)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT v.id, v.verse_num_str, v.full_text_iast, v.full_text_deva,
                          t.title AS text_title, p.pada_num, p.text_iast AS pada_text_iast
                   FROM padas p
                   JOIN verses v ON p.verse_id = v.id
                   JOIN texts  t ON v.text_id  = t.id
                   WHERE p.pada_hash = ?
                   ORDER BY v.id""",
                (pada_hash,)
            ).fetchall()
    return [dict(r) for r in rows]


def get_similar_verses(verse_id: int, limit: int = 5) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT vs.verse2_id AS vid, vs.similarity,
                      v.verse_num_str, v.full_text_iast, v.full_text_deva,
                      v.attribution, t.title AS text_title
               FROM verse_similarity vs
               JOIN verses v ON vs.verse2_id = v.id
               JOIN texts  t ON v.text_id    = t.id
               WHERE vs.verse1_id = ?
               ORDER BY vs.similarity DESC
               LIMIT ?""",
            (verse_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def get_cross_references(verse_id: int) -> list[dict]:
    """Return other verses in the same verse_group (cross-text duplicates)."""
    with get_conn() as conn:
        row = conn.execute(
            'SELECT verse_group_id FROM verses WHERE id = ?', (verse_id,)
        ).fetchone()
        if not row or not row['verse_group_id']:
            return []
        rows = conn.execute(
            """SELECT v.id, v.verse_num_str, v.full_text_iast, v.full_text_deva,
                      v.attribution, v.chapter, t.title AS text_title
               FROM verses v JOIN texts t ON v.text_id = t.id
               WHERE v.verse_group_id = ? AND v.id != ?
               ORDER BY v.id""",
            (row['verse_group_id'], verse_id)
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats() -> dict:
    with get_conn() as conn:
        total_verses = conn.execute('SELECT COUNT(*) FROM verses').fetchone()[0]
        total_padas  = conn.execute('SELECT COUNT(*) FROM padas').fetchone()[0]
        shared_padas = conn.execute(
            'SELECT COUNT(DISTINCT pada_hash) FROM padas GROUP BY pada_hash HAVING COUNT(*) > 1'
        ).fetchone()
        shared_padas_count = conn.execute(
            """SELECT COUNT(*) FROM (
               SELECT pada_hash FROM padas GROUP BY pada_hash HAVING COUNT(*) > 1
            )"""
        ).fetchone()[0]

        texts = conn.execute(
            'SELECT id, title, author, verse_count FROM texts ORDER BY id'
        ).fetchall()

        # Top 30 words: we compute this in Python for reliability
        all_texts_for_words = conn.execute(
            'SELECT full_text_simple FROM verses LIMIT 5000'
        ).fetchall()
        word_rows = _compute_word_freq(all_texts_for_words, limit=30)

        # Attribution distribution (top 15)
        attrib_rows = conn.execute(
            """SELECT attribution, COUNT(*) AS cnt FROM verses
               WHERE attribution IS NOT NULL AND attribution != ''
               GROUP BY attribution ORDER BY cnt DESC LIMIT 15"""
        ).fetchall()

        # pada_count distribution
        meter_rows = conn.execute(
            """SELECT pada_count, COUNT(*) AS cnt FROM verses
               GROUP BY pada_count ORDER BY pada_count"""
        ).fetchall()

    return {
        'total_verses':     total_verses,
        'total_padas':      total_padas,
        'shared_padas':     shared_padas_count,
        'texts':            [dict(r) for r in texts],
        'top_words':        [dict(r) for r in word_rows],
        'attributions':     [dict(r) for r in attrib_rows],
        'meter_dist':       [dict(r) for r in meter_rows],
    }


def get_chapters_for_text(text_id: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT chapter FROM verses
               WHERE text_id = ? AND chapter IS NOT NULL
               ORDER BY verse_num""",
            (text_id,)
        ).fetchall()
    return [r['chapter'] for r in rows]


def _compute_word_freq(rows, limit: int = 30) -> list[dict]:
    """Count word frequencies from simplified text rows."""
    import re
    from collections import Counter
    counts: Counter = Counter()
    for row in rows:
        text = row[0] if isinstance(row, (list, tuple)) else row['full_text_simple']
        words = re.split(r'\W+', text or '')
        for w in words:
            w = w.strip()
            if len(w) >= 4:
                counts[w] += 1
    return [{'word': w, 'cnt': c} for w, c in counts.most_common(limit)]


def get_concordance(word: str, page: int = 1, per_page: int = PER_PAGE) -> tuple[list, int]:
    from transliterate import simplify
    w_simple = simplify(word)
    with get_conn() as conn:
        total = conn.execute(
            """SELECT COUNT(*) FROM verses
               WHERE full_text_iast LIKE ? OR full_text_simple LIKE ?""",
            (f'%{word}%', f'%{w_simple}%')
        ).fetchone()[0]
        rows = conn.execute(
            """SELECT v.id, v.verse_num_str, v.full_text_iast, v.full_text_deva,
                      v.attribution, v.chapter, t.title AS text_title
               FROM verses v JOIN texts t ON v.text_id = t.id
               WHERE v.full_text_iast LIKE ? OR v.full_text_simple LIKE ?
               ORDER BY v.text_id, v.verse_num
               LIMIT ? OFFSET ?""",
            (f'%{word}%', f'%{w_simple}%', per_page, (page - 1) * per_page)
        ).fetchall()
    return [dict(r) for r in rows], total
