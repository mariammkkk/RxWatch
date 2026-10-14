"""Builds the compact, committed data artifacts the backend actually loads
at runtime, so the backend doesn't depend on the full gitignored raw CSVs
(the NDC directory alone is ~116 MB, the shortages/recalls raw pulls
another several MB -- none of that is fit to commit, and most of each
file's columns are never read).

Sources:
  - NDC directory: backend/data/ndc_directory.csv (the current complete
    bulk-downloaded pull -- gitignored, not committed).
  - Shortages: analysis/data/shortages_snapshot_2026-08-20.csv (the
    archived training snapshot, not the live backend/data/shortages.csv --
    the live /drug/shortages.json endpoint is mutable and ages records
    out over time, so the snapshot is the stable source of truth; see
    analysis/results.json's ndc_completeness_comparison for why).
  - Recalls: analysis/data/recalls_snapshot_2026-08-20.csv (same reason,
    for consistency, though this endpoint is append-only in practice).

Outputs (gzip-compressed CSV, committed -- see backend/data/.gitignore
exceptions):
  - backend/data/ndc_lookup.csv.gz: product_ndc, generic_name, labeler_name,
    brand_name, dosage_form, product_type -- the only 6 of ndc_directory's
    31 columns backend/main.py ever reads. Same row count (every row can
    contribute to a generic_name-level aggregate or a brand/generic text
    search), just narrower.
  - backend/data/shortages_lookup.csv.gz: generic_name, dosage_form,
    therapeutic_category, status, shortage_reason, openfda.product_ndc --
    the only 6 of shortages.csv's columns main.py reads. Same rows.
  - backend/data/recalls_lookup.csv.gz: generic_name, recall_count --
    main.py never reads a single recalls.csv row directly, only
    recalls.groupby(recall_col).size() (recall_col is "openfda.generic_name"
    if present, else "generic_name"). Precomputing that groupby here once,
    rather than shipping ~10,000 raw rows to recompute it on every backend
    startup, is a strictly smaller and strictly faster artifact with
    IDENTICAL output -- it's the exact same pandas call, just run here
    instead of in main.py.

Run from backend/data/, with the venv active: python3 build_lookup_files.py
"""
import os
import pandas as pd

NDC_SOURCE = "ndc_directory.csv"
SHORTAGES_SOURCE = "../../analysis/data/shortages_snapshot_2026-08-20.csv"
RECALLS_SOURCE = "../../analysis/data/recalls_snapshot_2026-08-20.csv"

NDC_OUT = "ndc_lookup.csv.gz"
SHORTAGES_OUT = "shortages_lookup.csv.gz"
RECALLS_OUT = "recalls_lookup.csv.gz"

NDC_COLUMNS = ["product_ndc", "generic_name", "labeler_name", "brand_name", "dosage_form", "product_type"]
SHORTAGES_COLUMNS = ["generic_name", "dosage_form", "therapeutic_category", "status",
                     "shortage_reason", "openfda.product_ndc"]


def report_size(path: str):
    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"  {path}: {size_mb:.2f} MB")
    return size_mb


def build_ndc():
    print(f"Reading {NDC_SOURCE} ...")
    ndc = pd.read_csv(NDC_SOURCE, usecols=NDC_COLUMNS)
    print(f"  {len(ndc)} rows, columns: {list(ndc.columns)}")
    ndc.to_csv(NDC_OUT, index=False, compression="gzip")
    report_size(NDC_OUT)


def build_shortages():
    print(f"Reading {SHORTAGES_SOURCE} ...")
    shortages = pd.read_csv(SHORTAGES_SOURCE, usecols=SHORTAGES_COLUMNS)
    print(f"  {len(shortages)} rows, columns: {list(shortages.columns)}")
    shortages.to_csv(SHORTAGES_OUT, index=False, compression="gzip")
    report_size(SHORTAGES_OUT)


def build_recalls():
    print(f"Reading {RECALLS_SOURCE} ...")
    recalls = pd.read_csv(RECALLS_SOURCE)
    recall_col = "openfda.generic_name" if "openfda.generic_name" in recalls.columns else "generic_name"
    print(f"  Grouping by {recall_col!r} (same logic main.py used to run at startup)")
    counts = recalls.groupby(recall_col).size().rename("recall_count").reset_index()
    counts = counts.rename(columns={recall_col: "generic_name"})
    print(f"  {len(recalls)} raw rows -> {len(counts)} distinct generic names")
    counts.to_csv(RECALLS_OUT, index=False, compression="gzip")
    report_size(RECALLS_OUT)


if __name__ == "__main__":
    print("=== Building compact lookup files ===\n")
    build_ndc()
    print()
    build_shortages()
    print()
    build_recalls()
    print("\nDone.")
