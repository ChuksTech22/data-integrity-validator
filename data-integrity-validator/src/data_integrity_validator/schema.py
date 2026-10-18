"""Schema validation: missing/unexpected columns and incompatible column types.

Type inference is deliberately simple and explainable: a column gets the
narrowest of integer < decimal < date < string that fits *every* non-blank
value. See the README for limitations (e.g. phone numbers or ZIP codes that
look like integers).
"""
from __future__ import annotations

import re
from typing import Callable, Iterable, List, Sequence

from .config import ValidatorConfig
from .io import LoadedCSV
from .models import DESTINATION, SOURCE, Issue, IssueType
from .normalize import parse_date, parse_decimal

_INT_RE = re.compile(r"^-?\d+$")


def _blank(value: str) -> bool:
    return value.strip() == ""


def infer_column_type(
    values: Iterable[str],
    date_formats: Sequence[str],
    is_null: Callable[[str], bool] = _blank,
) -> str:
    """Return 'empty', 'integer', 'decimal', 'date' or 'string' (null values are ignored)."""
    cells = [v.strip() for v in values if not is_null(v)]
    if not cells:
        return "empty"
    if all(_INT_RE.match(c) for c in cells):
        return "integer"
    if all(parse_decimal(c) is not None for c in cells):
        return "decimal"
    if date_formats and all(parse_date(c, date_formats) is not None for c in cells):
        return "date"
    return "string"


def types_compatible(a: str, b: str) -> bool:
    return a == b or "empty" in (a, b) or {a, b} == {"integer", "decimal"}


def _fits(expected: str, inferred: str) -> bool:
    if expected == "string" or inferred == "empty":
        return True
    if expected == "integer":
        return inferred == "integer"
    if expected == "decimal":
        return inferred in ("integer", "decimal")
    return inferred == expected  # date


def _misfits(values: Iterable[str], expected: str, formats: Sequence[str], limit: int = 3) -> List[str]:
    """Example values that do not fit the expected type (for readable messages)."""
    bad: List[str] = []
    for v in values:
        s = v.strip()
        if not s:
            continue
        ok = (
            expected == "string"
            or (expected == "integer" and _INT_RE.match(s))
            or (expected == "decimal" and parse_decimal(s) is not None)
            or (expected == "date" and parse_date(s, formats) is not None)
        )
        if not ok and s not in bad:
            bad.append(s)
        if len(bad) >= limit:
            break
    return bad


def check_schema(source: LoadedCSV, destination: LoadedCSV, config: ValidatorConfig) -> List[Issue]:
    issues: List[Issue] = []
    ignore = set(config.ignore_columns)
    src_cols = [c for c in source.columns if c not in ignore]
    dst_cols = [c for c in destination.columns if c not in ignore]

    for col in src_cols:
        if col not in dst_cols:
            issues.append(Issue(
                config.severity_for(IssueType.MISSING_COLUMN), IssueType.MISSING_COLUMN,
                DESTINATION, "", col, "column present", "column absent",
                f"Column {col!r} exists in the source but not in the destination; "
                "its values cannot be verified.",
            ))
    for col in dst_cols:
        if col not in src_cols:
            issues.append(Issue(
                config.severity_for(IssueType.UNEXPECTED_COLUMN), IssueType.UNEXPECTED_COLUMN,
                DESTINATION, "", col, "column absent", "column present",
                f"Column {col!r} exists in the destination but not in the source.",
            ))

    formats = config.all_date_formats()
    for col in src_cols:
        if col not in dst_cols:
            continue
        s_type = infer_column_type(source.values(col), formats, config.is_null)
        d_type = infer_column_type(destination.values(col), formats, config.is_null)
        if col in config.expected_types:
            expected = config.expected_types[col]
            for label, loaded, inferred in ((SOURCE, source, s_type), (DESTINATION, destination, d_type)):
                if not _fits(expected, inferred):
                    examples = _misfits(loaded.values(col), expected, formats)
                    issues.append(Issue(
                        config.severity_for(IssueType.TYPE_MISMATCH), IssueType.TYPE_MISMATCH,
                        label, "", col, expected, inferred,
                        f"Column {col!r} should be {expected} but {label} values look like "
                        f"{inferred}; non-conforming examples: {examples}.",
                    ))
        elif not types_compatible(s_type, d_type):
            examples = _misfits(destination.values(col), s_type, formats)
            issues.append(Issue(
                config.severity_for(IssueType.TYPE_MISMATCH), IssueType.TYPE_MISMATCH,
                DESTINATION, "", col, s_type, d_type,
                f"Column {col!r} is {s_type} in the source but {d_type} in the destination; "
                f"non-conforming destination examples: {examples}.",
            ))
    return issues
