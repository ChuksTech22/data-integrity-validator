"""Report generation: deterministic JSON (machine) and CSV (human).

Reports contain no timestamps and use stable ordering, so identical inputs and
configuration always produce byte-identical files.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Tuple

from . import __version__
from .io import LoadedCSV
from .validator import ValidationResult

CSV_COLUMNS = [
    "issue_id", "severity", "issue_type", "dataset", "record_id", "field",
    "expected", "observed", "normalization", "source_line", "destination_line",
    "explanation", "suggested_action",
]
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _input_meta(loaded: LoadedCSV) -> Dict[str, Any]:
    return {
        "path": loaded.path,
        "sha256": loaded.sha256,
        "rows": loaded.row_count,
        "columns": loaded.columns,
    }


def build_report(result: ValidationResult) -> Dict[str, Any]:
    return {
        "tool": {"name": "data-integrity-validator", "version": __version__},
        "inputs": {"source": _input_meta(result.source), "destination": _input_meta(result.destination)},
        "configuration": result.config.to_dict(),
        "summary": result.summary,
        "notes": result.notes,
        "issues": [i.to_dict() for i in result.issues],
    }


def _csv_safe(value: Any) -> Any:
    """Neutralize spreadsheet formula injection (CSV only; JSON keeps raw values)."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return "" if value is None else value


def write_reports(result: ValidationResult, output_dir: str) -> Tuple[Path, Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "integrity_report.json"
    csv_path = out / "integrity_report.csv"

    json_path.write_text(
        json.dumps(build_report(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for issue in result.issues:
            row = issue.to_dict()
            writer.writerow({c: _csv_safe(row[c]) for c in CSV_COLUMNS})
    return json_path, csv_path
