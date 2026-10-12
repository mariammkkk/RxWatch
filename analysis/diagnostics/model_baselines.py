# Baseline comparison table: majority-class dummy vs manufacturer_count vs full 4-feature model.
"""
Baseline comparison table for the deployed 4-feature model (AUC 0.8109,
std 0.0892): majority-class dummy, manufacturer_count-only, and
manufacturer_count+recall_count, all on the identical 830-row model_data
table and the same 5-fold CV setup as analysis.ipynb.

In-memory only -- does not touch backend/data/rxwatch_model*.pkl.

Run from analysis/diagnostics/, with the venv active: python3 model_baselines.py
"""
import ast
import sys
from pathlib import Path

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # for normalize_ndc
from normalize_ndc import normalize_ndc, expand_ndc_list

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc = pd.read_csv("../../backend/data/ndc_directory.csv")

# ---- feature engineering, identical to analysis.ipynb (verified in the
# prior fix-impact check to reproduce the committed 830-row table exactly) ----

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

y = model_data["is_supply_side"]
print(f"model_data: {len(model_data)} rows")

class_counts = y.value_counts()
majority_label = "Supply-side" if class_counts.idxmax() == 1 else "Demand-side"
print(f"Class counts -- Supply-side: {class_counts.get(1, 0)}, Demand-side: {class_counts.get(0, 0)} "
      f"-> majority class = {majority_label}")
print()

results = []


def evaluate(name, X, estimator, needs_proba_check=False):
    auc_scores = cross_val_score(estimator, X, y, cv=5, scoring="roc_auc")
    acc_scores = cross_val_score(estimator, X, y, cv=5, scoring="accuracy")
    results.append((name, X.shape[1], auc_scores.mean(), auc_scores.std(), acc_scores.mean()))
    print(f"{name}: mean AUC={auc_scores.mean():.4f}  std={auc_scores.std():.4f}  "
          f"mean accuracy={acc_scores.mean():.4f}")
    print(f"  fold AUCs: {auc_scores}")


# 1. majority-class dummy baseline
X_dummy = model_data[["manufacturer_count"]]  # unused by the dummy, just needs a matching row count
evaluate("Majority-class dummy", X_dummy, DummyClassifier(strategy="most_frequent"))

# 2. manufacturer_count only
X_mfr = model_data[["manufacturer_count"]]
evaluate("manufacturer_count only", X_mfr, LogisticRegression(max_iter=1000))

# 3. manufacturer_count + recall_count
X_mfr_recall = model_data[["manufacturer_count", "recall_count"]]
evaluate("manufacturer_count + recall_count", X_mfr_recall, LogisticRegression(max_iter=1000))

# 4. full 4-feature model (for the table; already confirmed == deployed baseline)
X_full = pd.concat([model_data[["manufacturer_count", "recall_count"]], category_dummies, dosage_dummies], axis=1)
evaluate("Full 4-feature model", X_full, LogisticRegression(max_iter=1000))

print()
print("=== Comparison table ===")
print(f"{'Model':<38s} {'#features':>9s} {'Mean AUC':>9s} {'Std':>7s} {'Mean Acc':>9s}")
for name, n_features, auc_mean, auc_std, acc_mean in results:
    print(f"{name:<38s} {n_features:>9d} {auc_mean:>9.4f} {auc_std:>7.4f} {acc_mean:>9.4f}")
