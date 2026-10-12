# Rebuilds the training feature table and retrains the model to check if the drug_class_lookup fix changes training.
"""
Rebuilds the training feature table exactly as analysis.ipynb does, and
retrains the 4-feature logistic regression model, to check whether the
backend/main.py drug_class_lookup name-matching fix (handling "/" as a
separator, stripping parenthetical NDC qualifiers) changes anything about
model training.

Run from analysis/diagnostics/, with the venv active: python3 rebuild_features_and_retrain.py
"""
import ast
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for normalize_ndc
from normalize_ndc import normalize_ndc, expand_ndc_list

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc = pd.read_csv("../../backend/data/ndc_directory.csv")

# ---------------------------------------------------------------------------
# feature engineering -- identical to analysis.ipynb's final pipeline.
# NOTE: this join is entirely NDC-*code*-based (product_ndc), and
# primary_category / dosage_category come directly from each shortages.csv
# row's own therapeutic_category / dosage_form columns. None of this touches
# backend/main.py's drug_class_lookup (generic_name string matching), which
# only exists to serve *inference-time* lookups for drugs outside this
# training set. So rebuilding this table with "the post-fix matching logic"
# should be a no-op -- confirming that empirically below.
# ---------------------------------------------------------------------------

shortages["ndc_list"] = shortages["openfda.product_ndc"].apply(expand_ndc_list)
shortages_exploded = shortages.explode("ndc_list").rename(columns={"ndc_list": "ndc"})

recalls["ndc"] = recalls["openfda.product_ndc"].apply(normalize_ndc)
ndc["ndc"] = ndc["product_ndc"].apply(normalize_ndc)

ndc_lookup = ndc[["ndc", "generic_name"]].drop_duplicates(subset="ndc").rename(
    columns={"generic_name": "ndc_generic_name"}
)
shortages_exploded = shortages_exploded.merge(ndc_lookup, on="ndc", how="left")

manufacturer_counts = ndc.groupby("generic_name")["labeler_name"].nunique().rename("manufacturer_count")
recall_counts = recalls.groupby("ndc").size().rename("recall_count")

features = shortages_exploded.merge(
    manufacturer_counts, left_on="ndc_generic_name", right_on="generic_name", how="left"
)
features = features.merge(recall_counts, on="ndc", how="left")
features["recall_count"] = features["recall_count"].fillna(0)

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

# re-explode/re-merge now that reason_category/primary_category/dosage_category exist
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

category_dummies = pd.get_dummies(model_data["primary_category_grouped"], prefix="cat", drop_first=True)
dosage_dummies = pd.get_dummies(model_data["dosage_category"], prefix="dose", drop_first=True)

X = pd.concat([model_data[["manufacturer_count", "recall_count"]], category_dummies, dosage_dummies], axis=1)
y = model_data["is_supply_side"]

print(f"Rebuilt feature table: {len(model_data)} rows, {X.shape[1]} features: {list(X.columns)}")

cv_scores = cross_val_score(LogisticRegression(max_iter=1000), X, y, cv=5, scoring="roc_auc")
print("Cross-validated AUC scores:", cv_scores)
print(f"Mean AUC: {cv_scores.mean():.4f}  Std: {cv_scores.std():.4f}")

# ---- compare against the committed baseline model/columns/feature table ----
baseline_model = joblib.load("../../backend/data/rxwatch_model.pkl")
baseline_columns = joblib.load("../../backend/data/rxwatch_model_columns.pkl")
baseline_features = pd.read_csv("../../backend/data/rxwatch_features_clean.csv")

print()
print("Baseline (committed) feature table row count:", len(baseline_features))
print("Baseline model columns:", baseline_columns)
print("Rebuilt columns match baseline columns:", list(X.columns) == baseline_columns)
print("Rebuilt row count matches baseline:", len(model_data) == len(baseline_features))

model_final = LogisticRegression(max_iter=1000)
model_final.fit(X, y)
joblib.dump(model_final, "../../backend/data/rxwatch_model_v2.pkl")
joblib.dump(list(X.columns), "../../backend/data/rxwatch_model_v2_columns.pkl")
print()
print("Saved ../backend/data/rxwatch_model_v2.pkl and rxwatch_model_v2_columns.pkl")

print()
print("v2 coefficients:")
for name, coef in zip(model_final.feature_names_in_, model_final.coef_[0]):
    print(f"  {name}: {coef:.4f}")
print()
print("baseline coefficients:")
for name, coef in zip(baseline_model.feature_names_in_, baseline_model.coef_[0]):
    print(f"  {name}: {coef:.4f}")
