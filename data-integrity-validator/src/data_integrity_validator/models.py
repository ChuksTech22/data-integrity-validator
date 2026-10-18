"""Core data types: issue severities, issue categories and the Issue record."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Lower rank = more severe. Used for sorting and --fail-on."""
        return {"error": 0, "warning": 1, "info": 2}[self.value]


class IssueType(str, Enum):
    # schema
    MISSING_COLUMN = "missing_column"
    UNEXPECTED_COLUMN = "unexpected_column"
    TYPE_MISMATCH = "type_mismatch"
    # identifiers / records
    MISSING_IDENTIFIER = "missing_identifier"
    DUPLICATE_ID = "duplicate_id"
    DUPLICATE_RECORD = "duplicate_record"
    MISSING_RECORD = "missing_record"
    UNEXPECTED_RECORD = "unexpected_record"
    IDENTIFIER_FORMATTING = "identifier_formatting"
    # field-level comparison
    VALUE_MISMATCH = "value_mismatch"
    MISSING_VALUE = "missing_value"
    UNEXPECTED_VALUE = "unexpected_value"
    WHITESPACE_DIFFERENCE = "whitespace_difference"
    FORMATTING_DIFFERENCE = "formatting_difference"
    # configurable integrity rules
    RULE_REQUIRED = "rule_required_field"
    RULE_EMAIL = "rule_email_format"
    RULE_NOT_NUMERIC = "rule_not_numeric"
    RULE_RANGE = "rule_numeric_range"
    RULE_DATE = "rule_date_format"
    RULE_ALLOWED = "rule_allowed_value"


DEFAULT_SEVERITY = {
    IssueType.MISSING_COLUMN: Severity.ERROR,
    IssueType.UNEXPECTED_COLUMN: Severity.WARNING,
    IssueType.TYPE_MISMATCH: Severity.ERROR,
    IssueType.MISSING_IDENTIFIER: Severity.ERROR,
    IssueType.DUPLICATE_ID: Severity.ERROR,
    IssueType.DUPLICATE_RECORD: Severity.WARNING,
    IssueType.MISSING_RECORD: Severity.ERROR,
    IssueType.UNEXPECTED_RECORD: Severity.WARNING,
    IssueType.IDENTIFIER_FORMATTING: Severity.WARNING,
    IssueType.VALUE_MISMATCH: Severity.ERROR,
    IssueType.MISSING_VALUE: Severity.ERROR,
    IssueType.UNEXPECTED_VALUE: Severity.WARNING,
    IssueType.WHITESPACE_DIFFERENCE: Severity.WARNING,
    IssueType.FORMATTING_DIFFERENCE: Severity.INFO,
    IssueType.RULE_REQUIRED: Severity.ERROR,
    IssueType.RULE_EMAIL: Severity.ERROR,
    IssueType.RULE_NOT_NUMERIC: Severity.ERROR,
    IssueType.RULE_RANGE: Severity.ERROR,
    IssueType.RULE_DATE: Severity.ERROR,
    IssueType.RULE_ALLOWED: Severity.ERROR,
}

SUGGESTED_ACTION = {
    IssueType.MISSING_COLUMN: "Check the field mapping in the migration tool and re-import the column, or confirm it was dropped on purpose.",
    IssueType.UNEXPECTED_COLUMN: "Confirm the column is intentional (for example import metadata); otherwise remove it or add it to ignore_columns.",
    IssueType.TYPE_MISMATCH: "Find the non-conforming values in the column and correct them, or fix the field type in the destination.",
    IssueType.MISSING_IDENTIFIER: "Supply the missing key value or exclude the row; rows without a complete key cannot be reconciled.",
    IssueType.DUPLICATE_ID: "Decide which row is authoritative, merge or delete the others, and check whether the import ran twice.",
    IssueType.DUPLICATE_RECORD: "Review both records; merge or delete the copy if the import created it.",
    IssueType.MISSING_RECORD: "Look for the record in the migration error log; re-import it or confirm it was excluded on purpose.",
    IssueType.UNEXPECTED_RECORD: "Trace where the record came from; remove it if it should not exist, or add it to the source if it should.",
    IssueType.IDENTIFIER_FORMATTING: "Standardize the identifier format in both systems so exact matching works.",
    IssueType.VALUE_MISMATCH: "Compare the record in both systems, decide which value is correct, and fix the wrong side.",
    IssueType.MISSING_VALUE: "Check the field mapping and import log, then restore the value from the source.",
    IssueType.UNEXPECTED_VALUE: "Find out where the destination value came from (default, enrichment or manual edit) and confirm it is wanted.",
    IssueType.WHITESPACE_DIFFERENCE: "Trim the whitespace in the destination (or enable cleanup in the import) to avoid failed lookups later.",
    IssueType.FORMATTING_DIFFERENCE: "Usually no action; standardize the format only if downstream systems are format-sensitive.",
    IssueType.RULE_REQUIRED: "Populate the required field or investigate why the value was lost.",
    IssueType.RULE_EMAIL: "Correct the email address from the source record or from the contact owner.",
    IssueType.RULE_NOT_NUMERIC: "Replace the non-numeric text with a valid number taken from the source.",
    IssueType.RULE_RANGE: "Verify the value against the source; look for sign or decimal-place errors.",
    IssueType.RULE_DATE: "Convert the date to the required format and double-check the day/month order.",
    IssueType.RULE_ALLOWED: "Map the value to one of the allowed values, or extend the allowed list if it is newly valid.",
}

SOURCE = "source"
DESTINATION = "destination"
COMPARISON = "comparison"


@dataclass(frozen=True)
class Issue:
    """One detected problem. Immutable so results cannot be altered after the fact."""

    severity: Severity
    issue_type: IssueType
    dataset: str  # "source", "destination" or "comparison"
    record_id: str  # "" for schema-level issues
    field: str
    expected: str
    observed: str
    explanation: str
    source_line: Optional[int] = None  # physical line in the file; 1 = header
    destination_line: Optional[int] = None
    normalization: str = ""  # which normalization made two values equivalent, if any
    suggested_action: str = ""  # filled from SUGGESTED_ACTION when left empty
    issue_id: str = ""  # assigned after sorting, e.g. DIV-0001

    def __post_init__(self) -> None:
        if not self.suggested_action:
            object.__setattr__(self, "suggested_action", SUGGESTED_ACTION[self.issue_type])

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "severity": self.severity.value,
            "issue_type": self.issue_type.value,
            "dataset": self.dataset,
            "record_id": self.record_id,
            "field": self.field,
            "expected": self.expected,
            "observed": self.observed,
            "explanation": self.explanation,
            "normalization": self.normalization,
            "suggested_action": self.suggested_action,
            "source_line": self.source_line,
            "destination_line": self.destination_line,
        }

    def sort_key(self) -> tuple:
        return (
            self.severity.rank,
            self.record_id,
            self.field,
            self.issue_type.value,
            self.dataset,
            self.source_line or 0,
            self.destination_line or 0,
        )


def line_fields(dataset: str, line: Optional[int]) -> dict:
    """Map a physical line number onto the right Issue keyword argument."""
    if dataset == SOURCE:
        return {"source_line": line}
    if dataset == DESTINATION:
        return {"destination_line": line}
    return {}
