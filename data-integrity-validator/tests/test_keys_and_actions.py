"""Composite keys, null keys, allowed values, null tokens, issue metadata."""
import io

import pytest

from data_integrity_validator.io import load_csv
from data_integrity_validator.models import SUGGESTED_ACTION, IssueType
from helpers import cfg, load, run, triples, types, write_csv
from data_integrity_validator.rules import validate_rules

PEOPLE = "first,last,city\nAnn,Lee,Lagos\nAnn,Kay,Accra\nBen,Lee,Abuja\n"


def test_composite_key_matches_on_all_parts(tmp_path):
    r = run(tmp_path, PEOPLE, PEOPLE, key_columns=["first", "last"])
    assert r.issues == [] and r.summary["records_matched"] == 3


def test_single_column_would_have_seen_these_as_duplicates(tmp_path):
    r = run(tmp_path, PEOPLE, PEOPLE, id_column="first")
    assert "duplicate_id" in types(r)


def test_composite_key_reports_missing_and_changed_values(tmp_path):
    dst = "first,last,city\nAnn,Lee,Lagos\nBen,Lee,Kano\n"
    r = run(tmp_path, PEOPLE, dst, key_columns=["first", "last"])
    assert triples(r) == {
        ("missing_record", "Ann|Kay", "first|last"),
        ("value_mismatch", "Ben|Lee", "city"),
    }


def test_composite_duplicate_key(tmp_path):
    dst = PEOPLE + "Ann,Lee,Lagos\n"
    r = run(tmp_path, PEOPLE, dst, key_columns=["first", "last"])
    assert ("duplicate_id", "Ann|Lee", "first|last") in triples(r)


def test_partially_null_composite_key_is_reported_not_matched(tmp_path):
    dst = "first,last,city\nAnn,,Lagos\nAnn,Kay,Accra\nBen,Lee,Abuja\n"
    r = run(tmp_path, PEOPLE, dst, key_columns=["first", "last"])
    got = triples(r)
    assert ("missing_identifier", "(line 2)", "first|last") in got
    assert ("missing_record", "Ann|Lee", "first|last") in got  # nothing silently absorbed


def test_null_token_key_is_treated_as_null(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\nNULL,b\n", normalization={"null_tokens": ["NULL"]})
    assert triples(r) == {("missing_identifier", "NULL", "id")}


def test_composite_key_columns_must_exist(tmp_path):
    from data_integrity_validator.exceptions import SchemaError
    from data_integrity_validator.validator import validate
    s = write_csv(tmp_path, "s.csv", PEOPLE)
    d = write_csv(tmp_path, "d.csv", "first,city\nAnn,Lagos\n")
    with pytest.raises(SchemaError, match="last"):
        validate(s, d, cfg(key_columns=["first", "last"]))


# ---- allowed values -------------------------------------------------
def test_allowed_values_rule(tmp_path):
    loaded = load(tmp_path, "id,stage\n1,lead\n2,Lead\n3,\n4, customer \n5,vip\n")
    issues, _ = validate_rules(loaded, "destination", cfg(allowed_values={"stage": ["lead", "customer"]}))
    assert [(i.record_id, i.observed) for i in issues] == [("2", "Lead"), ("5", "vip")]
    assert issues[0].issue_type == IssueType.RULE_ALLOWED
    assert issues[0].expected == "one of: lead, customer"


# ---- null tokens ----------------------------------------------------
def test_null_tokens_make_required_rule_and_comparison_consistent(tmp_path):
    norm = {"null_tokens": ["N/A"]}
    r = run(tmp_path, "id,email\n1,a@x.com\n", "id,email\n1,N/A\n", normalization=norm, required_fields=["email"])
    assert triples(r) == {("missing_value", "1", "email"), ("rule_required_field", "1", "email")}


def test_different_null_spellings_are_formatting_not_mismatch(tmp_path):
    r = run(tmp_path, "id,v\n1,NULL\n", "id,v\n1,\n", normalization={"null_tokens": ["NULL"]})
    assert triples(r) == {("formatting_difference", "1", "v")}
    assert r.issues[0].normalization == "null_token"


# ---- issue metadata ---------------------------------------------------
def test_every_issue_type_has_a_suggested_action():
    assert set(SUGGESTED_ACTION) == set(IssueType)
    assert all(len(text) > 20 for text in SUGGESTED_ACTION.values())


def test_issues_have_sequential_ids_and_actions(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n2,b\n3,c\n", "id,v\n1,x\n3,c\n4,z\n")
    assert [i.issue_id for i in r.issues] == [f"DIV-{n:04d}" for n in range(1, len(r.issues) + 1)]
    assert all(i.suggested_action for i in r.issues)


def test_formatting_issue_names_the_normalization_that_applied(tmp_path):
    r = run(tmp_path, "id,e\n1,a@x.com\n", "id,e\n1,A@X.COM\n", normalization={"casefold_fields": ["e"]})
    issue = r.issues[0]
    assert issue.normalization == "casefold"
    assert "casefold" in issue.explanation and "value mismatch" in issue.explanation


def test_loaded_data_is_immutable(tmp_path):
    loaded = load(tmp_path, "id,v\n1,a\n")
    assert isinstance(loaded.rows, tuple) and isinstance(loaded.rows[0], tuple)
    with pytest.raises(TypeError):
        loaded.rows[0][1] = "changed"
