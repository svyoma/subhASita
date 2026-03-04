"""
Pre-compute:
  1. Exact pāda matches (shared pāda hash groups)
  2. TF-IDF cosine verse similarity (char n-gram, top-K per verse)

Run once at first startup; idempotent afterwards.
"""

import sqlite3
import numpy as np
import db

_TFIDF_BUILT_KEY  = 'tfidf_built'
_PADA_BUILT_KEY   = 'padas_built'
_GROUPS_BUILT_KEY = 'groups_built'
_SIM_THRESHOLD    = 0.20
_TOP_K            = 6
_CHUNK            = 500


def build_pada_matches():
    """Find all pādas that share the same hash (exact textual match after normalisation)."""
    if db.get_build_state(_PADA_BUILT_KEY) == 'true':
        print('  pada matches already built, skipping.')
        return

    print('  Building exact pada matches...')
    with db.get_conn() as conn:
        # Group pādas by hash; only care about groups with ≥ 2 members
        rows = conn.execute(
            """SELECT pada_hash, GROUP_CONCAT(id, ',') AS ids
               FROM padas
               GROUP BY pada_hash
               HAVING COUNT(*) >= 2"""
        ).fetchall()

        pairs = []
        for row in rows:
            ids = sorted(int(i) for i in row['ids'].split(','))
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pairs.append((ids[i], ids[j]))

        if pairs:
            conn.executemany(
                'INSERT OR IGNORE INTO pada_matches (pada1_id, pada2_id) VALUES (?,?)',
                pairs
            )

    db.set_build_state(_PADA_BUILT_KEY, 'true')
    print(f'  Found {len(pairs)} shared-pada pairs.')


def build_tfidf_similarity():
    """Compute TF-IDF cosine similarity between all verses and store top-K pairs."""
    if db.get_build_state(_TFIDF_BUILT_KEY) == 'true':
        print('  TF-IDF similarities already built, skipping.')
        return

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import linear_kernel
    except ImportError:
        print('  scikit-learn not found; skipping TF-IDF similarity.')
        return

    print('  Loading verses for TF-IDF...')
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT id, full_text_iast FROM verses ORDER BY id'
        ).fetchall()

    if not rows:
        return

    ids   = [r['id'] for r in rows]
    # Strip hyphens so compound-hyphenated and unhyphenated forms match equally
    texts = [r['full_text_iast'].replace('-', ' ') for r in rows]
    n     = len(texts)
    print(f'  Vectorising {n} verses with char n-gram TF-IDF...')

    vectorizer = TfidfVectorizer(
        analyzer='char_wb',
        ngram_range=(3, 5),
        sublinear_tf=True,
        max_features=60_000,
        min_df=2,
    )
    X = vectorizer.fit_transform(texts)

    print('  Computing pairwise similarities in chunks...')
    all_pairs = []

    for start in range(0, n, _CHUNK):
        chunk = X[start:start + _CHUNK]
        sim_chunk = linear_kernel(chunk, X)  # dense (chunk_size × n)

        for local_i, row_sim in enumerate(sim_chunk):
            global_i  = start + local_i
            verse_id1 = ids[global_i]

            # Zero out self-similarity
            row_sim[global_i] = 0.0

            # Top-K indices (descending)
            top_idx = np.argpartition(row_sim, -min(_TOP_K, n - 1))[-_TOP_K:]
            top_idx = top_idx[np.argsort(row_sim[top_idx])[::-1]]

            for j in top_idx:
                sim = float(row_sim[j])
                if sim < _SIM_THRESHOLD:
                    continue
                verse_id2 = ids[j]
                # Store canonical order (smaller id first) to avoid duplicates
                v1, v2 = (verse_id1, verse_id2) if verse_id1 < verse_id2 else (verse_id2, verse_id1)
                all_pairs.append((v1, v2, sim))

        if (start // _CHUNK) % 5 == 0:
            print(f'    processed {min(start + _CHUNK, n)}/{n} verses...')

    print(f'  Storing {len(all_pairs)} similarity pairs...')
    with db.get_conn() as conn:
        conn.executemany(
            'INSERT OR IGNORE INTO verse_similarity (verse1_id, verse2_id, similarity) VALUES (?,?,?)',
            all_pairs
        )

    db.set_build_state(_TFIDF_BUILT_KEY, 'true')
    print('  TF-IDF similarity done.')


def build_verse_groups():
    """
    Group duplicate verses across texts using pada-hash fingerprints.

    For each verse, compute a fingerprint = sorted tuple of pada_hashes.
    Verses sharing the same fingerprint are assigned the same verse_group_id.
    """
    if db.get_build_state(_GROUPS_BUILT_KEY) == 'true':
        print('  verse groups already built, skipping.')
        return

    print('  Building cross-text verse groups...')
    from collections import defaultdict

    with db.get_conn() as conn:
        # Load all padas grouped by verse
        rows = conn.execute(
            """SELECT p.verse_id, p.pada_hash, v.text_id
               FROM padas p JOIN verses v ON p.verse_id = v.id
               ORDER BY p.verse_id, p.pada_num"""
        ).fetchall()

    # Build fingerprint -> list of (verse_id, text_id)
    verse_padas = defaultdict(list)
    for r in rows:
        verse_padas[r['verse_id']].append((r['pada_hash'], r['text_id']))

    fingerprint_groups = defaultdict(list)
    for vid, pada_list in verse_padas.items():
        text_id = pada_list[0][1]
        fp = tuple(ph for ph, _ in pada_list)
        fingerprint_groups[fp].append((vid, text_id))

    # Only keep groups with 2+ verses from DIFFERENT texts
    group_id = 1
    updates = []
    for fp, members in fingerprint_groups.items():
        if len(members) < 2:
            continue
        text_ids = set(tid for _, tid in members)
        if len(text_ids) < 2:
            continue
        for vid, _ in members:
            updates.append((group_id, vid))
        group_id += 1

    if updates:
        with db.get_conn() as conn:
            conn.executemany(
                'UPDATE verses SET verse_group_id = ? WHERE id = ?',
                updates
            )

    db.set_build_state(_GROUPS_BUILT_KEY, 'true')
    print(f'  Found {group_id - 1} verse groups ({len(updates)} verses linked).')


def build_all():
    print('Building similarity indexes...')
    build_pada_matches()
    build_verse_groups()
    build_tfidf_similarity()
    print('Similarity indexes ready.')
