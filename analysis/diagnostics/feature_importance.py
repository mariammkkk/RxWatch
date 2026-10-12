# Ablation + odds-ratio breakdown of which features drive the deployed model's predictions.
"""
Part A: ablation study splitting credit between primary_category and
dosage_category (extends model_baselines.py's comparison table).

Part B: coefficients/odds-ratios from the actual deployed model
(backend/data/rxwatch_model.pkl) -- not retrained, loaded as-is.

In-memory only -- does not touch backend/data/rxwatch_model*.pkl.

Run from analysis/diagnostics/, with the venv active: python3 feature_importance.py
"""
import ast
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for normalize_ndc
from normalize_ndc import normalize_ndc, expand_ndc_list

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc = pd.read_csv("../../backend/data/ndc_directory.csv")

# ---- feature engineering, identical to analysis.ipynb / model_baselines.py ----

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

category_dummies = pd.get_dummies(model_data["primary_category_grouped"], prefix="cat", drop_first=True)
dosage_dummies = pd.get_dummies(model_data["dosage_category"], prefix="dose", drop_first=True)

# confirm which level drop_first actually dropped for each group
all_cat_levels = sorted(model_data["primary_category_grouped"].unique())
all_dose_levels = sorted(model_data["dosage_category"].unique())
dropped_cat = [c for c in all_cat_levels if f"cat_{c}" not in category_dummies.columns][0]
dropped_dose = [d for d in all_dose_levels if f"dose_{d}" not in dosage_dummies.columns][0]

y = model_data["is_supply_side"]
print(f"model_data: {len(model_data)} rows")
print(f"category levels: {all_cat_levels}  -> dropped/reference = {dropped_cat!r}")
print(f"dosage levels:   {all_dose_levels}  -> dropped/reference = {dropped_dose!r}")
print()

# ===========================================================================
# PART A -- ablation table
# ===========================================================================

results = []


def evaluate(name, X, estimator):
    auc_scores = cross_val_score(estimator, X, y, cv=5, scoring="roc_auc")
    acc_scores = cross_val_score(estimator, X, y, cv=5, scoring="accuracy")
    results.append((name, X.shape[1], auc_scores.mean(), auc_scores.std(), acc_scores.mean()))


evaluate("Majority-class dummy", model_data[["manufacturer_count"]], DummyClassifier(strategy="most_frequent"))
evaluate("manufacturer_count only", model_data[["manufacturer_count"]], LogisticRegression(max_iter=1000))
evaluate("manufacturer_count + recall_count", model_data[["manufacturer_count", "recall_count"]],
         LogisticRegression(max_iter=1000))
evaluate("primary_category only", category_dummies, LogisticRegression(max_iter=1000))
evaluate("dosage_category only", dosage_dummies, LogisticRegression(max_iter=1000))
evaluate("Full 4-feature model", pd.concat(
    [model_data[["manufacturer_count", "recall_count"]], category_dummies, dosage_dummies], axis=1
), LogisticRegression(max_iter=1000))

print("=== PART A: ablation comparison table ===")
print(f"{'Model':<38s} {'#features':>9s} {'Mean AUC':>9s} {'Std':>7s} {'Mean Acc':>9s}")
for name, n_features, auc_mean, auc_std, acc_mean in results:
    print(f"{name:<38s} {n_features:>9d} {auc_mean:>9.4f} {auc_std:>7.4f} {acc_mean:>9.4f}")

# ===========================================================================
# PART B -- coefficients / odds ratios from the ACTUAL deployed model
# ===========================================================================

print()
print("=== PART B: deployed model coefficients & odds ratios ===")
deployed_model = joblib.load("../../backend/data/rxwatch_model.pkl")
deployed_columns = joblib.load("../../backend/data/rxwatch_model_columns.pkl")

rows = []
for name, coef in zip(deployed_model.feature_names_in_, deployed_model.coef_[0]):
    odds_ratio = np.exp(coef)
    rows.append((name, coef, odds_ratio))

rows.sort(key=lambda r: abs(r[1]), reverse=True)

print(f"{'Feature':<28s} {'coef':>8s} {'odds ratio':>11s}  direction")
for name, coef, odds_ratio in rows:
    direction = "supply-side" if coef > 0 else "demand-side"
    print(f"{name:<28s} {coef:>8.4f} {odds_ratio:>11.4f}  -> {direction}")
