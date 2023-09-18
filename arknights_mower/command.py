from __future__ import annotations

from . import __version__
from .solvers import *
from .utils import config
from .utils.device import Device
from .utils.log import logger
from .utils.param import ParamError, parse_operation_params


def mail(args: list[str] = [], device: Device = None):
    """
    mail
        自动收取邮件
    """
    MailSolver(device).run()


def base(args: list[str] = [], device: Device = None):
    """
    base [plan] [-c] [-d[F][N]] [-f[F][N]]
        自动处理基建的信赖/货物/订单/线索/无人机
        plan 表示选择的基建干员排班计划（建议搭配配置文件使用, 也可命令行直接输入）
        -c 是否自动收集并使用线索
        -d 是否自动消耗无人机，F 表示第几层（1-3），N 表示从左往右第几个房间（1-3）
        -f 是否使用菲亚梅塔恢复特定房间干员心情，恢复后恢复原位且工作位置不变，F、N 含义同上
    """
    from .data import base_room_list, agent_list
    
    arrange = None
    clue_collect = False
    drone_room = None
    fia_room = None
    any_room = []
    agents = []

    try:
        for p in args:
            if p[0] == '-':
                if p[1] == 'c':
                    clue_collect = True
                elif p[1] == 'd':
                    assert '1' <= p[2] <= '3'
                    assert '1' <= p[3] <= '3'
                    drone_room = f'room_{p[2]}_{p[3]}'
                elif p[1] == 'f':
                    assert '1' <= p[2] <= '3'
                    assert '1' <= p[3] <= '3'
                    fia_room = f'room_{p[2]}_{p[3]}'
            elif arrange is None:
                arrange = config.BASE_CONSTRUCT_PLAN.get(p)
                if arrange is None:
                    if p in base_room_list:
                        any_room.append(p)
                        agents.append([])
                    elif p in agent_list or 'free' == p.lower():
                        agents[-1].append(p)                
    except Exception:
        raise ParamError
    
    if arrange is None and any_room is not None and len(agents) > 0:
        arrange = dict(zip(any_room, agents))

    BaseConstructSolver(device).run(arrange, clue_collect, drone_room, fia_room)


def credit(args: list[str] = [], device: Device = None):
    """
    credit
        自动访友获取信用点
    """
    CreditSolver(device).run()


def shop(args: list[str] = [], device: Device = None):
    """
    shop [items ...]
        自动前往商店消费信用点
        items 优先考虑的物品，若不指定则使用配置文件中的优先级，默认为从上到下从左到右购买
    """
    if len(args) == 0:
        ShopSolver(device).run(config.SHOP_PRIORITY)
    else:
        ShopSolver(device).run(args)


def recruit(args: list[str] = [], email_config={}, maa_config={},device: Device = None):
    """
    recruit [agents ...]
        自动进行公共招募
        agents 优先考虑的公招干员，若不指定则使用配置文件中的优先级，默认为高稀有度优先
    """
    if len(args) == 0:
        RecruitSolver(device).run(config.RECRUIT_PRIORITY,email_config,maa_config)
    else:
        RecruitSolver(device).run(args,email_config)


def mission(args: list[str] = [], device: Device = None):
    """
    mission
        收集每日任务和每周任务奖励
    """
    MissionSolver(device).run()


def operation(args: list[str] = [], device: Device = None):
    """
    operation [level] [n] [-r[N]] [-R[N]] [-e|-E]
        自动进行作战，可指定次数或直到理智不足
        level 指定关卡名称，未指定则默认前往上一次关卡
        n 指定作战次数，未指定则默认作战直到理智不足
        -r 是否自动回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -R 是否使用源石回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -e 是否优先处理未完成的每周剿灭，优先使用代理卡；-E 表示只使用代理卡而不消耗理智
    operation --plan
        （使用配置文件中的参数以及计划）自动进行作战
    """

    if len(args) == 1 and args[0] == "--plan":
        remain_plan = OpeSolver(device).run(None, config.OPE_TIMES, config.OPE_POTION,
                                            config.OPE_ORIGINITE, config.OPE_ELIMINATE, config.OPE_PLAN)
        config.update_ope_plan(remain_plan)
        return

    level, times, potion, originite, eliminate = parse_operation_params(args)

    OpeSolver(device).run(level, times, potion, originite, eliminate)


def version(args: list[str] = [], device: Device = None):
    """
    version
        输出版本信息
    """
    print(f'arknights-mower: version: {__version__}')


def help(args: list[str] = [], device: Device = None):
    """
    help
        输出本段消息
    """
    print(
        'usage: arknights-mower command [command args] [--config filepath] [--debug]')
    print(
        'commands (prefix abbreviation accepted):')
    for cmd in global_cmds:
        if cmd.__doc__:
            print('    ' + str(cmd.__doc__.strip()))
        else:
            print('    ' + cmd.__name__)
    print(f'    --debug\n        启用调试功能，调试信息将会输出到 {config.LOGFILE_PATH} 中')
    print(f'    --config filepath\n        指定配置文件，默认使用 {config.PATH}')


"""
commands for schedule
operation will be replaced by operation_one in ScheduleSolver
"""
schedule_cmds = [base, credit, mail, mission, shop, recruit, operation]


def add_tasks(solver: ScheduleSolver = None, tag: str = ''):
    """
    为 schedule 模块添加任务
    """
    plan = config.SCHEDULE_PLAN.get(tag)
    if plan is not None:
        for args in plan:
            args = args.split()
            if 'schedule' in args:
                logger.error(
                    'Found `schedule` in `schedule`. Are you kidding me?')
                raise NotImplementedError
            try:
                target_cmd = match_cmd(args[0], schedule_cmds)
                if target_cmd is not None:
                    solver.add_task(tag, target_cmd, args[1:])
            except Exception as e:
                logger.error(e)


def schedule(args: list[str] = [], device: Device = None):
    """
    schedule
        执行配置文件中的计划任务
        计划执行时会自动存档至本地磁盘，启动时若检测到有存档，则会使用存档内容继续完成计划
        -n 忽略之前中断的计划任务，按照配置文件重新开始新的计划
    """
    new_schedule = False

    try:
        for p in args:
            if p[0] == '-':
                if p[1] == 'n':
                    new_schedule = True
    except Exception:
        raise ParamError

    solver = ScheduleSolver(device)
    if new_schedule or solver.load_from_disk(schedule_cmds, match_cmd) is False:
        if config.SCHEDULE_PLAN is not None:
            for tag in config.SCHEDULE_PLAN.keys():
                add_tasks(solver, tag)
        else:
            logger.warning('empty plan')
        solver.per_run()
    solver.run()


# all available commands
global_cmds = [base, credit, mail, mission, shop,
               recruit, operation, version, help, schedule]


def match_cmd(prefix: str, avail_cmds: list[str] = global_cmds):
    """ match command """
    target_cmds = [x for x in avail_cmds if x.__name__.startswith(prefix)]
    if len(target_cmds) == 1:
        return target_cmds[0]
    elif len(target_cmds) == 0:
        print('unrecognized command: ' + prefix)
        return None
    else:
        print('ambiguous command: ' + prefix)
        print('matched commands: ' + ','.join(x.__name__ for x in target_cmds))
        return None
