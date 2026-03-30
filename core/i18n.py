"""
i18n.py — Minimal internationalization module.

Usage:
    from core.i18n import init_i18n, t, list_available_languages

    # In main.py, BEFORE creating any widgets:
    init_i18n("es_ES")          # or "en_EN" (default)

    # Everywhere in GUI:
    t("btn.start")              # → "Start" / "Iniciar"
    t("log.repos_detected", count=3, names="a, b, c")
"""
import os
import glob
from typing import Any

# ── Module-level state (set once by init_i18n, then read-only) ──────────────

_STRINGS: dict[str, str] = {}       # active language
_EN_FALLBACK: dict[str, str] = {}   # always en_EN, loaded as fallback

_TRANSLATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config", "translations"
)


# ── Public API ───────────────────────────────────────────────────────────────

def init_i18n(language_code: str = "en_EN") -> None:
    """Load the translation file for *language_code*.

    Must be called before any widget is created.
    Falls back to en_EN if the requested file does not exist.
    """
    global _STRINGS, _EN_FALLBACK

    en_path = os.path.join(_TRANSLATIONS_DIR, "en_EN.yml")
    _EN_FALLBACK = _load_yaml(en_path)

    target_path = os.path.join(_TRANSLATIONS_DIR, f"{language_code}.yml")
    if os.path.exists(target_path) and language_code != "en_EN":
        _STRINGS = _load_yaml(target_path)
    else:
        _STRINGS = _EN_FALLBACK


def t(key: str, **kwargs: Any) -> str:
    """Return the translated string for *key*, applying optional format kwargs.

    Fallback chain: active language → en_EN → raw key (never raises).
    """
    value = _STRINGS.get(key) or _EN_FALLBACK.get(key) or key
    if kwargs:
        try:
            value = value.format_map(kwargs)
        except (KeyError, ValueError):
            pass
    return value


def list_available_languages() -> list[dict]:
    """Scan config/translations/*.yml and return metadata for each language.

    Returns a list of dicts sorted by name:
        [{"code": "en_EN", "name": "English"}, {"code": "es_ES", "name": "Español"}]
    """
    languages = []
    for path in glob.glob(os.path.join(_TRANSLATIONS_DIR, "*.yml")):
        data = _load_yaml(path, keep_meta=True)
        meta = data.get("_meta", {})
        code = meta.get("code") or os.path.splitext(os.path.basename(path))[0]
        name = meta.get("name") or code
        languages.append({"code": code, "name": name})
    return sorted(languages, key=lambda x: x["name"])


# ── Internal helpers ─────────────────────────────────────────────────────────

def _load_yaml(path: str, keep_meta: bool = False) -> dict:
    """Load a YAML file and return a flat dict, optionally keeping the _meta section."""
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if not keep_meta:
            data.pop("_meta", None)
        return {k: str(v) if not isinstance(v, dict) else v
                for k, v in data.items()}
    except Exception:
        return {}
