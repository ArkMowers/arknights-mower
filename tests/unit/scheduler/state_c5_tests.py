"""S5 的 C5 回归测试：`backup_plans` 为空时也必须装载 default_plan。

修复前行为（`state.py:45-46`）：`swap_plan` 被包在 `if self._backup_plans:` 里，
因此 `backup_plans=[]` 的用户**永远不会**执行 `swap_plan`，`self.plan` 保持 `{}`、
`self.config` 保持 `None`，随后 `_init_and_validate` 读到真实 `config.conf.dorm_order`
与空 plan 不匹配，抛出**误导性**的
`ConfigError: 宿舍优先级和当前宿舍不匹配...`，掩盖了真正原因。

修复：改为无条件 `self.swap_plan([False] * len(self._backup_plans))`，
对齐 v1 `utils/operators.py:145`。`swap_plan` 自身在 `default_plan` 缺失时早退、
`_backup_plans` 为空时不做合并，只从 `default_plan` 深拷贝 —— 因此无条件调用安全。

⚠️ 本文件**不**构造真实设备、**不**读真实 `config.conf`、**绝不**触发
`config.save_conf()`（那会写用户的 `conf.yml`）。为此用 `_Probe` 子类隔离
`_init_and_validate`（它会读 `config.conf.dorm_order` 并在分支里 `save_conf`）。
"""

import unittest

from arknights_mower.data import agent_list
from arknights_mower.scheduler.domain.plan import Plan, PlanConfig, Room
from arknights_mower.scheduler.state import SchedulerState

# 干员名必须真实存在于 agent_list，否则 _init_and_validate 的第一道校验会报错。
HIGH_AGENT = "能天使"
LOW_AGENT = "芬"
FREE = "Free"


class _Probe(SchedulerState):
    """只测 C5 装配逻辑，隔离 `_init_and_validate` 的真实 config 读写。"""

    def _init_and_validate(self, update: bool = False):
        return None  # 隔离校验，避免读真实 config / 写 conf.yml


def make_config() -> PlanConfig:
    """构造满足 `PlanConfig` 必填字段的配置（其余字段有默认值，从简不填）。"""
    return PlanConfig(
        rest_in_full=[],
        exhaust_require=[],
        resting_priority=[],
        workaholic=[],
        free_blacklist=[],
        refresh_trading_config=[],
        refresh_drained=[],
        ope_resting_priority=[],
    )


def make_plan(name: str) -> Plan:
    """构造合成 plan：一个制造站（含非空替换组）+ 一个满员宿舍。

    替换组非空是必需的：`state.py:397` 对非宿舍房间要求替换组，
    空替换组会报"替换组缺失"。
    """
    return Plan(
        plan={
            "room_1_1": [
                Room(agent=HIGH_AGENT, group="", replacement=[LOW_AGENT], facility="factory"),
            ],
            "dormitory_1": [
                Room(agent="波登可", group="", replacement=[], facility="dorm"),
                Room(agent="玫兰莎", group="", replacement=[], facility="dorm"),
                Room(agent=FREE, group="", replacement=[], facility="dorm"),
                Room(agent=FREE, group="", replacement=[], facility="dorm"),
                Room(agent=FREE, group="", replacement=[], facility="dorm"),
            ],
        },
        config=make_config(),
        name=name,
    )


class C5EmptyBackupPlansTests(unittest.TestCase):
    """验收标准 1：`backup_plans=[]` 时 plan 非空、config 非 None。"""

    def test_empty_backup_plans_still_loads_default_plan(self):
        """修复前行为：self.plan == {} 且 self.config is None（断言失败）。"""
        # Arrange
        synthetic = make_plan("默认")
        global_plan = {"default_plan": synthetic, "backup_plans": []}

        # Act
        state = _Probe(global_plan=global_plan)

        # Assert
        self.assertTrue(state.plan, "backup_plans=[] 时仍应装载 default_plan 到 self.plan")
        self.assertIsNotNone(state.config, "backup_plans=[] 时仍应装载 default_plan.config")
        self.assertIn("room_1_1", state.plan)
        self.assertEqual([], state.plan_condition)


class C5NonEmptyBackupPlansTests(unittest.TestCase):
    """验收标准 2：`backup_plans` 非空时行为与修复前一致（对照组）。"""

    def test_non_empty_backup_plans_keeps_previous_behaviour(self):
        """对照组：修复前后结果必须完全一致（含 plan_condition）。"""
        # Arrange
        synthetic = make_plan("默认")
        backup = make_plan("备用")
        global_plan = {"default_plan": synthetic, "backup_plans": [backup]}

        # Act
        state = _Probe(global_plan=global_plan)

        # Assert
        self.assertTrue(state.plan)
        self.assertIsNotNone(state.config)
        # 未选中任何 backup（全 False），plan_condition 记录条件长度
        self.assertEqual([False], state.plan_condition)
        # 默认房间里仍是 default_plan 的干员
        self.assertEqual(HIGH_AGENT, state.plan["room_1_1"][0].agent)

    def test_selected_backup_plan_merges_over_default(self):
        """非空 backup 且条件为 True 时，merge 行为保持（防拆分裂到 _merge_plan）。"""
        # Arrange
        synthetic = make_plan("默认")
        backup = make_plan("备用")
        backup.plan["room_1_1"][0].agent = "德克萨斯"
        global_plan = {"default_plan": synthetic, "backup_plans": [backup]}

        # Act
        state = _Probe(global_plan=global_plan)
        state.swap_plan([True])

        # Assert
        self.assertTrue(state.plan_condition == [True])
        self.assertEqual("德克萨斯", state.plan["room_1_1"][0].agent)


class ApiCompatibilityTests(unittest.TestCase):
    """验收标准 4：拆分后 `predict_exhaust` / `available_free` 仍是可调用契约。"""

    def test_predict_exhaust_and_available_free_still_exist(self):
        self.assertTrue(hasattr(SchedulerState, "predict_exhaust"))
        self.assertTrue(hasattr(SchedulerState, "available_free"))

    def test_available_free_keeps_free_type_parameter(self):
        import inspect

        signature = inspect.signature(SchedulerState.available_free)

        self.assertIn("free_type", signature.parameters)
        self.assertEqual("high", signature.parameters["free_type"].default)

    def test_fixture_agents_are_real(self):
        """守卫夹具本身：合成 plan 里的干员名必须真实，否则用例会因别的原因失败。"""
        self.assertIn(HIGH_AGENT, agent_list)
        self.assertIn(LOW_AGENT, agent_list)


if __name__ == "__main__":
    unittest.main()
