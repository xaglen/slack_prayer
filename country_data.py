"""
Missiological weighting, region rotation, and recency-dedup for
slack-countries.py's weekly country pick.

Data source: Joshua Project API v1 (https://api.joshuaproject.net/v1/countries.json),
field names and RegionName values confirmed against a live response 2026-08-05.
Re-run _reconcile_jp_names.py if JP renames a region or a country stops joining.
"""

import json
import logging
import math
import os
import random
import unicodedata
from datetime import date, timedelta
from urllib import parse

import requests

JP_API_BASE = "https://api.joshuaproject.net/v1"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "jp_cache.json")
CACHE_TTL_DAYS = 30
RECENCY_WINDOW_WEEKS = 26
MAX_ATTEMPTS = 15

# Order matters: this is the fixed rotation sequence, cycled by ISO week number.
# The buckets are never shown to users (the post names only the country). They follow
# Joshua Project's own regions, merged to 8 so Asia (~75% of the least-reached
# population) gets 2/8 of weeks and Africa + North Africa/Middle East 3/8 (Oct 2026).
# Interleaved so two low-need buckets never run back to back.
CONTINENTS = [
    "North Africa & Middle East",
    "West & Central Africa",
    "South & Central Asia",
    "Europe",
    "East & Southern Africa",
    "East & Southeast Asia",
    "Americas",
    "Oceania",
]

# Joshua Project's 12 RegionName values (keys normalize_name()'d) -> our 8 buckets.
# Confirmed against a live /v1/countries.json response (2026-08-05) via
# _reconcile_jp_names.py. Note JP files Turkey under "Asia, Central".
REGION_MAP = {
    "africa, north and middle east": "North Africa & Middle East",
    "africa, west and central": "West & Central Africa",
    "africa, east and southern": "East & Southern Africa",
    "asia, south": "South & Central Asia",
    "asia, central": "South & Central Asia",
    "asia, northeast": "East & Southeast Asia",
    "asia, southeast": "East & Southeast Asia",
    "europe, western": "Europe",
    "europe, eastern and eurasia": "Europe",
    "america, latin": "Americas",
    "america, north and caribbean": "Americas",
    "australia and pacific": "Oceania",
}

# OW-name (as it appears in country_slugs.csv) -> JP-name mismatches.
# Confirmed against a live /v1/countries.json response (2026-08-05) via
# _reconcile_jp_names.py -- both sides normalized with normalize_name()
# before lookup.
NAME_ALIASES = {
    "south korea": "korea, south",
    "north korea": "korea, north",
    "bosnia": "bosnia-herzegovina",
    "cabo verde": "cape verde",
    "micronesia": "micronesia, federated states",
    "hong kong": "china, hong kong",
    "kiribati": "kiribati (gilbert)",
    "macedonia": "north macedonia",
    "myanmar": "myanmar (burma)",
    "macau": "china, macau",
    "turkey": "turkiye (turkey)",
    "congo [drc]": "congo, democratic republic of",
    "republic of congo": "congo, republic of the",
    "falkland islands [islas malvinas]": "falkland islands",
    "palestinian territories": "west bank / gaza",
    "saint vincent and the grenadines": "st vincent and grenadines",
    "czech republic": "czechia",
    "u.s. virgin islands": "virgin islands (u.s.)",
}

# Territories to always exclude regardless of Joshua Project coverage --
# uninhabited, or not meaningfully a "country" to intercede for. Keys are
# normalize_name()'d against the country_slugs.csv name (not the JP name).
# Extend after reviewing what's left in country_slugs.csv post-join.
COUNTRY_DENYLIST = {
    "cocos [keeling] islands",
    "christmas island",
    "norfolk island",
    "wallis and futuna",
    "vatican city",
    "antarctica",
}


def normalize_name(name):
    if not name:
        return ""
    decomposed = unicodedata.normalize("NFKD", name)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().split())


def operation_world_url(slug):
    return f"https://operationworld.org/locations/{slug}/"


def build_wikipedia_url(country_name):
    return f"https://wikipedia.org/wiki/{parse.quote(country_name)}"


def jp_profile_url(rog3):
    return f"https://joshuaproject.net/countries/{rog3}"


def format_population(n):
    """18749000 -> '18.7M', 8620 -> '9K'"""
    if not n:
        return None
    n = int(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def quick_facts_line(jp_row):
    """% evangelical + unreached population -- fields already present in the
    cached JP response, no extra API calls."""
    parts = []
    pct = jp_row.get("PercentEvangelical")
    if pct is not None:
        parts.append(f"{round(pct, 1)}% evangelical")
    unreached_pop = format_population(jp_row.get("PoplPeoplesLR"))
    if unreached_pop:
        parts.append(f"{unreached_pop} in unreached people groups")
    return " · ".join(parts)


def fetch_jp_countries(api_key):
    """Single HTTP call to Joshua Project's /countries.json. Raises on any
    network error, non-200, or API-reported error."""
    url = f"{JP_API_BASE}/countries.json"
    response = requests.get(url, params={"api_key": api_key}, timeout=20)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and "api" in data:
        error = data.get("api", {}).get("error", {})
        raise RuntimeError(f"Joshua Project API error: {error.get('message', data)}")
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected Joshua Project response shape: {type(data)}")
    return data


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def cache_is_stale(cache):
    fetched_at = date.fromisoformat(cache["fetched_at"])
    return (date.today() - fetched_at).days > CACHE_TTL_DAYS


def save_cache(countries):
    with open(CACHE_PATH, "w") as f:
        json.dump({"fetched_at": date.today().isoformat(), "countries": countries}, f)


def get_jp_countries(api_key):
    """Cache-first orchestration: fresh fetch if cache missing/stale, falling
    back to a stale cache (with a logged warning) if the live fetch fails.
    Raises only if there's truly nothing to fall back to."""
    cache = load_cache()
    if cache and not cache_is_stale(cache):
        return cache["countries"]
    try:
        countries = fetch_jp_countries(api_key)
        save_cache(countries)
        return countries
    except Exception as e:
        logging.warning(f"country_data: Joshua Project fetch failed ({e})")
        if cache:
            logging.warning("country_data: falling back to stale cache")
            return cache["countries"]
        raise


def _weight_from_jp_row(row):
    """sqrt(PoplPeoplesLR): raw population made the draw near-deterministic (India,
    Australia, Yemen every rotation; ~72 distinct countries in 3 years); sqrt still
    favors the least-reached but spreads the picks (~92). PoplPeoplesLR is null for
    many well-evangelized countries (Estonia, Trinidad and Tobago, ...) -- JP isn't
    tracking a least-reached population there, which for our purposes means 0, not
    "no data". Floor at 1 so those stay in the pool at minimal weight."""
    raw = row.get("PoplPeoplesLR")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        value = 0
    return max(1.0, math.sqrt(value))


def _continent_from_jp_row(row):
    region_name = normalize_name(row.get("RegionName"))
    if not region_name:
        return None
    continent = REGION_MAP.get(region_name)
    if continent is None:
        logging.info(f"country_data: unmapped Joshua Project RegionName {row.get('RegionName')!r}")
    return continent


def build_country_pool(ow_rows, jp_countries):
    """Inner-join country_slugs.csv rows against Joshua Project countries by
    normalized name (+ NAME_ALIASES). Drops denylisted, unmatched, or
    incomplete entries. Returns a list of {name, slug, continent, weight,
    country_url, wikipedia_url, jp_profile_url, quick_facts, jp_scale_text,
    jp_scale_image_url} dicts."""
    jp_by_name = {}
    for row in jp_countries:
        key = normalize_name(row.get("Ctry"))
        if key:
            jp_by_name[key] = row

    pool = []
    unmatched = []
    for row in ow_rows:
        if len(row) < 2:
            continue
        ow_name, slug = row[0], row[1]
        norm = normalize_name(ow_name)
        if norm in COUNTRY_DENYLIST:
            continue
        jp_key = NAME_ALIASES.get(norm, norm)
        jp_row = jp_by_name.get(jp_key)
        if jp_row is None:
            unmatched.append(ow_name)
            continue
        weight = _weight_from_jp_row(jp_row)
        continent = _continent_from_jp_row(jp_row)
        if weight is None or continent is None:
            unmatched.append(ow_name)
            continue
        pool.append(
            {
                "name": ow_name,
                "slug": slug,
                "continent": continent,
                "weight": weight,
                "country_url": operation_world_url(slug),
                "wikipedia_url": build_wikipedia_url(ow_name),
                "jp_profile_url": jp_profile_url(jp_row.get("ROG3", "")),
                "quick_facts": quick_facts_line(jp_row),
                "jp_scale_text": jp_row.get("JPScaleText"),
                "jp_scale_image_url": jp_row.get("JPScaleImageURL"),
            }
        )

    if unmatched:
        logging.info(
            f"country_data: {len(unmatched)} country_slugs.csv entries had no usable "
            f"Joshua Project match: {', '.join(sorted(unmatched))}"
        )
    return pool


def continent_of_the_week(today=None):
    today = today or date.today()
    week_number = today.isocalendar()[1]
    return CONTINENTS[week_number % len(CONTINENTS)]


def excluded_recent_names(weeks=RECENCY_WINDOW_WEEKS):
    from django.utils import timezone

    from people.models import CountryPrayer

    cutoff = timezone.now() - timedelta(weeks=weeks)
    names = CountryPrayer.objects.filter(posted_at__gte=cutoff).values_list("country_name", flat=True)
    return {normalize_name(n) for n in names}


def eligible_candidates(pool, continent, excluded):
    return [c for c in pool if c["continent"] == continent and normalize_name(c["name"]) not in excluded]


def weighted_order(candidates):
    """Weighted draw-without-replacement: repeatedly random.choices() the
    remaining pool, remove what's drawn, until every candidate has a
    position. Returns a full reordering, not a fixed-size selection."""
    remaining = list(candidates)
    weights = [c["weight"] for c in remaining]
    ordered = []
    while remaining:
        idx = random.choices(range(len(remaining)), weights=weights, k=1)[0]
        ordered.append(remaining.pop(idx))
        weights.pop(idx)
    return ordered


def build_candidate_queue(pool, today=None):
    """Continent-of-the-week, filtered by recency-dedup, falling back through
    the remaining continents in rotation order and then the whole pool
    (still recency-filtered) if a bucket comes up empty. Returns a
    weighted-ordered queue to walk against Operation World; an empty queue
    tells the caller to fall back to the original unweighted random pick."""
    continent = continent_of_the_week(today)
    excluded = excluded_recent_names()

    order = [continent] + [c for c in CONTINENTS if c != continent]
    candidates = []
    for c in order:
        candidates = eligible_candidates(pool, c, excluded)
        if candidates:
            break

    if not candidates:
        candidates = [c for c in pool if normalize_name(c["name"]) not in excluded]

    return weighted_order(candidates)


def simulate(pool, n=500):
    """Offline dry-run harness: no network, no DB (recency exclusion is
    skipped, since it depends on real CountryPrayer rows). Simulates n
    consecutive weeks to sanity-check continent spread and weighted-draw
    skew before trusting this against the live Sunday cron."""
    from collections import Counter

    continent_counts = Counter()
    first_pick_counts = Counter()
    today = date.today()

    for i in range(n):
        simulated_date = today + timedelta(weeks=i)
        continent = continent_of_the_week(simulated_date)
        continent_counts[continent] += 1
        candidates = eligible_candidates(pool, continent, set())
        if not candidates:
            continue
        ordered = weighted_order(candidates)
        first_pick_counts[ordered[0]["name"]] += 1

    return {
        "pool_size": len(pool),
        "per_continent_pool_size": {c: len(eligible_candidates(pool, c, set())) for c in CONTINENTS},
        "continent_distribution": dict(continent_counts),
        "top_first_picks": first_pick_counts.most_common(20),
    }
