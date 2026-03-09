"""
config/cities/__init__.py
─────────────────────────
Implements the city registry and the public `get_city()` function.

get_city() supports:
  - Exact slug lookup            get_city("austin")
  - Case-insensitive             get_city("AUSTIN")
  - Space-to-underscore          get_city("san francisco")
  - State-qualified              get_city("austin, tx")
  - Known aliases                get_city("atx")
  - Unambiguous prefix match     get_city("aus")
  - Detailed error on miss       lists available cities + suggestions

Adding a new city
─────────────────
  1. Create  config/cities/<slug>.py  and define a CityConfig instance
  2. Add one entry to CITY_REGISTRY below
  3. Optionally add aliases to CITY_ALIASES
"""

from __future__ import annotations

import difflib
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.base import CityConfig


# ═══════════════════════════════════════════════════════════════
#  Lazy imports — city modules are only loaded when first accessed
# ═══════════════════════════════════════════════════════════════

def _load_austin() -> "CityConfig":
    from backend.austin import AUSTIN
    return AUSTIN


def _load_new_york_city() -> "CityConfig":
    from backend.new_york_city import NEW_YORK_CITY
    return NEW_YORK_CITY


# ── Registry: slug → loader callable ────────────────────────────
#   Add new cities here. Use lowercase_underscore slugs as keys.
#   The value is a zero-argument callable that returns a CityConfig.
#
_REGISTRY_LOADERS: Dict[str, callable] = {
    "austin":        _load_austin,
    "new_york_city": _load_new_york_city,
    # "houston":       _load_houston,
    # "dallas":        _load_dallas,
    # "san_antonio":   _load_san_antonio,
    # "san_francisco": _load_san_francisco,
    # "chicago":       _load_chicago,
    # "los_angeles":   _load_los_angeles,
}

# ── Aliases: any alternate name → canonical slug ─────────────────
#   Supports shorthand, abbreviations, and common misspellings.
CITY_ALIASES: Dict[str, str] = {
    # Austin
    "atx":              "austin",
    "austin tx":        "austin",
    "austin, tx":       "austin",
    "austin texas":     "austin",
    "austin, texas":    "austin",
    "city of austin":   "austin",

    # New York City
    "nyc":                  "new_york_city",
    "new york":             "new_york_city",
    "new york city":        "new_york_city",
    "new york, ny":         "new_york_city",
    "new york city, ny":    "new_york_city",
    "ny":                   "new_york_city",
    "manhattan":            "new_york_city",
    "brooklyn":             "new_york_city",
    "queens":               "new_york_city",
    "bronx":                "new_york_city",
    "staten island":        "new_york_city",

    # Placeholders for future cities (aliases won't break if loader missing)
    "hou":              "houston",
    "houston tx":       "houston",
    "houston, tx":      "houston",
    "dfw":              "dallas",
    "dallas tx":        "dallas",
    "dallas, tx":       "dallas",
    "sa":               "san_antonio",
    "san antonio":      "san_antonio",
    "san antonio, tx":  "san_antonio",
    "sf":               "san_francisco",
    "nyc":              "new_york",
    "new york city":    "new_york",
    "la":               "los_angeles",
    "los angeles":      "los_angeles",
}

# ── In-process cache so each city config is loaded only once ─────
_CACHE: Dict[str, "CityConfig"] = {}


# ═══════════════════════════════════════════════════════════════
#  Custom exception
# ═══════════════════════════════════════════════════════════════

class CityNotFoundError(KeyError):
    """
    Raised when get_city() cannot resolve the requested city.
    Carries a human-readable message and a list of suggestions.
    """
    def __init__(self, query: str, suggestions: List[str], available: List[str]):
        self.query = query
        self.suggestions = suggestions
        self.available = available
        parts = [f"City '{query}' not found in the registry."]
        if suggestions:
            parts.append(f"Did you mean: {', '.join(suggestions)}?")
        parts.append(f"Registered cities: {', '.join(available)}.")
        parts.append("To add a new city see config/cities/__init__.py.")
        super().__init__(" ".join(parts))


# ═══════════════════════════════════════════════════════════════
#  Internal helpers
# ═══════════════════════════════════════════════════════════════

def _normalize(raw: str) -> str:
    """Lowercase, strip, collapse whitespace, replace spaces with underscores."""
    return "_".join(raw.lower().strip().split())


def _resolve_slug(query: str) -> Optional[str]:
    """
    Try every resolution strategy in priority order.
    Returns a canonical slug string or None if no match.

    Priority:
      1. Exact slug match (after normalization)
      2. Alias match
      3. Unambiguous prefix match
      4. Unambiguous suffix match  (e.g. "tx/austin" → "austin")
      5. None
    """
    norm = _normalize(query)

    # 1. Direct slug hit
    if norm in _REGISTRY_LOADERS:
        return norm

    # 2. Alias
    if norm in CITY_ALIASES:
        alias_target = CITY_ALIASES[norm]
        # Only resolve if that slug is actually registered
        if alias_target in _REGISTRY_LOADERS:
            return alias_target

    # 3. Prefix match — e.g. "aus" → "austin"
    prefix_hits = [slug for slug in _REGISTRY_LOADERS if slug.startswith(norm)]
    if len(prefix_hits) == 1:
        return prefix_hits[0]

    # 4. Suffix / substring match — handles "city_of_austin" → "austin"
    sub_hits = [slug for slug in _REGISTRY_LOADERS if norm in slug]
    if len(sub_hits) == 1:
        return sub_hits[0]

    return None


def _fuzzy_suggestions(query: str, n: int = 3) -> List[str]:
    """Return up to n close matches from registered slugs + alias keys."""
    corpus = list(_REGISTRY_LOADERS.keys()) + list(CITY_ALIASES.keys())
    norm = _normalize(query)
    return difflib.get_close_matches(norm, corpus, n=n, cutoff=0.55)


# ═══════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════

def get_city(city_key: str) -> "CityConfig":
    """
    Retrieve a CityConfig by name, slug, or alias.

    Examples
    --------
    >>> cfg = get_city("austin")
    >>> cfg = get_city("Austin, TX")
    >>> cfg = get_city("ATX")
    >>> cfg = get_city("aus")          # unambiguous prefix

    Raises
    ------
    CityNotFoundError  — with fuzzy suggestions and list of available cities.
    TypeError          — if city_key is not a string.
    """
    if not isinstance(city_key, str):
        raise TypeError(
            f"get_city() expects a string, got {type(city_key).__name__!r}"
        )
    if not city_key.strip():
        raise ValueError("get_city() received an empty string")

    slug = _resolve_slug(city_key)

    if slug is None:
        raise CityNotFoundError(
            query=city_key,
            suggestions=_fuzzy_suggestions(city_key),
            available=list(_REGISTRY_LOADERS.keys()),
        )

    # Return cached instance if available
    if slug in _CACHE:
        return _CACHE[slug]

    # Load, validate, and cache
    loader = _REGISTRY_LOADERS[slug]
    city_cfg = loader()
    _CACHE[slug] = city_cfg
    return city_cfg


def list_cities() -> List[str]:
    """Return all registered city slugs."""
    return list(_REGISTRY_LOADERS.keys())


def list_aliases() -> Dict[str, str]:
    """Return the full alias → slug mapping."""
    return dict(CITY_ALIASES)


def register_city(slug: str, loader: callable, aliases: List[str] = None) -> None:
    """
    Programmatically register a city at runtime.

    Parameters
    ----------
    slug    : canonical lowercase_underscore slug, e.g. "houston"
    loader  : zero-argument callable returning a CityConfig instance
    aliases : optional list of alternate lookup strings

    Example
    -------
    >>> from config.cities.houston import HOUSTON
    >>> register_city("houston", lambda: HOUSTON, aliases=["hou", "houston tx"])
    """
    slug = _normalize(slug)
    _REGISTRY_LOADERS[slug] = loader
    # Invalidate cache for this slug in case it was previously a miss
    _CACHE.pop(slug, None)
    if aliases:
        for alias in aliases:
            CITY_ALIASES[_normalize(alias)] = slug


def get_city_or_none(city_key: str) -> Optional["CityConfig"]:
    """Like get_city() but returns None instead of raising on miss."""
    try:
        return get_city(city_key)
    except (CityNotFoundError, TypeError, ValueError):
        return None
