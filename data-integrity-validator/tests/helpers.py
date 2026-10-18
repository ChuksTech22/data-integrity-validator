"""Shared helpers for the test-suite."""
from pathlib import Path

from data_integrity_validator.config import ValidatorConfig
from data_integrity_validator.io import load_csv
from data_integrity_validator.validator import validate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def write_csv(tmp_path, name, text):
    path = Path(tmp_path) / name
    path.write_text(text, encoding="utf-8", newline="")
    return str(path)


def load(tmp_path, text, name="data.csv"):
    return load_csv(write_csv(tmp_path, name, text))


def cfg(**kwargs):
    """Build a ValidatorConfig from a plain dict (also exercises validation)."""
    if "key_columns" not in kwargs:
        kwargs.setdefault("id_column", "id")
    return ValidatorConfig.from_dict(kwargs)


def run(tmp_path, src_text, dst_text, **config):
    src = write_csv(tmp_path, "src.csv", src_text)
    dst = write_csv(tmp_path, "dst.csv", dst_text)
    return validate(src, dst, cfg(**config))


def triples(result):
    """Set of (issue_type, record_id, field) for easy assertions."""
    return {(i.issue_type.value, i.record_id, i.field) for i in result.issues}


def types(result):
    return sorted(i.issue_type.value for i in result.issues)
