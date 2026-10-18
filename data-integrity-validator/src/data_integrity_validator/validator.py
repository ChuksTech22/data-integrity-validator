"""Orchestration: load -> schema -> rules -> keys -> comparison -> summary."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List

from .config import ValidatorConfig
from .duplicates import find_duplicate_ids, find_duplicate_records, find_missing_identifiers
from .exceptions import SchemaError
from .io import LoadedCSV, load_csv
from .matching import build_index, compare_datasets
from .models import DESTINATION, SOURCE, Issue, Severity
from .rules import validate_rules
from .schema import check_schema


@dataclass
class ValidationResult:
    source: LoadedCSV
    destination: LoadedCSV
    config: ValidatorConfig
    issues: List[Issue]
    summary: Dict[str, Any]
    notes: List[str] = field(default_factory=list)


def validate(source_path: str, destination_path: str, config: ValidatorConfig) -> ValidationResult:
    source = load_csv(source_path)
    destination = load_csv(destination_path)

    for label, loaded in ((SOURCE, source), (DESTINATION, destination)):
        absent = [k for k in config.keys if k not in loaded.columns]
        if absent:
            raise SchemaError(
                f"Key column(s) {absent} not found in {label} file {loaded.path}. "
                f"Columns present: {', '.join(loaded.columns)}"
            )

    issues: List[Issue] = []
    notes: List[str] = []
    for label, loaded in ((SOURCE, source), (DESTINATION, destination)):
        if loaded.skipped_blank_lines:
            notes.append(f"{label}: {loaded.skipped_blank_lines} blank line(s) were skipped while reading")

    issues += check_schema(source, destination, config)

    indexes = {}
    for label, loaded in ((SOURCE, source), (DESTINATION, destination)):
        idx = build_index(loaded, config)
        indexes[label] = idx
        rule_issues, rule_notes = validate_rules(loaded, label, config)
        issues += rule_issues
        notes += rule_notes
        issues += find_missing_identifiers(loaded, idx, label, config)
        issues += find_duplicate_ids(loaded, idx, label, config)
        issues += find_duplicate_records(loaded, idx, label, config)

    outcome = compare_datasets(source, destination, indexes[SOURCE], indexes[DESTINATION], config)
    issues += outcome.issues
    issues.sort(key=lambda i: i.sort_key())
    issues = [replace(i, issue_id=f"DIV-{n:04d}") for n, i in enumerate(issues, start=1)]

    by_severity = Counter(i.severity.value for i in issues)
    summary = {
        "records_checked": {"source": source.row_count, "destination": destination.row_count},
        "unique_keys": {
            "source": len(indexes[SOURCE].groups),
            "destination": len(indexes[DESTINATION].groups),
        },
        "records_matched": outcome.matched_ids,
        "missing_in_destination": sum(1 for i in outcome.issues if i.issue_type.value == "missing_record"),
        "unexpected_in_destination": sum(1 for i in outcome.issues if i.issue_type.value == "unexpected_record"),
        "field_values_compared": outcome.field_comparisons,
        "suppressed_formatting_differences": outcome.suppressed_formatting,
        "issues_total": len(issues),
        "issues_by_severity": {s.value: by_severity.get(s.value, 0) for s in Severity},
        "issues_by_type": dict(sorted(Counter(i.issue_type.value for i in issues).items())),
    }
    return ValidationResult(source, destination, config, issues, summary, notes)
