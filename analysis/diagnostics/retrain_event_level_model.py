"""Retrains and saves the production event-level model (backend/data/
rxwatch_model.pkl + rxwatch_model_columns.pkl) on the PRIMARY event-level
recipe, using whatever ndc_directory.csv is currently in backend/data/.

Reproduces validation.py's PRIMARY feature-engineering exactly (same event
definition, same <5-event category threshold, same median aggregation to
one row per event), then fits LogisticRegression(max_iter=1000) on the
full (X_event, y_event) and saves it -- the same recipe the currently
deployed model was trained with (confirmed by matching its saved
coefficients against validation.py's sensitivity-check model_with object).

Run from analysis/diagnostics/, with the venv active:
    python3 retrain_event_level_model.py
"""
import ast
import sys
from pathlib import Path

import joblib
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from normalize_ndc import normalize_ndc, expand_ndc_list

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc = pd.read_csv("../../backend/data/ndc_directory.csv")

shortages["ndc_list"] = shortages["openfda.product_ndc"].apply(expand_ndc_list)
recalls["ndc"] = recalls["openfda.product_ndc"].apply(normalize_ndc)
ndc["ndc"] = ndc["product_ndc"].apply(normalize_ndc)

ndc_lookup = ndc[["ndc", "generic_name"]].drop_duplicates(subset="ndc").rename(
    columns={"generic_name": "ndc_generic_name"})
manufacturer_counts = ndc.groupby("generic_name")["labeler_name"].nunique().rename("manufacturer_count")
recall_counts = recalls.groupby("ndc").size().rename("recall_count")

supply_side = [
    "Discontinuation of the manufacture of the drug", "Shortage of an active ingredient",
    "Delay in shipping of the drug", "Requirements related to complying with good manufacturing practices",
    "Shortage of an inactive ingredient component", "Regulatory delay",
]
shortages["reason_category"] = shortages["shortage_reason"].apply(
    lambda x: "Supply-side" if x in supply_side
    else ("Demand-side" if x == "Demand increase for the drug"
    else ("Other" if pd.notna(x) else None)))


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
features = shortages_exploded.merge(manufacturer_counts, left_on="ndc_generic_name", right_on="generic_name", how="left")
features = features.merge(recall_counts, on="ndc", how="left")
features["recall_count"] = features["recall_count"].fillna(0)

model_data = features[features["reason_category"].isin(["Supply-side", "Demand-side"])].copy()
model_data["is_supply_side"] = (model_data["reason_category"] == "Supply-side").astype(int)
model_data = model_data.dropna(subset=["manufacturer_count", "recall_count", "primary_category", "dosage_category"])
model_data["event_id"] = model_data["generic_name"] + " | " + model_data["initial_posting_date"].astype(str)


def compute_event_labels(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for event_id, g in df.groupby("event_id"):
        companies_supply = g.loc[g["is_supply_side"] == 1, "company_name"].nunique()
        companies_demand = g.loc[g["is_supply_side"] == 0, "company_name"].nunique()
        if companies_supply > companies_demand:
            label = 1
        elif companies_demand > companies_supply:
            label = 0
        else:
            rows_supply = int((g["is_supply_side"] == 1).sum())
            rows_demand = int((g["is_supply_side"] == 0).sum())
            label = 1 if rows_supply >= rows_demand else 0
        rows.append({"event_id": event_id, "event_label": label})
    return pd.DataFrame(rows)


event_label_df = compute_event_labels(model_data)
model_data = model_data.merge(event_label_df, on="event_id", how="left")

events_per_category = model_data.drop_duplicates("event_id")["primary_category"].value_counts()
rare = events_per_category[events_per_category < 5].index
model_data["primary_category_grouped"] = model_data["primary_category"].apply(
    lambda x: "Other/Rare" if x in rare else x)

event_level = model_data.groupby("event_id").agg(
    manufacturer_count=("manufacturer_count", "median"),
    recall_count=("recall_count", "median"),
    primary_category=("primary_category_grouped", "first"),
    dosage_category=("dosage_category", "first"),
    event_label=("event_label", "first"),
).reset_index()

cat_dummies = pd.get_dummies(event_level["primary_category"], prefix="cat", drop_first=True)
dose_dummies = pd.get_dummies(event_level["dosage_category"], prefix="dose", drop_first=True)
X_event = pd.concat([event_level[["manufacturer_count", "recall_count"]], cat_dummies, dose_dummies], axis=1)
y_event = event_level["event_label"]

print(f"Retraining on {len(event_level)} events, {X_event.shape[1]} features: {list(X_event.columns)}")

model = LogisticRegression(max_iter=1000)
model.fit(X_event, y_event)

print()
print("New coefficients:")
for name, coef in zip(model.feature_names_in_, model.coef_[0]):
    print(f"  {name}: {coef:.4f}")
print(f"  intercept: {model.intercept_[0]:.4f}")

joblib.dump(model, "../../backend/data/rxwatch_model.pkl")
joblib.dump(list(X_event.columns), "../../backend/data/rxwatch_model_columns.pkl")
print()
print("Saved ../../backend/data/rxwatch_model.pkl and rxwatch_model_columns.pkl")
