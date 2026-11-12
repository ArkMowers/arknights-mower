"""Concrete write previews and state checks for the assistant execution owner."""

import json


def prepare_operation(name, args, function):
    if name == "submit_issue":
        return {
            "action": "发送反馈邮件",
            "recipients": ["354013233@qq.com", "1273725854@qq.com"],
            "content": args,
            "attachments": "Bug 反馈会按所列时间范围重新收集日志、截图及当前排班等诊断资料；Feature 反馈不附诊断文件。",
            "delivery": "成功仅表示邮件服务接受发送，不保证收件人已收到。",
        }, lambda: function(**args)
    from arknights_mower.agent.tools.mastery_plan import get_char_name
    from arknights_mower.utils import mastery_db

    if name == "add_mastery_plan":
        existing = mastery_db.get_plan_by_skill(args["char_id"], args["skill_index"])
        preview = {
            "action": "新增专精计划",
            "operator": get_char_name(args["char_id"]),
            "requested": args,
            "existing": existing,
        }

        def perform():
            result = function(**args)
            if not result.startswith("已添加专精计划"):
                return result
            saved = mastery_db.get_plan_by_skill(args["char_id"], args["skill_index"])
            if not saved or saved["target_level"] != args.get("target_level", 3):
                raise ValueError(
                    "计划写入后的读取结果未能确认，请核实实际计划，勿重复添加"
                )
            return result + f"（已重新读取核对，计划 ID {saved['id']}）"

        return preview, perform
    if name == "set_route":
        from arknights_mower.solvers.mastery import validate_route_supports

        error = validate_route_supports(args["supports_json"])
        if error:
            raise ValueError(error)
        profession = args["profession"]
        if profession not in {
            "先锋",
            "近卫",
            "重装",
            "狙击",
            "术师",
            "医疗",
            "辅助",
            "特种",
        }:
            raise ValueError("请选择有效职业")
        before = mastery_db.get_route(profession)
        preview = {
            "action": "覆盖此职业的自定义专精路线",
            "profession": profession,
            "before": json.loads(before["supports"]) if before else None,
            "after": json.loads(args["supports_json"]),
        }

        def perform():
            mastery_db.save_confirmed_route(profession, args["supports_json"], before)
            return f"已保存 {profession} 专精路线（已在同一事务中重新读取核对）"

        return preview, perform
    if name == "retry_plan_tool":
        plans = mastery_db.get_failed_plans()
        ids = sorted(plan["id"] for plan in plans)
        preview = {
            "action": "将下列全部失败计划重置为待执行",
            "plans": [
                {
                    key: plan.get(key)
                    for key in (
                        "id",
                        "char_id",
                        "char_name",
                        "skill_index",
                        "skill_name",
                        "target_level",
                        "failed_reason",
                    )
                }
                for plan in plans
            ],
        }

        def perform():
            count = mastery_db.retry_confirmed_plans(ids)
            return f"已核对重置 {count} 个失败的专精计划为待执行"

        return preview, perform
    raise ValueError("未注册的写入操作")
