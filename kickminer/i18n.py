"""Small localization helper.

Language files are JSON at ``lang/<code>.lang``. If a key is missing in the
selected language, it falls back to English and then to the key name itself -
so the bot always stays runnable. English is the default; German is available
as an alternative (``"Language": "de"`` in the config).
"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LANGUAGE = "en"
_LANG_DIR = Path(__file__).resolve().parent / "lang"

_current = DEFAULT_LANGUAGE
_data: dict[str, str] = {}
_fallback: dict[str, str] = {}


def _load_file(code: str) -> dict[str, str]:
    path = _LANG_DIR / f"{code}.lang"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def load_language(code: str | None) -> str:
    """Load the given language. Returns the code that is actually active."""

    global _current, _data, _fallback

    code = str(code or DEFAULT_LANGUAGE).lower().strip()
    _fallback = _load_file(DEFAULT_LANGUAGE)

    data = _load_file(code)
    if data:
        _current = code
        _data = data
    else:
        _current = DEFAULT_LANGUAGE
        _data = dict(_fallback)

    return _current


def current_language() -> str:
    return _current


def available_languages() -> list[str]:
    return sorted(p.stem for p in _LANG_DIR.glob("*.lang"))


def t(key: str, /, **params: object) -> str:
    """Translate ``key`` and substitute ``{placeholders}`` from ``params``."""

    text = _data.get(key) or _fallback.get(key) or key
    for name, value in params.items():
        text = text.replace("{" + name + "}", str(value))
    return text


# Load the default language on import so ``t()`` works before any explicit
# ``load_language`` call (e.g. a config error raised very early in startup).
load_language(DEFAULT_LANGUAGE)
