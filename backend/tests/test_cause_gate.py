# Tests for the causeEstimate gate (build_drug_result) and the drug-level
# shortage status rule (resolve_shortage_status_and_reasons). The gate must
# only show a cause estimate when status is current AND no stated reasons
# exist AND both class and dosage form are resolved; build_feature_row must
# refuse to build a row at all when class or dosage is unresolved.
#
# Run from backend/, with the venv active: pytest tests/test_cause_gate.py
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main import build_drug_result, build_feature_row, resolve_shortage_status_and_reasons


# --- status/reason lookup must not depend on the NDC match succeeding ---

def test_albuterol_returns_a_listed_status():
    # regression test: the NDC match for "albuterol" used to resolve to the
    # bare "Albuterol" NDC entry, which drug_class_lookup never attached
    # shortage data to (only "Albuterol Sulfate" was). Status must come
    # from matching the query against shortages.csv directly.
    r = build_drug_result("albuterol")
    assert r["shortageStatus"] != "not_listed"


def test_lisdexamfetamine_returns_nonempty_reasons_and_no_estimate():
    r = build_drug_result("lisdexamfetamine dimesylate")
    assert r["shortageStatus"] == "current"
    assert len(r["fdaStatedReasons"]) > 0
    assert r["causeEstimate"]["shown"] is False


def test_shortages_only_drug_with_no_ndc_match_still_gets_status():
    # Rifapentine has no NDC directory entry at all (confirmed: the NDC
    # match fails entirely), but it IS one of the 237 shortages.csv drugs
    # and must still get a real status, not "not_listed".
    r = build_drug_result("Rifapentine Tablet, Film Coated")
    assert r["matchedGenericName"] is None
    assert r["shortageStatus"] == "resolved"


# --- causeEstimate gate: each of the four conditions, checked with real drugs ---

def test_unknown_class_gives_no_estimate():
    # ibuprofen resolves (matched NDC entry) but has no shortage history,
    # so class/dosage are both null.
    r = build_drug_result("ibuprofen")
    assert r["facts"]["therapeuticClass"] is None
    assert r["causeEstimate"]["shown"] is False
    assert r["causeEstimate"]["supplyProbability"] is None


def test_stated_reason_gives_no_estimate():
    # Morphine Sulfate is Current with stated reasons on its records.
    r = build_drug_result("Morphine Sulfate")
    assert r["shortageStatus"] == "current"
    assert len(r["fdaStatedReasons"]) > 0
    assert r["causeEstimate"]["shown"] is False


def test_not_listed_gives_no_estimate():
    # cisplatin has zero occurrences of any form in shortages.csv (verified
    # by substring search); "sodium chloride" is no longer a valid
    # not_listed example since the strength-token-stripping fix lets it
    # correctly match "Sodium Chloride 0.9% Injection".
    r = build_drug_result("cisplatin")
    assert r["shortageStatus"] == "not_listed"
    assert r["causeEstimate"]["shown"] is False


def test_resolved_gives_no_estimate():
    # Triamcinolone Acetonide Injection's records are all status=Resolved,
    # and it's a clean single-entry normalized match (unlike
    # "Hydrocortisone Sodium Succinate", which collides on the shared
    # "hydrocortisone" key with "Hydrocortisone Acetate Suppository" --
    # a To Be Discontinued record -- and would misleadingly resolve to
    # to_be_discontinued if used here).
    r = build_drug_result("Triamcinolone Acetonide Injection")
    assert r["shortageStatus"] == "resolved"
    assert r["causeEstimate"]["shown"] is False


def test_all_four_conditions_met_gives_an_estimate():
    # Albuterol Sulfate Solution: current, no stated reason, class and
    # dosage both resolved, and confirmed NOT one of the 55 distinct drug
    # names among the 57 training events (those all have a stated reason
    # by definition, since that's how is_supply_side was labeled).
    r = build_drug_result("Albuterol Sulfate Solution")
    assert r["shortageStatus"] == "current"
    assert r["fdaStatedReasons"] == []
    assert r["facts"]["therapeuticClass"] is not None
    assert r["facts"]["dosageForm"] is not None
    assert r["causeEstimate"]["shown"] is True
    assert r["causeEstimate"]["supplyProbability"] is not None
    assert 0.0 <= r["causeEstimate"]["supplyProbability"] <= 1.0


def test_build_feature_row_refuses_unresolved_category():
    with pytest.raises(ValueError):
        build_feature_row(5, 0, None, "Oral")


def test_build_feature_row_refuses_unresolved_dosage():
    with pytest.raises(ValueError):
        build_feature_row(5, 0, "Cardiovascular", None)


def test_build_feature_row_refuses_both_unresolved():
    with pytest.raises(ValueError):
        build_feature_row(5, 0, None, None)


def test_build_feature_row_succeeds_when_both_resolved():
    X = build_feature_row(5, 0, "Cardiovascular", "Oral")
    assert X.shape[0] == 1


# --- drug-level status rule ---

def test_status_rule_no_match_is_not_listed():
    status, reasons, entries = resolve_shortage_status_and_reasons("")
    assert status == "not_listed"
    assert reasons == []
    assert entries == []


def test_status_rule_unknown_source_name_is_not_listed():
    status, reasons, entries = resolve_shortage_status_and_reasons("Not A Real Shortages Drug Name")
    assert status == "not_listed"
    assert reasons == []
    assert entries == []


def test_status_rule_all_resolved_records_gives_resolved():
    status, _, _ = resolve_shortage_status_and_reasons("Triamcinolone Acetonide Injection")
    assert status == "resolved"


def test_status_rule_dosage_aware_pooling_isolates_matching_presentation():
    # "Hydrocortisone Sodium Succinate Injection" (all Resolved) and
    # "Hydrocortisone Acetate Suppository" (all To Be Discontinued) both
    # normalize to bare "hydrocortisone" -- but the query here specifies a
    # dosage form ("injection"), so pooling must be restricted to the
    # matching presentation only, not pick up the unrelated suppository.
    status, _, entries = resolve_shortage_status_and_reasons("Hydrocortisone Sodium Succinate Injection")
    assert status == "resolved"
    assert entries == [{"name": "Hydrocortisone Sodium Succinate Injection", "status": "resolved"}]


def test_status_rule_pools_across_colliding_names_when_dosage_unspecified():
    # without a dosage form in the query, both presentations are pooled and
    # the ambiguity is visible via matchedShortageEntries -- a documented,
    # known limitation of querying a collision group with no dosage hint.
    status, _, entries = resolve_shortage_status_and_reasons("Hydrocortisone Sodium Succinate")
    assert status == "to_be_discontinued"
    assert len(entries) == 2
    assert {"name": "Hydrocortisone Acetate Suppository", "status": "to_be_discontinued"} in entries


def test_status_rule_current_mixed_with_discontinued_gives_current():
    # Atropine Sulfate Injection mixes Current and To Be Discontinued across
    # its records (confirmed during Step A fact-finding); Current must win.
    status, _, _ = resolve_shortage_status_and_reasons("Atropine Sulfate Injection")
    assert status == "current"


def test_status_rule_reasons_are_distinct_and_verbatim():
    _, reasons, _ = resolve_shortage_status_and_reasons("Morphine Sulfate Injection")
    assert len(reasons) == len(set(reasons))  # no duplicates
    assert all(isinstance(r, str) for r in reasons)
