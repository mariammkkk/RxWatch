"""
FastAPI service for drug shortage lookups. Returns FDA shortage status and
descriptive facts (manufacturer count, recall count, therapeutic class,
dosage form) straight from the data; the trained logistic regression model
is only consulted for an explicitly-gated, labeled experimental estimate
(see build_drug_result and the causeEstimate gate).

Run with: uvicorn main:app --reload --port 8000

Expects these files to exist:
  - rxwatch_model.pkl           (trained LogisticRegression, 9 features)
  - rxwatch_model_columns.pkl   (list of 9 column names, in order)
  - ndc_directory.csv           (NDC directory, manufacturer_count + brand/generic name lookup)
  - shortages.csv               (drug class / dosage form / status / reason lookup)
  - recalls.csv                 (recall_count lookup)
  - metadata.json               (pulled_at date shown to users as dataAsOf)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from collections import defaultdict
from rapidfuzz import fuzz, process
import pandas as pd
import joblib
import ast
import json
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

with open("data/metadata.json") as _f:
    DATA_AS_OF = json.load(_f)["pulled_at"]

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

# shortage status + stated reasons are resolved further down, once
# normalize_query_name exists -- see resolve_shortage_status_and_reasons.

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
# not the original ROW-count threshold -- Oncology still falls through to
# cat_Other/Rare below. Anti-Infective crossed the threshold (57 -> 60
# events, from the complete-NDC-file retrain) and got its own column.
# ------------------------------------------------------------------------

BASELINE_CATEGORY = "Analgesia/Addiction"
NAMED_CATEGORIES = {"Anesthesia", "Anti-Infective", "Cardiovascular",
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
# query-name normalization
#
# A query like "Lincomycin Hydrochloride Injection" (the kind of name
# shortages.csv itself uses) used to fail to match anything: the old
# partial-match fallback checked whether an ndc generic_name CONTAINS the
# query, which can never succeed once the query carries a dosage-form
# suffix longer than ndc's own plain entry. Stripping salts and dosage-form
# words off the query (and matching against a similarly-normalized index of
# ndc's names) fixes that directly, instead of relying on luck.
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    return name.strip().lower()

_PARENTHETICAL_QUERY_RE = re.compile(r"\([^)]*\)")

# cation words (electrolyte-forming metals) are ambiguous on their own --
# "Naproxen Sodium" should strip to "naproxen", but "Sodium Chloride" is a
# complete two-word drug name and must not collapse to just "chloride" (nor
# should "Potassium Chloride" or "Calcium Chloride" collide with it on the
# same stripped key). Handled by position + an all-salt-remainder guard in
# _strip_salt_words() below, not by blind regex substitution.
_CATION_WORDS = {"sodium", "potassium", "calcium", "magnesium"}
_OTHER_SALT_WORDS = (
    "hydrochloride sulfate acetate phosphate besylate maleate "
    "mesylate tartrate citrate succinate bitartrate dimesylate hydrobromide hbr "
    "bicarbonate chloride nitrate lactate gluconate fumarate "
    "oxalate carbonate benzoate besilate edisylate napsylate pamoate stearate "
    "valerate propionate aspartate saccharate monohydrate anhydrous dihydrate "
    "trihydrate hemihydrate hydrate base"
).split()
_ALL_SALT_WORDS = _CATION_WORDS | set(_OTHER_SALT_WORDS)


def _strip_salt_words(name: str) -> str:
    """Strip salt/ion words, except: a cation word in the first position is
    kept (it's load-bearing, e.g. "Sodium Chloride"), and nothing is
    stripped at all if doing so would leave the name empty or made up
    entirely of other salt/ion words (same "Sodium Chloride" case, from the
    other side -- stripping "chloride" alone would leave just "sodium")."""
    tokens = name.split()
    if not tokens:
        return name

    removable = [
        i for i, t in enumerate(tokens)
        if (t in _CATION_WORDS and i != 0) or t in _OTHER_SALT_WORDS
    ]
    remaining = [t for i, t in enumerate(tokens) if i not in removable]

    if not remaining or all(t in _ALL_SALT_WORDS for t in remaining):
        return name  # stripping would over-collapse -- leave untouched

    return " ".join(remaining)

# individual dosage-form words (not phrases -- "oral solution" is matched as
# the two separate words "oral" and "solution", combined back into a
# category below).
_DOSAGE_FORM_WORD_LIST = (
    "tablet capsule injection solution suspension aerosol powder suppository "
    "cream gel ointment lotion spray kit tincture liquid patch elixir syrup "
    "drops emulsion foam paste concentrate irrigant film coated inhalation nasal "
    "ophthalmic oral topical rectal vaginal extended delayed release chewable "
    "metered transdermal implant pellet enema douche swab sponge strip wafer "
    "troche lozenge for"
).split()
_DOSAGE_FORM_RE = re.compile(r"\b(" + "|".join(_DOSAGE_FORM_WORD_LIST) + r")\b", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[^\w\s]")


def _dosage_words_to_category(words: list[str]) -> str | None:
    """Mirrors simplify_dosage()'s Injectable/Oral/Other split, but takes a
    bag of individual dosage words (from query parsing) instead of one exact
    shortages.csv dosage_form phrase."""
    word_set = {w.lower() for w in words}
    if not word_set:
        return None
    if "injection" in word_set:
        return "Injectable"
    if ("tablet" in word_set or "capsule" in word_set or "chewable" in word_set
            or ("oral" in word_set and ("solution" in word_set or "suspension" in word_set))):
        return "Oral"
    return "Other"


# pharmacy-style shorthand, expanded to full words BEFORE the rest of
# normalization so the existing salt/dosage-word stripping picks them up
# naturally (e.g. "Metformin HCl 500mg Tab" -> "...hydrochloride...tablet").
# Longest keys first so e.g. "tabs" expands before a hypothetical shorter
# overlapping key would.
_ABBREVIATION_MAP = {
    "hcl": "hydrochloride",
    "tabs": "tablet", "tab": "tablet",
    "caps": "capsule", "cap": "capsule",
    "inj": "injection",
    "soln": "solution",
    "susp": "suspension",
    "er": "extended release", "xr": "extended release", "xl": "extended release",
    "sr": "extended release", "dr": "delayed release",
    "hfa": "inhalation",
}
_ABBREVIATION_RE = re.compile(
    r"\b(" + "|".join(sorted(_ABBREVIATION_MAP, key=len, reverse=True)) + r")\b", re.IGNORECASE
)


def _expand_abbreviations(name: str) -> str:
    return _ABBREVIATION_RE.sub(lambda m: _ABBREVIATION_MAP[m.group(1).lower()], name)


# strength/unit tokens: stripped from the matching KEY entirely (so
# "Metformin HCl 500mg Tab" and "Metformin" land on the same key), but
# their numbers are extracted separately (see extract_numbers_for_guard)
# and compared at match time instead -- a numeric mismatch (5% vs 50%)
# must still block a match even though neither string's key retains the
# number anymore.
_STRENGTH_PERCENT_RE = re.compile(r"\d+\.?\d*\s*%")
_STRENGTH_UNIT_RE = re.compile(r"\d+\.?\d*\s*(mg|mcg|ml|g|units?|meq)\b", re.IGNORECASE)

# decimal-aware: must run on the ORIGINAL string before punctuation
# stripping would otherwise split "0.9" into separate "0" and "9" tokens.
_DECIMAL_NUMBER_RE = re.compile(r"\d+\.\d+|\d+")


def extract_numbers_for_guard(raw_name: str) -> frozenset[str]:
    return frozenset(_DECIMAL_NUMBER_RE.findall(str(raw_name)))


def _numbers_compatible(query_numbers: frozenset, candidate_numbers: frozenset) -> bool:
    """Reject only when BOTH sides specify numbers and the candidate's are
    not all present in the query's (e.g. dextrose 5% vs 50% -- a genuine
    conflict). Query-only numbers ("metformin 500mg" vs "metformin") or
    candidate-only numbers ("sodium chloride" vs "Sodium Chloride 0.9%")
    both pass -- missing information on either side is not a conflict."""
    if not query_numbers or not candidate_numbers:
        return True
    return candidate_numbers.issubset(query_numbers)


# Active-ingredient count: a candidate whose ingredient count differs from
# the query's is rejected outright, regardless of numbers -- this is what
# stops "Dextrose 5% inj" (1 ingredient) from matching a 5-ingredient
# electrolyte combo product just because the combo's other ingredients are
# all salt/cation words that get stripped down to nothing.
_INGREDIENT_SEPARATOR_RE = re.compile(r",|;|\band\b|/", re.IGNORECASE)


def count_ingredients(raw_name: str) -> int:
    # strip dosage-form words FIRST: a comma-attached modifier like
    # "Tablet, Extended Release" or "Powder, For Solution" is one ingredient
    # with a two-word dosage descriptor, not two ingredients -- without
    # this, every such name would be miscounted and wrongly rejected
    # against its own single-ingredient query.
    name = _DOSAGE_FORM_RE.sub(" ", str(raw_name))
    parts = _INGREDIENT_SEPARATOR_RE.split(name)
    return len([p for p in parts if p.strip(" ,;")]) or 1


def _pre_strip(raw_name: str) -> str:
    """Lowercase, expand abbreviations, strip parenthetical qualifiers and
    strength/unit tokens, strip punctuation -- but NOT dosage or salt
    words yet. Shared by normalize_query_name() and _pre_strip_tokens()
    (used for collision-group ranking), so the two stay in sync."""
    name = str(raw_name).lower()
    name = _expand_abbreviations(name)
    name = _PARENTHETICAL_QUERY_RE.sub(" ", name)
    name = _STRENGTH_PERCENT_RE.sub(" ", name)
    name = _STRENGTH_UNIT_RE.sub(" ", name)
    name = _PUNCTUATION_RE.sub(" ", name)
    return re.sub(r"\s+", " ", name).strip()


def _pre_strip_tokens(raw_name: str) -> frozenset[str]:
    return frozenset(_pre_strip(raw_name).split())


def normalize_query_name(raw_name: str) -> tuple[str, str | None]:
    """Lowercase, expand pharmacy abbreviations, strip parenthetical
    qualifiers, strength/unit tokens, punctuation, dosage-form words, and
    salt words (see _strip_salt_words for the electrolyte guard).

    Returns (normalized_core_name, extracted_dosage_form_category) where the
    second value is "Injectable"/"Oral"/"Other"/None, taken from whatever
    dosage-form word(s) were found and stripped -- extracted rather than
    just discarded, since it's a useful signal about the query itself.
    Numbers are handled separately by extract_numbers_for_guard(), since
    they're stripped from the key here but still needed for the guard.
    """
    name = _pre_strip(raw_name)

    dosage_words_found = _DOSAGE_FORM_RE.findall(name)
    name = _DOSAGE_FORM_RE.sub(" ", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = _strip_salt_words(name)

    return name, _dosage_words_to_category(dosage_words_found)


def _rank_by_token_overlap(raws: list[str], query_tokens: frozenset[str]) -> list[str]:
    """Rank candidates sharing a normalized key by overlap with the query's
    pre-strip tokens: most shared tokens first, then fewest extra tokens as
    a tiebreak. Fixes e.g. "Hydrocortisone sodium succinate 100mg inj"
    picking the acetate variant just because it came first alphabetically,
    and "Metformin HCl 500mg Tab" picking an ER variant over a plain one."""
    def sort_key(raw: str) -> tuple[int, int]:
        cand_tokens = _pre_strip_tokens(raw)
        shared = len(query_tokens & cand_tokens)
        extra = len(cand_tokens - query_tokens)
        return (-shared, extra)

    return sorted(dict.fromkeys(raws), key=sort_key)


def _select_best_compatible_raw(raws: list[str], raw_query_name: str) -> str | None:
    """Given several raw names sharing a normalized key: rank by token
    overlap with the query (see _rank_by_token_overlap, defined below --
    forward reference is fine since this is only ever called later, after
    the whole module has loaded), then return the first that also passes
    the number guard and the ingredient-count check (rejecting e.g. a
    5-ingredient combo product for a 1-ingredient query regardless of
    numbers). None if every raw in the group conflicts."""
    query_tokens = _pre_strip_tokens(raw_query_name)
    query_numbers = extract_numbers_for_guard(raw_query_name)
    query_ingredient_count = count_ingredients(raw_query_name)
    for raw in _rank_by_token_overlap(raws, query_tokens):
        if not _numbers_compatible(query_numbers, extract_numbers_for_guard(raw)):
            continue
        if count_ingredients(raw) != query_ingredient_count:
            continue
        return raw
    return None


# normalized indices, built once at startup: normalized core name -> list of
# raw ndc generic_name / brand_name strings sharing that normalized form.
_ndc_generic_normalized_index: dict[str, list[str]] = defaultdict(list)
for _g in ndc["generic_name"].dropna().astype(str).unique():
    _norm_g, _ = normalize_query_name(_g)
    if _norm_g:
        _ndc_generic_normalized_index[_norm_g].append(_g)

_ndc_brand_normalized_index: dict[str, list[str]] = defaultdict(list)
if "brand_name" in ndc.columns:
    for _b in ndc["brand_name"].dropna().astype(str).unique():
        _norm_b, _ = normalize_query_name(_b)
        if _norm_b:
            _ndc_brand_normalized_index[_norm_b].append(_b)

# Raised from 85 after review turned up a false match at 85.7 (Somatropin ->
# Homatropine Hydrobromide, two unrelated drugs that happen to share most of
# their letters). 90 is the lowest score among confirmed-correct matches.
QUERY_FUZZY_THRESHOLD = 90

# Per-row simplified dosage category for every ndc_directory.csv entry,
# reusing the same word-based classifier as the query side
# (_dosage_words_to_category) instead of simplify_dosage()'s exact-value
# match, since ndc_directory's own dosage_form strings ("TABLET, COATED",
# "CAPSULE, LIQUID FILLED", "SUSPENSION/ DROPS", ...) aren't the same clean
# vocabulary as shortages.csv's dosage_form column.
_ndc_dosage_category = ndc["dosage_form"].apply(
    lambda x: _dosage_words_to_category(_DOSAGE_FORM_RE.findall(str(x))) if pd.notna(x) else None
)


def _pooled_manufacturer_count(matched_generic: str, query_extracted_dosage: str | None) -> int:
    """Distinct labelers across every raw ndc_directory generic_name string
    sharing matched_generic's normalized form, not just matched_generic's
    own exact string. The single-exact-string lookup undercounts real
    generics whose manufacturer base is split across many textual
    spellings in the data (e.g. "Ibuprofen" vs "ibuprofen tablet" vs
    "IBUPROFEN 200MG" are three different exact strings for the same real
    drug, each with its own small labeler count).

    When the query specifies a dosage form, restricts pooling to rows
    whose OWN dosage_form simplifies to the same category (e.g. an oral
    tablet query doesn't pool in an unrelated injectable labeler count),
    falling back to the ungated pool if that leaves nothing.

    This is the facts/display count only -- NOT what's fed to the model
    (see build_drug_result), which stays on the single-exact-string value
    to match analysis/validation.py's own manufacturer_count definition
    (see the comment above lookup_features's two return values)."""
    pool_key, _ = normalize_query_name(matched_generic)
    group = _ndc_generic_normalized_index.get(pool_key)
    if not group:
        return int(manufacturer_counts.get(matched_generic, 1))

    subset = ndc[ndc["generic_name"].isin(set(group))]
    if query_extracted_dosage:
        dose_subset = subset[_ndc_dosage_category.loc[subset.index] == query_extracted_dosage]
        if len(dose_subset) > 0:
            subset = dose_subset

    count = int(subset["labeler_name"].nunique())
    return count if count > 0 else int(manufacturer_counts.get(matched_generic, 1))


# ---------------------------------------------------------------------------
# drug-level shortage status + stated reasons
#
# Matches the user's query DIRECTLY against shortages.csv's own generic
# names (normalize_query_name on both sides, same exact-then-fuzzy-with-
# number-guard rules as the NDC match), independent of whether the NDC
# match succeeds. The earlier version derived this from the NDC-side
# drug_class_match_source, which meant: (1) a drug entirely absent from
# ndc_directory.csv (e.g. "Rifapentine") could never get a status even
# though it's one of the 237 shortages.csv drugs, (2) a bare query like
# "albuterol" could resolve to an NDC entry ("Albuterol") different from
# the one the shortages match had actually attached data to ("Albuterol
# Sulfate"), losing the status entirely, and (3) the single-row-per-
# normalized-key dedup used for category/dosage could silently pick the
# wrong one of several shortages.csv entries sharing a normalized key
# (e.g. "Lisdexamfetamine Dimesylate Capsule", 90 rows with stated reasons,
# vs "...Tablet, Chewable", 18 rows with none -- both normalize to
# "lisdexamfetamine"). Pooling ALL raw names sharing the normalized key
# (not just one) fixes all three at once.
# ---------------------------------------------------------------------------

_shortage_rows_by_generic_name: dict[str, list[dict]] = {
    _gname: _group[["status", "shortage_reason"]].to_dict("records")
    for _gname, _group in shortages.groupby("generic_name")
}

# each raw shortages.csv generic_name's own dosage_category (reusing the
# per-row column computed above), for the dosage-aware pooling tiebreak.
_shortage_dosage_by_generic_name: dict[str, str | None] = {
    _gname: next((v for v in _group["dosage_category"] if pd.notna(v)), None)
    for _gname, _group in shortages.groupby("generic_name")
}

_shortage_generic_normalized_index: dict[str, list[str]] = defaultdict(list)
for _s in shortages["generic_name"].dropna().astype(str).unique():
    _norm_s, _ = normalize_query_name(_s)
    if _norm_s:
        _shortage_generic_normalized_index[_norm_s].append(_s)

_shortage_normalized_keys = list(_shortage_generic_normalized_index.keys())


def _rollup_status(rows: list[dict]) -> str:
    statuses = {r["status"] for r in rows if pd.notna(r.get("status"))}
    if "Current" in statuses:
        return "current"
    if "To Be Discontinued" in statuses:
        return "to_be_discontinued"
    return "resolved"


def resolve_shortage_status_and_reasons(raw_query_name: str) -> tuple[str, list[str], list[dict], str | None]:
    """Drug-level status rule: any Current record gives "current"; otherwise
    any To Be Discontinued gives "to_be_discontinued"; otherwise "resolved".
    A drug with no matching shortages.csv records at all is "not_listed".
    fdaStatedReasons is every distinct verbatim shortage_reason across all
    pooled records (not just one), since records can disagree.

    Matching is number- and ingredient-count-guarded (same rules as the NDC
    side) and, when the query specifies a dosage form, pooling is
    restricted to presentations whose OWN dosage form matches it -- so e.g.
    querying "hydrocortisone sodium succinate injection" pools only the
    injection presentation, not an unrelated suppository that happens to
    share the same "hydrocortisone" normalized key.

    Returns (status, reasons, matchedShortageEntries, shortageMatchType)
    where matchedShortageEntries is
    [{"name": raw_generic_name, "status": that_presentation's_own_status}, ...]
    for every raw presentation that actually contributed to the rollup, and
    shortageMatchType is "exact"/"approximate"/None (None = not_listed).
    """
    normalized_query, query_extracted_dosage = normalize_query_name(raw_query_name)
    query_numbers = extract_numbers_for_guard(raw_query_name)
    query_ingredient_count = count_ingredients(raw_query_name)
    if not normalized_query:
        return "not_listed", [], [], None

    candidate_group = _shortage_generic_normalized_index.get(normalized_query)
    shortage_match_type = "exact" if candidate_group is not None else None

    if candidate_group is None:
        candidates = process.extract(
            normalized_query, _shortage_normalized_keys,
            scorer=fuzz.token_sort_ratio, score_cutoff=QUERY_FUZZY_THRESHOLD, limit=5,
        )
        for candidate_key, _score, _ in candidates:
            group = _shortage_generic_normalized_index[candidate_key]
            if any(_numbers_compatible(query_numbers, extract_numbers_for_guard(r))
                   and count_ingredients(r) == query_ingredient_count for r in group):
                candidate_group = group
                shortage_match_type = "approximate"
                break

    if not candidate_group:
        return "not_listed", [], [], None

    filtered = [
        r for r in dict.fromkeys(candidate_group)  # de-dupe, preserve order
        if _numbers_compatible(query_numbers, extract_numbers_for_guard(r))
        and count_ingredients(r) == query_ingredient_count
    ]
    if not filtered:
        return "not_listed", [], [], None

    pooled_raws = filtered
    if query_extracted_dosage:
        dosage_matched = [r for r in filtered
                           if _shortage_dosage_by_generic_name.get(r) == query_extracted_dosage]
        if dosage_matched:
            pooled_raws = dosage_matched

    all_rows = [row for raw in pooled_raws for row in _shortage_rows_by_generic_name.get(raw, [])]
    if not all_rows:
        return "not_listed", [], [], None

    status = _rollup_status(all_rows)
    reasons = sorted({r["shortage_reason"] for r in all_rows if pd.notna(r.get("shortage_reason"))})
    matched_entries = [
        {"name": raw, "status": _rollup_status(_shortage_rows_by_generic_name.get(raw, []))}
        for raw in pooled_raws
    ]
    return status, reasons, matched_entries, shortage_match_type


def resolve_collision_class_info(matched_generic: str, collision_raws: list[str] | None,
                                  query_extracted_dosage: str | None) -> dict:
    """When a normalized key's collision group (e.g. "hydrocortisone", which
    covers 22 raw NDC variants) has raw names with CONFLICTING therapeutic
    classes, picking one arbitrarily (the first by insertion order) is
    misleading. Prefer the variant whose dosage form matches the query's own
    extracted dosage form; if none matches, or the query gave no dosage
    form, report the class as unknown (null) rather than guessing."""
    own_info = drug_class_lookup.get(matched_generic, {})
    if not collision_raws or len(set(collision_raws)) < 2:
        return own_info

    classes_seen = set()
    for r in set(collision_raws):
        info = drug_class_lookup.get(r)
        if info and info.get("primary_category"):
            classes_seen.add(info["primary_category"])

    if len(classes_seen) < 2:
        # no real conflict (0 or 1 distinct classes across the group), but
        # matched_generic (picked arbitrarily, e.g. by abbreviation-driven
        # collision-group expansion) might itself be the one raw variant
        # the shortages match never attached data to -- fall back to
        # whichever group member actually has it, since they all agree.
        if own_info.get("primary_category"):
            return own_info
        for r in set(collision_raws):
            info = drug_class_lookup.get(r)
            if info and info.get("primary_category"):
                return info
        return own_info

    if query_extracted_dosage:
        for r in set(collision_raws):
            info = drug_class_lookup.get(r)
            if info and info.get("dosage_category") == query_extracted_dosage:
                return info

    ambiguous_info = dict(drug_class_lookup.get(matched_generic, {}))
    ambiguous_info["primary_category"] = None
    return ambiguous_info


def lookup_features(raw_name: str) -> dict:
    """Returns two distinct manufacturer counts: "manufacturer_count" (the
    single-exact-string value, matching analysis/validation.py's own
    definition -- the only one ever fed to the model, so inference stays
    on the same feature distribution the model was trained on) and
    "manufacturer_count_display" (pooled across every raw name variant
    sharing the matched normalized form, dosage-aware -- the one shown to
    the user and used for fewManufacturersFlag, since a pharmacist cares
    about the real number of suppliers, not which exact string openFDA
    happened to record)."""
    name = normalize_name(raw_name)
    normalized_query, query_extracted_dosage = normalize_query_name(raw_name)

    generic_names = ndc["generic_name"].dropna().astype(str)
    exact = generic_names[generic_names.str.lower() == name]
    query_numbers = extract_numbers_for_guard(raw_name)

    matched_generic = None
    match_method = None
    collision_raws = None  # full list of raw names sharing the matched normalized key, if any
    if len(exact) > 0:
        matched_generic = exact.iloc[0]
        match_method = "exact_raw_generic"
    else:
        if "brand_name" in ndc.columns:
            brand_names = ndc["brand_name"].dropna().astype(str)
            brand_exact = brand_names[brand_names.str.lower() == name]
            if len(brand_exact) > 0:
                matched_row = ndc[ndc["brand_name"] == brand_exact.iloc[0]].iloc[0]
                matched_generic = matched_row["generic_name"]
                match_method = "exact_raw_brand"

        # exact match on normalized names next -- never let fuzzy override
        # an exact hit, so fuzzy is only attempted below if this, and raw
        # exact/brand above, all find nothing. Numbers are stripped from
        # the key itself now (see normalize_query_name), so even an exact
        # key match can cover several differently-numbered real products
        # (e.g. "dextrose" covers both "50% Dextrose" and a hypothetical
        # "5% Dextrose") -- still has to pass the number guard, and gets
        # downgraded to "approximate" if the match relied on the candidate
        # having numbers the query never specified.
        if matched_generic is None and normalized_query in _ndc_generic_normalized_index:
            collision_raws = _ndc_generic_normalized_index[normalized_query]
            picked = _select_best_compatible_raw(collision_raws, raw_name)
            if picked is not None:
                matched_generic = picked
                candidate_numbers = extract_numbers_for_guard(picked)
                is_numeric_approx = not query_numbers and bool(candidate_numbers)
                match_method = "exact_normalized_generic_numeric_approx" if is_numeric_approx else "exact_normalized_generic"
        if matched_generic is None and normalized_query in _ndc_brand_normalized_index:
            brand_group = _ndc_brand_normalized_index[normalized_query]
            picked_brand = _select_best_compatible_raw(brand_group, raw_name)
            if picked_brand is not None:
                matched_row = ndc[ndc["brand_name"] == picked_brand].iloc[0]
                matched_generic = matched_row["generic_name"]
                candidate_numbers = extract_numbers_for_guard(picked_brand)
                is_numeric_approx = not query_numbers and bool(candidate_numbers)
                match_method = "exact_normalized_brand_numeric_approx" if is_numeric_approx else "exact_normalized_brand"

        if matched_generic is None and normalized_query:
            # check several candidates, not just the top one -- a wrong
            # candidate with a number mismatch (e.g. "50" vs "5") can
            # outscore a correct one, so the best-scoring match isn't
            # necessarily the first one that passes the number guard.
            candidates = process.extract(
                normalized_query, list(_ndc_generic_normalized_index.keys()),
                scorer=fuzz.token_sort_ratio, score_cutoff=QUERY_FUZZY_THRESHOLD, limit=5,
            )
            for candidate_key, score, _ in candidates:
                group = _ndc_generic_normalized_index[candidate_key]
                picked = _select_best_compatible_raw(group, raw_name)
                if picked is None:
                    continue
                collision_raws = group
                matched_generic = picked
                match_method = f"fuzzy_normalized_generic (score={score:.1f})"
                break

        if matched_generic is None:
            partial = generic_names[generic_names.str.lower().str.contains(name, na=False, regex=False)]
            if len(partial) > 0:
                matched_generic = partial.iloc[0]
                match_method = "partial_contains_raw"

    if matched_generic is None:
        return {
            "matched_generic_name": None,
            "manufacturer_count": None,
            "manufacturer_count_display": None,
            "primary_category": None,
            "dosage_category": None,
            "recall_count": 0,
            "match_method": None,
            "query_extracted_dosage_form": query_extracted_dosage,
        }

    manufacturer_count = int(manufacturer_counts.get(matched_generic, 1))
    manufacturer_count_display = _pooled_manufacturer_count(matched_generic, query_extracted_dosage)
    class_info = resolve_collision_class_info(matched_generic, collision_raws, query_extracted_dosage)
    recall_count = int(recall_counts_by_generic.get(matched_generic, 0))

    return {
        "matched_generic_name": matched_generic,
        "manufacturer_count": manufacturer_count,
        "manufacturer_count_display": manufacturer_count_display,
        "primary_category": class_info.get("primary_category"),
        "dosage_category": class_info.get("dosage_category"),
        "recall_count": recall_count,
        "match_method": match_method,
        "query_extracted_dosage_form": query_extracted_dosage,
    }

# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def build_feature_row(manufacturer_count: int, recall_count: int,
                       primary_category: str | None, dosage_category: str | None) -> pd.DataFrame:
    """Refuses to build a row when category or dosage is unresolved: an
    unresolved value must never be silently fed in as the baseline (e.g. an
    unmatched drug being scored as if it were a known Analgesia/Addiction,
    Injectable drug). Callers must check both are non-null first."""
    if primary_category is None or dosage_category is None:
        raise ValueError("build_feature_row requires a resolved primary_category and dosage_category")

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


_EXACT_MATCH_METHODS = {"exact_raw_generic", "exact_raw_brand", "exact_normalized_generic", "exact_normalized_brand"}


def classify_ndc_match_type(match_method: str | None) -> str | None:
    if match_method is None:
        return None
    if match_method in _EXACT_MATCH_METHODS:
        return "exact"
    return "approximate"  # fuzzy_normalized_generic (...) or partial_contains_raw


def build_drug_result(raw_name: str) -> dict:
    features = lookup_features(raw_name)
    matched_generic_name = features["matched_generic_name"]
    manufacturer_count = features["manufacturer_count"]
    manufacturer_count_display = features["manufacturer_count_display"]
    recall_count = features["recall_count"]
    primary_category = features["primary_category"]
    dosage_category = features["dosage_category"]

    shortage_status, fda_stated_reasons, matched_shortage_entries, shortage_match_type = \
        resolve_shortage_status_and_reasons(raw_name)

    cause_shown = (
        shortage_status == "current"
        and not fda_stated_reasons
        and primary_category is not None
        and dosage_category is not None
    )
    supply_probability = None
    if cause_shown:
        X = build_feature_row(manufacturer_count, recall_count, primary_category, dosage_category)
        supply_probability = float(model.predict_proba(X)[0][1])

    return {
        "name": raw_name,
        "matchedGenericName": matched_generic_name,
        "ndcMatchType": classify_ndc_match_type(features["match_method"]),
        "shortageMatchType": shortage_match_type,
        "shortageStatus": shortage_status,
        "fdaStatedReasons": fda_stated_reasons,
        "matchedShortageEntries": matched_shortage_entries,
        "facts": {
            "manufacturerCount": manufacturer_count_display,
            "recallCount": recall_count,
            "therapeuticClass": primary_category,
            "dosageForm": dosage_category,
        },
        "fewManufacturersFlag": manufacturer_count_display is not None and manufacturer_count_display in (1, 2),
        "causeEstimate": {
            "shown": cause_shown,
            "supplyProbability": supply_probability,
        },
    }

# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------

@app.post("/api/score-batch")
def score_batch(req: ScoreRequest):
    return {"dataAsOf": DATA_AS_OF, "results": [build_drug_result(name) for name in req.names]}


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
    return {"dataAsOf": DATA_AS_OF, **build_drug_result(name)}