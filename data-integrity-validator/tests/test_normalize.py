import pytest

from data_integrity_validator.config import NormalizationConfig
from data_integrity_validator.normalize import (
    classify_difference, collapse_whitespace, parse_date, parse_decimal,
)

NORM = NormalizationConfig(
    casefold_fields=["email"], phone_fields=["phone"], numeric_fields=["amount"],
    date_fields=["when"], accepted_date_formats=["%Y-%m-%d", "%m/%d/%Y"],
)


@pytest.mark.parametrize("field,src,dst,expected", [
    ("name", "Ann", "Ann", None),
    ("name", "Ann", "Ann ", "whitespace_difference"),
    ("name", "Ann  Lee", "Ann Lee", "whitespace_difference"),
    ("name", "Ann\u00a0Lee", "Ann Lee", "whitespace_difference"),
    ("name", " ", "", "whitespace_difference"),
    ("name", "Ann", "", "missing_value"),
    ("name", "Ann", "   ", "missing_value"),
    ("name", "", "Ann", "unexpected_value"),
    ("name", "Ann", "Anne", "value_mismatch"),
    ("name", "ann", "ANN", "value_mismatch"),  # case only ignored for configured fields
    ("email", "a@x.com", "A@X.com", "formatting_difference"),
    ("email", "a@x.com", "b@x.com", "value_mismatch"),
    ("phone", "+234 803 555", "+234803555", "formatting_difference"),
    ("phone", "+234803555", "+234803556", "value_mismatch"),
    ("amount", "1000", "1000.00", "formatting_difference"),
    ("amount", "1000", "1001", "value_mismatch"),
    ("amount", "1000", "abc", "value_mismatch"),
    ("amount", "1,000", "1000", "value_mismatch"),  # thousands separators are NOT guessed
    ("when", "2024-03-15", "03/15/2024", "formatting_difference"),
    ("when", "2024-03-15", "2024-03-16", "value_mismatch"),
    ("name", "e\u0301", "\u00e9", "formatting_difference"),  # NFD vs NFC
])
def test_classify_difference(field, src, dst, expected):
    result = classify_difference(field, src, dst, NORM)
    assert (result.value if result else None) == expected


def test_whitespace_normalization_can_be_disabled():
    strict = NormalizationConfig(strip_whitespace=False)
    assert classify_difference("name", "Ann", "Ann ", strict).value == "value_mismatch"


@pytest.mark.parametrize("text,ok", [
    ("-250.00", True), ("0", True), (".5", True), ("1e3", True),
    ("1,000", False), ("$5", False), ("NaN", False), ("Infinity", False), ("1_000", False), ("", False),
])
def test_parse_decimal(text, ok):
    assert (parse_decimal(text) is not None) == ok


@pytest.mark.parametrize("text,ok", [
    ("2024-03-05", True), ("2024-3-5", False), ("2024-02-30", False), ("05/03/2024", False), ("", False),
])
def test_parse_date_is_strict(text, ok):
    assert (parse_date(text, ["%Y-%m-%d"]) is not None) == ok


def test_collapse_whitespace():
    assert collapse_whitespace("  a \t b\n") == "a b"
