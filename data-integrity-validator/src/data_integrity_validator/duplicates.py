"""Key and duplicate-record checks, run independently on each dataset."""
from __future__ import annotations

from typing import Dict, List, Tuple

from .config import ValidatorConfig
from .io import LoadedCSV
from .matching import IdIndex
from .models import Issue, IssueType, line_fields
from .normalize import collapse_whitespace


def find_missing_identifiers(loaded: LoadedCSV, index: IdIndex, dataset: str, config: ValidatorConfig) -> List[Issue]:
    """Rows with a null/incomplete key cannot be matched; report them instead of dropping them."""
    return [
        Issue(
            config.severity_for(IssueType.MISSING_IDENTIFIER), IssueType.MISSING_IDENTIFIER, dataset,
            loaded.record_id(pos, config.keys), config.key_field_name, "complete, non-null key", "",
            "Row has a null or incomplete key, so it cannot be matched or compared.",
            **line_fields(dataset, loaded.lines[pos]),
        )
        for pos in index.blank
    ]


def find_duplicate_ids(loaded: LoadedCSV, index: IdIndex, dataset: str, config: ValidatorConfig) -> List[Issue]:
    issues: List[Issue] = []
    for positions in index.groups.values():
        if len(positions) < 2:
            continue
        rows = [loaded.rows[p] for p in positions]
        identical = all(r == rows[0] for r in rows[1:])
        where = ", ".join(str(loaded.lines[p]) for p in positions)
        detail = "all occurrences are identical" if identical else "occurrences contain conflicting values"
        issues.append(Issue(
            config.severity_for(IssueType.DUPLICATE_ID), IssueType.DUPLICATE_ID, dataset,
            loaded.record_id(positions[0], config.keys), config.key_field_name,
            "1 occurrence (unique key)", f"{len(positions)} occurrences",
            f"Key appears {len(positions)} times (lines {where}); {detail}.",
            **line_fields(dataset, loaded.lines[positions[0]]),
        ))
    return issues


def find_duplicate_records(loaded: LoadedCSV, index: IdIndex, dataset: str, config: ValidatorConfig) -> List[Issue]:
    """Different keys, identical content (whitespace-insensitive, all columns except the key)."""
    skip = set(config.ignore_columns) | set(config.keys)
    content_cols = [c for c in loaded.columns if c not in skip]
    if not content_cols:
        return []
    data = {c: loaded.values(c) for c in content_cols}
    signatures: Dict[Tuple[str, ...], List[int]] = {}
    for positions in index.groups.values():
        pos = positions[0]  # same-key rows are covered by duplicate_id
        sig = tuple(collapse_whitespace(data[c][pos]) for c in content_cols)
        if any(sig):
            signatures.setdefault(sig, []).append(pos)

    issues: List[Issue] = []
    for positions in signatures.values():
        if len(positions) < 2:
            continue
        first = positions[0]
        first_id = loaded.record_id(first, config.keys)
        for pos in positions[1:]:
            issues.append(Issue(
                config.severity_for(IssueType.DUPLICATE_RECORD), IssueType.DUPLICATE_RECORD, dataset,
                loaded.record_id(pos, config.keys), "*", "unique record content",
                f"identical to record {first_id}",
                f"All non-key fields match record {first_id!r} (line {loaded.lines[first]}); "
                "possible duplicate created under a new key.",
                **line_fields(dataset, loaded.lines[pos]),
            ))
    return issues
