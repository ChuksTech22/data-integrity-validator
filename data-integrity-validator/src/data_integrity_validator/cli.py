"""Command-line interface.

Exit codes: 0 = no issues at/above --fail-on threshold, 1 = issues found,
2 = bad input/config/usage.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys
from typing import List, Optional

from . import __version__
from .config import ValidatorConfig
from .exceptions import DataIntegrityError
from .models import Severity
from .report import write_reports
from .validator import validate


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="data-integrity-validator",
        description="Compare a source and destination CSV and report hidden data errors.",
    )
    p.add_argument("source", help="path to the source CSV (the trusted original)")
    p.add_argument("destination", help="path to the destination CSV (the migrated copy)")
    p.add_argument("--config", help="path to a JSON configuration file")
    p.add_argument(
        "--key", "--id-column", dest="key", action="append", metavar="COLUMN",
        help="column that identifies a record; repeat for a composite key "
             "(--key first_name --key last_name). Overrides the config file",
    )
    p.add_argument("--output-dir", default="reports", help="where to write reports (default: reports)")
    p.add_argument(
        "--fail-on", choices=["error", "warning", "info", "never"], default="error",
        help="exit with status 1 if any issue at or above this severity exists (default: error)",
    )
    p.add_argument("--quiet", action="store_true", help="suppress the console summary")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = ValidatorConfig.from_json_file(args.config) if args.config else ValidatorConfig()
        if args.key:
            config = dataclasses.replace(config, key_columns=list(args.key))
        result = validate(args.source, args.destination, config)
        json_path, csv_path = write_reports(result, args.output_dir)
    except DataIntegrityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    s = result.summary
    if not args.quiet:
        sev = s["issues_by_severity"]
        print(f"Source rows checked:       {s['records_checked']['source']}")
        print(f"Destination rows checked:  {s['records_checked']['destination']}")
        print(f"Records matched by key:    {s['records_matched']}")
        print(f"Missing in destination:    {s['missing_in_destination']}")
        print(f"Unexpected in destination: {s['unexpected_in_destination']}")
        print(f"Field values compared:     {s['field_values_compared']}")
        print(f"Issues detected:           {s['issues_total']} "
              f"(error={sev['error']}, warning={sev['warning']}, info={sev['info']})")
        if s["suppressed_formatting_differences"]:
            print(f"Suppressed formatting differences: {s['suppressed_formatting_differences']}")
        for note in result.notes:
            print(f"note: {note}")
        print(f"JSON report: {json_path}")
        print(f"CSV report:  {csv_path}")

    if args.fail_on != "never":
        threshold = Severity(args.fail_on).rank
        if any(i.severity.rank <= threshold for i in result.issues):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
