"""Configurable integrity rules applied to a single dataset.

Rules judge the *stripped* value and treat blanks and configured null tokens as null (skipped
by format rules, flagged by the required rule). Allowed-value matching is exact and case-sensitive. Whitespace differences against the source are
reported separately by the comparison stage.
"""
from __future__ import annotations

import re
from typing import List

from .config import ValidatorConfig
from .io import LoadedCSV
from .models import Issue, IssueType, line_fields
from .normalize import parse_date, parse_decimal

_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9._%+\-]+@(?:[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)


def is_valid_email(value: str) -> bool:
    s = value.strip()
    if not _EMAIL_RE.match(s):
        return False
    local = s.rsplit("@", 1)[0]
    return not (local.startswith(".") or local.endswith(".") or ".." in local)


def strict_date_ok(value: str, fmt: str) -> bool:
    return parse_date(value, [fmt]) is not None


def validate_rules(loaded: LoadedCSV, dataset: str, config: ValidatorConfig) -> "tuple[List[Issue], List[str]]":
    """Return (issues, notes). Notes record any rule skipped because a column is absent."""
    issues: List[Issue] = []
    notes: List[str] = []
    cols = set(loaded.columns)

    def usable(column: str, rule: str) -> bool:
        if column in cols:
            return True
        notes.append(f"Rule '{rule}' skipped for column {column!r} in {dataset}: column absent")
        return False

    def add(t: IssueType, pos: int, col: str, expected: str, observed: str, msg: str) -> None:
        issues.append(Issue(
            config.severity_for(t), t, dataset, loaded.record_id(pos, config.keys),
            col, expected, observed, msg, **line_fields(dataset, loaded.lines[pos]),
        ))

    for col in config.required_fields:
        if usable(col, "required"):
            for pos, v in enumerate(loaded.values(col)):
                if config.is_null(v):
                    add(IssueType.RULE_REQUIRED, pos, col, "non-empty value", v,
                        f"Required field {col!r} is empty.")

    for col in config.email_fields:
        if usable(col, "email"):
            for pos, v in enumerate(loaded.values(col)):
                if not config.is_null(v) and not is_valid_email(v):
                    add(IssueType.RULE_EMAIL, pos, col, "valid email address", v,
                        f"{v!r} is not a well-formed email address.")

    for col, rng in config.numeric_ranges.items():
        if not usable(col, "numeric_range"):
            continue
        for pos, v in enumerate(loaded.values(col)):
            if config.is_null(v):
                continue
            num = parse_decimal(v)
            if num is None:
                add(IssueType.RULE_NOT_NUMERIC, pos, col, "numeric value", v,
                    f"{v!r} is not numeric, so the range check cannot be applied.")
                continue
            if (rng.minimum is not None and num < rng.minimum) or (
                rng.maximum is not None and num > rng.maximum
            ):
                bounds = f"{rng.minimum if rng.minimum is not None else '-inf'} to " \
                         f"{rng.maximum if rng.maximum is not None else '+inf'}"
                add(IssueType.RULE_RANGE, pos, col, f"value between {bounds}", v,
                    f"{v} is outside the allowed range ({bounds}).")

    for col, allowed in config.allowed_values.items():
        if usable(col, "allowed_values"):
            for pos, v in enumerate(loaded.values(col)):
                if not config.is_null(v) and v.strip() not in allowed:
                    add(IssueType.RULE_ALLOWED, pos, col, "one of: " + ", ".join(allowed), v,
                        f"{v!r} is not in the allowed list for {col!r}.")

    for col, fmt in config.date_fields.items():
        if usable(col, "date_format"):
            for pos, v in enumerate(loaded.values(col)):
                if not config.is_null(v) and not strict_date_ok(v, fmt):
                    add(IssueType.RULE_DATE, pos, col, f"date in format {fmt}", v,
                        f"{v!r} does not match the required date format {fmt} (or is not a real date).")
    return issues, notes
