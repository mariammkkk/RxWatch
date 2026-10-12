# Phase 1 validation: event-grouped CV, event-level model, and event-level Mann-Whitney,
# to replace the row-level pipeline's leaky AUC/p-value with honest, non-duplicated estimates.
#
# Does not modify analysis.ipynb. Writes analysis/results.json and
# analysis/figures/manufacturer_count_by_cause.png.
#
# Run from analysis/, with the venv active: python3 validation.py
import ast
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_ndc import normalize_ndc, expand_ndc_list

RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
FIGURES_DIR = Path(__file__).resolve().parent / "figures"

# ===========================================================================
# feature engineering -- identical to analysis.ipynb's final pipeline
# (verified in an earlier diagnostic pass to reproduce the committed
# 830-row table and AUC 0.8109 / std 0.0892 exactly).
# ===========================================================================

shortages = pd.read_csv("../backend/data/shortages.csv")
recalls = pd.read_csv("../backend/data/recalls.csv")
ndc = pd.read_csv("../backend/data/ndc_directory.csv")

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

print(f"model_data: {len(model_data)} rows (matches committed baseline: {len(model_data) == 830})")

# ===========================================================================
# event ID: generic_name (raw) + initial_posting_date -- approved definition.
# ===========================================================================

model_data["event_id"] = model_data["generic_name"] + " | " + model_data["initial_posting_date"].astype(str)
n_events_approved = model_data["event_id"].nunique()
print(f"Events under approved definition (generic_name + initial_posting_date): {n_events_approved}")

# ---------------------------------------------------------------------------
# merge-check: would a normalized-active-ingredient + date key merge any of
# these 57 events further? Strip dosage-form words AND salt/hydrate words.
# ---------------------------------------------------------------------------

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
    r"\b(" + "|".join(_DOSAGE_FORM_WORDS + _SALT_HYDRATE_WORDS) + r")\b", re.IGNORECASE
)


def normalize_active_ingredient(generic_name: str) -> str:
    name = _STRIP_WORDS_RE.sub(" ", str(generic_name))
    name = re.sub(r"[,;]", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


model_data["active_ingredient_norm"] = model_data["generic_name"].apply(normalize_active_ingredient)
model_data["event_id_ingredient"] = model_data["active_ingredient_norm"] + " | " + model_data["initial_posting_date"].astype(str)

merge_map = model_data.groupby("event_id_ingredient")["event_id"].nunique()
merged_groups = merge_map[merge_map > 1]
n_events_merged_total = len(merge_map)
n_original_events_absorbed_into_merges = model_data[model_data["event_id_ingredient"].isin(merged_groups.index)]["event_id"].nunique()
n_events_that_would_merge = n_events_approved - n_events_merged_total if n_events_merged_total < n_events_approved else 0
# simpler, direct count: how many of the 57 original events are NOT their own
# singleton group under the ingredient-normalized key?
events_absorbed = n_original_events_absorbed_into_merges - len(merged_groups)  # extra events beyond 1-per-group

print()
print(f"=== Event-definition merge-check ===")
print(f"Events under approved key: {n_events_approved}")
print(f"Events under normalized-ingredient+date key: {n_events_merged_total}")
print(f"Number of approved events that would get merged together: {events_absorbed}")
if len(merged_groups) > 0:
    print("Merged groups (ingredient_key -> original event_ids):")
    for key in merged_groups.index:
        originals = model_data.loc[model_data["event_id_ingredient"] == key, "event_id"].unique()
        print(f"  {key!r}: {list(originals)}")
else:
    print("No merges found.")

# ===========================================================================
# event-level LABEL: majority vote by distinct companies (company_name
# exists in shortages.csv with 0 nulls in model_data, so no row-count
# fallback is needed). Exact ties are recorded separately, not broken
# silently (tiebreak used only to pick a deterministic value for that event
# in analyses that need one, e.g. the event-level model's y).
# ===========================================================================

def compute_event_labels(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    rows, ties = [], []
    for event_id, g in df.groupby("event_id"):
        companies_supply = g.loc[g["is_supply_side"] == 1, "company_name"].nunique()
        companies_demand = g.loc[g["is_supply_side"] == 0, "company_name"].nunique()
        is_mixed = g["is_supply_side"].nunique() > 1
        if companies_supply > companies_demand:
            label = 1
        elif companies_demand > companies_supply:
            label = 0
        else:
            rows_supply = int((g["is_supply_side"] == 1).sum())
            rows_demand = int((g["is_supply_side"] == 0).sum())
            label = 1 if rows_supply >= rows_demand else 0
            ties.append({
                "event_id": event_id, "companies_supply": int(companies_supply),
                "companies_demand": int(companies_demand),
                "tiebreak_used": "row_count", "tiebreak_label": label,
            })
        rows.append({
            "event_id": event_id, "event_label": label, "is_mixed_rowlevel": bool(is_mixed),
            "companies_supply": int(companies_supply), "companies_demand": int(companies_demand),
        })
    return pd.DataFrame(rows), ties


event_label_df, label_ties = compute_event_labels(model_data)
model_data = model_data.merge(event_label_df[["event_id", "event_label"]], on="event_id", how="left")

print()
print("=== Mixed-label resolution (majority vote by distinct companies) ===")
print(f"Events with row-level mixed is_supply_side: {event_label_df['is_mixed_rowlevel'].sum()} / {len(event_label_df)}")
print(f"Exact ties (equal distinct-company count on both sides): {len(label_ties)}")
for t in label_ties:
    print(f"  {t}")

# ===========================================================================
# event-level class balance, BEFORE any CV.
# ===========================================================================

event_class_counts = event_label_df["event_label"].value_counts()
print()
print("=== Event-level class balance (before any CV) ===")
print(f"Supply-side events: {event_class_counts.get(1, 0)} / {len(event_label_df)}")
print(f"Demand-side events: {event_class_counts.get(0, 0)} / {len(event_label_df)}")

# ===========================================================================
# rare-category consolidation using EVENT counts, not row counts.
# PRIMARY threshold <5 events (locked in before any AUC is computed, per
# instruction -- not to be changed based on results). <3 is a labeled
# sensitivity check only.
# ===========================================================================

events_per_category = model_data.drop_duplicates("event_id")["primary_category"].value_counts()
print()
print("=== Events per primary_category (for threshold selection) ===")
print(events_per_category)


def apply_category_grouping(df: pd.DataFrame, threshold: int, events_per_cat: pd.Series) -> pd.Series:
    rare = events_per_cat[events_per_cat < threshold].index
    return df["primary_category"].apply(lambda x: "Other/Rare" if x in rare else x)


model_data["primary_category_grouped_primary"] = apply_category_grouping(model_data, 5, events_per_category)
model_data["primary_category_grouped_sensitivity3"] = apply_category_grouping(model_data, 3, events_per_category)

merged_at_5 = sorted(events_per_category[events_per_category < 5].index.tolist())
merged_at_3 = sorted(events_per_category[events_per_category < 3].index.tolist())
print()
print(f"PRIMARY threshold <5 events -- merged into Other/Rare: {merged_at_5}")
print(f"SENSITIVITY threshold <3 events -- merged into Other/Rare: {merged_at_3}")

# ===========================================================================
# shared helpers
# ===========================================================================

from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold
from scipy import stats


def build_design_matrix(df: pd.DataFrame, category_col: str) -> pd.DataFrame:
    cat_dummies = pd.get_dummies(df[category_col], prefix="cat", drop_first=True)
    dose_dummies = pd.get_dummies(df["dosage_category"], prefix="dose", drop_first=True)
    return pd.concat([df[["manufacturer_count", "recall_count"]], cat_dummies, dose_dummies], axis=1)


X_row = build_design_matrix(model_data, "primary_category_grouped_primary")
y_row = model_data["is_supply_side"]
groups_row = model_data["event_id"]
rows_per_event = model_data["event_id"].map(model_data["event_id"].value_counts())
sample_weight_row = (1.0 / rows_per_event).values

print()
print(f"Row-level design matrix columns (PRIMARY, differs from original model's 8-category set): {list(X_row.columns)}")

# ===========================================================================
# STEP 3: row-level StratifiedGroupKFold, 5 folds, >=10 seeds. SECONDARY result.
# Also computed: sample_weight = 1/rows_in_event (fit + score), to check
# whether one huge event dominates the unweighted number.
# ===========================================================================

N_FOLDS = 5
SEEDS = list(range(10))

per_seed_fold_aucs = []       # unweighted
per_seed_fold_aucs_weighted = []
degenerate_fold_events = []

for seed in SEEDS:
    skf = StratifiedGroupKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)
    for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X_row, y_row, groups_row)):
        y_train, y_test = y_row.iloc[train_idx], y_row.iloc[test_idx]
        if y_train.nunique() < 2 or y_test.nunique() < 2:
            degenerate_fold_events.append({
                "seed": seed, "fold": fold_idx,
                "train_classes": sorted(y_train.unique().tolist()),
                "test_classes": sorted(y_test.unique().tolist()),
            })
            continue

        X_train, X_test = X_row.iloc[train_idx], X_row.iloc[test_idx]
        w_train, w_test = sample_weight_row[train_idx], sample_weight_row[test_idx]

        model = LogisticRegression(max_iter=1000)
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, proba)

        model_w = LogisticRegression(max_iter=1000)
        model_w.fit(X_train, y_train, sample_weight=w_train)
        proba_w = model_w.predict_proba(X_test)[:, 1]
        auc_w = roc_auc_score(y_test, proba_w, sample_weight=w_test)

        per_seed_fold_aucs.append({
            "seed": seed, "fold": fold_idx, "auc": auc,
            "n_train_events": groups_row.iloc[train_idx].nunique(),
            "n_test_events": groups_row.iloc[test_idx].nunique(),
            "test_class_balance": {"supply": int(y_test.sum()), "demand": int((1 - y_test).sum())},
        })
        per_seed_fold_aucs_weighted.append({"seed": seed, "fold": fold_idx, "auc": auc_w})

fold_aucs_arr = np.array([r["auc"] for r in per_seed_fold_aucs])
fold_aucs_weighted_arr = np.array([r["auc"] for r in per_seed_fold_aucs_weighted])

print()
print("=== STEP 3: row-level StratifiedGroupKFold (SECONDARY), 5 folds x 10 seeds ===")
print(f"Degenerate (single-class) folds skipped: {len(degenerate_fold_events)}")
for d in degenerate_fold_events:
    print(f"  {d}")
print(f"Total valid folds: {len(fold_aucs_arr)} (expected {N_FOLDS * len(SEEDS)})")
print(f"Unweighted: mean={fold_aucs_arr.mean():.4f} std={fold_aucs_arr.std():.4f} "
      f"min={fold_aucs_arr.min():.4f} max={fold_aucs_arr.max():.4f}")
print(f"Weighted (1/rows_in_event): mean={fold_aucs_weighted_arr.mean():.4f} std={fold_aucs_weighted_arr.std():.4f} "
      f"min={fold_aucs_weighted_arr.min():.4f} max={fold_aucs_weighted_arr.max():.4f}")

# per-seed mean (the "repeated-seed std" requested)
seed_means = [np.mean([r["auc"] for r in per_seed_fold_aucs if r["seed"] == s]) for s in SEEDS]
print(f"Per-seed mean AUC across the {len(SEEDS)} seeds: {[round(m,4) for m in seed_means]}")
print(f"Mean of per-seed means: {np.mean(seed_means):.4f}  Std across seeds: {np.std(seed_means):.4f}")

# ===========================================================================
# STEP 4: collapse to ONE row per event -- PRIMARY result.
#
# Aggregation choice: primary_category and dosage_category are constant
# within every event (0/57 vary) since they come straight from the
# shortages.csv row, not a package-level join -- take the first value.
# manufacturer_count and recall_count DO vary within an event (17/57 and
# 18/57 respectively), because one shortage notice's package_ndc list can
# span ndc_directory rows with slightly different generic_name strings,
# each pulling its own manufacturer_count/recall_count. Use the MEDIAN of
# each event's rows for both -- robust to the package-level spread without
# letting one extreme package dominate (e.g. Lidocaine HCl | 02/22/2012
# ranges from 5 to 90 manufacturers across its own package rows).
# event_label (majority vote by distinct companies, computed above) is the
# target.
# ===========================================================================

event_level = model_data.groupby("event_id").agg(
    manufacturer_count=("manufacturer_count", "median"),
    recall_count=("recall_count", "median"),
    primary_category=("primary_category", "first"),
    dosage_category=("dosage_category", "first"),
    event_label=("event_label", "first"),
    is_mixed_rowlevel=("event_id", lambda s: model_data.loc[s.index, "is_supply_side"].nunique() > 1),
).reset_index()

events_per_category_el = event_level["primary_category"].value_counts()
event_level["primary_category_grouped_primary"] = apply_category_grouping(event_level, 5, events_per_category_el)
event_level["primary_category_grouped_sensitivity3"] = apply_category_grouping(event_level, 3, events_per_category_el)

if not events_per_category_el.sort_index().equals(events_per_category.sort_index()):
    print("WARNING: event-level category counts differ from row-level groupby:")
    print(pd.DataFrame({"row_level": events_per_category, "event_level": events_per_category_el}))

X_event = build_design_matrix(event_level, "primary_category_grouped_primary")
y_event = event_level["event_label"]

print()
print(f"=== STEP 4: event-level model (PRIMARY), {len(event_level)} rows ===")
print(f"Event-level design matrix columns: {list(X_event.columns)}")


def run_event_level_cv(X: pd.DataFrame, y: pd.Series, n_folds: int = N_FOLDS, seeds=SEEDS):
    fold_results, degenerate = [], []
    for seed in seeds:
        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=seed)
        for fold_idx, (train_idx, test_idx) in enumerate(skf.split(X, y)):
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            if y_train.nunique() < 2 or y_test.nunique() < 2:
                degenerate.append({"seed": seed, "fold": fold_idx,
                                    "train_classes": sorted(y_train.unique().tolist()),
                                    "test_classes": sorted(y_test.unique().tolist())})
                continue
            model = LogisticRegression(max_iter=1000)
            model.fit(X.iloc[train_idx], y_train)
            proba = model.predict_proba(X.iloc[test_idx])[:, 1]
            auc = roc_auc_score(y_test, proba)
            fold_results.append({"seed": seed, "fold": fold_idx, "auc": auc, "n_test": len(test_idx)})
    return fold_results, degenerate


event_fold_results, event_degenerate = run_event_level_cv(X_event, y_event)
event_aucs_arr = np.array([r["auc"] for r in event_fold_results])

print(f"Degenerate (single-class) folds skipped: {len(event_degenerate)}")
for d in event_degenerate:
    print(f"  {d}")
print(f"Valid folds: {len(event_aucs_arr)} (expected {N_FOLDS * len(SEEDS)})")
print(f"Per-fold AUCs (first 10 shown): {[round(a, 4) for a in event_aucs_arr[:10]]}")
print(f"PRIMARY event-level AUC: mean={event_aucs_arr.mean():.4f} std={event_aucs_arr.std():.4f} "
      f"min={event_aucs_arr.min():.4f} max={event_aucs_arr.max():.4f}")
event_seed_means = [np.mean([r["auc"] for r in event_fold_results if r["seed"] == s]) for s in SEEDS]
print(f"Std across the {len(SEEDS)} per-seed means: {np.std(event_seed_means):.4f}")

# ===========================================================================
# SENSITIVITY 1: <3-event category threshold, event-level model.
# ===========================================================================

X_event_sens3 = build_design_matrix(event_level, "primary_category_grouped_sensitivity3")
event_fold_results_sens3, event_degenerate_sens3 = run_event_level_cv(X_event_sens3, y_event)
event_aucs_sens3_arr = np.array([r["auc"] for r in event_fold_results_sens3])

print()
print("=== SENSITIVITY 1: event-level model, <3-event category threshold ===")
print(f"mean={event_aucs_sens3_arr.mean():.4f} std={event_aucs_sens3_arr.std():.4f} "
      f"min={event_aucs_sens3_arr.min():.4f} max={event_aucs_sens3_arr.max():.4f}")

# ===========================================================================
# SENSITIVITY 2: exclude the single largest event (Lisdexamfetamine).
# ===========================================================================

largest_event_id = model_data["event_id"].value_counts().idxmax()
print()
print(f"=== SENSITIVITY 2: excluding the largest event ({largest_event_id!r}) ===")

event_level_excl = event_level[event_level["event_id"] != largest_event_id].copy()
X_event_excl = build_design_matrix(event_level_excl, "primary_category_grouped_primary")
y_event_excl = event_level_excl["event_label"]
event_fold_results_excl, event_degenerate_excl = run_event_level_cv(X_event_excl, y_event_excl)
event_aucs_excl_arr = np.array([r["auc"] for r in event_fold_results_excl])

print(f"Event-level AUC WITH largest event:    mean={event_aucs_arr.mean():.4f} std={event_aucs_arr.std():.4f}")
print(f"Event-level AUC WITHOUT largest event: mean={event_aucs_excl_arr.mean():.4f} std={event_aucs_excl_arr.std():.4f} "
      f"(n={len(event_level_excl)} events, {len(event_degenerate_excl)} degenerate folds skipped)")

model_with = LogisticRegression(max_iter=1000).fit(X_event, y_event)
model_without = LogisticRegression(max_iter=1000).fit(X_event_excl, y_event_excl)
dose_oral_with = dict(zip(model_with.feature_names_in_, model_with.coef_[0])).get("dose_Oral")
dose_oral_without = dict(zip(model_without.feature_names_in_, model_without.coef_[0])).get("dose_Oral")
print(f"dose_Oral coefficient WITH largest event:    {dose_oral_with}")
print(f"dose_Oral coefficient WITHOUT largest event: {dose_oral_without}")

# ===========================================================================
# SENSITIVITY 3: drop all mixed (row-level) events entirely, event-level
# model AND Mann-Whitney.
# ===========================================================================

event_level_clean = event_level[~event_level["is_mixed_rowlevel"]].copy()
print()
print(f"=== SENSITIVITY 3: dropping all {event_level['is_mixed_rowlevel'].sum()} mixed events "
      f"({len(event_level_clean)} events remain) ===")

X_event_clean = build_design_matrix(event_level_clean, "primary_category_grouped_primary")
y_event_clean = event_level_clean["event_label"]
event_fold_results_clean, event_degenerate_clean = run_event_level_cv(X_event_clean, y_event_clean)
event_aucs_clean_arr = np.array([r["auc"] for r in event_fold_results_clean]) if event_fold_results_clean else np.array([])

print(f"Event-level AUC on non-mixed events only: "
      f"mean={event_aucs_clean_arr.mean() if len(event_aucs_clean_arr) else float('nan'):.4f} "
      f"std={event_aucs_clean_arr.std() if len(event_aucs_clean_arr) else float('nan'):.4f} "
      f"({len(event_degenerate_clean)} degenerate folds skipped)")

# ===========================================================================
# STEP 6: event-level Mann-Whitney U, using event_label and each event's
# (median-aggregated) manufacturer_count. Also run on the "drop mixed" set.
# ===========================================================================

def run_event_mannwhitney(df: pd.DataFrame, label: str):
    supply = df.loc[df["event_label"] == 1, "manufacturer_count"]
    demand = df.loc[df["event_label"] == 0, "manufacturer_count"]
    u_stat, p_value = stats.mannwhitneyu(supply, demand, alternative="two-sided")
    n1, n2 = len(supply), len(demand)
    rank_biserial = (2 * u_stat) / (n1 * n2) - 1
    result = {
        "label": label, "U": float(u_stat), "p_value": float(p_value),
        "n_supply": int(n1), "n_demand": int(n2),
        "median_supply": float(supply.median()), "median_demand": float(demand.median()),
        "iqr_supply": [float(supply.quantile(0.25)), float(supply.quantile(0.75))],
        "iqr_demand": [float(demand.quantile(0.25)), float(demand.quantile(0.75))],
        "rank_biserial_correlation": float(rank_biserial),
    }
    print(f"=== Event-level Mann-Whitney ({label}) ===")
    for k, v in result.items():
        print(f"  {k}: {v}")
    return result


print()
mw_primary = run_event_mannwhitney(event_level, "event_level_primary (all 57 events)")
mw_clean = run_event_mannwhitney(event_level_clean, "event_level_sensitivity_drop_mixed")

# ===========================================================================
# row-level (leaky) Mann-Whitney, recomputed here (not taken from the
# master prompt's "p = 3.68e-10" or the notebook's "0.81 std 0.097" --
# both need to come from code actually run) for a verified before/after row
# in results.json.
# ===========================================================================

supply_row = model_data.loc[model_data["is_supply_side"] == 1, "manufacturer_count"]
demand_row = model_data.loc[model_data["is_supply_side"] == 0, "manufacturer_count"]
u_row, p_row = stats.mannwhitneyu(supply_row, demand_row, alternative="two-sided")
print()
print(f"=== Row-level (LEAKY) Mann-Whitney, for comparison: U={u_row}, p={p_row:.6e} ===")

# ===========================================================================
# figure: event-level manufacturer_count by shortage cause.
# ===========================================================================

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES_DIR.mkdir(exist_ok=True)
fig, ax = plt.subplots(figsize=(7, 5))
data_to_plot = [
    event_level.loc[event_level["event_label"] == 1, "manufacturer_count"],
    event_level.loc[event_level["event_label"] == 0, "manufacturer_count"],
]
ax.boxplot(data_to_plot, tick_labels=["Supply-side", "Demand-side"])
ax.set_ylabel("Manufacturer count (median per event)")
ax.set_title(f"Event-level manufacturer count by shortage cause (n={len(event_level)} events)")
fig.tight_layout()
fig.savefig(FIGURES_DIR / "manufacturer_count_by_cause.png", dpi=300)
print(f"\nSaved {FIGURES_DIR / 'manufacturer_count_by_cause.png'}")

# ===========================================================================
# results.json
# ===========================================================================

results = {
    "row_level_leaky": {
        "description": "Original row-level pipeline (830 rows = 57 events exploded by NDC package). "
                        "Kept for comparison only; known to leak near-duplicate rows across folds.",
        "auc_mean": 0.8109368139868286,
        "auc_std": 0.08920011349035244,
        "auc_source_note": "Verified by reproducing analysis.ipynb's final (drop_first=True) cell exactly; "
                            "the master prompt's cited 'std 0.097' belongs to a SUPERSEDED earlier notebook "
                            "cell (pre-drop_first-fix) and does not match what was actually fit and saved to "
                            "rxwatch_model.pkl. Using the verified number here per the no-invented-numbers rule.",
        "mannwhitney_U": float(u_row),
        "mannwhitney_p": float(p_row),
        "n_rows": int(len(model_data)),
        "n_events": int(n_events_approved),
    },
    "event_definition": {
        "key": "generic_name + initial_posting_date",
        "n_events_in_model_data": int(n_events_approved),
        "merge_check_normalized_ingredient": {
            "n_events_under_ingredient_key": int(n_events_merged_total),
            "n_events_that_would_merge": int(events_absorbed),
            "approved_without_change": True,
        },
        "rows_per_event": {"min": int(model_data["event_id"].value_counts().min()),
                            "median": float(model_data["event_id"].value_counts().median()),
                            "max": int(model_data["event_id"].value_counts().max())},
        "largest_event": largest_event_id,
        "largest_event_share_of_rows": float(model_data["event_id"].value_counts().max() / len(model_data)),
    },
    "mixed_label_resolution": {
        "method": "majority vote by distinct company_name count within event (company_name has 0 nulls)",
        "n_mixed_events_rowlevel": int(event_label_df["is_mixed_rowlevel"].sum()),
        "n_exact_ties": len(label_ties),
        "ties": label_ties,
    },
    "category_threshold": {
        "primary_threshold_events": 5,
        "primary_merged_categories": merged_at_5,
        "sensitivity_threshold_events": 3,
        "sensitivity_merged_categories": merged_at_3,
        "note": "Category dummy columns differ from the original row-level model's: threshold is based on "
                "EVENT counts, not row counts, so the kept categories (Anesthesia, Analgesia/Addiction, "
                "Cardiovascular, Psychiatry, Endocrinology/Metabolism) and the resulting cat_* columns in "
                "X are not the same set as rxwatch_model_columns.pkl.",
    },
    "event_level_class_balance": {
        "supply_side_events": int(event_class_counts.get(1, 0)),
        "demand_side_events": int(event_class_counts.get(0, 0)),
        "total_events": int(len(event_label_df)),
    },
    "primary": {
        "description": "Event-level model: one row per event (median-aggregated manufacturer_count/"
                        "recall_count, constant primary_category/dosage_category), <5-event category "
                        "threshold, 5-fold StratifiedKFold x 10 seeds.",
        "auc_mean": float(event_aucs_arr.mean()), "auc_std": float(event_aucs_arr.std()),
        "auc_min": float(event_aucs_arr.min()), "auc_max": float(event_aucs_arr.max()),
        "n_folds_total": len(event_aucs_arr), "n_degenerate_folds_skipped": len(event_degenerate),
        "per_fold_aucs": [float(a) for a in event_aucs_arr],
        "mannwhitney": mw_primary,
    },
    "secondary_row_level_grouped_cv": {
        "description": "Row-level pipeline, StratifiedGroupKFold (grouped by event_id) so no event's rows "
                        "split across train/test, 5 folds x 10 seeds.",
        "unweighted": {"auc_mean": float(fold_aucs_arr.mean()), "auc_std": float(fold_aucs_arr.std()),
                       "auc_min": float(fold_aucs_arr.min()), "auc_max": float(fold_aucs_arr.max()),
                       "per_fold_aucs": [float(a) for a in fold_aucs_arr]},
        "weighted_inverse_rows_per_event": {
            "auc_mean": float(fold_aucs_weighted_arr.mean()), "auc_std": float(fold_aucs_weighted_arr.std()),
            "auc_min": float(fold_aucs_weighted_arr.min()), "auc_max": float(fold_aucs_weighted_arr.max()),
        },
        "n_degenerate_folds_skipped": len(degenerate_fold_events),
        "per_seed_means": [float(m) for m in seed_means],
        "std_across_seed_means": float(np.std(seed_means)),
    },
    "sensitivity_checks": {
        "category_threshold_lt3": {
            "auc_mean": float(event_aucs_sens3_arr.mean()), "auc_std": float(event_aucs_sens3_arr.std()),
            "auc_min": float(event_aucs_sens3_arr.min()), "auc_max": float(event_aucs_sens3_arr.max()),
        },
        "excluding_largest_event": {
            "largest_event_id": largest_event_id,
            "auc_mean_with": float(event_aucs_arr.mean()), "auc_mean_without": float(event_aucs_excl_arr.mean()),
            "dose_oral_coef_with": float(dose_oral_with) if dose_oral_with is not None else None,
            "dose_oral_coef_without": float(dose_oral_without) if dose_oral_without is not None else None,
        },
        "drop_all_mixed_events": {
            "n_events_remaining": len(event_level_clean),
            "auc_mean": float(event_aucs_clean_arr.mean()) if len(event_aucs_clean_arr) else None,
            "auc_std": float(event_aucs_clean_arr.std()) if len(event_aucs_clean_arr) else None,
            "mannwhitney": mw_clean,
        },
    },
}

# ===========================================================================
# PERMUTATION TEST on the PRIMARY event-level model: shuffle the 57 event
# labels, rerun the EXACT same pipeline (<5 threshold, median aggregation,
# 5-fold x 10-seed StratifiedKFold -- full replication, not reduced; 1000
# permutations took ~5.7 min in a timing test, well within budget).
# ===========================================================================

import time

N_PERMUTATIONS = 1000
observed_auc = event_aucs_arr.mean()

print()
print(f"=== Permutation test ({N_PERMUTATIONS} permutations, full 5-fold x 10-seed each) ===")
t0 = time.time()
null_aucs = np.empty(N_PERMUTATIONS)
for i in range(N_PERMUTATIONS):
    y_shuffled = y_event.sample(frac=1, random_state=i).reset_index(drop=True)
    y_shuffled.index = y_event.index
    perm_fold_results, _ = run_event_level_cv(X_event, y_shuffled, seeds=SEEDS)
    null_aucs[i] = np.mean([r["auc"] for r in perm_fold_results])
elapsed = time.time() - t0

permutation_p = (np.sum(null_aucs >= observed_auc) + 1) / (N_PERMUTATIONS + 1)

print(f"Elapsed: {elapsed:.1f}s")
print(f"Observed PRIMARY event-level mean AUC: {observed_auc:.4f}")
print(f"Null distribution: mean={null_aucs.mean():.4f}, std={null_aucs.std():.4f}, "
      f"95th percentile={np.percentile(null_aucs, 95):.4f}")
print(f"Permutation p-value: {permutation_p:.4f}  "
      f"({int(np.sum(null_aucs >= observed_auc))} of {N_PERMUTATIONS} permuted AUCs >= observed)")

results["permutation_test"] = {
    "description": "1000 label permutations of the PRIMARY event-level model, full 5-fold x 10-seed "
                    "StratifiedKFold rerun per permutation (same methodology as the primary result).",
    "n_permutations": N_PERMUTATIONS,
    "observed_auc": float(observed_auc),
    "null_mean": float(null_aucs.mean()),
    "null_std": float(null_aucs.std()),
    "null_95th_percentile": float(np.percentile(null_aucs, 95)),
    "permutation_p_value": float(permutation_p),
    "n_permuted_aucs_gte_observed": int(np.sum(null_aucs >= observed_auc)),
}

with open(RESULTS_PATH, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nWrote {RESULTS_PATH}")
