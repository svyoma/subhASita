"""
Parse Sanskrit subhāṣita text files into structured verse data.

Handles three formats:
  Format A – NNNN-P pāda lines (subhāṣitāvaliḥ, mahāsubhāṣitasaṅgrahaḥ)
  Format B – free-form verses ending with ||N|| (saduktikarṇāmṛtam)
  Format C – GRETIL-style with .. abbrev_X.Y .. markers (ratnakosha, shatakatraya, darpadalana)
"""

import re
import os
from transliterate import to_devanagari, simplify

# ── Patterns ──────────────────────────────────────────────────────────────────
_PADA_LINE   = re.compile(r'^(\d{4})-(\d+)\s+(.+)$')
_VERSE_END_A = re.compile(r'(.*?)\|\s*\|(.*)')          # matches || or | |
_VERSE_END_B = re.compile(r'^(.*?)\|\|(\d+)\|\|(.*)')   # sadukti ||N||
_CHAPTER_NUM = re.compile(r'^\d+\.\s+(.+)$')            # "42. title"

# Format C: GRETIL verse-end marker  .. abbrev_X.Y [*(N)] ..
_VERSE_END_C = re.compile(
    r'\.\.\s*(\w+)_(\d+)\.(\d+)\s*(?:\*?\((\d+)\))?\s*\.\.'
)
_ATTRIB_PATT = re.compile(
    r'^[\w\sāīūṛṝḷṃḥṅñṭḍṇśṣĀĪŪṚṜḶṂḤṄÑṬḌṆŚṢ]+sya\s*[\|]?\s*(?:\([^)]*\))?$'
    r'|^\([^)]+\)$'
    r'|^bh[āa]\.\s+\w'
    r'|^kasyāpi'
    r'|^trivikramasya'
    r'|^vasantadevasya',
    re.UNICODE
)

# Tag keywords for auto-tagging
TAG_KEYWORDS = {
    'stuti/bhakti':  ['namaḥ', 'namaste', 'pātu', 'pāyāt', 'avatu', 'diśyāt', 'namas'],
    'viṣṇu/kṛṣṇa':  ['viṣṇu', 'hari ', 'kṛṣṇa', 'mādhava', 'keśava', 'murari', 'govinda',
                      'govardhan', 'murāri', 'vaikuṇṭha'],
    'śiva/rudra':    ['śiva', 'śambhu', 'maheśvara', 'śaṃkara', 'dhūrjaṭi', 'rudra',
                      'śūlin', ' hara ', 'tripura', 'bhairava', 'umā'],
    'kāvya/sāhitya': ['kāvya', 'kavi', 'sarasvatī', 'vāk', 'kavitvam', 'sūkti',
                      'śloka', 'padya', 'kāvyam'],
    'nīti/rājanīti': ['rāja', 'nṛpa', 'nīti', 'rājya', 'amātya', 'mantri', 'daṇḍa',
                      'prajā', 'rājñaḥ'],
    'vidyā/jñāna':   ['vidyā', 'paṇḍita', 'jñāna', 'śāstra', 'veda', 'śikṣā', 'śāstram'],
    'dharma':        ['dharma', 'puṇya', 'karma', 'satya', 'nyāya', 'ācāra', 'dharmam'],
    'vairāgya/mokṣa': ['vairāgya', 'mokṣa', 'nirvāṇa', 'saṃsāra', 'māyā', 'tyāga',
                        'mukti', 'viveka'],
    'śṛṅgāra/kāma': ['kāma', 'manmatha', 'rati', 'śṛṅgāra', 'virahiṇī', 'priyā',
                      'kānta', 'nāyikā', 'priya'],
    'mitra/bandhu':  ['mitra', 'suhṛd', 'bandhu', 'sakhi', 'snigdha'],
    'khala/durjana': ['khala', 'durjana', 'pāpa', 'piśuna', 'asādhu', 'khalasya'],
    'dāna/kāruṇya': ['dāna', 'dātṛ', 'kṛpā', 'karuṇā', 'udāra', 'tyāgaḥ'],
    'prakṛti/ṛtu':   ['vana', 'nadī', 'sāgara', 'giri', 'vṛkṣa', 'puṣpa', 'jalad',
                      'varṣā', 'hemanta', 'vasanta', 'grīṣma', 'śarat', 'megha'],
}


def _read_lines(filepath: str) -> list[str]:
    """Read file handling CR, CRLF and LF line endings."""
    with open(filepath, 'r', encoding='utf-8', newline='') as f:
        raw = f.read()
    # Normalise all line endings to LF
    raw = raw.replace('\r\n', '\n').replace('\r', '\n')
    return raw.split('\n')


def _parse_metadata(lines: list[str]) -> dict:
    """Extract key=value metadata from the +++ header block."""
    meta = {}
    in_header = False
    for line in lines:
        stripped = line.strip()
        if stripped == '+++':
            in_header = not in_header
            continue
        if in_header:
            m = re.match(r'^"?([^"=]+)"?\s*=\s*"?([^"]+)"?', stripped)
            if m:
                meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def _auto_tag(text: str) -> list[str]:
    tags = []
    text_lower = text.lower()
    for tag, keywords in TAG_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            tags.append(tag)
    return tags


def _normalize_pada(text: str) -> str:
    """Normalise pāda text for exact-match hashing. Hyphens are ignored."""
    text = re.sub(r'[\|\\/_\d\-]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def _format_full_text(padas_iast: list, padas_deva: list) -> tuple:
    """
    Format pādas with traditional Sanskrit dandas, one pāda per line.

    Single danda | (।) after the midpoint pāda (end of first ardha).
    Double danda || (॥) after the final pāda (end of verse).

    4-pāda verse:      2-pāda verse:
      pāda 1             pāda 1 |
      pāda 2 |           pāda 2 ||
      pāda 3
      pāda 4 ||

    Returns (full_iast, full_deva).
    """
    n = len(padas_iast)
    if n == 0:
        return '', ''
    half = n // 2          # count of pādas in first ardha
    lines_iast = []
    lines_deva = []
    for i, (pi, pd) in enumerate(zip(padas_iast, padas_deva)):
        if i == n - 1:            # final pāda → double danda
            lines_iast.append(pi + ' ||')
            lines_deva.append(pd + ' \u0965')
        elif i == half - 1:       # end of first ardha → single danda
            lines_iast.append(pi + ' |')
            lines_deva.append(pd + ' \u0964')
        else:
            lines_iast.append(pi)
            lines_deva.append(pd)
    return '\n'.join(lines_iast), '\n'.join(lines_deva)


# ── Format A ──────────────────────────────────────────────────────────────────

def parse_format_a(lines: list[str], metadata: dict) -> list[dict]:
    """Parse NNNN-P pāda-numbered files."""
    verses: dict[str, dict] = {}

    for line in lines:
        stripped = line.strip()
        m = _PADA_LINE.match(stripped)
        if not m:
            continue

        verse_num_str, pada_num_str, text = m.group(1), m.group(2), m.group(3)
        verse_num = int(verse_num_str)
        pada_num  = int(pada_num_str)

        # Detect verse end (|| or | |) and optional attribution
        attribution = None
        end_m = _VERSE_END_A.search(text)
        if end_m:
            text        = end_m.group(1).strip()
            attribution = end_m.group(2).strip() or None
        else:
            # Remove trailing hemistich separator |
            text = text.rstrip().rstrip('|').strip()

        if verse_num_str not in verses:
            verses[verse_num_str] = {
                'verse_num':     verse_num,
                'verse_num_str': verse_num_str,
                'padas':         {},
                'attribution':   None,
                'chapter':       None,
                'section':       None,
            }

        verses[verse_num_str]['padas'][pada_num] = text
        if attribution and not verses[verse_num_str]['attribution']:
            verses[verse_num_str]['attribution'] = attribution

    result = []
    for vs in sorted(verses.values(), key=lambda v: v['verse_num']):
        padas = vs['padas']
        sorted_padas = [padas[k] for k in sorted(padas)]
        padas_deva   = [to_devanagari(p) for p in sorted_padas]
        full_iast, full_deva = _format_full_text(sorted_padas, padas_deva)
        result.append({
            'verse_num':        vs['verse_num'],
            'verse_num_str':    vs['verse_num_str'],
            'pada_count':       len(sorted_padas),
            'padas_iast':       sorted_padas,
            'padas_deva':       padas_deva,
            'full_text_iast':   full_iast,
            'full_text_deva':   full_deva,
            'full_text_simple': simplify(full_iast),
            'attribution':      vs['attribution'],
            'chapter':          None,
            'section':          None,
            'auto_tags':        _auto_tag(full_iast),
        })
    return result


# ── Format B ──────────────────────────────────────────────────────────────────

def _skip_indices_format_b(lines: list[str]) -> set[int]:
    """
    Identify line indices that are header / preamble / abbreviation lines
    to be excluded from verse text in Format B files.

    Skips:
      - the +++ metadata header block
      - [[...]] annotation lines
      - standalone [ and ] marker lines (NOT block-tracking; only the lines themselves)
      - blank lines
      - abbreviation lines (su.ā. = subhāṣitāvalī style)
      - separator lines (---, ===)
    """
    skip: set[int] = set()
    in_header   = False
    past_header = False

    for i, line in enumerate(lines):
        s = line.strip()

        # +++ header block
        if s == '+++':
            in_header = not in_header
            skip.add(i)
            if not in_header:
                past_header = True
            continue

        if in_header:
            skip.add(i)
            continue

        if not past_header:
            skip.add(i)
            continue

        # annotation/reference lines:  [[title  Source: EB]]  or  [[...]]
        if s.startswith('[['):
            skip.add(i)
            continue

        # standalone bracket markers (just the [ or ] line itself)
        if s in ('[', ']'):
            skip.add(i)
            continue

        # blank lines
        if not s:
            skip.add(i)
            continue

        # separator lines
        if s.startswith('---') or s.startswith('==='):
            skip.add(i)
            continue

        # abbreviation lines:  amaru = amaruśatakaḥ   or   su.ra. = ...
        if re.match(r'^\w[\w.]*\s*=\s*\w', s):
            skip.add(i)
            continue

    return skip


def parse_format_b(lines: list[str], metadata: dict) -> list[dict]:
    """Parse saduktikarṇāmṛtam-style: free verse with ||N|| end markers."""

    skip_set = _skip_indices_format_b(lines)

    # Pass 1: Locate verse-end marker positions
    verse_end_positions = []  # (line_idx, text_before, verse_num_in_chap)
    for i, line in enumerate(lines):
        if i in skip_set:
            continue
        s = line.strip()
        m = _VERSE_END_B.match(s)
        if m:
            verse_end_positions.append((i, m.group(1).strip(), int(m.group(2))))

    if not verse_end_positions:
        return []

    # Pass 2: Collect verse text + detect chapter headings + attribution
    result  = []
    current_chapter = None
    current_section = None

    for vi, (end_idx, before_marker, verse_num_in_chap) in enumerate(verse_end_positions):
        start_idx = (verse_end_positions[vi - 1][0] + 1) if vi > 0 else 0

        # Collect non-skipped, non-blank lines in this segment
        segment = []
        for j in range(start_idx, end_idx + 1):
            if j in skip_set:
                continue
            s = lines[j].strip()
            if s:
                segment.append(s)

        # Last element is the verse-end line itself; drop it (we have before_marker)
        if segment:
            segment = segment[:-1]
        if before_marker:
            segment.append(before_marker)

        verse_text_lines = []
        attribution_for_prev = None
        # For vi==0 we skip short pre-verse preamble lines (title, author, section headings)
        in_attr_zone = (vi > 0)
        # For the first segment, skip preamble until we hit the first long line
        in_preamble = (vi == 0)

        for l in segment:
            # Numbered chapter heading?
            chap_m = _CHAPTER_NUM.match(l)
            if chap_m:
                current_chapter = chap_m.group(1).strip(' |')
                in_attr_zone = False
                in_preamble  = False
                continue

            # For the first verse segment: skip short preamble lines
            # (title repeats, section headings) that precede actual verse text
            if in_preamble:
                if len(l) <= 60 and '|' not in l:
                    # Store last such line as section heading
                    current_section = l
                    continue
                else:
                    in_preamble = False  # Long line → real verse text starts

            # Attribution for the PREVIOUS verse (start of this segment)
            if in_attr_zone and len(l) <= 100:
                # Strip trailing dandas for matching
                l_clean = l.rstrip(' |').strip()
                if _ATTRIB_PATT.match(l_clean) or _ATTRIB_PATT.match(l):
                    attribution_for_prev = l_clean
                    continue
                # Very short lines (≤30 chars after stripping dandas) → attribution
                if len(l_clean) <= 30 and len(l_clean) >= 3:
                    attribution_for_prev = l_clean
                    continue
                # Short line without | → section heading
                if len(l) <= 50 and '|' not in l and '(' not in l:
                    current_section = l
                    in_attr_zone = False
                    continue
                in_attr_zone = False  # Long line → start of verse text

            verse_text_lines.append(l)

        # Backfill attribution onto the PREVIOUS verse
        if attribution_for_prev and result:
            if result[-1]['attribution'] is None:
                result[-1]['attribution'] = attribution_for_prev

        verse_text_iast = '\n'.join(verse_text_lines).strip()
        if not verse_text_iast:
            continue

        # Split verse text into pādas at single-| separator (not ||)
        pada_raw   = re.split(r'(?<!\|)\|(?!\|)', verse_text_iast)
        padas_iast = [p.strip() for p in pada_raw if p.strip()]
        padas_deva = [to_devanagari(p) for p in padas_iast]
        full_iast, full_deva = _format_full_text(padas_iast, padas_deva)

        result.append({
            'verse_num':        len(result) + 1,
            'verse_num_str':    str(verse_num_in_chap),
            'pada_count':       len(padas_iast),
            'padas_iast':       padas_iast,
            'padas_deva':       padas_deva,
            'full_text_iast':   full_iast,
            'full_text_deva':   full_deva,
            'full_text_simple': simplify(full_iast),
            'attribution':      None,   # filled in next iteration
            'chapter':          current_chapter,
            'section':          current_section,
            'auto_tags':        _auto_tag(full_iast),
        })

    return result


# ── Format C (GRETIL) ────────────────────────────────────────────────────────

# Attribution line patterns for GRETIL anthologies (ratnakosha etc.)
# These appear BEFORE the verse they attribute.
#   "authorname-sya --"   "authorname-syaitau --"   "authorname-padanam --"
#   "authorname-sya . (ref)"   "authorname-sya .. (ref)"
#   "(ref)"  -- cross-reference only
# Attribution with double-dash:  "authorname --"
_GRETIL_ATTRIB_DASH = re.compile(
    r'^([\w\sāīūṛṝḷṃḥṅñṭḍṇśṣĀĪŪṚṜḶṂḤṄÑṬḌṆŚṢ\-]+?)\s*--\s*$',
    re.UNICODE
)
# Attribution with ref:  "authorname . (ref)"  or  "authorname .. (ref)"
_GRETIL_ATTRIB_REF = re.compile(
    r'^([\w\sāīūṛṝḷṃḥṅñṭḍṇśṣĀĪŪṚṜḶṂḤṄÑṬḌṆŚṢ\-]+?)\s*\.{1,2}\s*(\([^)]+\))\s*$',
    re.UNICODE
)
# Section end:  "iti chapter-vrajya .."  or  ".. iti chapter-vrajya .."
_GRETIL_SECTION_END = re.compile(r'^\.{0,2}\s*iti\s+.+$', re.UNICODE)
# Chapter heading:  "N. chapter-name"
_GRETIL_CHAPTER = re.compile(r'^(\d+)\.\s+(.+)$')
# Standalone section heading (no verse marker): "niti-satakam", "prathamo vicarah", etc.
_GRETIL_SECTION_HEADING = re.compile(
    r'^[\w\-āīūṛṝḷṃḥṅñṭḍṇśṣ]+[\w\-āīūṛṝḷṃḥṅñṭḍṇśṣ\s]*$',
    re.UNICODE
)


def _find_content_start(lines: list[str]) -> int:
    """Find the line index where actual content starts (after pAThaH or Intro block)."""
    for i, line in enumerate(lines):
        s = line.strip().lower()
        if s.startswith('pāṭhaḥ') or s == 'pāṭhaḥ':
            return i + 1
    # Fallback: skip past second +++ marker
    count = 0
    for i, line in enumerate(lines):
        if line.strip() == '+++':
            count += 1
            if count == 2:
                return i + 1
    return 0


def _extract_gretil_author(line: str) -> str | None:
    """
    Extract author name from a GRETIL attribution line.
    Returns cleaned author name or None.

    Matches:
      "authorname --"           (dash-style)
      "authorname . (ref)"      (ref-style)
      "authorname .. (ref)"     (ref-style)
    Does NOT match:
      Verse text ending with "." (hemistich separator)
      "(ref)" alone (cross-reference only)
    """
    s = line.strip()
    if not s or len(s) > 120:
        return None

    # Cross-reference only, e.g. "(skmsa.u.ka. 241)" -- not an author
    if s.startswith('(') and s.endswith(')'):
        return None

    # Dash-style: "authorname --"
    m = _GRETIL_ATTRIB_DASH.match(s)
    if m:
        author = m.group(1).strip().rstrip('-')
        if author and len(author) >= 3:
            return author

    # Ref-style: "authorname . (ref)" or "authorname .. (ref)"
    m = _GRETIL_ATTRIB_REF.match(s)
    if m:
        author = m.group(1).strip().rstrip('-')
        if author and len(author) >= 3:
            return author

    return None


def parse_format_c(lines: list[str], metadata: dict) -> list[dict]:
    """
    Parse GRETIL-style files with .. abbrev_X.Y .. verse-end markers.

    Handles:
    - ratnakosha (per-verse author attributions before each verse)
    - shatakatraya (3 sections, single author)
    - darpadalana (7 chapters, single author)
    """
    content_start = _find_content_start(lines)

    # Pass 1: find all verse-end marker positions
    verse_ends = []  # (line_idx, abbrev, chapter_num, verse_num, global_num)
    for i in range(content_start, len(lines)):
        m = _VERSE_END_C.search(lines[i].strip())
        if m:
            verse_ends.append((
                i,
                m.group(1),             # abbreviation
                int(m.group(2)),         # chapter number
                int(m.group(3)),         # verse number within chapter
                int(m.group(4)) if m.group(4) else None,  # global number
            ))

    if not verse_ends:
        return []

    # Build skip set for preamble lines (encoding descriptions, abbreviations, etc.)
    skip_set = set()
    in_skip = True
    for i in range(content_start, len(lines)):
        s = lines[i].strip()
        # Encoding description lines
        if re.match(r'^(long|short|vocalic|velar|palatal|retroflex|anusvara|visarga)\s+', s, re.I):
            skip_set.add(i)
            continue
        if re.match(r'^(description|Unless indicated|For a comprehensive|http://)', s):
            skip_set.add(i)
            continue
        if re.match(r'^(For further|set to UTF|Text converted|\(This file)', s):
            skip_set.add(i)
            continue
        # Abbreviation lines  "su.a. = subhasitavali"
        if re.match(r'^[\w.]+\s*=\s*\w', s):
            skip_set.add(i)
            continue
        # GRETIL boilerplate
        if s.startswith('THIS GRETIL') or s.startswith('COPYRIGHT'):
            skip_set.add(i)
            continue
        if s == 'Intro':
            skip_set.add(i)
            continue
        # Section end markers ("iti chapter-name")
        if _GRETIL_SECTION_END.match(s):
            skip_set.add(i)
            continue
        # Chapter-end number markers: "..N.."
        if re.match(r'^\.+\d+\.+$', s):
            skip_set.add(i)
            continue
        # Lines that are just cross-references in parens
        if s.startswith('(') and s.endswith(')') and '..' not in s:
            skip_set.add(i)
            continue
        # "(yugmam)" or similar annotations
        if s in ('(yugmam)', '(ardhodyam)'):
            skip_set.add(i)
            continue

    # Pass 2: collect verses
    result = []
    current_chapter = None
    current_section = None

    for vi, (end_idx, abbrev, chap_num, verse_in_chap, global_num) in enumerate(verse_ends):
        start_idx = (verse_ends[vi - 1][0] + 1) if vi > 0 else content_start

        # Collect non-skipped, non-blank lines in this segment
        segment_lines = []
        for j in range(start_idx, end_idx + 1):
            if j in skip_set:
                continue
            s = lines[j].strip()
            if not s:
                continue
            segment_lines.append(s)

        if not segment_lines:
            continue

        # Process lines: classify each as verse text or metadata
        verse_text_parts = []
        attribution_found = None   # attribution line found before this verse's text
        verse_text_started = False

        for text in segment_lines:
            # Verse-end marker line: extract text before marker
            vm = _VERSE_END_C.search(text)
            if vm:
                before = text[:vm.start()].strip()
                before = re.sub(r'\.\s*$', '', before).strip()
                if before:
                    verse_text_parts.append(before)
                verse_text_started = True
                continue

            # Before verse text starts, check for metadata lines.
            # Once we start seeing verse text, everything until the marker
            # is verse text (including short anustubh padas).
            if not verse_text_started:
                # Chapter heading?  "N. chapter-title"  (numbered)
                chap_m = _GRETIL_CHAPTER.match(text)
                if chap_m:
                    ch_name = chap_m.group(2).strip()
                    # Clean trailing markers: --, .., ..N, trailing numbers
                    ch_name = re.sub(r'\s*(?:--|\.\.\d*|\.\s*\d*|\d+)\s*$', '', ch_name).strip()
                    current_chapter = ch_name
                    continue

                # Attribution line? (appears before this verse's text = attribution for THIS verse)
                author = _extract_gretil_author(text)
                if author is not None:
                    attribution_found = author
                    continue

                # Check if this line looks like verse text:
                # Has hemistich separator (space-dot pattern)
                if re.search(r' \.$| \. ', text):
                    verse_text_started = True
                    verse_text_parts.append(text)
                    continue

                # Non-numbered chapter/section heading with specific keywords
                # Only match if the keyword is a standalone word (not inside
                # a compound like pravrajyā containing vrajyā)
                if len(text) < 50 and re.search(
                        r'(?:^|[\s\-])(?:śatakam|vicāraḥ|vrajyā|pariccheda)',
                        text):
                    current_chapter = text
                    continue

                # Short line without dots -> could be preamble or section heading
                # Skip it (preamble, author label, title repeat, etc.)
                continue

            # After verse text started, everything is verse text
            verse_text_parts.append(text)

        # Attribution found before this verse's text belongs to THIS verse
        attribution = attribution_found

        # Join verse text and split into padas
        raw_verse = ' '.join(verse_text_parts).strip()
        if not raw_verse:
            continue

        # Remove asterisk markers  .* (arya meter indicator)
        raw_verse = raw_verse.replace('.*', ' .')

        # Split at single '.' hemistich separators
        # In GRETIL, '.' separates hemistichs, '..' ends a verse
        # We already removed the .. marker, so split at remaining '.'
        pada_raw = re.split(r'\s*\.\s+', raw_verse)
        padas_iast = [p.strip() for p in pada_raw if p.strip()]

        if not padas_iast:
            continue

        padas_deva = [to_devanagari(p) for p in padas_iast]
        full_iast, full_deva = _format_full_text(padas_iast, padas_deva)

        verse_num_str = f'{chap_num}.{verse_in_chap}'

        result.append({
            'verse_num':        len(result) + 1,
            'verse_num_str':    verse_num_str,
            'pada_count':       len(padas_iast),
            'padas_iast':       padas_iast,
            'padas_deva':       padas_deva,
            'full_text_iast':   full_iast,
            'full_text_deva':   full_deva,
            'full_text_simple': simplify(full_iast),
            'attribution':      attribution,
            'chapter':          current_chapter,
            'section':          current_section,
            'auto_tags':        _auto_tag(full_iast),
        })

    return result


# ── Auto-detect and dispatch ───────────────────────────────────────────────────

def _detect_format(lines: list[str]) -> str:
    """Return 'A' for NNNN-P format, 'B' for ||N|| format, 'C' for GRETIL."""
    sample = lines[:300]
    a_count = sum(1 for l in sample if _PADA_LINE.match(l.strip()))
    b_count = sum(1 for l in sample if _VERSE_END_B.match(l.strip()))
    c_count = sum(1 for l in sample if _VERSE_END_C.search(l.strip()))
    if c_count > a_count and c_count > b_count:
        return 'C'
    return 'A' if a_count >= b_count else 'B'


def parse_file(filepath: str) -> tuple[dict, list[dict]]:
    """
    Parse a subhāṣita text file.

    Returns:
        (metadata_dict, list_of_verse_dicts)
    """
    lines    = _read_lines(filepath)
    metadata = _parse_metadata(lines)
    fmt      = _detect_format(lines)

    if fmt == 'A':
        verses = parse_format_a(lines, metadata)
    elif fmt == 'B':
        verses = parse_format_b(lines, metadata)
    else:
        verses = parse_format_c(lines, metadata)

    return metadata, verses


def detect_format(filepath: str) -> str:
    lines = _read_lines(filepath)
    return _detect_format(lines)
