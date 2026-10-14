"""
RxWatch: openFDA data pull

Pulls three datasets needed for the shortage prediction project:
  1. Drug shortages       -> api.fda.gov/drug/shortages.json
  2. Drug recalls         -> api.fda.gov/drug/enforcement.json
  3. NDC directory        -> api.fda.gov/drug/ndc.json

Saves each as a raw CSV in ./data/ so nothing is lost before cleaning.

Usage:
    pip install requests pandas --break-system-packages   # if not already installed
    python pull_openfda_data.py            # pulls all three datasets
    python pull_openfda_data.py ndc        # pulls only the NDC directory
                                            # (bulk download by default --
                                            # see NDC notes below), merging
                                            # into the existing metadata.json
                                            # (shortages/recalls untouched)
    python pull_openfda_data.py ndc api    # NDC via the paginated-API
                                            # fallback instead of bulk
    python pull_openfda_data.py shortages  # pulls only shortages
    python pull_openfda_data.py recalls    # pulls only recalls

Notes:
  - No API key is required, but you're rate-limited to ~240 requests/min
    and (more importantly) 1,000 requests/day without one. If you hit
    limits, get a free key at https://open.fda.gov/apis/authentication/
    and set API_KEY below.
  - openFDA enforces a HARD LIMIT: skip must be 25000 or less. Any endpoint
    with more than ~25,100 matching records (like the NDC directory) cannot
    be fully retrieved with simple pagination, so the last page just fails.
    A paginated pull works around this by recursively splitting the query
    into finer drug-name prefixes (a, aa, ab, ... ) whenever a prefix's
    results would exceed the ceiling -- but every prefix that needs
    splitting first makes a full round of "probe" requests before
    discovering it must split further, so the real request count for the
    full ~138,000-record NDC directory is well over 1,000 -- likely enough
    to exceed the anonymous daily quota in a single run. That quota
    (HTTP 429 once exhausted) is the most likely explanation for why the
    2026-08-20 NDC directory pull silently stopped partway through (ended
    up missing ~14,400 real records, including every finished "Ursodiol"
    product): the pull script's old code treated ANY non-200 response,
    429 included, as a clean end-of-results and moved on, rather than
    raising. No log from that run survives to confirm a 429 was hit, but
    the request-count math makes it the far more likely cause than a
    one-off transient error.
  - Because of that quota risk, NDC defaults to pulling openFDA's BULK
    download (https://api.fda.gov/download.json -> a single static JSON
    export, regenerated periodically) instead of the paginated API --
    one HTTP download instead of 1,000+ paginated search requests. The
    hardened paginated-API path (retries + RAISE instead of silent break,
    fail-loud completeness check against the live total) is kept as a
    fallback for when the bulk manifest or file is unavailable.
"""

import requests
import pandas as pd
import time
import os
import json
import string
import zipfile
from datetime import datetime, timezone

API_KEY = None
BASE_URL = "https://api.fda.gov"
OUTPUT_DIR = "data"
PAGE_SIZE = 100              # max allowed by openFDA per request
SLEEP_BETWEEN_CALLS = 0.3    # seconds between requests to avoid hitting rate limits
SKIP_CEILING = 25000         # openFDA hard limit: skip must be <= this value
MAX_RETRIES = 5              # per request, before giving up and raising
BACKOFF_BASE_SECONDS = 1.0   # doubles each retry: 1, 2, 4, 8, 16s
COMPLETENESS_TOLERANCE = 0.005  # 0.5% -- max allowed drift from the live total


class OpenFDAPullError(RuntimeError):
    """Raised on an unrecoverable pull failure: a request that exhausted
    all retries, or a finished pull whose row count doesn't match
    openFDA's own reported total within COMPLETENESS_TOLERANCE. Never
    swallowed -- the whole point is to fail loudly instead of silently
    shipping a truncated dataset."""


def _request_with_retries(url: str, params: dict, max_retries: int = MAX_RETRIES):
    """GET with exponential backoff on transient failures (network errors,
    timeouts, 429/5xx, anything not one of the two known terminal states).
    404 and "skip ceiling" 400s are legitimate terminal states the caller
    handles itself, so they're returned immediately, not retried. Raises
    OpenFDAPullError if max_retries is exhausted without a usable response."""
    last_error = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=30)
        except requests.RequestException as exc:
            last_error = str(exc)
            resp = None

        if resp is not None:
            if resp.status_code == 404:
                return resp
            if resp.status_code == 400 and "Skip value" in resp.text:
                return resp
            if resp.status_code == 200:
                return resp
            last_error = f"status {resp.status_code}: {resp.text[:300]}"

        if attempt < max_retries - 1:
            sleep_for = BACKOFF_BASE_SECONDS * (2 ** attempt)
            print(f"    Request failed ({last_error}), retrying in {sleep_for:.1f}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(sleep_for)

    raise OpenFDAPullError(
        f"Giving up on {url} (params={params}) after {max_retries} attempts: {last_error}"
    )


def fetch_live_total(endpoint: str) -> int:
    """openFDA's own meta.results.total for the full, unfiltered endpoint --
    the ground truth used for the post-pull completeness check."""
    params = {"limit": 1}
    if API_KEY:
        params["api_key"] = API_KEY
    resp = _request_with_retries(f"{BASE_URL}{endpoint}", params)
    if resp.status_code != 200:
        raise OpenFDAPullError(f"Could not fetch live total for {endpoint}: status {resp.status_code}")
    return resp.json()["meta"]["results"]["total"]


def check_completeness(endpoint: str, pulled_count: int) -> int:
    """Fetches the live total and raises if pulled_count differs from it by
    more than COMPLETENESS_TOLERANCE. Returns the live total on success, so
    callers can record it in metadata.json."""
    live_total = fetch_live_total(endpoint)
    diff = abs(pulled_count - live_total)
    pct = diff / live_total if live_total else 0.0
    print(f"  Live openFDA total for {endpoint} (unfiltered): {live_total}")
    print(f"  Pulled: {pulled_count}  Difference: {diff} ({pct * 100:.3f}%)")
    if pct > COMPLETENESS_TOLERANCE:
        raise OpenFDAPullError(
            f"{endpoint} pull is incomplete: pulled {pulled_count} records but openFDA "
            f"reports {live_total} live -- a {pct * 100:.3f}% difference, over the "
            f"{COMPLETENESS_TOLERANCE * 100:.1f}% completeness tolerance. Refusing to "
            f"treat this pull as complete."
        )
    return live_total


def fetch_all(endpoint: str, extra_params: dict | None = None):
    """
    Page through an openFDA endpoint and return (records, hit_ceiling, last_updated).
    hit_ceiling=True means we stopped because of the skip<=25000 limit,
    not because we ran out of real results, caller should split further.
    last_updated is openFDA's own meta.last_updated date for this dataset,
    taken from the first successful response (same value on every page).
    Any request that exhausts its retries raises OpenFDAPullError (see
    _request_with_retries) -- this function never silently treats a
    failure as end-of-data.
    """
    all_records = []
    skip = 0
    last_updated = None
    params = extra_params.copy() if extra_params else {}
    if API_KEY:
        params["api_key"] = API_KEY

    while True:
        params["limit"] = PAGE_SIZE
        params["skip"] = skip
        url = f"{BASE_URL}{endpoint}"

        resp = _request_with_retries(url, params)

        if resp.status_code == 404:
            print(f"    Reached end of data at skip={skip}.")
            break

        if resp.status_code == 400 and "Skip value" in resp.text:
            print(f"    Hit skip ceiling at skip={skip}, needs splitting.")
            return all_records, True, last_updated

        payload = resp.json()
        results = payload.get("results", [])

        if last_updated is None:
            last_updated = payload.get("meta", {}).get("last_updated")

        if not results:
            break

        all_records.extend(results)
        print(f"    Pulled {len(all_records)} records so far (skip={skip})...")

        if len(results) < PAGE_SIZE:
            break

        skip += PAGE_SIZE
        time.sleep(SLEEP_BETWEEN_CALLS)

    return all_records, False, last_updated


def fetch_all_recursive(endpoint: str, field: str, prefix: str, base_params=None, depth: int = 0):
    """
    Pull all records matching `field:{prefix}*`, automatically splitting
    into finer prefixes (prefix+a, prefix+b, ... prefix+9) whenever a
    single prefix's results exceed the pagination ceiling. Guarantees no
    records are silently dropped, no matter how unevenly names are
    distributed across letters. Returns (records, last_updated).
    """
    indent = "  " * (depth + 1)
    params = base_params.copy() if base_params else {}
    params["search"] = f"{field}:{prefix}*"

    print(f"{indent}Trying prefix '{prefix}'...")
    records, hit_ceiling, last_updated = fetch_all(endpoint, params)

    if not hit_ceiling:
        print(f"{indent}Prefix '{prefix}' complete: {len(records)} records.")
        return records, last_updated

    print(f"{indent}Prefix '{prefix}' exceeded ceiling ({len(records)}+ records), splitting further.")
    all_records = []
    for c in list(string.ascii_lowercase) + list(string.digits):
        sub_records, sub_last_updated = fetch_all_recursive(endpoint, field, prefix + c, base_params, depth + 1)
        all_records.extend(sub_records)
        last_updated = last_updated or sub_last_updated
    return all_records, last_updated


def save_raw_and_csv(records: list, name: str):
    """Save both the raw JSON (safety net) and a flattened CSV."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    raw_path = os.path.join(OUTPUT_DIR, f"{name}_raw.json")
    with open(raw_path, "w") as f:
        json.dump(records, f)
    print(f"  Saved raw JSON -> {raw_path}")

    if records:
        df = pd.json_normalize(records)
        # Drop exact duplicate rows: recursive splitting can occasionally
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
        print(f"  No records returned for {name}, nothing to save.")


def pull_shortages() -> dict:
    print("=== Pulling drug shortages ===")
    shortages, _, shortages_last_updated = fetch_all("/drug/shortages.json")
    save_raw_and_csv(shortages, "shortages")
    return {"openfda_last_updated": shortages_last_updated, "record_count": len(shortages)}


def pull_recalls() -> dict:
    print("\n=== Pulling drug recalls (enforcement reports) ===")
    recalls, hit_ceiling, recalls_last_updated = fetch_all(
        "/drug/enforcement.json",
        extra_params={"search": "report_date:[20180101 TO 20261231]"},
    )
    if hit_ceiling:
        print("  WARNING: recalls pull hit the skip ceiling too, consider narrowing the date range further.")
    save_raw_and_csv(recalls, "recalls")
    return {"openfda_last_updated": recalls_last_updated, "record_count": len(recalls)}


def pull_ndc_api() -> dict:
    """Hardened paginated-API fallback. Prefer pull_ndc_bulk() (see
    pull_ndc() below) -- this path needs 1,000+ real HTTP requests for the
    full directory and is very likely to hit the anonymous daily quota
    (see the module docstring)."""
    print("\n=== Pulling NDC directory via paginated API (fallback mode) ===")
    print("  This pulls in chunks and will take a while, the directory has 100,000+ records.")
    ndc_all = []
    ndc_last_updated = None
    for c in list(string.ascii_lowercase) + list(string.digits):
        records, last_updated = fetch_all_recursive("/drug/ndc.json", "generic_name", c)
        ndc_all.extend(records)
        ndc_last_updated = ndc_last_updated or last_updated
        print(f"  Running total after prefix '{c}': {len(ndc_all)} records.")

    print(f"\n  Total NDC directory records pulled: {len(ndc_all)}")
    live_total = check_completeness("/drug/ndc.json", len(ndc_all))
    save_raw_and_csv(ndc_all, "ndc_directory")
    return {
        "openfda_last_updated": ndc_last_updated,
        "record_count": len(ndc_all),
        "live_total_at_pull_time": live_total,
        "source": "openFDA paginated API pull",
    }


def fetch_bulk_manifest() -> dict:
    """The full openFDA download.json manifest: {"results": {"drug": {...},
    ...}} with one section per dataset, each listing its export_date,
    partition file URL(s), and total_records."""
    resp = _request_with_retries(f"{BASE_URL}/download.json", {})
    if resp.status_code != 200:
        raise OpenFDAPullError(f"Could not fetch {BASE_URL}/download.json: status {resp.status_code}")
    return resp.json()


def _download_file(url: str, dest_path: str, max_retries: int = MAX_RETRIES):
    """Streams url to dest_path with retries. Separate from
    _request_with_retries since this is a large binary download (stream +
    write-to-disk), not a small JSON API call."""
    last_error = None
    for attempt in range(max_retries):
        try:
            with requests.get(url, stream=True, timeout=120) as resp:
                if resp.status_code != 200:
                    last_error = f"status {resp.status_code}"
                else:
                    with open(dest_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            f.write(chunk)
                    return
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < max_retries - 1:
            sleep_for = BACKOFF_BASE_SECONDS * (2 ** attempt)
            print(f"    Download failed ({last_error}), retrying in {sleep_for:.1f}s "
                  f"(attempt {attempt + 1}/{max_retries})...")
            time.sleep(sleep_for)

    raise OpenFDAPullError(f"Giving up downloading {url} after {max_retries} attempts: {last_error}")


def pull_ndc_bulk() -> dict:
    """Default NDC pull mode: openFDA's bulk download (a single static
    JSON export regenerated periodically), parsed with the exact same
    pd.json_normalize flattening save_raw_and_csv() already uses for the
    paginated-API path, so the resulting ndc_directory.csv has identical
    columns/format either way. One HTTP download instead of 1,000+
    paginated search requests -- not subject to the anonymous daily quota
    that the paginated path almost certainly hit on 2026-08-20."""
    print("\n=== Pulling NDC directory via openFDA bulk download ===")
    manifest = fetch_bulk_manifest()
    partition = manifest.get("results", {}).get("drug", {}).get("ndc")
    if not partition:
        raise OpenFDAPullError("download.json has no drug.ndc partition info")

    export_date = partition.get("export_date") or manifest.get("export_date")
    file_url = partition["partitions"][0]["file"]
    listed_total = partition.get("total_records")
    print(f"  Partition file: {file_url}")
    print(f"  Export date: {export_date}  Listed total_records: {listed_total}")

    zip_path = os.path.join(OUTPUT_DIR, "_ndc_bulk_download.zip")
    print("  Downloading (~27 MB zip)...")
    _download_file(file_url, zip_path)

    print("  Unzipping and parsing...")
    with zipfile.ZipFile(zip_path) as zf:
        json_names = [n for n in zf.namelist() if n.endswith(".json")]
        if len(json_names) != 1:
            raise OpenFDAPullError(f"Expected exactly one .json entry in {zip_path}, found {json_names}")
        with zf.open(json_names[0]) as f:
            payload = json.load(f)
    os.remove(zip_path)

    ndc_last_updated = payload.get("meta", {}).get("last_updated")
    records = payload.get("results", [])
    reported_total = payload.get("meta", {}).get("results", {}).get("total")
    print(f"  Parsed {len(records)} records (file's own meta.results.total={reported_total}, "
          f"download.json listed total_records={listed_total}).")

    live_total = check_completeness("/drug/ndc.json", len(records))
    save_raw_and_csv(records, "ndc_directory")
    return {
        "openfda_last_updated": ndc_last_updated,
        "record_count": len(records),
        "live_total_at_pull_time": live_total,
        "source": "openFDA bulk download",
        "bulk_export_date": export_date,
        "bulk_file_url": file_url,
    }


def pull_ndc(mode: str = "bulk") -> dict:
    """mode="bulk" (default): pull_ndc_bulk(). mode="api": the hardened
    paginated-API fallback, pull_ndc_api()."""
    if mode == "api":
        return pull_ndc_api()
    return pull_ndc_bulk()


def _load_existing_metadata() -> dict:
    metadata_path = os.path.join(OUTPUT_DIR, "metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            return json.load(f)
    return {"pulled_at": None, "source": None, "datasets": {}}


def _save_metadata(pulled_at: str, source: str, datasets_meta: dict):
    metadata_path = os.path.join(OUTPUT_DIR, "metadata.json")
    with open(metadata_path, "w") as f:
        json.dump({"pulled_at": pulled_at, "source": source, "datasets": datasets_meta}, f, indent=2)
    print(f"\n  Saved {metadata_path}")


def main(only: str | None = None, ndc_mode: str = "bulk"):
    """only=None pulls all three datasets (original behavior). "ndc" /
    "shortages" / "recalls" pulls just that one dataset and merges its
    metadata entry into the existing metadata.json, leaving the other two
    datasets' files and metadata entries untouched. ndc_mode controls how
    the NDC directory is pulled when it's included ("bulk" default, "api"
    for the hardened paginated fallback) -- see pull_ndc()."""
    pulled_at = datetime.now(timezone.utc).isoformat()
    datasets_meta = dict(_load_existing_metadata().get("datasets", {}))

    if only in (None, "shortages"):
        datasets_meta["shortages"] = pull_shortages()
    if only in (None, "recalls"):
        datasets_meta["recalls"] = pull_recalls()
    if only in (None, "ndc"):
        datasets_meta["ndc_directory"] = pull_ndc(mode=ndc_mode)

    _save_metadata(pulled_at, "openFDA API pull", datasets_meta)
    print("\nDone. Check the ./data folder for shortages.csv, recalls.csv, and ndc_directory.csv")


if __name__ == "__main__":
    import sys
    _only = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] in ("ndc", "shortages", "recalls") else None
    _ndc_mode = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] in ("bulk", "api") else "bulk"
    main(only=_only, ndc_mode=_ndc_mode)