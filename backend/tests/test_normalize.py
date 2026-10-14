# Tests for main.normalize_query_name() and the collision tiebreak in
# resolve_collision_class_info(): the query-side normalization added in
# Phase 2 to fix lookup_features() failing on dosage-form-suffixed names.
#
# Run from backend/, with the venv active: pytest tests/test_normalize.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main import (
    normalize_query_name, resolve_collision_class_info, _ndc_generic_normalized_index,
    extract_numbers_for_guard, _numbers_compatible, lookup_features, build_drug_result,
    count_ingredients, _pre_strip_tokens, _rank_by_token_overlap,
)


def test_lowercases_and_strips_punctuation():
    # "sulfate" is also a salt word, so it's stripped too -- this tests
    # punctuation handling combined with that, not punctuation in isolation.
    name, dosage = normalize_query_name("Albuterol-Sulfate, Inc.")
    assert name == "albuterol inc"


def test_strips_single_salt_word():
    name, dosage = normalize_query_name("Albuterol Sulfate")
    assert name == "albuterol"
    assert dosage is None


def test_strips_dosage_word_injection_and_extracts_injectable():
    name, dosage = normalize_query_name("Lincomycin Hydrochloride Injection")
    assert name == "lincomycin"
    assert dosage == "Injectable"


def test_strips_tablet_and_extracts_oral():
    name, dosage = normalize_query_name("Quinapril Hydrochloride Tablet")
    assert name == "quinapril"
    assert dosage == "Oral"


def test_strips_capsule_and_extracts_oral():
    name, dosage = normalize_query_name("Ursodiol Capsule")
    assert name == "ursodiol"
    assert dosage == "Oral"


def test_oral_plus_solution_combination_extracts_oral():
    name, dosage = normalize_query_name("Oxycodone Hydrochloride Oral Solution")
    assert name == "oxycodone"
    assert dosage == "Oral"


def test_unrecognized_dosage_form_extracts_other():
    name, dosage = normalize_query_name("Podofilox Topical Gel")
    assert name == "podofilox"
    assert dosage == "Other"


def test_no_dosage_form_present_extracts_none():
    name, dosage = normalize_query_name("metformin")
    assert name == "metformin"
    assert dosage is None


def test_multiple_salts_and_dosage_in_one_name():
    name, dosage = normalize_query_name("Acetaminophen; Oxycodone Hydrochloride Tablet")
    assert "acetaminophen" in name
    assert "oxycodone" in name
    assert "hydrochloride" not in name
    assert "tablet" not in name
    assert dosage == "Oral"


def test_whitespace_collapses_after_stripping():
    name, dosage = normalize_query_name("Epinephrine   Bitartrate    Injection")
    assert name == "epinephrine"
    assert "  " not in name


def test_case_insensitive():
    lower_name, lower_dosage = normalize_query_name("ibuprofen tablet")
    upper_name, upper_dosage = normalize_query_name("IBUPROFEN TABLET")
    assert lower_name == upper_name
    assert lower_dosage == upper_dosage


def test_powder_for_solution_strips_for_as_dosage_word():
    name, dosage = normalize_query_name("Streptozocin Powder, For Solution")
    assert name == "streptozocin"
    assert dosage == "Other"


# --- electrolyte collision guard ---
# A cation word (sodium/potassium/calcium/magnesium) in first position, or
# whose removal would leave only other salt/ion words, must not be stripped.
# Otherwise "Sodium Chloride", "Potassium Chloride", and "Calcium Chloride"
# would all collapse onto the same normalized key.

def test_sodium_chloride_not_collapsed():
    name, dosage = normalize_query_name("Sodium Chloride Injection")
    assert name == "sodium chloride"


def test_potassium_chloride_not_collapsed():
    name, dosage = normalize_query_name("Potassium Chloride Injection")
    assert name == "potassium chloride"


def test_calcium_chloride_not_collapsed():
    name, dosage = normalize_query_name("Calcium Chloride Injection")
    assert name == "calcium chloride"


def test_sodium_bicarbonate_not_collapsed():
    name, dosage = normalize_query_name("Sodium Bicarbonate Injection")
    assert name == "sodium bicarbonate"


def test_naproxen_sodium_still_strips_trailing_cation():
    # a cation word NOT in first position is still strippable, since it's
    # genuinely just a salt-form suffix here, not part of a two-word name.
    name, dosage = normalize_query_name("Naproxen Sodium Tablet")
    assert name == "naproxen"


def test_sodium_potassium_calcium_chloride_are_distinct_keys():
    sodium, _ = normalize_query_name("Sodium Chloride")
    potassium, _ = normalize_query_name("Potassium Chloride")
    calcium, _ = normalize_query_name("Calcium Chloride")
    assert len({sodium, potassium, calcium}) == 3


def test_parenthetical_qualifier_stripped():
    # ports the parenthetical-stripping fix from drug_class_lookup's own
    # normalization, so a query matches an NDC entry like "Ursodiol (Process
    # IV)" without needing to type the manufacturing qualifier.
    name, dosage = normalize_query_name("Ursodiol (Process IV)")
    assert name == "ursodiol"


# --- hydrocortisone collision tiebreak ---
# "hydrocortisone" normalizes 22 distinct raw NDC names onto one key; two of
# them resolve to conflicting therapeutic classes (Analgesia/Addiction vs
# Pulmonary/Allergy). Picking either arbitrarily is misleading, so the
# resolver should prefer the dosage-matching variant, or report the class
# as unknown rather than guess.

def test_hydrocortisone_collision_resolves_by_matching_dosage_form():
    raws = _ndc_generic_normalized_index["hydrocortisone"]
    info = resolve_collision_class_info(raws[0], raws, "Injectable")
    assert info.get("primary_category") == "Pulmonary/Allergy"
    assert info.get("dosage_category") == "Injectable"


def test_hydrocortisone_collision_with_no_dosage_hint_returns_unknown_class():
    raws = _ndc_generic_normalized_index["hydrocortisone"]
    info = resolve_collision_class_info(raws[0], raws, None)
    assert info.get("primary_category") is None


def test_hydrocortisone_collision_with_unmatched_dosage_hint_returns_unknown_class():
    raws = _ndc_generic_normalized_index["hydrocortisone"]
    # no raw in this collision group has dosage_category "Oral"
    info = resolve_collision_class_info(raws[0], raws, "Oral")
    assert info.get("primary_category") is None


def test_non_colliding_key_is_unaffected_by_tiebreak():
    # a key with only one raw name (or no conflicting classes) should just
    # return that name's own class info, untouched.
    raws = _ndc_generic_normalized_index["lincomycin"]
    info = resolve_collision_class_info(raws[0], raws, None)
    assert info.get("primary_category") == "Anti-Infective"


# --- number guard: reject only when both sides have numbers and the
# candidate's aren't a subset of the query's. Missing numbers on either
# side pass -- that's missing information, not a conflict. ---

def test_extract_numbers_parses_decimals_as_one_token():
    # must run before punctuation stripping would split "0.9" into "0"/"9".
    assert extract_numbers_for_guard("Sodium Chloride 0.9% Injection") == frozenset({"0.9"})


def test_extract_numbers_handles_multiple_numbers():
    assert extract_numbers_for_guard("Sodium Chloride 0.9% 1000mL") == frozenset({"0.9", "1000"})


def test_numbers_compatible_when_neither_side_has_numbers():
    assert _numbers_compatible(frozenset(), frozenset()) is True


def test_numbers_compatible_when_query_only_has_numbers():
    # "metformin 500 mg" vs "metformin" -- query-only numbers pass.
    assert _numbers_compatible(frozenset({"500"}), frozenset()) is True


def test_numbers_compatible_when_candidate_only_has_numbers():
    # "sodium chloride" vs "Sodium Chloride 0.9%" -- candidate-only numbers
    # pass too (missing info on the query side, not a conflict).
    assert _numbers_compatible(frozenset(), frozenset({"0.9"})) is True


def test_numbers_incompatible_on_genuine_conflict():
    # dextrose 5% vs 50% dextrose -- both sides specify, and disagree.
    assert _numbers_compatible(frozenset({"5"}), frozenset({"50"})) is False


def test_numbers_compatible_when_candidate_subset_of_query():
    # candidate's number(s) all appear in the query's -- query is just more
    # specific (extra info), not conflicting.
    assert _numbers_compatible(frozenset({"0.9", "1000"}), frozenset({"0.9"})) is True


def test_candidate_only_numbers_downgrades_match_type_to_approximate():
    # "teriparatide" used to exercise this on the incomplete NDC file (exact-
    # key-matched a numbered candidate); the complete re-pulled file now has
    # a literal "teriparatide" entry, so it exact-raw-matches directly
    # instead. "Octinoxate Zinc Oxide" (no numbers) exact-key-matches
    # "Octinoxate 6% Zinc Oxide 3%", which carries numbers the query never
    # specified -- candidate-only numbers, so matchType downgrades to
    # approximate even though the key matched exactly.
    f = lookup_features("Octinoxate Zinc Oxide")
    assert f["matched_generic_name"] is not None
    assert f["match_method"] == "exact_normalized_generic_numeric_approx"


def test_query_only_numbers_stays_exact():
    r = build_drug_result("Sodium Chloride 0.9% 1000mL")
    assert r["ndcMatchType"] == "exact"


# --- pharmacy-style abbreviation expansion, applied before normalization ---

def test_hcl_abbreviation_expands_to_hydrochloride():
    name, _ = normalize_query_name("Metformin HCl")
    assert name == "metformin"  # hydrochloride is then stripped as a salt word


def test_tab_and_caps_abbreviations_expand_to_dosage_words():
    name1, dosage1 = normalize_query_name("Lisinopril Tab")
    name2, dosage2 = normalize_query_name("Amoxicillin Caps")
    assert name1 == "lisinopril" and dosage1 == "Oral"
    assert name2 == "amoxicillin" and dosage2 == "Oral"


def test_inj_and_soln_abbreviations_expand_to_dosage_words():
    name1, dosage1 = normalize_query_name("Furosemide Inj")
    name2, dosage2 = normalize_query_name("Dextrose Soln")
    assert dosage1 == "Injectable"
    assert dosage2 == "Other"  # "solution" alone, without "oral", isn't classified Oral


def test_er_xr_xl_sr_dr_abbreviations_are_stripped_as_dosage_words():
    for abbrev in ["ER", "XR", "XL", "SR"]:
        name, _ = normalize_query_name(f"Metformin {abbrev}")
        assert name == "metformin"
    name_dr, _ = normalize_query_name("Omeprazole DR")
    assert name_dr == "omeprazole"


def test_hfa_abbreviation_treated_as_inhalation_dosage_word():
    name, _ = normalize_query_name("Albuterol HFA")
    assert name == "albuterol"


def test_strength_and_unit_tokens_stripped_from_key_but_numbers_tracked():
    name, _ = normalize_query_name("Metformin HCl 500mg Tab")
    assert name == "metformin"
    assert extract_numbers_for_guard("Metformin HCl 500mg Tab") == frozenset({"500"})


# --- matchedShortageEntries (dosage-aware pooling on the shortages side) ---

def test_matched_shortage_entries_present_in_response():
    r = build_drug_result("lisdexamfetamine dimesylate")
    assert isinstance(r["matchedShortageEntries"], list)
    assert len(r["matchedShortageEntries"]) >= 1
    assert all({"name", "status"} <= set(e.keys()) for e in r["matchedShortageEntries"])


# --- ingredient count rule: reject a candidate whose ingredient count
# differs from the query's, regardless of numbers ---

def test_count_ingredients_single():
    assert count_ingredients("Dextrose 5% Injection") == 1


def test_count_ingredients_comma_separated():
    assert count_ingredients(
        "Dextrose Monohydrate, Sodium Chloride, Sodium Lactate, Calcium Chloride, Magnesium Chloride"
    ) == 5


def test_count_ingredients_and_separated():
    assert count_ingredients("Acetaminophen and Oxycodone Hydrochloride") == 2


def test_count_ingredients_semicolon_and_slash_separated():
    assert count_ingredients("Atazanavir Sulfate; Cobicistat") == 2
    assert count_ingredients("Quinapril Hydrochloride/Hydrochlorothiazide") == 2


def test_dextrose_5_percent_does_not_match_5_ingredient_combo():
    # the fix for the headline bug: "Dextrose 5% inj" (1 ingredient) must
    # not match a 5-ingredient electrolyte combo just because the combo's
    # other ingredients are all salt/cation words that strip to nothing.
    f = lookup_features("Dextrose 5% inj")
    assert f["matched_generic_name"] is not None
    assert count_ingredients(f["matched_generic_name"]) == 1


def test_dextrose_50_percent_does_not_match_5_ingredient_combo():
    f = lookup_features("Dextrose 50%")
    assert f["matched_generic_name"] is not None
    assert count_ingredients(f["matched_generic_name"]) == 1


# --- collision-group ranking: prefer the candidate with the most token
# overlap with the query (after abbreviation expansion, before salt/dosage
# stripping), then fewest extra tokens ---

def test_rank_by_token_overlap_prefers_more_shared_tokens():
    query_tokens = _pre_strip_tokens("Hydrocortisone Sodium Succinate Injection")
    raws = _ndc_generic_normalized_index["hydrocortisone"]
    ranked = _rank_by_token_overlap(raws, query_tokens)
    assert "sodium" in _pre_strip_tokens(ranked[0])
    assert "succinate" in _pre_strip_tokens(ranked[0])


def test_hydrocortisone_sodium_succinate_query_picks_sodium_succinate_variant():
    # not the acetate variant, which used to win just by being first in
    # insertion order.
    f = lookup_features("Hydrocortisone sodium succinate 100mg inj")
    assert "succinate" in f["matched_generic_name"].lower()
    assert "acetate" not in f["matched_generic_name"].lower()
    assert f["primary_category"] == "Pulmonary/Allergy"


def test_metformin_hcl_tab_query_does_not_pick_er_variant():
    # not the extended-release variant, which shares fewer tokens with the
    # query than a plain hydrochloride/tablet variant does.
    f = lookup_features("Metformin HCl 500mg Tab")
    assert "er" not in f["matched_generic_name"].lower().split()
    assert "extended" not in f["matched_generic_name"].lower()


def test_matched_generic_and_class_come_from_the_same_variant():
    # the class/dosage returned must describe the SAME raw name reported
    # as matchedGenericName, not a different collision-group member.
    f = lookup_features("Hydrocortisone sodium succinate 100mg inj")
    from main import drug_class_lookup
    own_info = drug_class_lookup.get(f["matched_generic_name"])
    if own_info and own_info.get("primary_category"):
        assert f["primary_category"] == own_info["primary_category"]


# --- ndcMatchType / shortageMatchType are reported separately ---

def test_ndc_and_shortage_match_types_are_both_present_and_independent():
    r = build_drug_result("lincomycin hydrochloride")
    assert "ndcMatchType" in r
    assert "shortageMatchType" in r
    assert "matchType" not in r
    assert r["ndcMatchType"] == "exact"
    assert r["shortageMatchType"] == "exact"


def test_shortage_match_type_is_none_when_not_listed():
    r = build_drug_result("cisplatin")
    assert r["shortageStatus"] == "not_listed"
    assert r["shortageMatchType"] is None
