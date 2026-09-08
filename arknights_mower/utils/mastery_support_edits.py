"""Validate and edit saved per-plan assistant selections."""

from dataclasses import dataclass

from . import mastery_support_data as data
from .mastery_support_types import (
    BASE_HOURS,
    SupportPlanError,
    decode_supports,
    editable_after,
)


@dataclass(frozen=True)
class EditContext:
    names: dict
    target: dict
    blocked: dict
    central: int

    def set_operator(self, stage, field, name):
        if name is None and field == "swap_target":
            stage[field] = None
            return
        if (
            not isinstance(name, str)
            or name not in self.names
            or name == self.target.get("name")
        ):
            raise SupportPlanError("协助者必须是已拥有的其他干员")
        data.check_schedule_name(name, self.blocked)
        stage[field] = name
        meta, char = self.names[name]
        stats = data.trainer_stats(meta, char, self.target, stage["level"])
        prefix = "swap_" if field == "swap_target" else ""
        stage[prefix + "efficiency"] = stats["efficiency"]
        if field == "swap_target":
            stage["swap_halves"] = stats["halves"]


def _edit_context(plan):
    blocked, central = data.schedule_context()
    metadata = data.training_data()
    owned = {c["id"]: c for c in data.owned_roster()}
    names = {m["name"]: (m, owned[cid]) for cid, m in metadata.items() if cid in owned}
    return EditContext(names, metadata.get(plan["char_id"], {}), blocked, central)


def _edit_stage(stage, edit, context, bounds):
    if not isinstance(edit, dict) or edit.get("level") != stage["level"]:
        raise SupportPlanError("专精阶段不匹配")
    changed = any(edit.get(f) != stage.get(f) for f in ("operator", "swap_target"))
    stage = dict(stage)
    locked, target = bounds
    if stage["level"] <= locked:
        if changed:
            raise SupportPlanError("已开始的专精阶段不能修改协助者")
        return stage
    for field in ("operator", "swap_target"):
        context.set_operator(stage, field, edit.get(field))
    if stage["level"] == target:
        stage["swap_target"] = None
    # Edited chains have no guaranteed carry. Runtime uses the observed countdown.
    stage.update(
        manual=stage.get("manual", False) or changed,
        central_bonus=context.central,
        activate_with=None,
        half_inherited=False,
        next_carry=None,
        hours=BASE_HOURS[stage["level"]]
        / data.rate(stage["efficiency"], context.central),
        switch_after=None,
    )
    return stage


def edit_supports(plan, edits):
    """Manual choices require identity/roster/schedule checks, not a speed threshold."""
    saved = decode_supports(plan)
    if not saved:
        raise SupportPlanError("此计划尚无自动协助方案，请重新添加计划")
    if not isinstance(edits, list) or len(edits) != len(saved["stages"]):
        raise SupportPlanError("请提交全部专精阶段的协助者")
    context = _edit_context(plan)
    bounds = editable_after(plan), saved["target"]
    stages = [
        _edit_stage(stage, edit, context, bounds)
        for stage, edit in zip(saved["stages"], edits)
    ]
    return {
        **saved,
        "stages": stages,
        "hours": sum(s["hours"] for s in stages),
        "central_bonus": context.central,
    }
