"""Offline ownership, skill-stage and read-only AI planning contracts."""

import copy
import hashlib
import json

import pytest

from arknights_mower.agent.tools import riic
from arknights_mower.utils import building_skills
from arknights_mower.utils.config.plan import PlanModel


@pytest.fixture
def state(monkeypatch):
    catalog = {
        "赫默": [
            {
                "skill_key": 0,
                "skill_level": 0,
                "phase_level": "精0 1级",
                "skillname": "制造α",
                "roomType": "制造站",
                "des": "生产力+15%",
            },
            {
                "skill_key": 0,
                "skill_level": 1,
                "phase_level": "精2 1级",
                "skillname": "制造β",
                "roomType": "制造站",
                "des": "生产力+25%",
            },
        ],
        "孑": [
            {
                "skill_key": 0,
                "skill_level": 0,
                "phase_level": "精0 1级",
                "skillname": "摊贩经济",
                "roomType": "贸易站",
                "des": "每差1笔+4%",
            }
        ],
        "银灰": [
            {
                "skill_key": 0,
                "skill_level": 0,
                "phase_level": "精2 1级",
                "skillname": "订单",
                "roomType": "贸易站",
                "des": "效率+20%",
            }
        ],
    }
    snapshot = {
        "has_data": True,
        "message": "已同步",
        "operators": [
            {"name": "赫默", "owned": True, "phase": 0, "level": 1},
            {"name": "孑", "owned": False, "phase": None, "level": None},
            {"name": "银灰", "owned": True, "phase": 0, "level": 1},
        ],
    }
    plan = PlanModel(
        plan1={
            "room_1_1": {
                "name": "制造站",
                "product": "gold",
                "plans": [{"agent": "赫默"}],
            },
            "room_1_2": {
                "name": "贸易站",
                "product": "lmd",
                "plans": [{"agent": "银灰"}],
            },
        },
        advanced_settings={"api_key": "private-test-value"},
    )
    monkeypatch.setattr(riic, "skill_index", lambda: catalog)
    monkeypatch.setattr(building_skills, "skill_index", lambda: catalog)
    monkeypatch.setattr(riic, "load_skill_snapshot", lambda: copy.deepcopy(snapshot))
    monkeypatch.setattr(
        riic,
        "load_income_cache",
        lambda: {
            "has_inventory": True,
            "inventory": {"gold": 9167, "lmd": 6459788},
            "observed_at": 1791719522.119031,
        },
    )
    monkeypatch.setattr(riic.config, "plan", plan, raising=False)
    return snapshot, plan


def result(fn, **kwargs):
    return json.loads(fn(**kwargs))


def test_skills_select_current_slot_and_explicit_growth_wins(state):
    current = result(riic.get_riic_knowledge, operators=["赫默"])
    assert [s["skillname"] for s in current["operators"][0]["active_skills"]] == [
        "制造α"
    ]
    manual = result(
        riic.get_riic_knowledge,
        operators=["赫默"],
        roster_overrides=[{"name": "赫默", "owned": True, "phase": 2, "level": 1}],
    )
    assert [s["skillname"] for s in manual["operators"][0]["active_skills"]] == [
        "制造β"
    ]
    assert manual["operators"][0]["source"] == "user"
    assert state[0]["operators"][0]["phase"] == 0


@pytest.mark.parametrize("external_selected", [False, True])
def test_knowledge_reads_packaged_terms_only_with_bundled_resources(
    state, monkeypatch, tmp_path, external_selected
):
    package = tmp_path / "arknights_mower"
    relative = "pages/basement_skill/buffer.json"
    bundled = tmp_path / "ui" / "dist" / relative
    bundled.parent.mkdir(parents=True)
    bundled.write_text(
        json.dumps(
            {
                "linked": {
                    "termId": "cc.test.linked",
                    "termName": "联动",
                    "description": "依赖<$cc.test.nested>进驻</>",
                },
                "nested": {
                    "termId": "cc.test.nested",
                    "termName": "进驻",
                    "description": "进驻对应设施",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    selected = tmp_path / "external" / "ui" / "src" / relative
    monkeypatch.setattr(building_skills, "__rootdir__", package)
    monkeypatch.setattr(
        building_skills,
        "resource_ui_path",
        lambda _relative, *, source: selected if external_selected else None,
    )
    monkeypatch.setattr(riic, "term_index", building_skills.term_index.__wrapped__)
    riic.skill_index()["赫默"][0]["des"] = "生产力+15%，需要<$cc.test.linked>联动</>"

    response = result(riic.get_riic_knowledge, operators=["赫默"])

    if external_selected:
        assert response["error"]["code"] == "resource_unavailable"
    else:
        assert [
            skill["skillname"] for skill in response["operators"][0]["active_skills"]
        ] == ["制造α"]
        assert {term["id"] for term in response["terms"]} == {
            "cc.test.linked",
            "cc.test.nested",
        }
        assert response["missing_terms"] == []


def test_knowledge_without_term_references_reads_independent_topics(state, monkeypatch):
    def missing_terms():
        raise FileNotFoundError("buffer.json")

    monkeypatch.setattr(riic, "term_index", missing_terms)

    response = result(riic.get_riic_knowledge, topic="code_diagnosis")
    assert response["code_locations"]["sources"]
    response = result(riic.get_riic_knowledge, operators=["赫默"])
    assert response["operators"][0]["active_skills"]
    assert response["terms"] == []


def test_draft_rejects_unowned_and_locked_skills_without_mutation(state):
    before = state[1].model_dump()
    response = result(
        riic.try_riic_plan, assignments=[{"room": "room_1_2", "operators": ["孑"]}]
    )
    assert not response["valid"]
    assert any(e["code"] == "unowned_operator" for e in response["errors"])
    locked = result(riic.try_riic_plan, assignments=[])
    assert any(e["code"] == "skill_not_unlocked" for e in locked["errors"])
    assert state[1].model_dump() == before
    assert "private-test-value" not in json.dumps(response)


def test_draft_checks_preserved_rooms_duplicates_and_capacity(state):
    response = result(
        riic.try_riic_plan, assignments=[{"room": "room_1_2", "operators": ["赫默"]}]
    )
    assert any(e["code"] == "duplicate_operator" for e in response["errors"])
    response = result(
        riic.try_riic_plan,
        assignments=[{"room": "room_1_1", "operators": ["赫默", "银灰"]}],
    )
    assert any(e["code"] == "capacity_exceeded" for e in response["errors"])
    response = result(
        riic.try_riic_plan, assignments=[{"room": "room_3_3", "operators": ["赫默"]}]
    )
    assert any(e["code"] == "unknown_room" for e in response["errors"])


def test_partial_draft_is_explicit_and_accepts_user_owned_snapshot(state):
    response = result(
        riic.try_riic_plan,
        assignments=[{"room": "room_1_2", "operators": ["孑"]}],
        roster_overrides=[{"name": "孑", "owned": True, "phase": 0, "level": 1}],
    )
    assert response["valid"]
    assert response["scope"] == "primary_staffing_only"
    assert response["draft"]["room_1_1"]["plans"][0]["agent"] == "赫默"
    assert not response["saved"]
    assert response["unchecked"]


def test_absent_box_never_infers_ownership(state):
    state[0].update(has_data=False, operators=[])
    response = result(riic.try_riic_plan, assignments=[])
    assert not response["valid"]
    assert any(e["code"] == "ownership_unknown" for e in response["errors"])
    context = result(riic.get_riic_context)
    assert context["owned_operators"] == []
    assert not context["has_data"]
    knowledge = result(riic.get_riic_knowledge, operators=["赫默"])
    assert knowledge["operators"][0]["active_skills"] == []
    assert knowledge["operators"][0]["skills"][1]["status"] == "unknown"


def test_growth_unknown_stays_unknown_after_ownership_only_override(state):
    response = result(
        riic.try_riic_plan,
        assignments=[],
        roster_overrides=[{"name": "赫默", "owned": True}],
    )
    assert any(e["code"] == "growth_unknown" for e in response["errors"])


def test_physical_capacity_and_duplicate_room_are_rejected(state):
    state[1].plan1.room_1_1.plans *= 4
    response = result(riic.try_riic_plan, assignments=[])
    assert any(e["code"] == "capacity_exceeded" for e in response["errors"])
    response = result(
        riic.try_riic_plan,
        assignments=[
            {"room": "room_1_1", "operators": ["赫默"]},
            {"room": "room_1_1", "operators": []},
        ],
    )
    assert any(e["code"] == "duplicate_room" for e in response["errors"])


def test_nested_terms_expand_once_and_missing_terms_remain_visible(state, monkeypatch):
    riic.skill_index()["赫默"][0]["des"] += "<$alpha>联动</>"
    monkeypatch.setattr(
        riic,
        "term_index",
        lambda: {
            "alpha": {"termName": "甲", "description": "<$beta>乙</>"},
            "beta": {"termName": "乙", "description": "<$alpha>甲</><$missing>缺失</>"},
        },
    )
    response = result(riic.get_riic_knowledge, operators=["赫默"])
    assert {t["id"] for t in response["terms"]} == {"alpha", "beta"}
    assert response["missing_terms"] == ["missing"]
    assert "<" not in response["operators"][0]["active_skills"][0]["des"]


@pytest.mark.parametrize("workflow", ["manual", "graph"])
def test_model_workflows_dispatch_real_read_only_trial(state, monkeypatch, workflow):
    from langchain_core.messages import AIMessage, ToolMessage

    from arknights_mower.agent import agent

    call = {
        "id": "trial",
        "type": "function",
        "function": {
            "name": "try_riic_plan",
            "arguments": json.dumps(
                {
                    "assignments": [{"room": "room_1_2", "operators": ["孑"]}],
                    "roster_overrides": [
                        {"name": "孑", "owned": True, "phase": 0, "level": 1}
                    ],
                }
            ),
        },
    }
    observations = []

    class Model:
        def stream(self, messages):
            yield self.invoke(messages)

        def invoke(self, messages):
            observations.extend(m for m in messages if isinstance(m, ToolMessage))
            if not observations:
                return AIMessage(content="", additional_kwargs={"tool_calls": [call]})
            return AIMessage(content="主班草案已检查")

    monkeypatch.setattr(agent, "build_llm", lambda *args, **kwargs: Model())
    before = state[1].model_dump()
    messages = agent._build_messages("按我的BOX尝试排班")
    if workflow == "manual":
        assert (
            list(agent._run_manual_tool_loop(messages, "test-key"))[-1]
            == "主班草案已检查"
        )
    else:
        if agent.StateGraph is None:
            pytest.skip("LangGraph optional dependency unavailable")
        reply = agent.build_workflow("test-key").invoke({"messages": messages})
        assert reply["messages"][-1].content == "主班草案已检查"
    assert json.loads(observations[-1].content)["valid"]
    assert state[1].model_dump() == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"operators": ["赫默"] * 13},
        {"topic": "../../conf"},
        {
            "roster_overrides": [
                {"name": "赫默", "owned": True, "phase": True, "level": 1}
            ]
        },
    ],
)
def test_invalid_tool_arguments_return_structured_errors(state, kwargs):
    assert (
        result(riic.get_riic_knowledge, **kwargs)["error"]["code"]
        == "invalid_arguments"
    )


def test_context_joins_existing_combinations_and_exposes_no_settings(state):
    context = result(riic.get_riic_context)
    karlan = next(g for g in context["combinations"] if g["id"] == "builtin-karlan")
    assert "孑" in karlan["missing"]
    assert "银灰" in karlan["owned"]
    assert "private-test-value" not in json.dumps(context)


@pytest.mark.parametrize(
    "role,facts,code",
    [
        ("primary", {"owned": False}, "unowned_operator"),
        ("primary", {"phase": None, "level": None}, "growth_unknown"),
        (
            "replacement",
            {"owned": True, "phase": None, "level": None},
            "growth_unknown",
        ),
    ],
)
def test_context_reports_main_staffing_issues_without_rejecting_context(
    state, role, facts, code
):
    snapshot, saved = state
    name = "赫默" if role == "primary" else "孑"
    if role == "replacement":
        saved.plan1.room_1_1.plans[0].replacement = [name]
    next(row for row in snapshot["operators"] if row["name"] == name).update(facts)
    before_plan, before_roster = saved.model_dump(), copy.deepcopy(snapshot)
    context = result(riic.get_riic_context)
    assert "error" not in context
    assert context["normal_plan"]["plan1"]["room_1_1"]["plans"][0]["agent"] == "赫默"
    issues = context["normal_plan_issues"]
    assert issues["scope"] == "main_staffing_static_only"
    assert not issues["native_checked"] and not issues["income_checked"]
    assert any(
        error["code"] == code and error["operator"] == name and error["role"] == role
        for error in issues["errors"]
    )
    assert saved.model_dump() == before_plan
    assert snapshot == before_roster


def test_context_issues_use_same_roster_and_exclude_backups_and_native_checks(
    state, monkeypatch
):
    snapshot, saved = state
    from arknights_mower.utils.config.plan import BackupPlan

    saved.backup_plans = [
        BackupPlan(
            name="private-backup-name",
            trigger={"left": "private-trigger"},
            plan={"room_1_2": {"name": "贸易站", "plans": [{"agent": "孑"}]}},
        )
    ]
    before_plan = saved.model_dump()
    before_conf = riic.config.conf.model_dump()
    calls = []

    def load_once():
        calls.append("roster")
        assert len(calls) == 1
        return copy.deepcopy(snapshot)

    monkeypatch.setattr(riic, "load_skill_snapshot", load_once)
    monkeypatch.setattr(
        riic, "_native_operators", lambda *a: pytest.fail("native check forbidden")
    )
    monkeypatch.setattr(
        riic, "Operators", lambda *a, **kw: pytest.fail("native construction forbidden")
    )
    monkeypatch.setattr(riic.config, "save_plan", lambda: pytest.fail("save forbidden"))
    monkeypatch.setattr(riic.config, "save_conf", lambda: pytest.fail("save forbidden"))
    context = result(
        riic.get_riic_context,
        roster_overrides=[
            {"name": "银灰", "owned": True, "phase": 2, "level": 1},
        ],
    )
    assert calls == ["roster"]
    assert context["normal_plan_issues"]["errors"] == []
    assert not context["normal_plan_issues"]["native_checked"]
    assert context["normal_backup_count"] == 1
    assert "孑" in context["normal_reserved_names"]
    assert context["normal_plan"]["backup_plans"] == []
    assert saved.model_dump() == before_plan
    assert riic.config.conf.model_dump() == before_conf
    for secret in ("private-trigger", "private-backup-name", "private-test-value"):
        assert secret not in json.dumps(context)


def test_context_issues_include_locked_skills_and_facility_skill_warnings(state):
    saved = state[1]
    saved.plan1.room_1_1.plans[0].replacement = ["银灰"]
    context = result(riic.get_riic_context)
    issues = context["normal_plan_issues"]
    assert any(
        error["code"] == "skill_not_unlocked" and error["operator"] == "银灰"
        for error in issues["errors"]
    )
    assert any(
        warning["code"] == "no_facility_skill" and warning["role"] == "replacement"
        for warning in issues["warnings"]
    )


def test_context_fixed_facility_issue_identifies_expected_and_actual_names(state):
    state[1].plan1.central = riic.Facility(name="控制中枢", plans=[])
    context = result(riic.get_riic_context)
    assert {
        "code": "invalid_fixed_facility",
        "room": "central",
        "expected": "中枢",
        "actual": "控制中枢",
    } in context["normal_plan_issues"]["errors"]


def test_tools_are_available_to_both_model_workflows():
    from arknights_mower.agent import agent

    names = {tool["function"]["name"] for tool in agent.get_tools()}
    for name in ("get_riic_context", "get_riic_knowledge", "try_riic_plan"):
        assert name in names
        assert name in agent.tool_func_map
        assert name in agent.tool_message_map
    assert "try_riic_plan" in agent._build_ai_intro()


@pytest.mark.parametrize(
    "topic",
    [
        "taxonomy",
        "mower_plan",
        "new_operators",
        "income_export",
        "freshness",
        "plan_review",
        "mower_tutorial",
        "code_diagnosis",
    ],
)
def test_extended_knowledge_topics_are_queryable_and_read_only(state, topic):
    snapshot, plan = state
    before = plan.model_dump()
    response = result(riic.get_riic_knowledge, topic=topic, operators=["赫默"])
    assert response["topic"] == topic
    assert response["guide"]
    assert response["operators"][0]["active_skills"][0]["skillname"] == "制造α"
    assert plan.model_dump() == before
    assert "api_key" not in json.dumps(response)
    declared = riic.get_riic_knowledge_tool_def["function"]["parameters"]["properties"][
        "topic"
    ]["enum"]
    assert topic in declared


def test_tutorial_topic_reads_current_source_sections(state):
    response = result(riic.get_riic_knowledge, topic="mower_tutorial")
    tutorial = response["tutorial"]
    assert tutorial["available"] and not tutorial["truncated"]
    assert tutorial["missing_sections"] == []
    sections = {section["anchor"]: section for section in tutorial["sections"]}
    assert "下班参考线" in sections["schedule-design-mood"]["text"]
    assert "整组替班" in sections["schedule-design-mood"]["text"]
    assert "待命不恢复心情" in sections["schedule-design-standby"]["text"]
    assert sections["schedule-design-mood"]["url"].endswith("#schedule-design-mood")
    assert "<script" not in json.dumps(tutorial)


def test_tutorial_topic_reads_packaged_html_and_reports_missing_sections(
    state, monkeypatch, tmp_path
):
    from arknights_mower.agent.tools import riic_tutorial

    monkeypatch.setattr(riic_tutorial, "__rootdir__", tmp_path / "arknights_mower")
    guide = tmp_path / "ui" / "dist" / "docs" / riic_tutorial.GUIDE_NAME
    guide.parent.mkdir(parents=True)
    guide.write_text(
        '<h2 id="schedule-design-mood">工休估算</h2><p>明确资料 &amp; 实测</p>'
        '<script>不要作为教程返回</script><h2 id="other">无关章节</h2><p>忽略</p>',
        encoding="utf-8",
    )
    response = result(riic.get_riic_knowledge, topic="mower_tutorial")["tutorial"]
    assert response["available"]
    assert response["source"].startswith("ui/dist/docs/")
    assert response["sections"][0]["text"] == "明确资料 & 实测"
    assert "schedule-design-standby" in response["missing_sections"]
    guide.unlink()
    missing = result(riic.get_riic_knowledge, topic="mower_tutorial")["tutorial"]
    assert not missing["available"]
    assert missing["sections"] == []


def test_tutorial_large_sections_are_explicitly_omitted(state, monkeypatch, tmp_path):
    from arknights_mower.agent.tools import riic_tutorial

    monkeypatch.setattr(riic_tutorial, "__rootdir__", tmp_path / "arknights_mower")
    guide = tmp_path / "ui" / riic_tutorial.GUIDE_NAME
    guide.parent.mkdir()
    guide.write_text(
        '<h2 id="schedule-design-mood">工休估算</h2><p>' + "长" * 12001 + "</p>",
        encoding="utf-8",
    )
    response = result(riic.get_riic_knowledge, topic="mower_tutorial")["tutorial"]
    assert response["truncated"]
    assert "schedule-design-mood" in response["missing_sections"]
    assert response["sections"] == []


def test_code_diagnosis_locations_read_real_source_context(state):
    from arknights_mower.agent.tools.get_source_snippet import get_source_snippet

    response = result(riic.get_riic_knowledge, topic="code_diagnosis")
    locations = response["code_locations"]
    assert "不是故障时版本" in locations["scope"]
    assert len(locations["sources"]) == 6
    for source in locations["sources"]:
        assert source["available"] and not source["missing_symbols"]
        assert len(source["sha256"]) == 64
        for entry in source["locations"]:
            snippet = result(
                get_source_snippet,
                file_path=source["file_path"],
                line_number=entry["line_number"],
                context=1,
            )
            assert entry["symbol"] in snippet["source_code"]


def test_code_locations_follow_source_lines_and_keep_missing_code_explicit(
    state, monkeypatch, tmp_path
):
    import importlib

    source_tool = importlib.import_module(
        "arknights_mower.agent.tools.get_source_snippet"
    )
    monkeypatch.setattr(source_tool, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(source_tool, "_PACKAGE_ROOT", tmp_path / "arknights_mower")
    worker = tmp_path / "ui" / "src" / "riic" / "incomeWorker.js"
    worker.parent.mkdir(parents=True)
    worker.write_text("// first\n// second\nexport function calculateIncome(plan) {}\n")
    response = result(riic.get_riic_knowledge, topic="code_diagnosis")["code_locations"]
    assert response["sources"][0]["locations"][0]["line_number"] == 3
    assert all(not row["available"] for row in response["sources"][1:])
    before = response["sources"][0]["sha256"]
    worker.write_text(
        "// first\n// second\n// third\nexport function calculateIncome(plan) {}\n"
    )
    changed = result(riic.get_riic_knowledge, topic="code_diagnosis")["code_locations"]
    assert changed["sources"][0]["locations"][0]["line_number"] == 4
    assert changed["sources"][0]["sha256"] != before
    worker.write_text("// symbol absent\n")
    missing = result(riic.get_riic_knowledge, topic="code_diagnosis")["code_locations"]
    assert missing["sources"][0]["available"]
    assert missing["sources"][0]["locations"] == []
    assert missing["sources"][0]["missing_symbols"] == [
        "export function calculateIncome("
    ]


def test_code_diagnosis_indexes_and_reads_a_source_larger_than_one_mib(
    state, monkeypatch, tmp_path
):
    from arknights_mower.agent.tools import get_source_snippet as source_tool

    monkeypatch.setattr(source_tool, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(source_tool, "_PACKAGE_ROOT", tmp_path / "arknights_mower")
    source = tmp_path / "ui" / "src" / "riic" / "incomeWorker.js"
    source.parent.mkdir(parents=True)
    padding = b"// " + b"x" * 1020 + b"\r\n"
    marker = b"export function calculateIncome(plan) {}"
    raw = b"\xef\xbb\xbf" + padding * 1024 + marker + b"\r// final"
    assert len(raw) > 1024**2
    source.write_bytes(raw)

    response = result(riic.get_riic_knowledge, topic="code_diagnosis")
    indexed = response["code_locations"]["sources"][0]

    assert indexed["available"]
    assert indexed["line_count"] == 1026
    assert indexed["sha256"] == hashlib.sha256(raw).hexdigest()
    assert indexed["locations"][0]["line_number"] == 1025
    snippet = result(
        source_tool.get_source_snippet,
        file_path=indexed["file_path"],
        line_number=1025,
        context=0,
    )
    assert snippet["source_code"] == marker.decode() + "\n"


def test_source_fragment_stops_at_requested_lines_and_applies_its_budgets(
    state, monkeypatch, tmp_path
):
    from arknights_mower.agent.tools import get_source_snippet as source_tool

    monkeypatch.setattr(source_tool, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(source_tool, "_PACKAGE_ROOT", tmp_path / "arknights_mower")
    monkeypatch.setattr(source_tool, "_MAX_SOURCE_SCAN_BYTES", 32)
    monkeypatch.setattr(source_tool, "_MAX_SNIPPET_BYTES", 12)
    source = tmp_path / "ui" / "src" / "riic" / "incomeWorker.js"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"first\nsecond\n" + b"padding\n" * 8)

    def fragment(line, context=0):
        return result(
            source_tool.get_source_snippet,
            file_path=str(source),
            line_number=line,
            context=context,
        )["source_code"]

    assert fragment(1) == "first\n"
    assert "返回字节上限" in fragment(1, context=1)
    assert "扫描字节上限" in fragment(10)
    response = result(riic.get_riic_knowledge, topic="code_diagnosis")
    indexed = response["code_locations"]["sources"][0]
    assert not indexed["available"]
    assert "超出读取范围" in indexed["reason"]
    assert "sha256" not in indexed

    monkeypatch.setattr(source_tool, "_MAX_SOURCE_LINE_BYTES", 8)
    source.write_bytes(b"first\n" + b"x" * 9 + b"\n")
    assert fragment(1) == "first\n"
    assert "源码行超过" in fragment(2)


def test_knowledge_schema_covers_every_supported_topic():
    declared = riic.get_riic_knowledge_tool_def["function"]["parameters"]["properties"][
        "topic"
    ]["enum"]
    assert set(declared) == set(riic._read_data("knowledge")["topics"])


@pytest.fixture
def complete_state(state, monkeypatch):
    snapshot, saved = state
    for name in ("凛冬", "旅骨", "菲亚梅塔", "国度", "行铃"):
        riic.skill_index()[name] = []
        snapshot["operators"].append(
            {"name": name, "owned": True, "phase": 2, "level": 90}
        )
    snapshot["operators"][1].update(owned=True, phase=0, level=1)
    snapshot["operators"][2].update(phase=2)
    for name in ("save_conf", "save_plan", "save_rescue_plan"):
        monkeypatch.setattr(
            riic.config, name, lambda *a, **kw: pytest.fail("persistence forbidden")
        )
    return snapshot, saved


def _complete_plan():
    return {
        "plan1": {
            "room_1_1": {
                "name": "制造站",
                "product": "gold",
                "plans": [
                    {
                        "agent": "赫默",
                        "group": "生产",
                        "replacement": ["凛冬"],
                        "group_bindings": [{"group": "", "replacement": ["旅骨"]}],
                    }
                ],
            },
            "room_1_2": {
                "name": "贸易站",
                "product": "lmd",
                "plans": [{"agent": "银灰", "group": "生产", "replacement": ["孑"]}],
            },
            "dormitory_1": {
                "name": "宿舍",
                "plans": [
                    {"agent": "菲亚梅塔", "replacement": ["赫默"]},
                    *[{"agent": "Free"} for _ in range(4)],
                ],
            },
        },
        "facility_levels": {"room_1_1": 1, "room_1_2": 1, "dormitory_1": 1},
        "conf": {"rest_in_full": "赫默"},
        "advanced_settings": {"fia_fool": True, "free_room": True},
    }


def test_complete_plan_runs_native_validation_and_preserves_full_bindings(
    complete_state,
):
    original_plan = complete_state[1].model_dump()
    original_conf = riic.config.conf.model_dump()
    draft = _complete_plan()
    original_draft = copy.deepcopy(draft)
    response = result(riic.try_riic_plan, plan=draft)
    assert response["valid"], response
    assert response["native_checked"]
    assert response["scope"] == "complete_main_plan"
    assert response["status"] == "passed"
    slot = response["plan"]["plan1"]["room_1_1"]["plans"][0]
    assert slot["replacement"] == ["凛冬"]
    assert slot["group_bindings"] == [{"group": "", "replacement": ["旅骨"]}]
    assert response["plan"]["plan1"]["dormitory_1"]["plans"][0]["replacement"] == [
        "赫默"
    ]
    assert response["plan"]["conf"]["rest_in_full"] == "赫默"
    assert response["plan"]["advanced_settings"]["fia_fool"] is True
    assert response["unchecked"] and not response["saved"]
    assert complete_state[1].model_dump() == original_plan
    assert riic.config.conf.model_dump() == original_conf
    assert draft == original_draft
    assert "private-test-value" not in json.dumps(response)


@pytest.mark.parametrize(
    "location", ["primary", "replacement", "binding", "fia_target"]
)
@pytest.mark.parametrize(
    "fact,code",
    [
        ({"owned": False, "phase": None, "level": None}, "unowned_operator"),
        ({"owned": True, "phase": None, "level": None}, "growth_unknown"),
    ],
)
def test_complete_plan_requires_all_owned_growth(complete_state, location, fact, code):
    draft = _complete_plan()
    name = {
        "primary": "银灰",
        "replacement": "凛冬",
        "binding": "旅骨",
        "fia_target": "赫默",
    }[location]
    next(row for row in complete_state[0]["operators"] if row["name"] == name).update(
        fact
    )
    response = result(riic.try_riic_plan, plan=draft)
    assert not response["valid"]
    assert any(
        error["code"] == code and error["operator"] == name
        for error in response["errors"]
    )
    if location == "fia_target":
        assert any(error.get("role") == "fia_target" for error in response["errors"])
    assert not response["native_checked"]


def test_complete_plan_checks_replacement_skill_unlock(complete_state):
    draft = _complete_plan()
    draft["plan1"]["room_1_1"]["plans"][0]["replacement"] = ["银灰"]
    next(row for row in complete_state[0]["operators"] if row["name"] == "银灰").update(
        phase=0
    )
    draft["plan1"]["room_1_2"]["plans"][0]["agent"] = "国度"
    draft["plan1"]["room_1_2"]["plans"][0]["replacement"] = ["银灰"]
    response = result(riic.try_riic_plan, plan=draft)
    assert not response["valid"]
    assert any(
        error["code"] == "skill_not_unlocked" and error.get("role") == "replacement"
        for error in response["errors"]
    )


@pytest.mark.parametrize(
    "change",
    ["shared_cover", "self_cover", "duplicate_bindings", "fia_target_outside_main"],
)
def test_complete_plan_uses_real_native_group_and_fia_rules(complete_state, change):
    draft = _complete_plan()
    manufacturing = draft["plan1"]["room_1_1"]["plans"][0]
    if change == "shared_cover":
        draft["plan1"]["room_1_2"]["plans"][0]["replacement"] = ["凛冬"]
    elif change == "self_cover":
        manufacturing["replacement"] = ["赫默"]
    elif change == "duplicate_bindings":
        manufacturing["group_bindings"][0]["group"] = "生产"
    else:
        draft["plan1"]["dormitory_1"]["plans"][0]["replacement"] = ["旅骨"]
    response = result(riic.try_riic_plan, plan=draft)
    assert not response["valid"]
    assert any(
        error["code"] == "native_validation_failed" for error in response["errors"]
    )


def test_complete_plan_allows_new_single_layout_and_products(complete_state):
    draft = _complete_plan()
    draft["plan1"]["room_3_3"] = draft["plan1"].pop("room_1_1")
    draft["plan1"]["room_3_3"]["product"] = "exp3"
    draft["facility_levels"].pop("room_1_1")
    draft["facility_levels"]["room_3_3"] = 1
    response = result(riic.try_riic_plan, plan=draft)
    assert response["valid"], response
    assert response["plan"]["plan1"]["room_3_3"]["product"] == "exp3"
    assert "room_1_1" not in response["draft"]
    assert any("电力" in line for line in response["unchecked"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(
            backup_plans=[{"name": "ignored", "trigger": {"left": "True"}}]
        ),
        lambda p: p.update(extra_secret="forbidden"),
        lambda p: p["plan1"]["room_1_1"]["plans"][0].update(replacment=["孑"]),
        lambda p: p.update(advanced_settings={"api_key": "forbidden"}),
        lambda p: p.update(conf={"mood_limits": {"lowr": 3}}),
        lambda p: p["plan1"].update(gaming_1={"plans": []}),
    ],
)
def test_complete_plan_rejects_ignored_or_conditional_fields(complete_state, mutate):
    draft = _complete_plan()
    mutate(draft)
    response = result(riic.try_riic_plan, plan=draft)
    assert response["error"]["code"] == "invalid_arguments"


def test_complete_and_legacy_inputs_are_exclusive(complete_state):
    assert result(riic.try_riic_plan, assignments=[], plan=_complete_plan())["error"]
    assert result(riic.try_riic_plan)["error"]
    assert result(riic.try_riic_plan, assignments=[], mode="rescue")["error"]


def test_context_exposes_safe_main_snapshot_and_cache_freshness(complete_state):
    _, saved = complete_state
    saved.plan1.room_1_1.plans[0].replacement = ["凛冬"]
    saved.plan1.room_1_1.plans[0].group_bindings = [
        riic.GroupBinding(group="轮休", replacement=["旅骨"])
    ]
    saved.facility_levels = {"room_1_1": 1}
    from arknights_mower.utils.config.plan import BackupPlan

    saved.backup_plans = [
        BackupPlan(
            name="private-backup-name",
            trigger={"left": "private-expression"},
            task={"room_1_2": ["行铃"]},
            plan={
                "room_1_1": {
                    "name": "制造站",
                    "plans": [{"agent": "国度", "replacement": ["孑"]}],
                }
            },
        )
    ]
    before = saved.model_dump()
    response = result(riic.get_riic_context)
    assert response["inventory"] == {"gold": 9167, "lmd": 6459788}
    assert response["observed_at"] == 1791719522.119031
    assert response["facility_levels"] == {"room_1_1": 1}
    assert response["normal_backup_count"] == 1
    assert set(response["normal_reserved_names"]) >= {
        "赫默",
        "银灰",
        "凛冬",
        "旅骨",
        "国度",
        "孑",
        "行铃",
    }
    assert response["normal_plan"]["backup_plans"] == []
    assert response["normal_plan"]["plan1"]["room_1_1"]["plans"][0][
        "group_bindings"
    ] == [{"group": "轮休", "replacement": ["旅骨"]}]
    rendered = json.dumps(response)
    for secret in (
        "private-expression",
        "private-backup-name",
        "private-test-value",
        "api_key",
    ):
        assert secret not in rendered
    assert saved.model_dump() == before


@pytest.mark.parametrize(
    "residual",
    [
        {},
        {"replacement": ["旅骨"]},
        {"replacement": ["未知残留代号"]},
        {
            "group": "旧组",
            "group_bindings": [
                {"group": "旧附加组", "replacement": ["旅骨", "未知残留代号"]}
            ],
        },
    ],
)
def test_rescue_compiles_recycle_empty_slots_without_rejecting_inheritance(
    complete_state, monkeypatch, residual
):
    from arknights_mower.utils.emergency_plan import compile_rescue_schedule

    normal = _complete_plan()
    normal["plan1"]["recycle"] = {
        "name": "回收站",
        "plans": [
            {"agent": "国度", "replacement": ["旅骨"]},
            {"agent": "行铃", "replacement": ["旅骨"]},
        ],
    }
    normal["facility_levels"]["recycle"] = 3
    saved = PlanModel(**normal)
    monkeypatch.setattr(riic.config, "plan", saved)
    riic.skill_index()["伊桑"] = []
    complete_state[0]["operators"].append(
        {"name": "伊桑", "owned": True, "phase": 2, "level": 1}
    )
    source = {
        "plan1": {
            "room_1_1": {"plans": [{"agent": "伊桑"}]},
            "recycle": {"plans": [{"agent": "", **residual}]},
        }
    }
    before = saved.model_dump()
    before_conf = riic.config.conf.model_dump()
    before_source = copy.deepcopy(source)
    data = riic._native_operators(saved, riic.config.conf.model_copy(deep=True))
    compiled = compile_rescue_schedule(data, PlanModel(**source))
    response = result(riic.try_riic_plan, plan=source, mode="rescue")
    assert response["valid"], response
    assert response["scope"] == "rescue_snapshot"
    assert response["normal_native_checked"] and response["rescue_snapshot_checked"]
    assert not response["native_checked"]
    assert response["resolvedPlan"]["plan1"]["recycle"]["plans"] == [
        {"agent": "国度", "group": "", "replacement": ["旅骨"], "group_bindings": []},
        {"agent": "行铃", "group": "", "replacement": ["旅骨"], "group_bindings": []},
    ]
    assert response["plan"]["plan1"]["recycle"]["plans"][0]["agent"] == ""
    assert (
        response["resolvedPlan"]["plan1"]["recycle"]["plans"]
        == compiled.plan1.recycle.model_dump()["plans"]
    )
    assert saved.model_dump() == before
    assert riic.config.conf.model_dump() == before_conf
    assert source == before_source


@pytest.mark.parametrize(
    "replacement,code",
    [
        ("旅骨", "normal_reference_overlap"),
        ("未知残留代号", "unknown_operator"),
    ],
)
def test_rescue_explicit_worker_keeps_all_binding_reference_checks(
    complete_state, monkeypatch, replacement, code
):
    saved = PlanModel(**_complete_plan())
    monkeypatch.setattr(riic.config, "plan", saved)
    source = {
        "plan1": {
            "room_1_1": {
                "plans": [
                    {
                        "agent": "国度",
                        "group_bindings": [
                            {"group": "新组", "replacement": [replacement]}
                        ],
                    }
                ]
            }
        }
    }
    before_plan, before_conf = saved.model_dump(), riic.config.conf.model_dump()
    response = result(riic.try_riic_plan, plan=source, mode="rescue")
    assert not response["valid"]
    assert any(error["code"] == code for error in response["errors"])
    assert saved.model_dump() == before_plan
    assert riic.config.conf.model_dump() == before_conf


@pytest.mark.parametrize("room", ["dormitory_1", "factory", "train"])
def test_rescue_special_blank_slots_do_not_ignore_replacement_references(
    complete_state, monkeypatch, room
):
    monkeypatch.setattr(riic.config, "plan", PlanModel(**_complete_plan()))
    response = result(
        riic.try_riic_plan,
        mode="rescue",
        plan={
            "plan1": {
                "room_1_1": {"plans": [{"agent": "国度"}]},
                room: {"plans": [{"agent": "", "replacement": ["未知残留代号"]}]},
            }
        },
    )
    assert not response["valid"]
    assert any(
        error["code"] == "unknown_operator" and error["operator"] == "未知残留代号"
        for error in response["errors"]
    )


def test_normal_reserved_names_keep_blank_slot_references(complete_state):
    saved = complete_state[1]
    saved.plan1.room_1_1.plans[0].agent = ""
    saved.plan1.room_1_1.plans[0].replacement = ["未知残留代号"]
    context = result(riic.get_riic_context)
    assert "未知残留代号" in context["normal_reserved_names"]
    assert any(
        error["code"] == "unknown_operator" and error["operator"] == "未知残留代号"
        for error in context["normal_plan_issues"]["errors"]
    )


@pytest.mark.parametrize(
    "reference", ["main_replacement", "multibinding", "fia_target", "backup_task"]
)
def test_rescue_excludes_every_normal_reference(complete_state, monkeypatch, reference):
    normal = _complete_plan()
    from arknights_mower.utils.config.plan import BackupPlan

    saved = PlanModel(**normal)
    if reference == "backup_task":
        saved.backup_plans = [BackupPlan(task={"room_1_1": ["国度"]})]
    monkeypatch.setattr(riic.config, "plan", saved)
    name = {
        "main_replacement": "凛冬",
        "multibinding": "旅骨",
        "fia_target": "赫默",
        "backup_task": "国度",
    }[reference]
    response = result(
        riic.try_riic_plan,
        plan={"plan1": {"room_1_1": {"plans": [{"agent": name}]}}},
        mode="rescue",
    )
    assert not response["valid"]
    assert response["errors"] == [
        {"code": "normal_reference_overlap", "operators": [name]}
    ]
    assert "resolvedPlan" not in response


def test_rescue_with_normal_backups_is_incomplete_without_resolved_plan(
    complete_state, monkeypatch
):
    from arknights_mower.utils.config.plan import BackupPlan

    saved = PlanModel(**_complete_plan())
    saved.backup_plans = [BackupPlan(name="运行条件待实测", trigger={"left": "False"})]
    monkeypatch.setattr(riic.config, "plan", saved)
    response = result(
        riic.try_riic_plan,
        plan={"plan1": {"room_1_1": {"plans": [{"agent": "国度"}]}}},
        mode="rescue",
    )
    assert not response["valid"] and response["status"] == "incomplete", response
    assert response["rescue_snapshot_checked"]
    assert "resolvedPlan" not in response
    assert response["warnings"][-1]["code"] == "conditional_normal_plan"


def test_rescue_inherited_unowned_replacement_cannot_pass(complete_state, monkeypatch):
    monkeypatch.setattr(riic.config, "plan", PlanModel(**_complete_plan()))
    next(row for row in complete_state[0]["operators"] if row["name"] == "孑").update(
        owned=False
    )
    response = result(
        riic.try_riic_plan,
        plan={"plan1": {"room_1_1": {"plans": [{"agent": "国度"}]}}},
        mode="rescue",
    )
    assert not response["valid"]
    assert any(
        error["code"] == "unowned_operator" and error["operator"] == "孑"
        for error in response["errors"]
    )
    assert "resolvedPlan" not in response


def test_rescue_product_mismatch_does_not_pass_main_only_snapshot(
    complete_state, monkeypatch
):
    monkeypatch.setattr(riic.config, "plan", PlanModel(**_complete_plan()))
    response = result(
        riic.try_riic_plan,
        mode="rescue",
        plan={
            "plan1": {
                "room_1_1": {
                    "name": "制造站",
                    "product": "exp3",
                    "plans": [{"agent": "国度"}],
                }
            }
        },
    )
    assert not response["valid"] and response["status"] == "failed"
    assert any(
        error["code"] == "native_validation_failed" and "产物不一致" in error["message"]
        for error in response["errors"]
    )
    assert "resolvedPlan" not in response


def test_complete_plan_schema_exposes_full_bindings_and_advanced_allowlist():
    parameters = riic.try_riic_plan_tool_def["function"]["parameters"]
    schema = parameters["properties"]["plan"]
    assert schema["required"] == ["plan1"]
    assert schema["additionalProperties"] is False
    assert "assignments" not in parameters.get("required", [])
    assert set(schema["properties"]["advanced_settings"]["properties"]) == set(
        riic.ADVANCED_SETTING_KEYS
    )
    assert "api_key" not in json.dumps(schema)
    assert "group_bindings" in json.dumps(parameters)
    assert "replacement" in json.dumps(parameters)
    assert schema["properties"]["backup_plans"]["maxItems"] == 0
    assert parameters["$defs"]["RIICFacility"]["properties"]["name"]["enum"] == [
        "",
        *riic.FACILITY_CAPACITY,
    ]


@pytest.mark.parametrize(
    "room,actual,corrected",
    [
        ("room_1_1", "赤金", "gold"),
        ("room_1_1", "作战记录", "exp3"),
        ("room_1_2", "龙门币", "lmd"),
    ],
)
def test_invalid_product_lists_facility_codes_that_can_correct_the_plan(
    complete_state, room, actual, corrected
):
    draft = _complete_plan()
    draft["plan1"][room]["product"] = actual
    response = result(riic.try_riic_plan, plan=draft)
    products = riic.MANUFACTURE_PRODUCTS if room == "room_1_1" else riic.TRADE_PRODUCTS
    assert not response["valid"]
    assert {
        "code": "invalid_product",
        "room": room,
        "actual": actual,
        "allowed": list(products),
    } in response["errors"]
    assert corrected in list(products)
    draft["plan1"][room]["product"] = corrected
    corrected_response = result(riic.try_riic_plan, plan=draft)
    assert corrected_response["valid"], corrected_response


def test_product_schema_reuses_shared_codes_and_retains_null_and_empty():
    schema = riic.try_riic_plan_tool_def["function"]["parameters"]["$defs"][
        "RIICFacility"
    ]["properties"]["product"]
    variants = schema["anyOf"]
    assert {"type": "null"} in variants
    assert next(item for item in variants if item.get("type") == "string")["enum"] == [
        "",
        *riic.MANUFACTURE_PRODUCTS,
        *riic.TRADE_PRODUCTS,
    ]


def test_nested_conf_error_identifies_correct_level_without_echoing_values(
    complete_state,
):
    draft = _complete_plan()
    secret = "private-submitted-value"
    draft["plan1"]["conf"] = {"api_key": secret}
    response = result(riic.try_riic_plan, plan=draft)
    error = response["error"]
    assert error["code"] == "invalid_arguments"
    assert "plan.plan1" in error["message"] and "未知字段" in error["message"]
    assert "plan.conf" in error["message"]
    assert secret not in json.dumps(response)
    assert "api_key" not in json.dumps(response)


@pytest.mark.parametrize(
    "path", ["root", "facility", "slot", "binding", "conf", "advanced"]
)
def test_unknown_plan_fields_have_bounded_safe_messages(complete_state, path):
    draft = _complete_plan()
    slot = draft["plan1"]["room_1_1"]["plans"][0]
    target = {
        "root": draft,
        "facility": draft["plan1"]["room_1_1"],
        "slot": slot,
        "binding": slot["group_bindings"][0],
        "conf": draft["conf"],
        "advanced": draft["advanced_settings"],
    }[path]
    target["private-field-name"] = "private-field-value"
    response = result(riic.try_riic_plan, plan=draft)
    assert response["error"]["code"] == "invalid_arguments"
    assert "plan" in response["error"]["message"]
    assert len(response["error"]["message"]) <= 240
    assert "private-field-name" not in json.dumps(response)
    assert "private-field-value" not in json.dumps(response)


@pytest.mark.parametrize(
    "location", ["facility_name", "facility_level", "operator_mood_limit"]
)
def test_pydantic_plan_errors_expose_only_safe_location_and_type(
    complete_state, location
):
    draft = _complete_plan()
    secret_key, secret_value = "private-dynamic-key", "private-model-input"
    if location == "facility_name":
        draft["plan1"]["room_1_1"]["name"] = {secret_key: secret_value}
    elif location == "facility_level":
        draft["facility_levels"] = {secret_key: secret_value}
    else:
        draft["conf"]["operator_mood_limits"] = {secret_key: {"upper": 0}}
    response = result(riic.try_riic_plan, plan=draft)
    error = response["error"]
    assert error["code"] == "invalid_arguments"
    assert error["details"]
    assert all(
        set(item) == {"loc", "type"} and item["loc"][0] == "plan"
        for item in error["details"]
    )
    assert secret_key not in json.dumps(response)
    assert secret_value not in json.dumps(response)
    for key in ("input", "ctx", "url"):
        assert all(key not in item for item in error["details"])
