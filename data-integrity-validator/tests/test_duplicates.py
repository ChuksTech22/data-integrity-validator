from helpers import cfg, run, triples, types


def test_identical_duplicate_id(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\n1,a\n")
    assert triples(r) == {("duplicate_id", "1", "id")}
    issue = r.issues[0]
    assert issue.dataset == "destination" and "identical" in issue.explanation
    assert "lines 2, 3" in issue.explanation


def test_conflicting_duplicate_id_also_surfaces_value_mismatch(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\n1,b\n")
    assert triples(r) == {("duplicate_id", "1", "id"), ("value_mismatch", "1", "v")}
    dup = [i for i in r.issues if i.issue_type.value == "duplicate_id"][0]
    assert "conflicting" in dup.explanation


def test_duplicates_in_source_are_reported_against_the_source(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n1,a\n", "id,v\n1,a\n")
    dup = [i for i in r.issues if i.issue_type.value == "duplicate_id"]
    assert len(dup) == 1 and dup[0].dataset == "source"


def test_blank_identifier_is_reported_not_dropped(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\n,b\n")
    assert triples(r) == {("missing_identifier", "(line 3)", "id")}
    assert r.summary["records_checked"]["destination"] == 2


def test_ids_are_case_sensitive_by_default(tmp_path):
    r = run(tmp_path, "id,v\nA1,a\n", "id,v\na1,a\n")
    assert types(r) == ["missing_record", "unexpected_record"]


def test_case_insensitive_ids_match_but_flag_formatting(tmp_path):
    r = run(tmp_path, "id,v\nA1,a\n", "id,v\na1,a\n", id_case_sensitive=False)
    assert types(r) == ["identifier_formatting"]


def test_duplicate_record_under_a_new_id(tmp_path):
    r = run(tmp_path, "id,v,w\n1,a,x\n2,b,y\n", "id,v,w\n1,a,x\n2,b,y\n3, a ,x\n")
    assert ("duplicate_record", "3", "*") in triples(r)
    dup = [i for i in r.issues if i.issue_type.value == "duplicate_record"][0]
    assert dup.observed == "identical to record 1"  # whitespace-insensitive


def test_same_id_rows_are_not_double_reported_as_duplicate_records(tmp_path):
    r = run(tmp_path, "id,v\n1,a\n", "id,v\n1,a\n1,a\n")
    assert "duplicate_record" not in types(r)


def test_rows_with_no_content_are_not_duplicate_records(tmp_path):
    r = run(tmp_path, "id,v\n1,\n2,\n", "id,v\n1,\n2,\n")
    assert r.issues == []
