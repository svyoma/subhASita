"""
subhāṣita Explorer — Flask application
Run: python app.py
"""

import os
import math
import datetime
from pathlib import Path
from flask import (Flask, render_template, request, jsonify,
                   redirect, url_for, abort)

import db
import parse
import similarity_engine

app = Flask(__name__)
app.secret_key = 'subhashita-explorer-secret'


@app.template_filter('format_number')
def format_number(value):
    try:
        return f'{int(value):,}'
    except (ValueError, TypeError):
        return value

TEXT_DIR = Path(__file__).parent
TEXT_GLOB = 'Devanagari_IAST_*.txt'

PER_PAGE = 20


# ── Startup initialisation ────────────────────────────────────────────────────

def init_app():
    print('Initialising database...')
    db.init_schema()

    txt_files = sorted(TEXT_DIR.glob(TEXT_GLOB))
    for fpath in txt_files:
        filename = fpath.name
        if db.text_already_loaded(filename):
            print(f'  {filename}: already loaded.')
            continue
        print(f'  Parsing {filename}...')
        metadata, verses = parse.parse_file(str(fpath))
        print(f'    -> {len(verses)} verses parsed')
        if verses:
            db.insert_text_and_verses(metadata, verses, filename)
            print(f'    -> inserted into DB')
        else:
            print(f'    -> (empty, skipped)')

    similarity_engine.build_all()
    print('Ready.')


# ── Template helpers ──────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    texts = db.get_all_texts()
    return {
        'all_texts': texts,
        'current_year': datetime.date.today().year,
    }


def paginate(total: int, page: int, per_page: int = PER_PAGE) -> dict:
    total_pages = max(1, math.ceil(total / per_page))
    return {
        'page':        page,
        'per_page':    per_page,
        'total':       total,
        'total_pages': total_pages,
        'has_prev':    page > 1,
        'has_next':    page < total_pages,
        'prev_page':   page - 1,
        'next_page':   page + 1,
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    # Date-seeded "verse of the day"
    today_seed = int(datetime.date.today().strftime('%Y%m%d'))
    verse_of_day = db.get_random_verse(seed=today_seed)
    stats = db.get_stats()
    return render_template('index.html',
                           verse_of_day=verse_of_day,
                           stats=stats)


@app.route('/browse')
def browse():
    query      = request.args.get('q', '').strip()
    text_id    = request.args.get('text_id', type=int)
    chapter    = request.args.get('chapter', '').strip() or None
    tag        = request.args.get('tag', '').strip() or None
    pada_count = request.args.get('pada_count', type=int)
    page       = max(1, request.args.get('page', 1, type=int))

    verses, total = db.search_verses(
        query=query, text_id=text_id, chapter=chapter,
        tag=tag, pada_count=pada_count, page=page, per_page=PER_PAGE
    )

    chapters = []
    if text_id:
        chapters = db.get_chapters_for_text(text_id)

    return render_template(
        'browse.html',
        verses=verses,
        pager=paginate(total, page),
        query=query,
        sel_text_id=text_id,
        sel_chapter=chapter,
        sel_tag=tag,
        sel_pada_count=pada_count,
        chapters=chapters,
    )


@app.route('/verse/<int:verse_id>')
def verse_detail(verse_id):
    verse = db.get_verse(verse_id)
    if not verse:
        abort(404)

    padas_with_matches = db.get_padas_for_verse(verse_id)
    similar = db.get_similar_verses(verse_id)
    cross_refs = db.get_cross_references(verse_id)

    # For each pāda that has matches, load the matching verses
    shared_pada_info = []
    seen_hashes = set()
    for p in padas_with_matches:
        if p['match_count'] > 0 and p['pada_hash'] not in seen_hashes:
            seen_hashes.add(p['pada_hash'])
            matching_verses = db.get_verses_sharing_pada(p['pada_hash'], exclude_verse_id=verse_id)
            shared_pada_info.append({
                'pada':    p,
                'matches': matching_verses,
            })

    return render_template(
        'verse.html',
        verse=verse,
        shared_pada_info=shared_pada_info,
        similar=similar,
        cross_refs=cross_refs,
    )


@app.route('/shared-padas')
def shared_padas():
    min_count = request.args.get('min', 2, type=int)
    items = db.get_shared_padas(min_count=min_count)
    return render_template('shared_padas.html', items=items, min_count=min_count)


@app.route('/concordance')
def concordance():
    word  = request.args.get('word', '').strip()
    page  = max(1, request.args.get('page', 1, type=int))
    results, total = [], 0
    if word:
        results, total = db.get_concordance(word, page=page, per_page=PER_PAGE)
    return render_template(
        'concordance.html',
        word=word,
        results=results,
        pager=paginate(total, page),
    )


@app.route('/insights')
def insights():
    stats = db.get_stats()
    return render_template('insights.html', stats=stats)


@app.route('/random')
def random_verse():
    verse = db.get_random_verse()
    if not verse:
        abort(404)
    # If JSON requested (AJAX), return JSON
    if request.accept_mimetypes.accept_json and \
       not request.accept_mimetypes.accept_html:
        return jsonify({
            'id':           verse['id'],
            'iast':         verse['full_text_iast'],
            'deva':         verse['full_text_deva'],
            'attribution':  verse['attribution'],
            'text_title':   verse['text_title'],
            'verse_num_str': verse['verse_num_str'],
        })
    return redirect(url_for('verse_detail', verse_id=verse['id']))


@app.route('/sources')
def sources():
    texts = db.get_all_texts()
    return render_template('sources.html', texts=texts)


@app.route('/favorites')
def favorites():
    return render_template('favorites.html')


# ── JSON API ──────────────────────────────────────────────────────────────────

@app.route('/api/verse/<int:verse_id>')
def api_verse(verse_id):
    verse = db.get_verse(verse_id)
    if not verse:
        return jsonify({'error': 'not found'}), 404
    return jsonify({
        'id':           verse['id'],
        'iast':         verse['full_text_iast'],
        'deva':         verse['full_text_deva'],
        'attribution':  verse['attribution'],
        'chapter':      verse['chapter'],
        'text_title':   verse['text_title'],
    })


@app.route('/api/similar/<int:verse_id>')
def api_similar(verse_id):
    results = db.get_similar_verses(verse_id, limit=8)
    return jsonify(results)


@app.route('/api/random')
def api_random():
    verse = db.get_random_verse()
    if not verse:
        return jsonify({'error': 'no verses'}), 404
    return jsonify({
        'id':           verse['id'],
        'iast':         verse['full_text_iast'],
        'deva':         verse['full_text_deva'],
        'attribution':  verse['attribution'],
        'text_title':   verse['text_title'],
        'verse_num_str': verse['verse_num_str'],
        'url':          url_for('verse_detail', verse_id=verse['id']),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    with app.app_context():
        init_app()
    app.run(debug=False, host='127.0.0.1', port=5000)
