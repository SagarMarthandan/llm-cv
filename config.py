"""
config.py — Centralized configuration for LLM-CV Pipeline.

Provides default paths and constants with environment variable override support.
"""
import json
import os


# Base paths (override with environment variables if needed)
# Calculate paths relative to skill directory for portability
SKILL_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SKILL_DIR  # Skill is self-contained; Applications/ lives inside it

DEFAULT_BASE_FILES_DIR = os.getenv(
    "LLM_CV_BASE_FILES_DIR",
    os.path.join(SKILL_DIR, "okf", "base_files")
)


# Applications directory (where the pipeline saves application folders)
# Lives outside the skill directory at /home/sagar/Applications so application
# data persists independently of skill updates. Override via LLM_CV_APPLICATIONS_DIR env var.
APPLICATIONS_DIR = os.getenv(
    "LLM_CV_APPLICATIONS_DIR",
    "/home/sagar/Applications"
)

# ─── Candidate personal info ──────────────────────────────────────────────────
# Used by renderers as fallback defaults and by step docs as reference values.
# The YAML `name`/`sender` fields always take precedence over these defaults.
CANDIDATE_NAME = os.getenv("LLM_CV_CANDIDATE_NAME", "Sagar Marthandan")
CANDIDATE_PHONE = os.getenv("LLM_CV_CANDIDATE_PHONE", "+49 176 74138359")
CANDIDATE_EMAIL = os.getenv("LLM_CV_CANDIDATE_EMAIL", "sagar.marthandan@yahoo.com")
CANDIDATE_GITHUB = os.getenv("LLM_CV_CANDIDATE_GITHUB", "https://github.com/SagarMarthandan")
# Candidate photo (headshot) for resume — stamped onto the final PDF's
# top-right corner as a post-processing step. Set to None/empty to disable.
# Override via env var or YAML contact_info.photo.
CANDIDATE_PHOTO = os.getenv(
    "LLM_CV_CANDIDATE_PHOTO",
    os.path.join(SKILL_DIR, "okf", "SAGAR_MARTHANDAN_foto.jpg")
)

# Candidate signature image for cover letter — embedded between closing and
# typed name. PNG with transparent background recommended. Set to None/empty
# to disable (cover letter falls back to typed name only).
# Override via env var or YAML signature_image field.
CANDIDATE_SIGNATURE = os.getenv(
    "LLM_CV_CANDIDATE_SIGNATURE",
    os.path.join(SKILL_DIR, "okf", "SAGAR_MARTHANDAN_signature.png")
)

# Diversity audit thresholds
DIVERSITY_VENDOR_CLUSTER_THRESHOLD = int(os.getenv("LLM_CV_DIVERSITY_VENDOR_THRESHOLD", "3"))
DIVERSITY_REFERRAL_RATE_MIN = float(os.getenv("LLM_CV_DIVERSITY_REFERRAL_MIN", "0.20"))
DIVERSITY_LOOKBACK_DAYS = int(os.getenv("LLM_CV_DIVERSITY_LOOKBACK_DAYS", "14"))


# ─── Candidate city geocode table ─────────────────────────────────────────────
# The candidate's 4 home cities with approximate coordinates (lat, lon).
# Used by nearest_candidate_city() to avoid a web search per application.
CANDIDATE_CITIES = {
    "Kiel":      (54.32, 10.13),
    "Frankfurt": (50.11,  8.68),
    "Berlin":    (52.52, 13.40),
    "Köln":      (50.94,  6.96),
}

# Static mapping of common German job locations to their nearest candidate city.
# Falls back to web search for locations not in this table (see
# 01_ats_and_jd_archival.md section 5). To add new locations, append to this dict.
JOB_LOCATION_TO_CANDIDATE_CITY = {
    # Munich area -> Frankfurt (nearest of the 4)
    "Munich": "Frankfurt, Germany",
    "München": "Frankfurt, Germany",
    "Stuttgart": "Frankfurt, Germany",
    "Karlsruhe": "Frankfurt, Germany",
    "Mannheim": "Frankfurt, Germany",
    "Heidelberg": "Frankfurt, Germany",
    "Würzburg": "Frankfurt, Germany",
    "Wuerzburg": "Frankfurt, Germany",
    "Nürnberg": "Frankfurt, Germany",
    "Nuremberg": "Frankfurt, Germany",
    "Augsburg": "Frankfurt, Germany",
    "Regensburg": "Frankfurt, Germany",
    "Freiburg": "Frankfurt, Germany",
    "Ludwigsburg": "Frankfurt, Germany",
    "Böblingen": "Frankfurt, Germany",
    "Boeblingen": "Frankfurt, Germany",
    # Frankfurt area
    "Frankfurt": "Frankfurt, Germany",
    "Frankfurt am Main": "Frankfurt, Germany",
    "Wiesbaden": "Frankfurt, Germany",
    "Mainz": "Frankfurt, Germany",
    "Darmstadt": "Frankfurt, Germany",
    # Cologne area -> Köln
    "Köln": "Köln, Germany",
    "Cologne": "Köln, Germany",
    "Koln": "Köln, Germany",
    "Düsseldorf": "Köln, Germany",
    "Duesseldorf": "Köln, Germany",
    "Bonn": "Köln, Germany",
    "Aachen": "Köln, Germany",
    "Dortmund": "Köln, Germany",
    "Duisburg": "Köln, Germany",
    "Münster": "Köln, Germany",
    "Muenster": "Köln, Germany",
    "Krefeld": "Köln, Germany",
    "Dusseldorf": "Köln, Germany",
    # Berlin area
    "Berlin": "Berlin, Germany",
    "Potsdam": "Berlin, Germany",
    "Leipzig": "Berlin, Germany",
    "Dresden": "Berlin, Germany",
    "Hamburg": "Kiel, Germany",
    # Kiel area
    "Kiel": "Kiel, Germany",
    "Lübeck": "Kiel, Germany",
    "Luebeck": "Kiel, Germany",
    "Flensburg": "Kiel, Germany",
    "Hannover": "Kiel, Germany",
    "Hanover": "Kiel, Germany",
    "Bremen": "Kiel, Germany",
    "Remote": "Kiel, Germany",
    "Home Office": "Kiel, Germany",
    "Home-Office": "Kiel, Germany",
    "Deutschland": "Kiel, Germany",
    "Germany": "Kiel, Germany",
    "Nationwide": "Kiel, Germany",
}


def nearest_candidate_city(job_location: str) -> str:
    """Look up the nearest candidate city for a job location string.

    Uses the static JOB_LOCATION_TO_CANDIDATE_CITY table first, then falls back
    to a persistent location cache (okf/.location_cache.json) for locations
    previously resolved via web search. Returns None if the location is not
    found in either the table or the cache (caller should fall back to web
    search and then call cache_location_result() to store the answer).
    Normalizes input by stripping whitespace and trying case-insensitive match.
    """
    if not job_location:
        return None
    loc = job_location.strip()
    # Try exact match first
    if loc in JOB_LOCATION_TO_CANDIDATE_CITY:
        return JOB_LOCATION_TO_CANDIDATE_CITY[loc]
    # Try case-insensitive match
    loc_lower = loc.lower()
    for key, value in JOB_LOCATION_TO_CANDIDATE_CITY.items():
        if key.lower() == loc_lower:
            return value
    # Try substring match (e.g., "Munich, Germany" contains "Munich")
    for key, value in JOB_LOCATION_TO_CANDIDATE_CITY.items():
        if key.lower() in loc_lower:
            return value
    # Check the location cache (for locations previously resolved via web search)
    cached = _lookup_location_cache(loc)
    if cached:
        return cached
    return None


# ─── Location web search cache ────────────────────────────────────────────────
# Caches results of web searches for job locations not in the static table.
# Geography doesn't change, so cache entries are permanent.

_LOCATION_CACHE_PATH = os.path.join(SKILL_DIR, "okf", ".location_cache.json")


def _load_location_cache() -> dict:
    """Load the location cache from disk."""
    try:
        if os.path.exists(_LOCATION_CACHE_PATH):
            with open(_LOCATION_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_location_cache(cache: dict) -> None:
    """Save the location cache to disk."""
    try:
        os.makedirs(os.path.dirname(_LOCATION_CACHE_PATH), exist_ok=True)
        with open(_LOCATION_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _lookup_location_cache(job_location: str) -> str | None:
    """Check the location cache for a previously resolved location.

    Tries exact, case-insensitive, and substring matches (same strategy as
    the static table).
    """
    cache = _load_location_cache()
    if not cache:
        return None
    loc = job_location.strip()
    if loc in cache:
        return cache[loc]
    loc_lower = loc.lower()
    for key, value in cache.items():
        if key.lower() == loc_lower:
            return value
    for key, value in cache.items():
        if key.lower() in loc_lower:
            return value
    return None


def cache_location_result(job_location: str, nearest_city: str) -> None:
    """Store a web-search-resolved location in the persistent cache.

    Called by the pipeline after a web search resolves a location that wasn't
    in the static table. Future runs with the same location will hit the cache
    instead of doing another web search.
    """
    if not job_location or not nearest_city:
        return
    cache = _load_location_cache()
    cache[job_location.strip()] = nearest_city.strip()
    _save_location_cache(cache)


