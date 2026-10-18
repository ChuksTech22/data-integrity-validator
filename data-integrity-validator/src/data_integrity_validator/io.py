"""CSV ingestion with strict, explicit error handling and no third-party dependencies.

Files are read as text only (no type guessing), so "007" stays "007" and empty
cells stay "" instead of silently becoming NaN or numbers.
"""
from __future__ import annotations

import csv
import hashlib
import io as _io
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from .exceptions import CSVLoadError


@dataclass(frozen=True)
class LoadedCSV:
    path: str
    header: Tuple[str, ...]
    rows: Tuple[Tuple[str, ...], ...]  # immutable: nothing downstream can alter the data
    lines: Tuple[int, ...]  # physical start line of each record (1 = header)
    sha256: str
    skipped_blank_lines: int

    @property
    def columns(self) -> List[str]:
        return list(self.header)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def values(self, column: str) -> List[str]:
        idx = self.header.index(column)
        return [row[idx] for row in self.rows]

    def record_id(self, position: int, keys: Sequence[str]) -> str:
        """Key value(s) joined by '|', or a '(line N)' label when any key part is absent/blank."""
        if all(k in self.header for k in keys):
            parts = [self.rows[position][self.header.index(k)].strip() for k in keys]
            if all(parts):
                return "|".join(parts)
        return f"(line {self.lines[position]})"


def load_csv(path: str) -> LoadedCSV:
    p = Path(path)
    if not p.exists():
        raise CSVLoadError(f"File not found: {path}")
    if p.is_dir():
        raise CSVLoadError(f"Expected a CSV file but got a directory: {path}")
    try:
        raw = p.read_bytes()
    except OSError as exc:
        raise CSVLoadError(f"Cannot read {path}: {exc}") from exc
    if not raw.strip():
        raise CSVLoadError(f"File is empty: {path}")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CSVLoadError(
            f"{path} is not valid UTF-8 (byte {exc.start}); re-export it as UTF-8"
        ) from exc

    reader = csv.reader(_io.StringIO(text, newline=""), strict=True)
    header: List[str] = []
    rows: List[Tuple[str, ...]] = []
    lines: List[int] = []
    blanks = 0
    last_line = 0
    try:
        for record in reader:
            start_line = last_line + 1
            last_line = reader.line_num
            if not record:
                blanks += 1
                continue
            if not header:
                header = record
                _check_header(header, path)
                continue
            if len(record) != len(header):
                raise CSVLoadError(
                    f"{path}: line {start_line} has {len(record)} fields, expected {len(header)}"
                )
            rows.append(tuple(record))
            lines.append(start_line)
    except csv.Error as exc:
        raise CSVLoadError(f"{path}: malformed CSV near line {reader.line_num}: {exc}") from exc
    if not header:
        raise CSVLoadError(f"{path} contains no header row")

    digest = hashlib.sha256(raw).hexdigest()
    return LoadedCSV(str(path), tuple(header), tuple(rows), tuple(lines), digest, blanks)


def _check_header(header: List[str], path: str) -> None:
    if any(h.strip() == "" for h in header):
        raise CSVLoadError(f"{path}: header contains an empty column name")
    seen = set()
    for h in header:
        if h in seen:
            raise CSVLoadError(f"{path}: duplicate column name {h!r} in header")
        seen.add(h)
