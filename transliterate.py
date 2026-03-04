"""IAST → Devanāgarī transliteration using aksharamukha."""
import unicodedata

try:
    from aksharamukha import transliterate as _ax
    _HAS_AKSHA = True
except ImportError:
    _HAS_AKSHA = False

try:
    from indic_transliteration import sanscript as _san
    _HAS_INDIC = True
except ImportError:
    _HAS_INDIC = False


def to_devanagari(iast_text: str) -> str:
    """Convert IAST text to Devanāgarī script.

    Primary: aksharamukha  (preferred by user)
    Fallback: indic_transliteration
    Last resort: return original IAST
    """
    if not iast_text:
        return iast_text

    if _HAS_AKSHA:
        try:
            return _ax.process('IAST', 'Devanagari', iast_text)
        except Exception:
            pass

    if _HAS_INDIC:
        try:
            return _san.transliterate(iast_text, _san.IAST, _san.DEVANAGARI)
        except Exception:
            pass

    return iast_text


def simplify(text: str) -> str:
    """Strip diacritics for fuzzy/simplified search (rāja → raja)."""
    if not text:
        return ''
    normalized = unicodedata.normalize('NFD', text)
    return ''.join(c for c in normalized if unicodedata.category(c) != 'Mn').lower()
