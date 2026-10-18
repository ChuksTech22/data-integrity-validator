"""Key indexing (single or composite) and record-to-record comparison."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .config import ValidatorConfig
from .io import LoadedCSV
from .models import COMPARISON, Issue, IssueType
from .normalize import classify

Key = Tuple[str, ...]


@dataclass
class IdIndex:
    groups: Dict[Key, List[int]] = field(default_factory=dict)  # key -> row positions, file order
    blank: List[int] = field(default_factory=list)  # rows whose key is null or incomplete


def key_columns_data(loaded: LoadedCSV, config: ValidatorConfig) -> List[List[str]]:
    return [loaded.values(c) for c in config.keys]


def build_index(loaded: LoadedCSV, config: ValidatorConfig) -> IdIndex:
    """Group rows by key. A row with ANY null key part is set aside, never matched or dropped."""
    index = IdIndex()
    cols = key_columns_data(loaded, config)
    for pos in range(loaded.row_count):
        parts = tuple(col[pos].strip() for col in cols)
        if any(config.is_null(p) for p in parts):
            index.blank.append(pos)
            continue
        key = parts if config.id_case_sensitive else tuple(p.casefold() for p in parts)
        index.groups.setdefault(key, []).append(pos)
    return index


@dataclass
class ComparisonOutcome:
    issues: List[Issue]
    matched_ids: int
    field_comparisons: int
    suppressed_formatting: int


_LABEL = {
    IssueType.VALUE_MISMATCH: "Value differs between source and destination.",
    IssueType.MISSING_VALUE: "Value present in source is empty in destination.",
    IssueType.UNEXPECTED_VALUE: "Value is empty in source but filled in destination.",
}


def _message(kind: IssueType, src: str, dst: str, how: str) -> str:
    if kind == IssueType.WHITESPACE_DIFFERENCE:
        return f"Values differ only in whitespace: source {src!r} vs destination {dst!r}."
    if kind == IssueType.FORMATTING_DIFFERENCE:
        return (f"Values are equivalent after '{how}' normalization but formatted differently: "
                f"{src!r} vs {dst!r}. Without that normalization this would be a value mismatch.")
    return _LABEL[kind]


def compare_datasets(
    source: LoadedCSV,
    destination: LoadedCSV,
    src_index: IdIndex,
    dst_index: IdIndex,
    config: ValidatorConfig,
) -> ComparisonOutcome:
    """Compare matched records field by field.

    For keys that are duplicated, EVERY destination occurrence is compared against
    the FIRST source occurrence (duplicates are reported separately), so no
    destination row is skipped.
    """
    ignore = set(config.ignore_columns) | set(config.keys)
    dst_cols = set(destination.columns)
    common = [c for c in source.columns if c in dst_cols and c not in ignore]
    src_data = {c: source.values(c) for c in common}
    dst_data = {c: destination.values(c) for c in common}
    src_keys = key_columns_data(source, config)
    dst_keys = key_columns_data(destination, config)
    key_field = config.key_field_name

    issues: List[Issue] = []
    matched = comparisons = suppressed = 0

    for key, s_positions in src_index.groups.items():
        s_pos = s_positions[0]
        s_label = source.record_id(s_pos, config.keys)
        if key not in dst_index.groups:
            issues.append(Issue(
                config.severity_for(IssueType.MISSING_RECORD), IssueType.MISSING_RECORD,
                COMPARISON, s_label, key_field, "record present in destination", "record absent",
                f"Record {s_label!r} exists in the source but was not found in the destination.",
                source_line=source.lines[s_pos],
            ))
            continue
        matched += 1
        s_raw = tuple(col[s_pos] for col in src_keys)
        for d_pos in dst_index.groups[key]:
            d_raw = tuple(col[d_pos] for col in dst_keys)
            if s_raw != d_raw:
                issues.append(Issue(
                    config.severity_for(IssueType.IDENTIFIER_FORMATTING), IssueType.IDENTIFIER_FORMATTING,
                    COMPARISON, s_label, key_field, "|".join(s_raw), "|".join(d_raw),
                    "Keys matched only after normalization (whitespace/case).",
                    source_line=source.lines[s_pos], destination_line=destination.lines[d_pos],
                    normalization="key_whitespace_case",
                ))
            for col in common:
                s_val, d_val = src_data[col][s_pos], dst_data[col][d_pos]
                comparisons += 1
                kind, how = classify(col, s_val, d_val, config.normalization)
                if kind is None:
                    continue
                if kind == IssueType.FORMATTING_DIFFERENCE and not config.normalization.report_formatting_differences:
                    suppressed += 1  # counted and surfaced in the summary, never silent
                    continue
                issues.append(Issue(
                    config.severity_for(kind), kind, COMPARISON, s_label, col, s_val, d_val,
                    _message(kind, s_val, d_val, how),
                    source_line=source.lines[s_pos], destination_line=destination.lines[d_pos],
                    normalization=how,
                ))

    for key, d_positions in dst_index.groups.items():
        if key not in src_index.groups:
            d_pos = d_positions[0]
            label = destination.record_id(d_pos, config.keys)
            issues.append(Issue(
                config.severity_for(IssueType.UNEXPECTED_RECORD), IssueType.UNEXPECTED_RECORD,
                COMPARISON, label, key_field, "record absent", "record present",
                f"Record {label!r} exists in the destination but not in the source.",
                destination_line=destination.lines[d_pos],
            ))
    return ComparisonOutcome(issues, matched, comparisons, suppressed)
