"""Diagnostic only -- does not replace or modify the PRIMARY result in
results.json. Decomposes the AUC change (0.6271 -> 0.7128) from the NDC
re-pull into two independent effects:

  (a) 57 ORIGINAL events, NEW manufacturer_count values
      -> isolates the effect of corrected counts among already-included
         events (holding the event set, and therefore the category
         threshold/columns, fixed at the old 57-event state).
  (b) 60 NEW events, OLD manufacturer_count values where available
      (the 3 new events have no old value at all -- they weren't in the
      old model_data -- so they use their new value, the only one that
      exists)
      -> isolates the effect of the 3 new events (and whatever category
         threshold crossing they cause, i.e. the Anti-Infective column)
         holding counts at old values wherever that's meaningful.

Combined with the two results already in results.json --
  OLD counts / 57 events = 0.6271 (the pre-re-pull primary result)
  NEW counts / 60 events = 0.7128 (the current primary result)
-- this is a full 2x2 decomposition.

Run from analysis/diagnostics/, with the venv active:
    python3 decompose_auc_change.py
"""
import ast
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from normalize_ndc import normalize_ndc, expand_ndc_list

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

N_FOLDS = 5
SEEDS = list(range(10))
N_PERMUTATIONS = 1000

shortages = pd.read_csv("../../backend/data/shortages.csv")
recalls = pd.read_csv("../../backend/data/recalls.csv")
ndc_new = pd.read_csv("../../backend/data/ndc_directory.csv")
ndc_old = pd.read_csv("../../backend/data/ndc_directory_2026-08-20_incomplete.csv")

shortages["ndc_list"] = shortages["openfda.product_ndc"].apply(expand_ndc_list)
recalls["ndc"] = recalls["openfda.product_ndc"].apply(normalize_ndc)
ndc_new["ndc"] = ndc_new["product_ndc"].apply(normalize_ndc)
ndc_old["ndc"] = ndc_old["product_ndc"].apply(normalize_ndc)

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
recall_counts = recalls.groupby("ndc").size().rename("recall_count")
shortages_exploded_base = shortages.explode("ndc_list").rename(columns={"ndc_list": "ndc"})


def build_model_data(ndc_df, manufacturer_counts):
    ndc_lookup = ndc_df[["ndc", "generic_name"]].drop_duplicates(subset="ndc").rename(
        columns={"generic_name": "ndc_generic_name"})
    se = shortages_exploded_base.merge(ndc_lookup, on="ndc", how="left")
    features = se.merge(manufacturer_counts, left_on="ndc_generic_name", right_on="generic_name", how="left")
    features = features.merge(recall_counts, on="ndc", how="left")
    features["recall_count"] = features["recall_count"].fillna(0)
    md = features[features["reason_category"].isin(["Supply-side", "Demand-side"])].copy()
    md["is_supply_side"] = (md["reason_category"] == "Supply-side").astype(int)
    md = md.dropna(subset=["manufacturer_count", "recall_count", "primary_category", "dosage_category"])
    md["event_id"] = md["generic_name"] + " | " + md["initial_posting_date"].astype(str)
    return md.reset_index().rename(columns={"index": "orig_idx"})


manufacturer_counts_new = ndc_new.groupby("generic_name")["labeler_name"].nunique().rename("manufacturer_count")
manufacturer_counts_old = ndc_old.groupby("generic_name")["labeler_name"].nunique().rename("manufacturer_count")

md_old = build_model_data(ndc_old, manufacturer_counts_old)
md_new = build_model_data(ndc_new, manufacturer_counts_new)

old_event_ids = set(md_old["event_id"])
new_event_ids = set(md_new["event_id"]) - old_event_ids

print(f"OLD: {len(md_old)} rows, {md_old['event_id'].nunique()} events")
print(f"NEW: {len(md_new)} rows, {md_new['event_id'].nunique()} events")
print(f"New events (not in old): {sorted(new_event_ids)}")


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


def apply_category_grouping(df, threshold, events_per_cat):
    rare = events_per_cat[events_per_cat < threshold].index
    return df["primary_category"].apply(lambda x: "Other/Rare" if x in rare else x)


def build_design_matrix(df, category_col):
    cat_dummies = pd.get_dummies(df[category_col], prefix="cat", drop_first=True)
    dose_dummies = pd.get_dummies(df["dosage_category"], prefix="dose", drop_first=True)
    return pd.concat([df[["manufacturer_count", "recall_count"]], cat_dummies, dose_dummies], axis=1)


def run_event_level_cv(X, y, seeds=SEEDS):
    fold_results, degenerate = [], []
    for seed in seeds:
        skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            if y_train.nunique() < 2 or y_test.nunique() < 2:
                degenerate.append({"seed": seed, "fold": fold_idx})
                continue
            model = LogisticRegression(max_iter=1000)
            model.fit(X.iloc[train_idx], y_train)
            proba = model.predict_proba(X.iloc[test_idx])[:, 1]
            fold_results.append({"seed": seed, "fold": fold_idx, "auc": roc_auc_score(y_test, proba)})
    return fold_results, degenerate


def run_variant(model_data, label):
    event_label_df = compute_event_labels(model_data)
    model_data = model_data.merge(event_label_df, on="event_id", how="left")
    events_per_category = model_data.drop_duplicates("event_id")["primary_category"].value_counts()
    model_data["primary_category_grouped"] = apply_category_grouping(model_data, 5, events_per_category)

    event_level = model_data.groupby("event_id").agg(
        manufacturer_count=("manufacturer_count", "median"),
        recall_count=("recall_count", "median"),
        primary_category=("primary_category_grouped", "first"),
        dosage_category=("dosage_category", "first"),
        event_label=("event_label", "first"),
    ).reset_index()

    X = build_design_matrix(event_level, "primary_category")
    y = event_level["event_label"]

    fold_results, degenerate = run_event_level_cv(X, y)
    aucs = np.array([r["auc"] for r in fold_results])
    observed_auc = aucs.mean()

    t0 = time.time()
    null_aucs = np.empty(N_PERMUTATIONS)
    for i in range(N_PERMUTATIONS):
        y_shuffled = y.sample(frac=1, random_state=i).reset_index(drop=True)
        y_shuffled.index = y.index
        perm_results, _ = run_event_level_cv(X, y_shuffled)
        null_aucs[i] = np.mean([r["auc"] for r in perm_results])
    permutation_p = (np.sum(null_aucs >= observed_auc) + 1) / (N_PERMUTATIONS + 1)
    elapsed = time.time() - t0

    print()
    print(f"=== {label} ===")
    print(f"n_events={len(event_level)}  columns={list(X.columns)}")
    print(f"AUC mean={aucs.mean():.4f} std={aucs.std():.4f}  "
          f"({len(degenerate)} degenerate folds skipped, elapsed {elapsed:.1f}s)")
    print(f"Permutation p-value: {permutation_p:.4f}")

    anti_infective_coef = None
    anti_infective_events = None
    if "cat_Anti-Infective" in X.columns:
        model_fit = LogisticRegression(max_iter=1000).fit(X, y)
        anti_infective_coef = dict(zip(model_fit.feature_names_in_, model_fit.coef_[0])).get("cat_Anti-Infective")
        ai_events = event_level[event_level["primary_category"] == "Anti-Infective"]
        anti_infective_events = {
            "n_events": len(ai_events),
            "supply_side": int((ai_events["event_label"] == 1).sum()),
            "demand_side": int((ai_events["event_label"] == 0).sum()),
            "event_ids": ai_events["event_id"].tolist(),
        }
        print(f"cat_Anti-Infective coefficient: {anti_infective_coef:.4f}")
        print(f"Anti-Infective events: {anti_infective_events}")

    return {
        "n_events": len(event_level), "auc_mean": float(aucs.mean()), "auc_std": float(aucs.std()),
        "permutation_p_value": float(permutation_p),
        "anti_infective_coefficient": float(anti_infective_coef) if anti_infective_coef is not None else None,
        "anti_infective_events": anti_infective_events,
    }


# --- (a) 57 original events, NEW manufacturer_count values ---
md_a = md_new[md_new["event_id"].isin(old_event_ids)].copy()
result_a = run_variant(md_a, "(a) 57 ORIGINAL events, NEW manufacturer_count")

# --- (b) 60 events, OLD manufacturer_count where available (new events keep their only value) ---
old_by_idx = md_old.set_index("orig_idx")["manufacturer_count"]
md_b = md_new.copy()
md_b["manufacturer_count"] = md_b["orig_idx"].map(old_by_idx).fillna(md_b["manufacturer_count"])
result_b = run_variant(md_b, "(b) 60 events (incl. 3 new), OLD manufacturer_count where available")

print()
print("=== Full 2x2 decomposition ===")
print(f"OLD counts / 57 events (baseline, from results.json): AUC=0.6271, permutation p=0.0939")
print(f"NEW counts / 57 events (a):                           AUC={result_a['auc_mean']:.4f}, permutation p={result_a['permutation_p_value']:.4f}")
print(f"OLD counts / 60 events (b):                           AUC={result_b['auc_mean']:.4f}, permutation p={result_b['permutation_p_value']:.4f}")
print(f"NEW counts / 60 events (actual primary):              AUC=0.7128, permutation p=0.0090")
