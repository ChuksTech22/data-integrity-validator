"""Configuration: what to validate, how to normalize, and how severe each issue is.

Every key is validated on load. Unknown keys raise ConfigError so that a typo
(``"requried_fields"``) can never silently disable a rule.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import ConfigError
from .models import DEFAULT_SEVERITY, IssueType, Severity

VALID_TYPES = ("string", "integer", "decimal", "date")


def _check_keys(data: Dict[str, Any], allowed: set, where: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ConfigError(
            f"Unknown key(s) in {where}: {', '.join(unknown)}. "
            f"Allowed: {', '.join(sorted(allowed))}"
        )


def _str_list(value: Any, name: str) -> List[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"'{name}' must be a list of strings")
    return list(value)


def _bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"'{name}' must be true or false")
    return value


def _check_date_format(fmt: str, name: str) -> None:
    try:
        datetime.strptime(datetime(2001, 2, 3).strftime(fmt), fmt)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"Invalid date format {fmt!r} in '{name}': {exc}") from exc


@dataclass(frozen=True)
class NumericRange:
    minimum: Optional[Decimal] = None
    maximum: Optional[Decimal] = None

    @classmethod
    def from_dict(cls, data: Any, name: str) -> "NumericRange":
        if not isinstance(data, dict):
            raise ConfigError(f"numeric_ranges['{name}'] must be an object with min and/or max")
        _check_keys(data, {"min", "max"}, f"numeric_ranges['{name}']")
        if not data:
            raise ConfigError(f"numeric_ranges['{name}'] needs at least one of min/max")
        try:
            lo = Decimal(str(data["min"])) if "min" in data else None
            hi = Decimal(str(data["max"])) if "max" in data else None
        except InvalidOperation as exc:
            raise ConfigError(f"numeric_ranges['{name}'] has a non-numeric bound") from exc
        if lo is not None and hi is not None and lo > hi:
            raise ConfigError(f"numeric_ranges['{name}']: min is greater than max")
        return cls(lo, hi)

    def to_dict(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.minimum is not None:
            out["min"] = str(self.minimum)
        if self.maximum is not None:
            out["max"] = str(self.maximum)
        return out


@dataclass
class NormalizationConfig:
    """Normalization is used ONLY to classify differences; data is never rewritten."""

    strip_whitespace: bool = True
    unicode_nfc: bool = True
    casefold_fields: List[str] = field(default_factory=list)
    phone_fields: List[str] = field(default_factory=list)
    numeric_fields: List[str] = field(default_factory=list)
    date_fields: List[str] = field(default_factory=list)
    accepted_date_formats: List[str] = field(default_factory=lambda: ["%Y-%m-%d"])
    null_tokens: List[str] = field(default_factory=list)  # extra spellings of "no value", e.g. ["NULL", "N/A"]
    report_formatting_differences: bool = True

    def is_null(self, value: str) -> bool:
        """Blank/whitespace-only, or one of the explicitly configured null tokens."""
        stripped = value.strip()
        if stripped == "":
            return True
        return any(stripped.casefold() == t.casefold() for t in self.null_tokens)

    @classmethod
    def from_dict(cls, data: Any) -> "NormalizationConfig":
        if not isinstance(data, dict):
            raise ConfigError("'normalization' must be an object")
        keys = set(cls.__dataclass_fields__)
        _check_keys(data, keys, "normalization")
        cfg = cls()
        for key, value in data.items():
            if key in ("strip_whitespace", "unicode_nfc", "report_formatting_differences"):
                setattr(cfg, key, _bool(value, f"normalization.{key}"))
            else:
                setattr(cfg, key, _str_list(value, f"normalization.{key}"))
        for fmt in cfg.accepted_date_formats:
            _check_date_format(fmt, "normalization.accepted_date_formats")
        return cfg


@dataclass
class ValidatorConfig:
    id_column: str = "id"
    key_columns: List[str] = field(default_factory=list)  # composite key; overrides id_column
    id_case_sensitive: bool = True
    ignore_columns: List[str] = field(default_factory=list)
    required_fields: List[str] = field(default_factory=list)
    email_fields: List[str] = field(default_factory=list)
    numeric_ranges: Dict[str, NumericRange] = field(default_factory=dict)
    date_fields: Dict[str, str] = field(default_factory=dict)
    allowed_values: Dict[str, List[str]] = field(default_factory=dict)
    expected_types: Dict[str, str] = field(default_factory=dict)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    severity_overrides: Dict[str, str] = field(default_factory=dict)

    # ---- construction -------------------------------------------------
    @classmethod
    def from_dict(cls, data: Any) -> "ValidatorConfig":
        if not isinstance(data, dict):
            raise ConfigError("Configuration must be a JSON object")
        _check_keys(data, set(cls.__dataclass_fields__), "configuration")
        cfg = cls()
        if "id_column" in data:
            if not isinstance(data["id_column"], str) or not data["id_column"]:
                raise ConfigError("'id_column' must be a non-empty string")
            cfg.id_column = data["id_column"]
        if "key_columns" in data:
            if "id_column" in data:
                raise ConfigError("Use either 'id_column' or 'key_columns', not both")
            kc = _str_list(data["key_columns"], "key_columns")
            if not kc or any(k == "" for k in kc) or len(set(kc)) != len(kc):
                raise ConfigError("'key_columns' needs one or more distinct, non-empty column names")
            cfg.key_columns = kc
        if "id_case_sensitive" in data:
            cfg.id_case_sensitive = _bool(data["id_case_sensitive"], "id_case_sensitive")
        for key in ("ignore_columns", "required_fields", "email_fields"):
            if key in data:
                setattr(cfg, key, _str_list(data[key], key))
        if "numeric_ranges" in data:
            if not isinstance(data["numeric_ranges"], dict):
                raise ConfigError("'numeric_ranges' must be an object")
            cfg.numeric_ranges = {
                k: NumericRange.from_dict(v, k) for k, v in data["numeric_ranges"].items()
            }
        if "date_fields" in data:
            df = data["date_fields"]
            if not isinstance(df, dict) or not all(isinstance(v, str) for v in df.values()):
                raise ConfigError("'date_fields' must map column names to strptime formats")
            for col, fmt in df.items():
                _check_date_format(fmt, f"date_fields['{col}']")
            cfg.date_fields = dict(df)
        if "allowed_values" in data:
            av = data["allowed_values"]
            if not isinstance(av, dict):
                raise ConfigError("'allowed_values' must map column names to lists of strings")
            for col, vals in av.items():
                if not _str_list(vals, f"allowed_values['{col}']"):
                    raise ConfigError(f"allowed_values['{col}'] must not be empty")
            cfg.allowed_values = {k: list(v) for k, v in av.items()}
        if "expected_types" in data:
            et = data["expected_types"]
            if not isinstance(et, dict):
                raise ConfigError("'expected_types' must be an object")
            for col, typ in et.items():
                if typ not in VALID_TYPES:
                    raise ConfigError(
                        f"expected_types['{col}']={typ!r} invalid; choose from {', '.join(VALID_TYPES)}"
                    )
            cfg.expected_types = dict(et)
        if "normalization" in data:
            cfg.normalization = NormalizationConfig.from_dict(data["normalization"])
        if "severity_overrides" in data:
            so = data["severity_overrides"]
            if not isinstance(so, dict):
                raise ConfigError("'severity_overrides' must be an object")
            valid_types = {t.value for t in IssueType}
            valid_sev = {s.value for s in Severity}
            for k, v in so.items():
                if k not in valid_types:
                    raise ConfigError(f"severity_overrides: unknown issue type {k!r}")
                if v not in valid_sev:
                    raise ConfigError(f"severity_overrides[{k!r}]={v!r}; choose from {sorted(valid_sev)}")
            cfg.severity_overrides = dict(so)
        return cfg

    @classmethod
    def from_json_file(cls, path: str) -> "ValidatorConfig":
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Cannot read config file {path}: {exc}") from exc
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file {path} is not valid JSON: {exc}") from exc
        return cls.from_dict(data)

    # ---- helpers ------------------------------------------------------
    @property
    def keys(self) -> List[str]:
        """Columns that together identify a record (one column unless a composite key is set)."""
        return list(self.key_columns) if self.key_columns else [self.id_column]

    @property
    def key_field_name(self) -> str:
        return "|".join(self.keys)

    def is_null(self, value: str) -> bool:
        return self.normalization.is_null(value)

    def severity_for(self, issue_type: IssueType) -> Severity:
        override = self.severity_overrides.get(issue_type.value)
        return Severity(override) if override else DEFAULT_SEVERITY[issue_type]

    def all_date_formats(self) -> Tuple[str, ...]:
        seen: List[str] = []
        for fmt in [*self.normalization.accepted_date_formats, *self.date_fields.values()]:
            if fmt not in seen:
                seen.append(fmt)
        return tuple(seen)

    def to_dict(self) -> Dict[str, Any]:
        n = self.normalization
        return {
            "key_columns": self.keys,
            "id_case_sensitive": self.id_case_sensitive,
            "ignore_columns": list(self.ignore_columns),
            "required_fields": list(self.required_fields),
            "email_fields": list(self.email_fields),
            "numeric_ranges": {k: v.to_dict() for k, v in sorted(self.numeric_ranges.items())},
            "date_fields": dict(sorted(self.date_fields.items())),
            "allowed_values": {k: list(v) for k, v in sorted(self.allowed_values.items())},
            "expected_types": dict(sorted(self.expected_types.items())),
            "normalization": {
                "strip_whitespace": n.strip_whitespace,
                "unicode_nfc": n.unicode_nfc,
                "casefold_fields": list(n.casefold_fields),
                "phone_fields": list(n.phone_fields),
                "numeric_fields": list(n.numeric_fields),
                "date_fields": list(n.date_fields),
                "accepted_date_formats": list(n.accepted_date_formats),
                "null_tokens": list(n.null_tokens),
                "report_formatting_differences": n.report_formatting_differences,
            },
            "severity_overrides": dict(sorted(self.severity_overrides.items())),
        }
