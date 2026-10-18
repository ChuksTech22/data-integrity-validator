import pytest

from data_integrity_validator.rules import is_valid_email, validate_rules
from helpers import cfg, load


@pytest.mark.parametrize("email", ["a@b.co", "first.last+tag@sub.example.com", "x_y%z@a-b.org", " pad@x.com "])
def test_valid_emails(email):
    assert is_valid_email(email)


@pytest.mark.parametrize("email", ["a@b", "a@@b.com", "@b.com", "a b@c.com", ".a@b.com", "a..b@c.com", "a@b.c", "plain"])
def test_invalid_emails(email):
    assert not is_valid_email(email)


def run_rules(tmp_path, text, **config):
    return validate_rules(load(tmp_path, text), "destination", cfg(**config))


def test_required_field_flags_blank_and_whitespace_only(tmp_path):
    issues, _ = run_rules(tmp_path, 'id,email\n1,a@b.com\n2,\n3,"  "\n', required_fields=["email"])
    assert [(i.record_id, i.issue_type.value) for i in issues] == [("2", "rule_required_field"), ("3", "rule_required_field")]
    assert issues[0].destination_line == 3 and issues[0].source_line is None


def test_email_rule_skips_blank_values(tmp_path):
    issues, _ = run_rules(tmp_path, "id,email\n1,\n2,bad@x\n", email_fields=["email"])
    assert [(i.record_id, i.observed) for i in issues] == [("2", "bad@x")]


@pytest.mark.parametrize("value,flagged,kind", [
    ("0", False, None), ("100", False, None), ("50.5", False, None),
    ("-0.01", True, "rule_numeric_range"), ("100.01", True, "rule_numeric_range"),
    ("abc", True, "rule_not_numeric"), ("1,000", True, "rule_not_numeric"), ("", False, None),
])
def test_numeric_range_bounds_are_inclusive(tmp_path, value, flagged, kind):
    issues, _ = run_rules(tmp_path, f'id,amt\n1,"{value}"\n', numeric_ranges={"amt": {"min": 0, "max": 100}})
    assert bool(issues) == flagged
    if flagged:
        assert issues[0].issue_type.value == kind


def test_one_sided_range(tmp_path):
    issues, _ = run_rules(tmp_path, "id,amt\n1,-5\n2,9999\n", numeric_ranges={"amt": {"min": 0}})
    assert [i.record_id for i in issues] == ["1"]


@pytest.mark.parametrize("value,ok", [
    ("2024-03-05", True), ("2024-3-5", False), ("2024-02-30", False), ("05/03/2024", False),
])
def test_date_rule_is_strict(tmp_path, value, ok):
    issues, _ = run_rules(tmp_path, f"id,d\n1,{value}\n", date_fields={"d": "%Y-%m-%d"})
    assert (issues == []) == ok


def test_rule_on_absent_column_is_noted_not_silent(tmp_path):
    issues, notes = run_rules(tmp_path, "id,a\n1,x\n", required_fields=["email"])
    assert issues == []
    assert any("email" in n and "skipped" in n for n in notes)


def test_blank_identifier_uses_line_label(tmp_path):
    issues, _ = run_rules(tmp_path, "id,email\n,\n", required_fields=["email"])
    assert issues[0].record_id == "(line 2)"
