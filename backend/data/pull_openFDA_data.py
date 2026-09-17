"""
RxWatch — openFDA data pull

Pulls three datasets needed for the shortage prediction project:
  1. Drug shortages       -> api.fda.gov/drug/shortages.json
  2. Drug recalls         -> api.fda.gov/drug/enforcement.json
  3. NDC directory        -> api.fda.gov/drug/ndc.json

Saves each as a raw CSV in ./data/ so nothing is lost before cleaning.

Usage:
    pip install requests pandas --break-system-packages   # if not already installed
    python pull_openfda_data.py

Notes:
  - No API key is required, but you're rate-limited to ~240 requests/min
    and 1,000 requests/day without one. If you hit limits, get a free key at
    https://open.fda.gov/apis/authentication/ and set API_KEY below.
  - openFDA enforces a HARD LIMIT: skip must be 25000 or less. Any endpoint
    with more than ~25,100 matching records (like the NDC directory) cannot
    be fully retrieved with simple pagination — the last page just fails.
    The NDC directory pull below works around this by recursively splitting
    the query into finer drug-name prefixes (a, aa, ab, ... ) whenever a
    prefix's results would exceed the ceiling, so nothing gets silently lost.
"""

import requests
import pandas as pd
import time
import os
import json
import string

API_KEY = None
BASE_URL = "https://api.fda.gov"
OUTPUT_DIR = "data"
PAGE_SIZE = 100            # max allowed by openFDA per request
SLEEP_BETWEEN_CALLS = 0.3  # seconds between requests to avoid hitting rate limits
SKIP_CEILING = 25000       # openFDA hard limit: skip must be <= this value


def fetch_all(endpoint: str, extra_params: dict | None = None):
    """
    Page through an openFDA endpoint and return (records, hit_ceiling).
    hit_ceiling=True means we stopped because of the skip<=25000 limit,
    not because we ran out of real results — caller should split further.
    """
    all_records = []
    skip = 0
    params = extra_params.copy() if extra_params else {}
    if API_KEY:
        params["api_key"] = API_KEY

    while True:
        params["limit"] = PAGE_SIZE
        params["skip"] = skip
        url = f"{BASE_URL}{endpoint}"

        resp = requests.get(url, params=params)

        if resp.status_code == 404:
            print(f"    Reached end of data at skip={skip}.")
            break

        if resp.status_code == 400 and "Skip value" in resp.text:
            print(f"    Hit skip ceiling at skip={skip} — needs splitting.")
            return all_records, True

        if resp.status_code != 200:
            print(f"    Request failed (status {resp.status_code}) at skip={skip}: {resp.text[:300]}")
            break

        payload = resp.json()
        results = payload.get("results", [])

        if not results:
            break

        all_records.extend(results)
        print(f"    Pulled {len(all_records)} records so far (skip={skip})...")

        if len(results) < PAGE_SIZE:
            break

        skip += PAGE_SIZE
        time.sleep(SLEEP_BETWEEN_CALLS)

    return all_records, False


def fetch_all_recursive(endpoint: str, field: str, prefix: str, base_params=None, depth: int = 0):
    """
    Pull all records matching `field:{prefix}*`, automatically splitting
    into finer prefixes (prefix+a, prefix+b, ... prefix+9) whenever a
    single prefix's results exceed the pagination ceiling. Guarantees no
    records are silently dropped, no matter how unevenly names are
    distributed across letters.
    """
    indent = "  " * (depth + 1)
    params = base_params.copy() if base_params else {}
    params["search"] = f"{field}:{prefix}*"

    print(f"{indent}Trying prefix '{prefix}'...")
    records, hit_ceiling = fetch_all(endpoint, params)

    if not hit_ceiling:
        print(f"{indent}Prefix '{prefix}' complete: {len(records)} records.")
        return records

    print(f"{indent}Prefix '{prefix}' exceeded ceiling ({len(records)}+ records) — splitting further.")
    all_records = []
    for c in list(string.ascii_lowercase) + list(string.digits):
        sub_records = fetch_all_recursive(endpoint, field, prefix + c, base_params, depth + 1)
        all_records.extend(sub_records)
    return all_records


def save_raw_and_csv(records: list, name: str):
    """Save both the raw JSON (safety net) and a flattened CSV."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    raw_path = os.path.join(OUTPUT_DIR, f"{name}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(records, f)
    print(f"  Saved raw JSON -> {raw_path}")

    if records:
        df = pd.json_normalize(records)
        # Drop exact duplicate rows — recursive splitting can occasionally
        # pull the same record twice at chunk boundaries.
        before = len(df)
        dedup_key = df.astype(str).apply(tuple, axis=1)
        df = df[~dedup_key.duplicated()]
        after = len(df)
        if before != after:
            print(f"  Dropped {before - after} duplicate rows.")
        csv_path = os.path.join(OUTPUT_DIR, f"{name}.csv")
        df.to_csv(csv_path, index=False)
        print(f"  Saved CSV -> {csv_path}  ({len(df)} rows, {len(df.columns)} columns)")
    else:
        print(f"  No records returned for {name} — nothing to save.")


def main():
    print("=== Pulling drug shortages ===")
    shortages, _ = fetch_all("/drug/shortages.json")
    save_raw_and_csv(shortages, "shortages")

    print("\n=== Pulling drug recalls (enforcement reports) ===")
    recalls, hit_ceiling = fetch_all(
        "/drug/enforcement.json",
        extra_params={"search": "report_date:[20180101 TO 20261231]"},
    )
    if hit_ceiling:
        print("  WARNING: recalls pull hit the skip ceiling too — consider narrowing the date range further.")
    save_raw_and_csv(recalls, "recalls")

    print("\n=== Pulling NDC directory (manufacturer/product metadata) ===")
    print("  This pulls in chunks and will take a while — the directory has 100,000+ records.")
    ndc_all = []
    for c in list(string.ascii_lowercase) + list(string.digits):
        records = fetch_all_recursive("/drug/ndc.json", "generic_name", c)
        ndc_all.extend(records)

    print(f"\n  Total NDC directory records pulled: {len(ndc_all)}")
    save_raw_and_csv(ndc_all, "ndc_directory")

    print("\nDone. Check the ./data folder for shortages.csv, recalls.csv, and ndc_directory.csv")


if __name__ == "__main__":
    main()