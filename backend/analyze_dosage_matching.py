"""
Reports drug_class_lookup match coverage before/after the shortages.csv <->
ndc_directory.csv generic_name normalization fix, plus a spot-check sample.

Run with: python3 analyze_dosage_matching.py   (from backend/, with the venv active)
"""
import random

import main as m

# "before" lookup: raw shortages.csv generic_name, keyed the buggy way.
old_drug_class_lookup = (
    m.shortages.dropna(subset=["generic_name"])
    .drop_duplicates(subset="generic_name", keep="last")
    .set_index("generic_name")[["primary_category", "dosage_category"]]
    .to_dict("index")
)

unique_generics = m.ndc["generic_name"].dropna().astype(str).unique()


def coverage(lookup):
    matched = sum(1 for g in unique_generics if lookup.get(g, {}).get("primary_category") is not None)
    return matched, len(unique_generics)


old_matched, total = coverage(old_drug_class_lookup)
new_matched, _ = coverage(m.drug_class_lookup)

print(f"BEFORE fix: {old_matched}/{total} unique ndc_directory.csv generic_name values "
      f"matched a non-null primary_category ({100 * old_matched / total:.2f}%)")
print(f"AFTER  fix: {new_matched}/{total} unique ndc_directory.csv generic_name values "
      f"matched a non-null primary_category ({100 * new_matched / total:.2f}%)")

matched_names = [g for g in unique_generics if m.drug_class_lookup.get(g, {}).get("primary_category") is not None]
random.seed(7)
sample = random.sample(matched_names, min(15, len(matched_names)))

print()
print("=== 15 random matched pairs (ndc generic_name -> matched shortages generic_name -> category/dosage) ===")
for g in sample:
    info = m.drug_class_lookup[g]
    src = m.drug_class_match_source.get(g, "?")
    print(f"{g!r:45s} -> {src!r:60s} -> {info['primary_category']} / {info['dosage_category']}")
