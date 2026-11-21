"""真实反馈 ZIP 的引用位置、读取边界和分析引用校验。"""

import hashlib
import importlib
import json
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from arknights_mower.agent.tools import feedback_references as references


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    source_module = importlib.import_module(
        "arknights_mower.agent.tools.get_source_snippet"
    )
    root = tmp_path / "installed"
    package = root / "arknights_mower"
    (package / "solvers").mkdir(parents=True)
    path = package / "solvers/example.py"
    path.write_text(
        "".join(f"value_{i} = {i}\n" for i in range(1, 81)), encoding="utf-8"
    )
    monkeypatch.setattr(source_module, "_PROJECT_ROOT", root)
    monkeypatch.setattr(source_module, "_PACKAGE_ROOT", package)
    monkeypatch.setattr(references, "_PROJECT_ROOT", root)
    return root, path


def make_bundle(tmp_path, members):
    path = tmp_path / "feedback.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as bundle:
        for name, content in members.items():
            bundle.writestr(name, content)
    return path


def log(message, level="INFO", location="missing.py:1"):
    return f"2026-11-06 12:00:00,123 {location} {level} run: {message}\n"


def test_zip_original_lines_multiline_duplicates_and_deterministic_ids(tmp_path):
    error = log("failed", "ERROR")
    raw = (
        log("first") + error + "Traceback (most recent call last):\n  details\n" + error
    )
    bundle = make_bundle(
        tmp_path, {"runtime.log": raw, "screenshots/private.txt": "ignored"}
    )
    index = references.build_feedback_references(bundle)
    rows = index["records"]
    assert [(row["start_line"], row["end_line"]) for row in rows] == [
        (1, 1),
        (2, 4),
        (5, 5),
    ]
    assert rows[1]["text"] == error + "Traceback (most recent call last):\n  details\n"
    assert rows[1]["time"] == "2026-11-06 12:00:00,123"
    assert rows[1]["level"] == "ERROR"
    assert rows[1]["id"] != rows[2]["id"]
    assert index == references.build_feedback_references(bundle)
    assert index["coverage"]["scan_complete"]
    assert rows[1]["raw_sha256"] == hashlib.sha256(rows[1]["text"].encode()).hexdigest()
    assert len(index["coverage"]["members"]) == 1


def test_appended_logs_do_not_invalidate_existing_record_ids(tmp_path):
    bundle = make_bundle(tmp_path, {"runtime.log": log("failure", "ERROR")})
    before = references.build_feedback_references(bundle)
    bundle = make_bundle(
        tmp_path, {"runtime.log": log("failure", "ERROR") + log("later debug", "DEBUG")}
    )
    after = references.build_feedback_references(bundle)
    assert before["evidence_id"] != after["evidence_id"]
    assert before["records"][0]["id"] == after["records"][0]["id"]


def test_early_error_and_business_debug_survive_unrelated_debug(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "MAX_RECORDS", 4)
    raw = log("early failure", "ERROR") + log("mastery recovery", "DEBUG")
    raw += "".join(log(f"SQL html screenshot {i}", "DEBUG") for i in range(100))
    raw += log("late warning", "WARNING")
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw})
    )
    assert [row["start_line"] for row in index["records"]] == [1, 2, 3, 103]
    assert index["coverage"]["unindexed_scanned_records"] == 99


def test_focus_match_precedes_unrelated_error_and_is_declared(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "MAX_RECORDS", 1)
    raw = log("unrelated failure", "ERROR") + log("FIAMMETTA waiting", "DEBUG")
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw}), ["fiammetta"]
    )
    assert index["records"][0]["start_line"] == 2
    assert index["records"][0]["focus_matched"]
    assert "机械匹配" in index["limitations"][0]


@pytest.mark.parametrize("terms", ["text", ["x"] * 6, [""], ["x" * 51], [1]])
def test_focus_terms_are_bounded(tmp_path, terms):
    bundle = make_bundle(tmp_path, {"runtime.log": log("text")})
    with pytest.raises(ValueError, match="关注词"):
        references.build_feedback_references(bundle, terms)


def test_windows_and_history_snapshots_are_indexed_in_member_order(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(references, "MAX_RECORDS", 8)
    members = {
        "runtime.log": "".join(log(f"task {i}") for i in range(100)),
        "task_history.jsonl": '{"time": 1, "message": "task"}\n{"time": 2}\n',
        "operator_history.jsonl": '{"current_time":"2026-11-06 12:00:00","mood":4}\n',
        "mastery_plans.jsonl": '{"operator":"阿米娅"}\n',
        "mastery_routes.jsonl": '{"route":"training"}\n',
        "windows/1/runtime.log": log("previous interval", "WARNING"),
        "windows/1/task_history.jsonl": '{"time":0}\n',
        "windows/1/operator_history.jsonl": '{"mood":1}\n',
        "windows/../runtime.log": log("unsafe", "ERROR"),
    }
    index = references.build_feedback_references(make_bundle(tmp_path, members))
    rows = index["records"]
    assert {row["member"] for row in rows} == set(members) - {
        "runtime.log",
        "windows/../runtime.log",
    }
    assert [row["member"] for row in rows] == [
        "task_history.jsonl",
        "task_history.jsonl",
        "operator_history.jsonl",
        "mastery_plans.jsonl",
        "mastery_routes.jsonl",
        "windows/1/runtime.log",
        "windows/1/task_history.jsonl",
        "windows/1/operator_history.jsonl",
    ]
    histories = [row for row in rows if row["member"] == "task_history.jsonl"]
    assert [(row["start_line"], row["time"]) for row in histories] == [(1, 1), (2, 2)]
    assert (
        next(row for row in rows if row["member"] == "mastery_plans.jsonl")["kind"]
        == "current_snapshot"
    )
    assert (
        next(row for row in rows if row["member"] == "operator_history.jsonl")["kind"]
        == "database_history"
    )


@pytest.mark.parametrize(
    "limit_name,limit,reason",
    [
        ("MAX_SCAN_BYTES", 50, "scan_byte_limit"),
        ("MAX_SCAN_LINES", 1, "scan_line_limit"),
    ],
)
def test_scanning_limits_are_explicit(tmp_path, monkeypatch, limit_name, limit, reason):
    monkeypatch.setattr(references, limit_name, limit)
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": log("first") + log("second")})
    )
    coverage = index["coverage"]["members"][0]
    assert not coverage["scan_complete"]
    assert coverage["stop_reason"] == reason
    assert index["records"][0]["text_truncated"]
    assert not index["coverage"]["scan_complete"]


def test_long_lines_keep_physical_line_numbers_and_bounded_text(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "MAX_LINE_BYTES", 80)
    first = log("中" * 10000, "ERROR")
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": first + log("next", "WARNING")})
    )
    rows = index["records"]
    assert [(row["start_line"], row["end_line"]) for row in rows] == [(1, 1), (2, 2)]
    assert rows[0]["text_truncated"]
    assert len(rows[0]["text"].encode()) <= references.MAX_RECORD_TEXT_BYTES
    assert rows[0]["raw_sha256"] == hashlib.sha256(first.encode()).hexdigest()


def test_windows_internal_traceback_maps_to_allowlisted_current_source(
    tmp_path, source_tree
):
    _, path = source_tree
    raw = (
        log("failure", "ERROR")
        + '  File "C:\\Mower\\_internal\\arknights_mower\\solvers\\example.py", line 40, in run\n'
    )
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw})
    )
    source = index["sources"][0]
    assert source["file"] == "arknights_mower/solvers/example.py"
    assert source["source_kind"] == "installed-current-source"
    assert not source["historical_source_verified"]
    assert (source["requested_line"], source["start_line"], source["end_line"]) == (
        40,
        20,
        60,
    )
    assert source["text"] == "".join(path.read_text().splitlines(keepends=True)[19:60])
    assert source["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert source["record_id"] == index["records"][0]["id"]


@pytest.mark.parametrize(
    "location",
    [
        "../../outside.py:1",
        "/etc/outside.py:1",
        "C:\\private\\outside.py:1",
        "arknights_mower/solvers/../../outside.py:1",
        "arknights_mower/solvers/link.py:1",
        "arknights_mower/solvers/example.py:99999",
        "arknights_mower/solvers/example.py:0",
    ],
)
def test_disallowed_paths_symlink_escape_and_invalid_lines_are_not_read(
    tmp_path, source_tree, location
):
    root, _ = source_tree
    outside = tmp_path / "outside.py"
    outside.write_text("private_secret = 1\n")
    (root / "arknights_mower/solvers/link.py").symlink_to(outside)
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": log("failure", "ERROR", location)})
    )
    assert index["sources"] == []
    assert index["coverage"]["source_omissions"]
    assert "private_secret" not in json.dumps(index)


def test_only_four_sources_and_exact_edge_range(tmp_path, source_tree):
    _, path = source_tree
    raw = log("failure", "ERROR") + "".join(
        f' File "arknights_mower/solvers/example.py", line {line}\n'
        for line in (1, 2, 3, 4, 5)
    )
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw})
    )
    assert len(index["sources"]) == 4
    assert (index["sources"][0]["start_line"], index["sources"][0]["end_line"]) == (
        1,
        21,
    )
    assert any(
        row["reason"] == "source_count_limit"
        for row in index["coverage"]["source_omissions"]
    )


def test_source_scan_budget_is_reported(tmp_path, source_tree, monkeypatch):
    monkeypatch.setattr(references, "MAX_SOURCE_SCAN_BYTES", 10)
    index = references.build_feedback_references(
        make_bundle(
            tmp_path,
            {
                "runtime.log": log(
                    "failure", "ERROR", "arknights_mower/solvers/example.py:1"
                )
            },
        )
    )
    assert not index["sources"]
    assert (
        index["coverage"]["source_omissions"][0]["reason"] == "source_scan_byte_limit"
    )
    assert index["coverage"]["source_scanned_bytes"] == 0


def test_serialized_index_has_hard_limit_and_reports_omission(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "MAX_INDEX_BYTES", 10000)
    monkeypatch.setattr(references, "MAX_ESCAPED_INDEX_BYTES", 20000)
    raw = "".join(log("中" * 2000, "ERROR") for _ in range(80))
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw})
    )
    assert len(json.dumps(index, ensure_ascii=False).encode()) <= 10000
    assert len(json.dumps(index).encode()) <= 20000
    assert index["coverage"]["index_truncated"]
    assert index["coverage"]["indexed_record_count"] == len(index["records"])
    assert index["coverage"]["unindexed_scanned_records"] == 80 - len(index["records"])


def test_validation_requires_current_references_and_explicit_inference_note(
    tmp_path, source_tree
):
    index = references.build_feedback_references(
        make_bundle(
            tmp_path,
            {
                "runtime.log": log(
                    "failure", "ERROR", "arknights_mower/solvers/example.py:40"
                )
            },
        )
    )
    log_id, source_id = index["records"][0]["id"], index["sources"][0]["id"]
    analysis = {
        "status": "analyzed",
        "claims": [
            {
                "kind": "code_inference",
                "text": "可能在此处失败",
                "references": [log_id, source_id],
            }
        ],
        "unknowns": ["尚无历史源码"],
    }
    validated = references.validate_feedback_analysis(analysis, index)
    assert validated["claims"] == analysis["claims"]
    assert "推断" in validated["note"] and "不证明解释正确" in validated["note"]
    analysis["claims"][0]["references"].append("log-unrelated-package")
    with pytest.raises(ValueError, match="不属于此次"):
        references.validate_feedback_analysis(analysis, index)


@pytest.mark.parametrize(
    "claim",
    [
        {"kind": "log_interpretation", "text": "claim", "references": []},
        {"kind": "code_inference", "text": "claim", "references": ["log-ok"]},
        {"kind": "log_interpretation", "text": "claim", "references": ["source-ok"]},
        {"kind": "log_interpretation", "text": "", "references": ["log-ok"]},
        {"kind": "log_interpretation", "text": "x" * 2001, "references": ["log-ok"]},
        {"kind": "log_interpretation", "text": "claim", "references": ["log-ok"] * 9},
    ],
)
def test_invalid_claims_are_rejected(claim):
    index = {"records": [{"id": "log-ok"}], "sources": [{"id": "source-ok"}]}
    with pytest.raises(ValueError):
        references.validate_feedback_analysis(
            {"status": "analyzed", "claims": [claim], "unknowns": []}, index
        )


def test_unknown_requires_reason_and_allows_no_claims():
    index = {"records": [], "sources": []}
    result = references.validate_feedback_analysis(
        {"status": "unknown", "claims": [], "unknowns": ["没有可用的故障时日志"]}, index
    )
    assert result["status"] == "unknown" and result["claims"] == []
    with pytest.raises(ValueError):
        references.validate_feedback_analysis(
            {"status": "unknown", "claims": [], "unknowns": []}, index
        )


def test_source_id_survives_changes_outside_quoted_range(tmp_path, source_tree):
    _, path = source_tree
    bundle = make_bundle(
        tmp_path,
        {
            "runtime.log": log(
                "failure", "ERROR", "arknights_mower/solvers/example.py:1"
            )
        },
    )
    before = references.build_feedback_references(bundle)["sources"][0]
    path.write_text(path.read_text() + "new_tail = 1\n")
    after = references.build_feedback_references(bundle)["sources"][0]
    assert before["source_sha256"] != after["source_sha256"]
    assert before["id"] == after["id"]
    assert before["text_sha256"] == after["text_sha256"]


def test_changed_quote_rejects_previous_analysis_reference(tmp_path):
    bundle = make_bundle(tmp_path, {"runtime.log": log("old failure", "ERROR")})
    old = references.build_feedback_references(bundle)["records"][0]["id"]
    bundle = make_bundle(tmp_path, {"runtime.log": log("new failure", "ERROR")})
    index = references.build_feedback_references(bundle)
    with pytest.raises(ValueError, match="不属于此次"):
        references.validate_feedback_analysis(
            {
                "status": "analyzed",
                "claims": [
                    {
                        "kind": "log_interpretation",
                        "text": "旧分析",
                        "references": [old],
                    }
                ],
                "unknowns": [],
            },
            index,
        )


def test_member_limit_and_missing_runtime_are_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(references, "MAX_LOG_MEMBERS", 1)
    index = references.build_feedback_references(
        make_bundle(
            tmp_path,
            {"runtime.log": log("first"), "windows/1/runtime.log": log("second")},
        )
    )
    assert index["coverage"]["omitted_members"] == 1
    assert not index["coverage"]["scan_complete"]
    missing = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.txt": "preview only"})
    )
    assert missing["records"] == []
    assert not missing["coverage"]["scan_complete"]


def test_duplicate_log_members_cannot_have_ambiguous_references(tmp_path):
    bundle = make_bundle(tmp_path, {"runtime.log": log("first")})
    with pytest.warns(UserWarning, match="Duplicate name"):
        with ZipFile(bundle, "a") as archive:
            archive.writestr("runtime.log", log("second"))
    with pytest.raises(ValueError, match="重名"):
        references.build_feedback_references(bundle)


def test_code_inference_rejects_source_from_other_unreferenced_record(
    tmp_path, source_tree
):
    raw = log("first failure", "ERROR", "arknights_mower/solvers/example.py:1")
    raw += log("second failure", "ERROR", "arknights_mower/solvers/example.py:40")
    index = references.build_feedback_references(
        make_bundle(tmp_path, {"runtime.log": raw})
    )
    first, second = index["records"]
    first_source, second_source = index["sources"]
    assert first_source["record_id"] == first["id"]
    assert second_source["record_id"] == second["id"]
    claim = {
        "kind": "code_inference",
        "text": "源码可能解释此失败",
        "references": [first["id"], first_source["id"], second_source["id"]],
    }
    analysis = {"status": "analyzed", "claims": [claim], "unknowns": []}
    with pytest.raises(ValueError, match="源码关联记录"):
        references.validate_feedback_analysis(analysis, index)
    claim["references"].append(second["id"])
    assert references.validate_feedback_analysis(analysis, index)["claims"] == [claim]


@pytest.mark.parametrize(
    "byte_budget,line_budget,reason",
    [(1024, 100, "scan_byte_limit"), (100000, 8, "scan_line_limit")],
)
def test_large_debug_log_cannot_exhaust_later_members_scan_budget(
    tmp_path, monkeypatch, byte_budget, line_budget, reason
):
    monkeypatch.setattr(references, "MAX_SCAN_BYTES", byte_budget)
    monkeypatch.setattr(references, "MAX_SCAN_LINES", line_budget)
    noise = "".join(
        log(f"unrelated SQL screenshot html {i} " + "x" * 300, "DEBUG")
        for i in range(100)
    )
    index = references.build_feedback_references(
        make_bundle(
            tmp_path,
            {
                "runtime.log": noise,
                "mastery_plans.jsonl": '{"operator":"阿米娅","status":"current"}\n',
                "windows/1/runtime.log": log("previous interval failure", "ERROR"),
            },
        )
    )
    coverage = index["coverage"]["members"]
    assert coverage[0]["stop_reason"] == reason
    assert not coverage[0]["scan_complete"]
    assert all(
        row["scanned_bytes"] > 0 and row["scanned_lines"] > 0 for row in coverage
    )
    assert sum(row["scanned_bytes"] for row in coverage) <= byte_budget
    assert sum(row["scanned_lines"] for row in coverage) <= line_budget
    assert {row["member"] for row in index["records"]} == {
        "runtime.log",
        "mastery_plans.jsonl",
        "windows/1/runtime.log",
    }
    assert all(row["scan_complete"] for row in coverage[1:])
    assert not index["coverage"]["scan_complete"]
