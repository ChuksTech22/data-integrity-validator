import contextlib
import io
import json

import pytest

from data_integrity_validator.cli import main
from helpers import EXAMPLES, write_csv

CLEAN = "id,name\n1,Ann\n2,Bob\n"


def invoke(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(args)
    return code, buf.getvalue()


def test_example_run_exits_1_and_writes_both_reports(tmp_path):
    out = tmp_path / "out"
    code, stdout = invoke([str(EXAMPLES / "source.csv"), str(EXAMPLES / "destination.csv"),
                           "--config", str(EXAMPLES / "config.json"), "--output-dir", str(out)])
    assert code == 1
    assert "Issues detected:" in stdout and "Source rows checked:       30" in stdout
    report = json.loads((out / "integrity_report.json").read_text(encoding="utf-8"))
    assert set(report) == {"tool", "inputs", "configuration", "summary", "notes", "issues"}
    assert report["summary"]["issues_total"] == len(report["issues"])
    header = (out / "integrity_report.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == ("issue_id,severity,issue_type,dataset,record_id,field,expected,observed,"
                      "normalization,source_line,destination_line,explanation,suggested_action")


def test_clean_files_exit_0(tmp_path):
    s, d = write_csv(tmp_path, "s.csv", CLEAN), write_csv(tmp_path, "d.csv", CLEAN)
    code, stdout = invoke([s, d, "--output-dir", str(tmp_path / "o")])
    assert code == 0 and "Issues detected:           0" in stdout


def test_fail_on_thresholds(tmp_path):
    s = write_csv(tmp_path, "s.csv", "id,name\n1,Ann\n")
    d = write_csv(tmp_path, "d.csv", "id,name\n1,Ann \n")  # warning-level whitespace issue only
    o = str(tmp_path / "o")
    assert invoke([s, d, "--output-dir", o])[0] == 0
    assert invoke([s, d, "--output-dir", o, "--fail-on", "warning"])[0] == 1
    assert invoke([s, d, "--output-dir", o, "--fail-on", "never"])[0] == 0


def test_quiet_suppresses_summary(tmp_path):
    s, d = write_csv(tmp_path, "s.csv", CLEAN), write_csv(tmp_path, "d.csv", CLEAN)
    assert invoke([s, d, "--output-dir", str(tmp_path / "o"), "--quiet"]) == (0, "")


def test_key_flag_and_id_column_alias(tmp_path):
    s = write_csv(tmp_path, "s.csv", "key,v\nA,1\n")
    d = write_csv(tmp_path, "d.csv", "key,v\nB,1\n")
    assert invoke([s, d, "--key", "key", "--output-dir", str(tmp_path / "o")])[0] == 1
    assert invoke([s, d, "--id-column", "key", "--output-dir", str(tmp_path / "o")])[0] == 1


def test_repeated_key_flag_builds_a_composite_key(tmp_path):
    s = write_csv(tmp_path, "s.csv", "first,last,v\nAnn,Lee,1\nAnn,Kay,2\n")
    d = write_csv(tmp_path, "d.csv", "first,last,v\nAnn,Lee,1\nAnn,Kay,2\n")
    out = tmp_path / "o"
    code, _ = invoke([s, d, "--key", "first", "--key", "last", "--output-dir", str(out), "--quiet"])
    assert code == 0
    report = json.loads((out / "integrity_report.json").read_text(encoding="utf-8"))
    assert report["configuration"]["key_columns"] == ["first", "last"]


def test_help_exits_zero_and_lists_options():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
    assert exc.value.code == 0
    text = buf.getvalue()
    for flag in ("--config", "--key", "--output-dir", "--fail-on", "--quiet"):
        assert flag in text


def test_console_output_does_not_echo_record_values(tmp_path):
    out = tmp_path / "o"
    _, stdout = invoke([str(EXAMPLES / "source.csv"), str(EXAMPLES / "destination.csv"),
                        "--config", str(EXAMPLES / "config.json"), "--output-dir", str(out)])
    for sensitive in ("tunde.adeyemi", "example.com", "+2348035550", "Okafor"):
        assert sensitive not in stdout


@pytest.mark.parametrize("case", ["missing_file", "bad_config", "no_id_column"])
def test_input_problems_exit_2(tmp_path, case):
    s, d = write_csv(tmp_path, "s.csv", CLEAN), write_csv(tmp_path, "d.csv", CLEAN)
    o = str(tmp_path / "o")
    if case == "missing_file":
        args = [s, str(tmp_path / "nope.csv"), "--output-dir", o]
    elif case == "bad_config":
        bad = write_csv(tmp_path, "c.json", '{"requried_fields": []}')
        args = [s, d, "--config", bad, "--output-dir", o]
    else:
        args = [s, d, "--id-column", "nonexistent", "--output-dir", o]
    assert invoke(args)[0] == 2


def test_same_inputs_give_byte_identical_reports(tmp_path):
    base = [str(EXAMPLES / "source.csv"), str(EXAMPLES / "destination.csv"),
            "--config", str(EXAMPLES / "config.json"), "--quiet"]
    invoke(base + ["--output-dir", str(tmp_path / "a")])
    invoke(base + ["--output-dir", str(tmp_path / "b")])
    for name in ("integrity_report.json", "integrity_report.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_csv_report_neutralizes_formulas_but_json_keeps_raw_values(tmp_path):
    s = write_csv(tmp_path, "s.csv", "id,v\n1,ok\n")
    d = write_csv(tmp_path, "d.csv", "id,v\n1,=HYPERLINK(\"http://x\")\n")
    out = tmp_path / "o"
    invoke([s, d, "--output-dir", str(out), "--quiet"])
    assert "'=HYPERLINK" in (out / "integrity_report.csv").read_text(encoding="utf-8")
    raw = json.loads((out / "integrity_report.json").read_text(encoding="utf-8"))
    assert raw["issues"][0]["observed"] == '=HYPERLINK("http://x")'
