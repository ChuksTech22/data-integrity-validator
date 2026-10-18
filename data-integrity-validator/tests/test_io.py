import hashlib

import pytest

from data_integrity_validator.exceptions import CSVLoadError
from data_integrity_validator.io import load_csv
from helpers import load, write_csv


def test_load_basic_preserves_text_exactly(tmp_path):
    loaded = load(tmp_path, "id,code,note\n1,007,\n2,0.50,x\n")
    assert loaded.columns == ["id", "code", "note"]
    assert loaded.values("code") == ["007", "0.50"]  # no numeric coercion
    assert loaded.values("note") == ["", "x"]  # empty stays "", never NaN
    assert loaded.lines == (2, 3)


def test_header_only_file_has_zero_rows(tmp_path):
    loaded = load(tmp_path, "id,name\n")
    assert len(loaded.rows) == 0 and loaded.columns == ["id", "name"]


def test_missing_file(tmp_path):
    with pytest.raises(CSVLoadError, match="not found"):
        load_csv(str(tmp_path / "nope.csv"))


def test_directory_instead_of_file(tmp_path):
    with pytest.raises(CSVLoadError, match="directory"):
        load_csv(str(tmp_path))


@pytest.mark.parametrize("content", ["", "   \n\n"])
def test_empty_file(tmp_path, content):
    with pytest.raises(CSVLoadError, match="empty"):
        load_csv(write_csv(tmp_path, "e.csv", content))


def test_ragged_row_is_an_error_not_silently_padded(tmp_path):
    with pytest.raises(CSVLoadError, match="line 3 has 2 fields, expected 3"):
        load_csv(write_csv(tmp_path, "r.csv", "a,b,c\n1,2,3\n4,5\n"))


def test_duplicate_header(tmp_path):
    with pytest.raises(CSVLoadError, match="duplicate column"):
        load_csv(write_csv(tmp_path, "d.csv", "id,name,id\n1,a,b\n"))


def test_empty_header_name(tmp_path):
    with pytest.raises(CSVLoadError, match="empty column name"):
        load_csv(write_csv(tmp_path, "h.csv", "id,,name\n1,2,3\n"))


def test_utf8_bom_is_handled(tmp_path):
    p = tmp_path / "bom.csv"
    p.write_bytes(b"\xef\xbb\xbfid,name\n1,a\n")
    assert load_csv(str(p)).columns == ["id", "name"]


def test_invalid_utf8_is_reported(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_bytes(b"id,name\n1,\xff\n")
    with pytest.raises(CSVLoadError, match="UTF-8"):
        load_csv(str(p))


def test_blank_lines_are_counted_not_hidden(tmp_path):
    loaded = load(tmp_path, "id,n\n1,a\n\n2,b\n\n")
    assert len(loaded.rows) == 2
    assert loaded.skipped_blank_lines == 2
    assert loaded.lines == (2, 4)


def test_multiline_quoted_field_keeps_correct_line_numbers(tmp_path):
    loaded = load(tmp_path, 'id,note\n1,"a\nb"\n2,c\n')
    assert loaded.values("note") == ["a\nb", "c"]
    assert loaded.lines == (2, 4)


def test_unterminated_quote_is_reported(tmp_path):
    with pytest.raises(CSVLoadError):
        load_csv(write_csv(tmp_path, "q.csv", 'id,note\n1,"never closed\n'))


def test_loading_never_modifies_the_file(tmp_path):
    path = write_csv(tmp_path, "keep.csv", "id,name\n1, padded \n")
    before = open(path, "rb").read()
    loaded = load_csv(path)
    assert open(path, "rb").read() == before
    assert loaded.sha256 == hashlib.sha256(before).hexdigest()
    assert loaded.values("name") == [" padded "]  # whitespace preserved
