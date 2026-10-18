import json

import pytest

from data_integrity_validator.config import ValidatorConfig
from data_integrity_validator.exceptions import ConfigError
from data_integrity_validator.models import IssueType, Severity


def test_defaults():
    c = ValidatorConfig()
    assert c.id_column == "id" and c.normalization.strip_whitespace is True
    assert c.severity_for(IssueType.VALUE_MISMATCH) == Severity.ERROR
    assert c.severity_for(IssueType.FORMATTING_DIFFERENCE) == Severity.INFO


@pytest.mark.parametrize("bad", [
    {"requried_fields": ["x"]},  # typo must not silently disable a rule
    {"normalization": {"strip_whitespaces": True}},
    {"id_column": ""},
    {"required_fields": "email"},
    {"numeric_ranges": {"a": {}}},
    {"numeric_ranges": {"a": {"min": 5, "max": 1}}},
    {"numeric_ranges": {"a": {"min": "abc"}}},
    {"expected_types": {"a": "float"}},
    {"severity_overrides": {"not_a_type": "error"}},
    {"severity_overrides": {"value_mismatch": "fatal"}},
    {"date_fields": {"d": "%Q-%Q"}},
    {"normalization": {"strip_whitespace": "yes"}},
])
def test_invalid_configs_raise(bad):
    with pytest.raises(ConfigError):
        ValidatorConfig.from_dict(bad)


def test_non_object_config():
    with pytest.raises(ConfigError):
        ValidatorConfig.from_dict([1, 2])


def test_severity_override_applies():
    c = ValidatorConfig.from_dict({"severity_overrides": {"whitespace_difference": "info"}})
    assert c.severity_for(IssueType.WHITESPACE_DIFFERENCE) == Severity.INFO


def test_from_json_file_errors(tmp_path):
    with pytest.raises(ConfigError, match="Cannot read"):
        ValidatorConfig.from_json_file(str(tmp_path / "missing.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ConfigError, match="not valid JSON"):
        ValidatorConfig.from_json_file(str(bad))


def test_round_trip_to_dict_is_json_serializable():
    c = ValidatorConfig.from_dict({
        "id_column": "k", "numeric_ranges": {"x": {"min": 0, "max": 10.5}},
        "date_fields": {"d": "%Y-%m-%d"},
    })
    data = json.loads(json.dumps(c.to_dict()))
    assert data["numeric_ranges"]["x"] == {"min": "0", "max": "10.5"}
    assert data["key_columns"] == ["k"]
    assert ValidatorConfig.from_dict({"id_column": data["key_columns"][0]}).keys == ["k"]


@pytest.mark.parametrize("bad", [
    {"key_columns": []},
    {"key_columns": ["a", "a"]},
    {"key_columns": ["a", ""]},
    {"id_column": "a", "key_columns": ["a", "b"]},  # ambiguous: refuse to guess
    {"allowed_values": {"a": []}},
    {"allowed_values": {"a": "x"}},
    {"normalization": {"null_tokens": "NULL"}},
])
def test_invalid_key_and_rule_configs(bad):
    with pytest.raises(ConfigError):
        ValidatorConfig.from_dict(bad)


def test_composite_keys_and_null_tokens():
    c = ValidatorConfig.from_dict({"key_columns": ["a", "b"], "normalization": {"null_tokens": ["NULL", "n/a"]}})
    assert c.keys == ["a", "b"] and c.key_field_name == "a|b"
    assert c.is_null("") and c.is_null("  ") and c.is_null("null") and c.is_null(" N/A ")
    assert not c.is_null("none")
