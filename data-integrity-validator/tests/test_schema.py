import pytest

from data_integrity_validator.exceptions import SchemaError
from data_integrity_validator.schema import check_schema, infer_column_type, types_compatible
from data_integrity_validator.validator import validate
from helpers import cfg, load, run, triples, write_csv


@pytest.mark.parametrize("values,expected", [
    (["1", "2", "-3"], "integer"),
    (["1", "2.5"], "decimal"),
    (["2024-01-02", "2024-02-03"], "date"),
    (["a", "1"], "string"),
    (["", "  "], "empty"),
    (["1", "", "2"], "integer"),
    (["+2348035550101"], "decimal"),  # documented limitation: phone-like values look numeric
])
def test_infer_column_type(values, expected):
    assert infer_column_type(values, ["%Y-%m-%d"]) == expected


@pytest.mark.parametrize("a,b,ok", [
    ("integer", "integer", True), ("integer", "decimal", True), ("decimal", "integer", True),
    ("empty", "string", True), ("date", "string", False), ("decimal", "string", False),
])
def test_types_compatible(a, b, ok):
    assert types_compatible(a, b) == ok


def test_missing_and_unexpected_columns(tmp_path):
    src = load(tmp_path, "id,a,b\n1,x,y\n", "s.csv")
    dst = load(tmp_path, "id,a,c\n1,x,z\n", "d.csv")
    got = {(i.issue_type.value, i.field) for i in check_schema(src, dst, cfg())}
    assert got == {("missing_column", "b"), ("unexpected_column", "c")}


def test_incompatible_type_is_detected(tmp_path):
    src = load(tmp_path, "id,amt\n1,10.5\n2,20\n", "s.csv")
    dst = load(tmp_path, "id,amt\n1,10.5\n2,TBD\n", "d.csv")
    issues = check_schema(src, dst, cfg())
    assert [(i.issue_type.value, i.field, i.expected, i.observed) for i in issues] == [
        ("type_mismatch", "amt", "decimal", "string")
    ]
    assert "TBD" in issues[0].explanation


def test_integer_vs_decimal_is_compatible(tmp_path):
    src = load(tmp_path, "id,amt\n1,10\n", "s.csv")
    dst = load(tmp_path, "id,amt\n1,10.00\n", "d.csv")
    assert check_schema(src, dst, cfg()) == []


def test_expected_type_overrides_inference(tmp_path):
    src = load(tmp_path, "id,phone\n1,08035550101\n", "s.csv")
    dst = load(tmp_path, "id,phone\n1,0803 555 0101\n", "d.csv")
    assert check_schema(src, dst, cfg()) != []  # integer vs string, inferred
    assert check_schema(src, dst, cfg(expected_types={"phone": "string"})) == []


def test_expected_type_violation_reported_per_dataset(tmp_path):
    src = load(tmp_path, "id,qty\n1,5\n", "s.csv")
    dst = load(tmp_path, "id,qty\n1,five\n", "d.csv")
    issues = check_schema(src, dst, cfg(expected_types={"qty": "integer"}))
    assert [(i.dataset, i.field) for i in issues] == [("destination", "qty")]


def test_ignored_columns_are_not_schema_issues(tmp_path):
    src = load(tmp_path, "id,a\n1,x\n", "s.csv")
    dst = load(tmp_path, "id,a,import_batch\n1,x,B1\n", "d.csv")
    assert check_schema(src, dst, cfg(ignore_columns=["import_batch"])) == []


def test_null_tokens_do_not_distort_type_inference(tmp_path):
    src = load(tmp_path, "id,amt\n1,10\n2,N/A\n", "s.csv")
    dst = load(tmp_path, "id,amt\n1,10\n2,\n", "d.csv")
    assert check_schema(src, dst, cfg()) != []  # without tokens, "N/A" makes the column a string
    assert check_schema(src, dst, cfg(normalization={"null_tokens": ["N/A"]})) == []


def test_missing_id_column_is_fatal_with_clear_message(tmp_path):
    s = write_csv(tmp_path, "s.csv", "id,a\n1,x\n")
    d = write_csv(tmp_path, "d.csv", "key,a\n1,x\n")
    with pytest.raises(SchemaError, match=r"Key column\(s\) \['id'\] not found in destination"):
        validate(s, d, cfg())
