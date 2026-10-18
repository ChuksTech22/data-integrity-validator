"""Proves the validator finds every injected error in the synthetic sample data.

The answer key (examples/known_errors.json) was written by hand when the data
was built; it is independent of the validator's output.
"""
import json

import pytest

from data_integrity_validator.config import ValidatorConfig
from data_integrity_validator.validator import validate
from helpers import EXAMPLES, triples

KEY = json.loads((EXAMPLES / "known_errors.json").read_text(encoding="utf-8"))["expected_issues"]
KEY_TUPLES = [(e["issue_type"], e["record_id"], e["field"]) for e in KEY]


def run_example():
    return validate(
        str(EXAMPLES / "source.csv"), str(EXAMPLES / "destination.csv"),
        ValidatorConfig.from_json_file(str(EXAMPLES / "config.json")),
    )


@pytest.mark.parametrize("issue_type,record_id,field", KEY_TUPLES)
def test_each_known_error_is_detected(issue_type, record_id, field):
    assert (issue_type, record_id, field) in triples(run_example())


def test_nothing_beyond_the_answer_key_is_reported():
    """No false positives: the validator reports exactly the injected errors."""
    assert triples(run_example()) == set(KEY_TUPLES)
    assert len(run_example().issues) == len(KEY_TUPLES)


def test_summary_counts_match_the_sample_files():
    s = run_example().summary
    assert s["records_checked"] == {"source": 30, "destination": 31}
    assert s["unique_keys"] == {"source": 30, "destination": 29}
    assert s["records_matched"] == 27
    assert s["missing_in_destination"] == 3 and s["unexpected_in_destination"] == 2
    assert sum(s["issues_by_severity"].values()) == s["issues_total"] == 28


def test_a_file_compared_with_itself_is_clean():
    """Control experiment: no issues when nothing is wrong."""
    src = str(EXAMPLES / "source.csv")
    result = validate(src, src, ValidatorConfig.from_json_file(str(EXAMPLES / "config.json")))
    assert result.issues == []


def test_row_counts_alone_would_have_missed_most_errors():
    """30 vs 31 rows looks like a near-perfect transfer, yet 28 issues exist."""
    s = run_example().summary
    assert abs(s["records_checked"]["source"] - s["records_checked"]["destination"]) == 1
    assert s["issues_total"] > 20
