# Diagnostic: checks whether dose_Oral's large model coefficient is a real signal or a data artifact.
"""
Diagnostic-only pass on dose_Oral's large coefficient (OR 13.48x) in the
deployed model: class balance, sample size, confounding with
primary_category, and baseline-frequency comparison. Does not touch or
retrain any model.

Run from analysis/diagnostics/, with the venv active: python3 dose_oral_diagnostic.py
"""
import ast
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for normalize_ndc
from normalize_ndc import normalize_ndc, expand_ndc_list

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc = pd.read_csv("../../backend/data/ndc_directory.csv")

shortages["ndc_list"] = shortages["openfda.product_ndc"].apply(expand_ndc_list)
recalls["ndc"] = recalls["openfda.product_ndc"].apply(normalize_ndc)
ndc["ndc"] = ndc["product_ndc"].apply(normalize_ndc)

ndc_lookup = ndc[["ndc", "generic_name"]].drop_duplicates(subset="ndc").rename(
    columns={"generic_name": "ndc_generic_name"}
)
manufacturer_counts = ndc.groupby("generic_name")["labeler_name"].nunique().rename("manufacturer_count")
recall_counts = recalls.groupby("ndc").size().rename("recall_count")

supply_side = [
    "Discontinuation of the manufacture of the drug",
    "Shortage of an active ingredient",
    "Delay in shipping of the drug",
    "Requirements related to complying with good manufacturing practices",
    "Shortage of an inactive ingredient component",
    "Regulatory delay",
]
shortages["reason_category"] = shortages["shortage_reason"].apply(
    lambda x: "Supply-side" if x in supply_side
    else ("Demand-side" if x == "Demand increase for the drug"
    else ("Other" if pd.notna(x) else None))
)


def get_primary_category(x):
    if pd.isna(x):
        return None
    try:
        parsed = ast.literal_eval(x) if isinstance(x, str) else x
        if isinstance(parsed, list) and len(parsed) > 0:
            return parsed[0]
    except (ValueError, SyntaxError):
        return None
    return None


def simplify_dosage(x):
    if pd.isna(x):
        return None
    if x == "Injection":
        return "Injectable"
    elif x in ["Tablet", "Capsule", "Tablet, Chewable", "Capsule, Extended Release",
               "Oral Suspension", "Oral Solution"]:
        return "Oral"
    else:
        return "Other"


shortages["primary_category"] = shortages["therapeutic_category"].apply(get_primary_category)
shortages["dosage_category"] = shortages["dosage_form"].apply(simplify_dosage)

shortages_exploded = shortages.explode("ndc_list").rename(columns={"ndc_list": "ndc"})
shortages_exploded = shortages_exploded.merge(ndc_lookup, on="ndc", how="left")
features = shortages_exploded.merge(
    manufacturer_counts, left_on="ndc_generic_name", right_on="generic_name", how="left"
)
features = features.merge(recall_counts, on="ndc", how="left")
features["recall_count"] = features["recall_count"].fillna(0)

model_data = features[features["reason_category"].isin(["Supply-side", "Demand-side"])].copy()
model_data["is_supply_side"] = (model_data["reason_category"] == "Supply-side").astype(int)
model_data = model_data.dropna(subset=["manufacturer_count", "recall_count", "primary_category", "dosage_category"])

category_counts = model_data["primary_category"].value_counts()
rare_categories = category_counts[category_counts < 20].index
model_data["primary_category_grouped"] = model_data["primary_category"].apply(
    lambda x: "Other/Rare" if x in rare_categories else x
)

print(f"model_data: {len(model_data)} rows\n")

# ---- 1 & 2: sample size + class balance per dosage_category ----
print("=== 1/2: sample size and class balance per dosage_category ===")
sizes = model_data["dosage_category"].value_counts()
print("Row counts:\n", sizes, "\n")

balance = pd.crosstab(model_data["dosage_category"], model_data["reason_category"])
balance_pct = pd.crosstab(model_data["dosage_category"], model_data["reason_category"], normalize="index")
print("Counts:\n", balance, "\n")
print("Row-normalized (fraction within each dosage_category):\n", balance_pct.round(4), "\n")

# ---- 3: confounding check against primary_category ----
print("=== 3: dosage_category x primary_category_grouped crosstab ===")
cross_counts = pd.crosstab(model_data["dosage_category"], model_data["primary_category_grouped"])
print("Counts:\n", cross_counts, "\n")
cross_pct = pd.crosstab(model_data["dosage_category"], model_data["primary_category_grouped"], normalize="index")
print("Row-normalized (where does each dosage_category's mass sit across categories):\n", cross_pct.round(3), "\n")

print("=== 3b: manufacturer_count by dosage_category ===")
print(model_data.groupby("dosage_category")["manufacturer_count"].describe(), "\n")

# ---- 4: overall frequency vs supply-side-rate skew ----
print("=== 4: overall frequency vs supply-side rate ===")
overall_freq = (sizes / sizes.sum()).round(4)
overall_supply_rate = model_data["is_supply_side"].mean()
print("Overall frequency of each dosage_category (share of all 830 rows):\n", overall_freq, "\n")
print(f"Overall supply-side rate across ALL rows (baseline): {overall_supply_rate:.4f}\n")
supply_rate_by_dose = model_data.groupby("dosage_category")["is_supply_side"].mean()
print("Supply-side rate BY dosage_category (compare to baseline above):\n", supply_rate_by_dose.round(4))
