import hashlib

from data_integrity_validator.models import Severity
from helpers import run, triples, types, write_csv, cfg
from data_integrity_validator.validator import validate

BASE = "id,name,email\n1,Ann,ann@x.com\n2,Bob,bob@x.com\n"


def test_identical_files_produce_no_issues(tmp_path):
    r = run(tmp_path, BASE, BASE)
    assert r.issues == []
    assert r.summary["records_matched"] == 2
    assert r.summary["field_values_compared"] == 4  # 2 records x 2 non-id fields


def test_missing_and_unexpected_records(tmp_path):
    r = run(tmp_path, BASE, "id,name,email\n2,Bob,bob@x.com\n3,Cy,cy@x.com\n")
    assert triples(r) == {("missing_record", "1", "id"), ("unexpected_record", "3", "id")}
    assert r.summary["missing_in_destination"] == 1 and r.summary["unexpected_in_destination"] == 1


def test_each_difference_kind_is_distinguished(tmp_path):
    dst = "id,name,email\n1,Ann ,ANN@x.com\n2,,bobby@x.com\n"
    r = run(tmp_path, BASE, dst, normalization={"casefold_fields": ["email"]})
    assert triples(r) == {
        ("whitespace_difference", "1", "name"),
        ("formatting_difference", "1", "email"),
        ("missing_value", "2", "name"),
        ("value_mismatch", "2", "email"),
    }
    sev = {i.issue_type.value: i.severity for i in r.issues}
    assert sev["whitespace_difference"] == Severity.WARNING
    assert sev["formatting_difference"] == Severity.INFO
    assert sev["value_mismatch"] == Severity.ERROR


def test_issue_carries_expected_observed_and_lines(tmp_path):
    r = run(tmp_path, BASE, "id,name,email\n1,Ann,other@x.com\n2,Bob,bob@x.com\n")
    i = r.issues[0]
    assert (i.record_id, i.field, i.expected, i.observed) == ("1", "email", "ann@x.com", "other@x.com")
    assert i.source_line == 2 and i.destination_line == 2


def test_equal_row_counts_can_hide_errors(tmp_path):
    """Same row count, yet one record vanished and another was duplicated."""
    src = "id,v\n1,a\n2,b\n3,c\n"
    dst = "id,v\n1,a\n3,c\n3,c\n"
    r = run(tmp_path, src, dst)
    assert r.summary["records_checked"]["source"] == r.summary["records_checked"]["destination"] == 3
    assert triples(r) == {("missing_record", "2", "id"), ("duplicate_id", "3", "id")}


def test_every_destination_duplicate_is_compared(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\n1,x\n1,y\n")
    mism = [i for i in r.issues if i.issue_type.value == "value_mismatch"]
    assert [m.observed for m in mism] == ["x", "y"]


def test_identifier_whitespace_is_flagged(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n 1 ,a\n")
    assert types(r) == ["identifier_formatting"]


def test_suppressed_formatting_differences_are_counted(tmp_path):
    r = run(tmp_path, "id,e\n1,a@x.com\n", "id,e\n1,A@X.COM\n",
            normalization={"casefold_fields": ["e"], "report_formatting_differences": False})
    assert r.issues == [] and r.summary["suppressed_formatting_differences"] == 1


def test_severity_override_changes_reported_severity(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,b\n", severity_overrides={"value_mismatch": "warning"})
    assert r.issues[0].severity == Severity.WARNING


def test_ignored_columns_are_not_compared(tmp_path):
    r = run(tmp_path, "id,v,ts\n1,a,1\n", "id,v,ts\n1,a,2\n", ignore_columns=["ts"])
    assert r.issues == []


def test_inputs_are_never_modified(tmp_path):
    s = write_csv(tmp_path, "s.csv", "id,v\n1, a \n")
    d = write_csv(tmp_path, "d.csv", "id,v\n1,b\n")
    before = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in (s, d)]
    result = validate(s, d, cfg(normalization={"strip_whitespace": True}))
    after = [hashlib.sha256(open(p, "rb").read()).hexdigest() for p in (s, d)]
    assert before == after
    assert result.source.values("v") == [" a "]  # in-memory data also untouched
    assert result.source.sha256 == before[0]


def test_results_are_sorted_deterministically(tmp_path):
    a = run(tmp_path, "id,v\n2,x\n1,x\n", "id,v\n1,y\n2,y\n")
    b = run(tmp_path, "id,v\n1,x\n2,x\n", "id,v\n2,y\n1,y\n")
    assert [(i.record_id, i.field) for i in a.issues] == [(i.record_id, i.field) for i in b.issues]
