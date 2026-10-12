"""
FastAPI service that scores drugs for shortage risk
using the trained logistic regression model, and returns JSON matching
the frontend's ScoredDrug shape.

Run with: uvicorn main:app --reload --port 8000

Expects these files to exist:
  - rxwatch_model.pkl           (trained LogisticRegression, 11 features)
  - rxwatch_model_columns.pkl   (list of 11 column names, in order)
  - ndc_directory.csv           (NDC directory — manufacturer_count + brand/generic name lookup)
  - shortages.csv               (drug class / dosage form lookup)
  - recalls.csv                 (recall_count lookup)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from collections import defaultdict
from rapidfuzz import fuzz, process
import pandas as pd
import joblib
import ast
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------
# load model + reference data once at startup
# -----------------------------------------------------------------------

model = joblib.load("data/rxwatch_model.pkl")
model_columns = joblib.load("data/rxwatch_model_columns.pkl")

ndc = pd.read_csv("data/ndc_directory.csv")
shortages = pd.read_csv("data/shortages.csv")
recalls = pd.read_csv("data/recalls.csv")

manufacturer_counts = ndc.groupby("generic_name")["labeler_name"].nunique()

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

# -----------------------------------------------------------------------
# drug_class_lookup matching
#
# shortages.csv's generic_name bakes the dosage form into the string
# (e.g. "Albuterol Sulfate Inhalation Aerosol"), while ndc_directory.csv's
# generic_name is the plain ingredient name (e.g. "albuterol sulfate").
# Strip the dosage form off the shortages side, then match the result
# against ndc's generic names: exact first, fuzzy for near-misses (salt
# form, strength suffix, word order, punctuation).
# -----------------------------------------------------------------------

_DOSAGE_FORM_WORDS = (
    "tablet capsule injection solution suspension aerosol powder suppository "
    "cream gel ointment lotion spray kit tincture liquid patch elixir syrup "
    "drops emulsion foam paste concentrate irrigant film inhalation nasal "
    "ophthalmic oral topical rectal vaginal extended delayed release chewable "
    "metered transdermal implant pellet enema douche swab sponge strip wafer "
    "troche lozenge"
).split()
_DOSAGE_FORM_FALLBACK_RE = re.compile(r"\b(" + "|".join(_DOSAGE_FORM_WORDS) + r")\b", re.IGNORECASE)

# Highest similarity score seen among wrong fuzzy candidates during manual
# review (e.g. "conivaptan hydrochloride" -> "ecopipam hydrochloride" = 82.6)
# was 82.6; 85 leaves a margin above that while still catching genuine
# near-misses like "dextrose monohydrate 10%" -> "dextrose monohydrate" (90.9).
FUZZY_MATCH_THRESHOLD = 85

_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")

def _clean_match_key(name: str) -> str:
    """Final cleanup shared by both sides of the match: '/' is just another
    ingredient separator (e.g. "Quinapril Hydrochloride/Hydrochlorothiazide"),
    so give it surrounding whitespace like "and"/","/";" already have."""
    name = re.sub(r"\s*/\s*", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()

def normalize_shortage_generic_name(generic_name: str, dosage_form) -> str:
    """Strip the trailing dosage-form phrase off a shortages.csv generic_name."""
    name = str(generic_name).strip()
    original = name.lower()

    if pd.notna(dosage_form) and str(dosage_form).strip():
        pattern = re.compile(r"\b" + re.escape(str(dosage_form).strip()) + r"\b", re.IGNORECASE)
        matches = list(pattern.finditer(name))
        if matches:
            name = name[: matches[-1].start()]

    if name.strip().lower() == original:
        # dosage_form was missing or didn't appear verbatim in the string --
        # fall back to cutting at the first generic dosage-related word.
        match = _DOSAGE_FORM_FALLBACK_RE.search(name)
        if match:
            name = name[: match.start()]

    return _clean_match_key(name.strip().strip(",;"))

shortages["normalized_generic_name"] = shortages.apply(
    lambda r: normalize_shortage_generic_name(r["generic_name"], r["dosage_form"])
    if pd.notna(r["generic_name"]) else None,
    axis=1,
)

_shortage_by_normalized = (
    shortages.dropna(subset=["normalized_generic_name"])
    .drop_duplicates(subset="normalized_generic_name", keep="last")
    .set_index("normalized_generic_name")
)

# every distinct ndc generic_name, grouped by its match key (lowercased,
# "/"-normalized, and with parenthetical suffixes like "(Process IV)" or
# "(Isomer Free)" stripped) so matching is insensitive to that noise --
# but drug_class_lookup still gets the exact-cased, unstripped keys that
# lookup_features() (matched_generic) will query it with.
_ndc_raw_by_lower: dict[str, list[str]] = defaultdict(list)
for _raw in ndc["generic_name"].dropna().astype(str).unique():
    _match_key = _clean_match_key(_PARENTHETICAL_RE.sub("", _raw))
    _ndc_raw_by_lower[_match_key].append(_raw)

drug_class_lookup: dict[str, dict] = {}
# ndc raw generic_name -> the shortages.csv generic_name it was matched from,
# kept only for debugging/reporting (not used in scoring).
drug_class_match_source: dict[str, str] = {}

def _apply_drug_class_match(normalized_key: str, shortage_row) -> int:
    raws = _ndc_raw_by_lower.get(normalized_key)
    if not raws:
        return 0
    info = {
        "primary_category": shortage_row["primary_category"],
        "dosage_category": shortage_row["dosage_category"],
    }
    for raw in raws:
        drug_class_lookup[raw] = info
        drug_class_match_source[raw] = shortage_row["generic_name"]
    return len(raws)

_unmatched_normalized = []
for _normalized_key, _row in _shortage_by_normalized.iterrows():
    if _apply_drug_class_match(_normalized_key, _row) == 0:
        _unmatched_normalized.append(_normalized_key)

_fuzzy_recovered = 0
_ndc_lower_candidates = list(_ndc_raw_by_lower.keys())
for _normalized_key in _unmatched_normalized:
    _best = process.extractOne(
        _normalized_key, _ndc_lower_candidates,
        scorer=fuzz.token_sort_ratio, score_cutoff=FUZZY_MATCH_THRESHOLD,
    )
    if _best is not None:
        if _apply_drug_class_match(_best[0], _shortage_by_normalized.loc[_normalized_key]) > 0:
            _fuzzy_recovered += 1

print(
    f"[drug_class_lookup] {len(_shortage_by_normalized) - len(_unmatched_normalized)} exact + "
    f"{_fuzzy_recovered} fuzzy matches out of {len(_shortage_by_normalized)} shortages.csv drugs "
    f"(fuzzy threshold={FUZZY_MATCH_THRESHOLD})"
)

# recall count per generic_name
recall_col = "openfda.generic_name" if "openfda.generic_name" in recalls.columns else "generic_name"
if recall_col in recalls.columns:
    recall_counts_by_generic = recalls.groupby(recall_col).size()
else:
    recall_counts_by_generic = pd.Series(dtype=int)

# ------------------------------------------------------------------------
# category/dosage mapping : must match training exactly, including the
# dropped baseline categories (drop_first=True dropped these two):
#   therapeutic baseline = "Analgesia/Addiction"  (all cat_ columns = 0)
#   dosage baseline      = "Injectable"            (all dose_ columns = 0)
#
# As of the Phase 1 event-level retrain (analysis/validation.py), the
# category set uses an EVENT-count rare-category threshold (<5 events),
# not the original ROW-count threshold -- Anti-Infective and Oncology no
# longer get their own column and fall through to cat_Other/Rare below.
# ------------------------------------------------------------------------

BASELINE_CATEGORY = "Analgesia/Addiction"
NAMED_CATEGORIES = {"Anesthesia", "Cardiovascular",
                     "Endocrinology/Metabolism", "Psychiatry"}
# "other/rare" also has its own column -> anything not baseline/named/None falls here

BASELINE_DOSAGE = "Injectable"
NAMED_DOSAGE = {"Oral", "Other"}


def map_category_to_column(primary_category: str | None) -> str | None:
    """Return the cat_ column to set to 1, or None if it's the baseline (leave all zero)"""
    if primary_category is None or primary_category == BASELINE_CATEGORY:
        return None
    if primary_category in NAMED_CATEGORIES:
        return f"cat_{primary_category}"
    return "cat_Other/Rare"


def map_dosage_to_column(dosage_category: str | None) -> str | None:
    """Return the dose_ column to set to 1, or None if it's the baseline (leave all zero)"""
    if dosage_category is None or dosage_category == BASELINE_DOSAGE:
        return None
    if dosage_category in NAMED_DOSAGE:
        return f"dose_{dosage_category}"
    return "dose_Other"


# ---------------------------------------------------------------------------
# request/response models
# ---------------------------------------------------------------------------

class ScoreRequest(BaseModel):
    names: list[str]

# ---------------------------------------------------------------------------
# feature lookup
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    return name.strip().lower()

def lookup_features(raw_name: str) -> dict:
    name = normalize_name(raw_name)

    generic_names = ndc["generic_name"].dropna().astype(str)
    exact = generic_names[generic_names.str.lower() == name]

    matched_generic = None
    if len(exact) > 0:
        matched_generic = exact.iloc[0]
    else:
        if "brand_name" in ndc.columns:
            brand_names = ndc["brand_name"].dropna().astype(str)
            brand_exact = brand_names[brand_names.str.lower() == name]
            if len(brand_exact) > 0:
                matched_row = ndc[ndc["brand_name"] == brand_exact.iloc[0]].iloc[0]
                matched_generic = matched_row["generic_name"]

        if matched_generic is None:
            partial = generic_names[generic_names.str.lower().str.contains(name, na=False, regex=False)]
            if len(partial) > 0:
                matched_generic = partial.iloc[0]

    if matched_generic is None:
        return {
            "matched_generic_name": None,
            "manufacturer_count": None,
            "primary_category": None,
            "dosage_category": None,
            "recall_count": 0,
        }

    manufacturer_count = int(manufacturer_counts.get(matched_generic, 1))
    class_info = drug_class_lookup.get(matched_generic, {})
    recall_count = int(recall_counts_by_generic.get(matched_generic, 0))

    return {
        "matched_generic_name": matched_generic,
        "manufacturer_count": manufacturer_count,
        "primary_category": class_info.get("primary_category"),
        "dosage_category": class_info.get("dosage_category"),
        "recall_count": recall_count,
    }

# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def build_feature_row(manufacturer_count: int, recall_count: int,
                       primary_category: str | None, dosage_category: str | None) -> pd.DataFrame:
    row = {col: 0 for col in model_columns}
    row["manufacturer_count"] = manufacturer_count
    row["recall_count"] = recall_count

    cat_col = map_category_to_column(primary_category)
    if cat_col and cat_col in row:
        row[cat_col] = 1

    dose_col = map_dosage_to_column(dosage_category)
    if dose_col and dose_col in row:
        row[dose_col] = 1

    return pd.DataFrame([row], columns=model_columns)


def score_one(raw_name: str) -> dict:
    features = lookup_features(raw_name)
    manufacturer_count = features["manufacturer_count"] if features["manufacturer_count"] is not None else 5
    recall_count = features["recall_count"]
    primary_category = features["primary_category"]
    dosage_category = features["dosage_category"]

    X = build_feature_row(manufacturer_count, recall_count, primary_category, dosage_category)
    supply_prob = float(model.predict_proba(X)[0][1])

    score = round(supply_prob * 100)
    tier = "Critical" if score >= 75 else "High" if score >= 55 else "Medium" if score >= 30 else "Low"
    cause = "Supply-side" if supply_prob >= 0.55 else "Demand-side" if supply_prob <= 0.45 else "Unclear"

    dosage_form_display = dosage_category if dosage_category else "Oral"

    factors = [
        {"label": "Manufacturer count", "value": f"{manufacturer_count} active",
         "weight": round(abs(model.coef_[0][0]) * manufacturer_count)},
        {"label": "Drug class", "value": primary_category or "Unknown", "weight": 10},
        {"label": "Dosage form", "value": dosage_category or "Unknown", "weight": 10},
    ]

    explanation = (
        f"Predicted {cause.lower()} risk (model confidence: {score}%). "
        f"Based on {manufacturer_count} manufacturer(s), "
        f"drug class '{primary_category or 'unmatched'}', "
        f"and dosage form '{dosage_category or 'unmatched'}'."
    )

    return {
        "name": raw_name,
        "manufacturers": manufacturer_count,
        "drugClass": primary_category or "Unknown",
        "dosageForm": dosage_form_display,
        "classProneToShortage": primary_category in {"Anesthesia", "Cardiovascular"},
        "activeShortage": features["matched_generic_name"] is not None and
                           features["matched_generic_name"] in shortages["generic_name"].values,
        "demandSpike": cause == "Demand-side",
        "score": score,
        "tier": tier,
        "cause": cause,
        "explanation": explanation,
        "factors": factors,
    }

# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@app.post("/api/score-batch")
def score_batch(req: ScoreRequest):
    return {"results": [score_one(name) for name in req.names]}


@app.get("/api/health")
def health():
    return {"status": "ok", "model_loaded": model is not None}


@app.get("/api/drug-search")
def drug_search(q: str, limit: int = 8):
    query = q.strip().lower()
    if len(query) < 2:
        return {"suggestions": []}

    suggestions = []
    seen = set()

    generic_matches = ndc[ndc["generic_name"].astype(str).str.lower().str.contains(query, na=False, regex=False)]
    for name in generic_matches["generic_name"].dropna().unique():
        if name in seen:
            continue
        seen.add(name)
        suggestions.append({"name": name, "generic_name": None, "is_brand": False})
        if len(suggestions) >= limit:
            return {"suggestions": suggestions}

    if "brand_name" in ndc.columns:
        brand_matches = ndc[ndc["brand_name"].astype(str).str.lower().str.contains(query, na=False, regex=False)]
        for _, row in brand_matches.dropna(subset=["brand_name"]).iterrows():
            brand = row["brand_name"]
            generic = row.get("generic_name")
            key = (brand, generic)
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({"name": brand, "generic_name": generic, "is_brand": True})
            if len(suggestions) >= limit:
                break

    return {"suggestions": suggestions[:limit]}


@app.get("/api/drug-features")
def drug_features(name: str):
    return score_one(name)