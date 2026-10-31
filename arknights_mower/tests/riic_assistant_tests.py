"""Offline ownership, skill-stage and read-only AI planning contracts."""

import copy
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
        def invoke(self, messages):
            observations.extend(m for m in messages if isinstance(m, ToolMessage))
            if not observations:
                return AIMessage(content="", additional_kwargs={"tool_calls": [call]})
            return AIMessage(content="主班草案已检查")

    monkeypatch.setattr(agent, "build_llm", lambda *args, **kwargs: Model())
    before = state[1].model_dump()
    messages = agent._build_messages("按我的BOX尝试排班")
    if workflow == "manual":
        assert agent._run_manual_tool_loop(messages, "test-key")[-1] == "主班草案已检查"
    else:
        if agent.MessageGraph is None:
            pytest.skip("LangGraph optional dependency unavailable")
        assert (
            agent.build_workflow("test-key").invoke(messages)[-1].content
            == "主班草案已检查"
        )
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


def test_tools_are_available_to_both_model_workflows():
    from arknights_mower.agent import agent

    names = {tool["function"]["name"] for tool in agent.get_tools()}
    for name in ("get_riic_context", "get_riic_knowledge", "try_riic_plan"):
        assert name in names
        assert name in agent.tool_func_map
        assert name in agent.tool_message_map
    assert "try_riic_plan" in agent._build_ai_intro()


@pytest.mark.parametrize(
    "topic", ["taxonomy", "mower_plan", "new_operators", "income_export", "freshness"]
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


def test_knowledge_schema_covers_every_supported_topic():
    declared = riic.get_riic_knowledge_tool_def["function"]["parameters"]["properties"][
        "topic"
    ]["enum"]
    assert set(declared) == set(riic._read_data("knowledge")["topics"])
