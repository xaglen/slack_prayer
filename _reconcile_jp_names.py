"""
One-time helper: run by hand after JOSHUA_PROJECT_API_KEY is set in settings.py,
to see which country_slugs.csv names fail to join against Joshua Project's
country list, and to sanity-check REGION_MAP's region-name strings against a
real API response.

Not wired into the weekly cron. Once NAME_ALIASES / COUNTRY_DENYLIST /
REGION_MAP in country_data.py are settled, archive this script (don't delete
it, per repo convention) to scripts/_archive/pray/.

Usage: venv/bin/python scripts/pray/_reconcile_jp_names.py
"""

import csv

import country_data
import settings

with open("country_slugs.csv", newline="") as csvfile:
    ow_rows = list(csv.reader(csvfile, delimiter=",", quotechar='"'))

jp_countries = country_data.fetch_jp_countries(settings.JOSHUA_PROJECT_API_KEY)
print(f"Fetched {len(jp_countries)} countries from Joshua Project.\n")

jp_region_names = sorted({row.get("RegionName") for row in jp_countries if row.get("RegionName")})
print("Live RegionName values seen (compare against country_data.REGION_MAP keys):")
for name in jp_region_names:
    mapped = country_data.REGION_MAP.get(country_data.normalize_name(name), "  <-- UNMAPPED")
    print(f"  {name!r}: {mapped}")
print()

pool = country_data.build_country_pool(ow_rows, jp_countries)
matched_names = {country_data.normalize_name(c["name"]) for c in pool}

unmatched = [row[0] for row in ow_rows if len(row) >= 2 and country_data.normalize_name(row[0]) not in matched_names]
print(f"{len(pool)} of {len(ow_rows)} country_slugs.csv rows joined successfully.\n")
print(f"{len(unmatched)} unmatched (add to NAME_ALIASES or COUNTRY_DENYLIST as appropriate):")
for name in sorted(unmatched):
    print(f"  {name}")
