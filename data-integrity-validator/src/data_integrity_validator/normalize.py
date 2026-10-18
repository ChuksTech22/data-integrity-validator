"""Value parsing and difference classification.

Nothing here mutates data. Normalization is applied to *copies of values inside
comparison functions* purely to decide what KIND of difference exists
(whitespace, formatting, or a genuine mismatch). Every difference is still
reported, and the report names the normalization that made two values equivalent.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional, Tuple

from .config import NormalizationConfig
from .models import IssueType

_DECIMAL_RE = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def is_blank(value: str) -> bool:
    """Whitespace-only values are treated as empty."""
    return value.strip() == ""


def collapse_whitespace(value: str) -> str:
    """Trim and collapse any run of whitespace (including NBSP) to one space."""
    return " ".join(value.split())


def parse_decimal(value: str) -> Optional[Decimal]:
    """Strict decimal parse: no thousands separators, no currency symbols, finite only."""
    s = value.strip()
    if not _DECIMAL_RE.match(s):
        return None
    return Decimal(s)


def parse_date(value: str, formats: Iterable[str]) -> Optional[date]:
    """Parse with the first matching format; round-trips to reject loose input like 2024-3-5."""
    s = value.strip()
    for fmt in formats:
        try:
            parsed = datetime.strptime(s, fmt)
        except ValueError:
            continue
        if parsed.strftime(fmt) == s:
            return parsed.date()
    return None


def phone_digits(value: str) -> str:
    return re.sub(r"\D", "", value)


def classify(
    field: str, source: str, destination: str, norm: NormalizationConfig
) -> Tuple[Optional[IssueType], str]:
    """Return (kind of difference or None, name of the normalization that reconciled the values).

    The second element is "" unless the values only matched after normalization.
    """
    if source == destination:
        return None, ""

    s_null, d_null = norm.is_null(source), norm.is_null(destination)
    if s_null and d_null:
        if is_blank(source) and is_blank(destination):
            return IssueType.WHITESPACE_DIFFERENCE, "whitespace"
        return IssueType.FORMATTING_DIFFERENCE, "null_token"
    if d_null:
        return IssueType.MISSING_VALUE, ""
    if s_null:
        return IssueType.UNEXPECTED_VALUE, ""

    a, b = source, destination
    if norm.strip_whitespace:
        a, b = collapse_whitespace(a), collapse_whitespace(b)
        if a == b:
            return IssueType.WHITESPACE_DIFFERENCE, "whitespace"
    if norm.unicode_nfc:
        a, b = unicodedata.normalize("NFC", a), unicodedata.normalize("NFC", b)
        if a == b:
            return IssueType.FORMATTING_DIFFERENCE, "unicode_nfc"
    if field in norm.casefold_fields and a.casefold() == b.casefold():
        return IssueType.FORMATTING_DIFFERENCE, "casefold"
    if field in norm.phone_fields:
        da, db = phone_digits(a), phone_digits(b)
        if da and da == db:
            return IssueType.FORMATTING_DIFFERENCE, "phone_digits"
    if field in norm.numeric_fields:
        na, nb = parse_decimal(a), parse_decimal(b)
        if na is not None and nb is not None and na == nb:
            return IssueType.FORMATTING_DIFFERENCE, "numeric_value"
    if field in norm.date_fields:
        formats = norm.accepted_date_formats
        da_, db_ = parse_date(a, formats), parse_date(b, formats)
        if da_ is not None and da_ == db_:
            return IssueType.FORMATTING_DIFFERENCE, "date_value"
    return IssueType.VALUE_MISMATCH, ""


def classify_difference(
    field: str, source: str, destination: str, norm: NormalizationConfig
) -> Optional[IssueType]:
    """Convenience wrapper returning only the kind of difference."""
    return classify(field, source, destination, norm)[0]
