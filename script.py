from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.solvers.base_construct import BaseConstructSolver
from arknights_mower.solvers.recruit import RecruitSolver
from arknights_mower.utils import rapidocr
from arknights_mower.data import base_room_list

logger.setLevel("INFO")

rapidocr.initialize_ocr()

config.ADB_CONTROL_CLIENT == "scrcpy"
config.ADB_DEVICE = ["192.168.240.112:5555"]

solver = BaseConstructSolver()
solver.last_room = ""


shifts = {
    "main": [
        {
            "central": ["阿米娅", "凯尔希", "冰酿", "焰尾", "杜宾"],
            "room_1_2": ["绮良", "巫恋", "龙舌兰"],
            "room_1_1": ["图耶", "但书"],
            "room_3_1": ["鸿雪"],
            "room_2_2": ["苍苔", "砾", "斑点"],
            "room_2_1": ["梅尔", "夜烟"],
            "room_3_2": ["多萝西", "白面鸮", "槐琥"],
            "room_3_3": ["稀音", "红云", "豆苗"],
            "dormitories": ["桃金娘", "杜林", "褐果", "至简"],
        },
        {
            "central": ["麒麟R夜刀", "火龙S黑角", "涤火杰西卡", "寒芒克洛丝", "炎狱炎熔"],
            "room_1_2": ["能天使", "拉普兰德", "德克萨斯"],
            "room_1_1": ["推进之王", "摩根"],
            "room_3_1": ["泰拉大陆调查团"],
            "room_2_2": ["泡泡", "火神", "褐果"],
            "room_2_1": ["清流", "杏仁"],
            "room_3_2": ["水月", "香草", "杰西卡"],
            "room_3_3": ["断罪者", "食铁兽", "Castle-3"],
        },
    ],
    "power": {
        "facilities": ["room_1_3", "room_2_3"],
        "operators": ["格雷伊", "承曦格雷伊", "澄闪"],
    },
    "meeting": ["伊内丝", "陈", "白雪"],
    "contact": ["斥罪", "艾雅法拉"],
}

l = {"meeting": 2, "contact": 1, "central": 5}

actions = {}
working_operators = []
dormitories = []

for s in shifts:
    if s in base_room_list:
        # 设施内换人
        solver.enter_room(s)
        # 得到当前干员位置与心情
        res = solver.get_agent_from_room(s, length=l[s])
        solver.back()
        # 按心情排序
        sorted_ops = sorted(res, key=lambda i: i[1])
        # 第一个是心情最低的
        to_replace = sorted_ops[0][0]
        logger.info(f"心情最低的干员：{to_replace}")
        # 找到列表中没上的人里最靠前的
        working_ops = [o[0] for o in res]
        available_ops = list(filter(lambda x: x not in working_ops, shifts[s]))
        new_op = available_ops[0]
        logger.info(f"替换为：{new_op}")
        # 不破坏原来的顺序，找到原来干员的位置
        replace_index = working_ops.index(to_replace)
        working_ops[replace_index] = new_op
        logger.info(f"将{to_replace}替换为{new_op}，新排班为{working_ops}")
        actions[s] = working_ops
        working_operators += working_ops
    elif isinstance(shifts[s], list):
        # 跨设施组合
        # 进第一个房间看看是哪组在上班
        first_room = list(shifts[s][0].keys())[0]
        logger.info(f"跨站策略{s}的第一个房间是{first_room}，进去看看")
        solver.enter_room(first_room)
        res = solver.get_agent_from_room(s, length=1)
        solver.back()
        # 正在工作的干员
        working_ops = [o[0] for o in res]
        # 看看在哪一班里
        shift_idx = 0
        for idx, t in enumerate(shifts[s]):
            if t[first_room][0] in working_ops:
                shift_idx = idx
                break
        next_idx = 1 - shift_idx
        logger.info(f"正在工作的是第{shift_idx + 1}班{shifts[s][shift_idx]}")
        logger.info(f"将要换成第{next_idx + 1}班{shifts[s][next_idx]}")
        for f in shifts[s][next_idx]:
            if f in base_room_list:
                working_operators += shifts[s][next_idx][f]
                actions[f] = shifts[s][next_idx][f]
            elif f == "dormitories":
                dormitories += shifts[s][next_idx][f]
    elif isinstance(shifts[s], dict):
        tmp = []
        for i in shifts[s]["facilities"]:
            solver.enter_room(i)
            op = solver.get_agent_from_room(i, length=1)[0]
            logger.info(op)
            tmp.append((i, op[0]))
            solver.back()
            shifts[s]["operators"].remove(op[0])
        available_op = shifts[s]["operators"][0]
        m = min(tmp, key=lambda x: x[1])
        actions[m[0]] = [available_op]


if "褐果" in working_operators:
    solver.制造站切换产物("room_2_2", "源石碎片")
else:
    solver.制造站切换产物("room_2_2", "赤金")

logger.info(actions)
solver.run(actions)

logger.info("清空宿舍")
solver.run(
    {
        "dormitory_1": [""] * 5,
        "dormitory_2": [""] * 5,
        "dormitory_3": [""] * 5,
        "dormitory_4": [""] * 5,
    }
)
dormitories = dormitories + ["Free"] * (20 - len(dormitories))
logger.info("宿舍安排休息")
solver.run(
    {
        "dormitory_1": dormitories[0:5],
        "dormitory_2": dormitories[5:10],
        "dormitory_3": dormitories[10:15],
        "dormitory_4": dormitories[15:20],
    }
)

# RecruitSolver().run(
#     recruit_config={
#         "recruit_enable": True,
#         "permit_target": 30,
#         "recruit_robot": True,
#         "recruitment_time": False,
#     },
#     send_message_config={
#         "email_config": {"mail_enable": False},
#         "serverJang_push_config": {"server_push_enable": False},
#     },
# )
