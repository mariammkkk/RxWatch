"""Pre-declared diagnostic only -- does not replace or modify PRIMARY.

Two of the three new events from the NDC re-pull are both rifampin
(Rifampin Capsule | 12/22/2021, Rifampin Injection | 02/17/2021), both
Anti-Infective and supply-side, and may share a root cause (e.g. one
manufacturing problem producing two separate FDA shortage postings for
the same drug in different dosage forms). If so, treating them as two
independent events in the primary StratifiedKFold (which is NOT grouped --
every event-level row is already "its own event", so ordinary folds can
split two same-ingredient events across train/test) could overstate how
much independent evidence the primary AUC rests on.

This reruns the PRIMARY event-level pipeline (same 60 events, same
<5-event category threshold, same design matrix) with StratifiedGroupKFold
grouped by normalized active ingredient (reusing validation.py's own
normalize_active_ingredient -- strips dosage-form and salt/hydrate words)
instead of by event_id, so every event sharing an ingredient always lands
in the same fold. Same 5 folds x 10 seeds, same 1000-permutation test.

Run from analysis/diagnostics/, with the venv active:
    python3 grouped_by_ingredient_cv.py
"""
import ast
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from normalize_ndc import normalize_ndc, expand_ndc_list

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold

RESULTS_PATH = Path(__file__).resolve().parent.parent / "results.json"
N_FOLDS = 5
SEEDS = list(range(10))
N_PERMUTATIONS = 1000

# ===========================================================================
# rebuild the exact PRIMARY event_level table (60 events, new counts).
# ===========================================================================

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

# --- normalized active ingredient (identical to validation.py's merge-check) ---

_DOSAGE_FORM_WORDS = (
    "tablet capsule injection solution suspension aerosol powder suppository "
    "cream gel ointment lotion spray kit tincture liquid patch elixir syrup "
    "drops emulsion foam paste concentrate irrigant film inhalation nasal "
    "ophthalmic oral topical rectal vaginal extended delayed release chewable "
    "metered transdermal implant pellet enema douche swab sponge strip wafer "
    "troche lozenge for"
).split()
_SALT_HYDRATE_WORDS = (
    "hydrochloride sulfate sodium potassium acetate phosphate besylate maleate "
    "mesylate tartrate citrate succinate bitartrate dimesylate hydrobromide hbr "
    "calcium magnesium bicarbonate chloride nitrate lactate gluconate fumarate "
    "oxalate carbonate benzoate besilate edisylate napsylate pamoate stearate "
    "valerate propionate aspartate saccharate monohydrate anhydrous dihydrate "
    "trihydrate hemihydrate hydrate base anhydrous"
).split()
_STRIP_WORDS_RE = re.compile(
    r"\b(" + "|".join(_DOSAGE_FORM_WORDS + _SALT_HYDRATE_WORDS) + r")\b", re.IGNORECASE)


def normalize_active_ingredient(generic_name: str) -> str:
    name = _STRIP_WORDS_RE.sub(" ", str(generic_name))
    name = re.sub(r"[,;]", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


model_data["active_ingredient_norm"] = model_data["generic_name"].apply(normalize_active_ingredient)


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
    active_ingredient_norm=("active_ingredient_norm", "first"),
).reset_index()

print(f"PRIMARY event_level: {len(event_level)} events")

# every ingredient with >=2 events
ingredient_counts = event_level["active_ingredient_norm"].value_counts()
multi_ingredient = ingredient_counts[ingredient_counts >= 2]
print()
print(f"=== Ingredients with 2+ events ({len(multi_ingredient)}) ===")
for ing, n in multi_ingredient.items():
    events_for_ing = event_level.loc[event_level["active_ingredient_norm"] == ing, "event_id"].tolist()
    print(f"  {ing!r}: {n} events -- {events_for_ing}")

cat_dummies = pd.get_dummies(event_level["primary_category"], prefix="cat", drop_first=True)
dose_dummies = pd.get_dummies(event_level["dosage_category"], prefix="dose", drop_first=True)
X = pd.concat([event_level[["manufacturer_count", "recall_count"]], cat_dummies, dose_dummies], axis=1)
y = event_level["event_label"]
groups = event_level["active_ingredient_norm"]

print()
print(f"Design matrix columns: {list(X.columns)}")
print(f"Distinct ingredient groups: {groups.nunique()} (vs {len(event_level)} events -- "
      f"{len(event_level) - groups.nunique()} events share a group with at least one other event)")


def run_grouped_cv(X, y, groups, seeds=SEEDS):
    fold_results, degenerate = [], []
    for seed in seeds:
        skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
        for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y, groups)):
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            if y_train.nunique() < 2 or y_test.nunique() < 2:
                degenerate.append({"seed": seed, "fold": fold_idx})
                continue
            model = LogisticRegression(max_iter=1000)
            model.fit(X.iloc[train_idx], y_train)
            proba = model.predict_proba(X.iloc[test_idx])[:, 1]
            fold_results.append({"seed": seed, "fold": fold_idx, "auc": roc_auc_score(y_test, proba)})
    return fold_results, degenerate


fold_results, degenerate = run_grouped_cv(X, y, groups)
aucs = np.array([r["auc"] for r in fold_results])
observed_auc = aucs.mean()

print()
print("=== StratifiedGroupKFold by normalized active ingredient, 5 folds x 10 seeds ===")
print(f"Valid folds: {len(aucs)} (expected {N_FOLDS * len(SEEDS)}), "
      f"{len(degenerate)} degenerate folds skipped")
print(f"AUC mean={aucs.mean():.4f} std={aucs.std():.4f} min={aucs.min():.4f} max={aucs.max():.4f}")

t0 = time.time()
null_aucs = np.empty(N_PERMUTATIONS)
for i in range(N_PERMUTATIONS):
    y_shuffled = y.sample(frac=1, random_state=i).reset_index(drop=True)
    y_shuffled.index = y.index
    perm_results, _ = run_grouped_cv(X, y_shuffled, groups)
    null_aucs[i] = np.mean([r["auc"] for r in perm_results])
elapsed = time.time() - t0
permutation_p = (np.sum(null_aucs >= observed_auc) + 1) / (N_PERMUTATIONS + 1)

print(f"Permutation test elapsed: {elapsed:.1f}s")
print(f"Observed AUC: {observed_auc:.4f}  Null mean: {null_aucs.mean():.4f}  "
      f"Permutation p-value: {permutation_p:.4f}")

flag_needed = observed_auc < 0.65 or permutation_p > 0.05
print()
print(f"Flag (AUC < 0.65 or p > 0.05): {flag_needed}")

diagnostic = {
    "description": "PRE-DECLARED diagnostic (does not replace primary): PRIMARY event-level pipeline "
                    "(60 events, complete-NDC-file manufacturer_count, <5-event category threshold) "
                    "rerun with StratifiedGroupKFold grouped by normalized active ingredient instead of "
                    "by event_id, so events sharing an ingredient (e.g. the two rifampin events) always "
                    "land in the same fold.",
    "n_events": int(len(event_level)),
    "n_distinct_ingredient_groups": int(groups.nunique()),
    "ingredients_with_2_or_more_events": [
        {"ingredient": ing, "n_events": int(n),
         "event_ids": event_level.loc[event_level["active_ingredient_norm"] == ing, "event_id"].tolist()}
        for ing, n in multi_ingredient.items()
    ],
    "auc_mean": float(aucs.mean()), "auc_std": float(aucs.std()),
    "auc_min": float(aucs.min()), "auc_max": float(aucs.max()),
    "n_folds_total": len(aucs), "n_degenerate_folds_skipped": len(degenerate),
    "permutation_test": {
        "n_permutations": N_PERMUTATIONS,
        "observed_auc": float(observed_auc),
        "null_mean": float(null_aucs.mean()),
        "null_std": float(null_aucs.std()),
        "permutation_p_value": float(permutation_p),
    },
    "flagged_auc_below_065_or_p_above_005": bool(flag_needed),
}

with open(RESULTS_PATH) as f:
    results = json.load(f)
results["diagnostic_grouped_by_ingredient"] = diagnostic
with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nSaved diagnostic to {RESULTS_PATH} under 'diagnostic_grouped_by_ingredient'")
