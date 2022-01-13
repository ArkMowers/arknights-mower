import sys
import time
import traceback
import schedule as sd
from pathlib import Path

from .__init__ import __version__, __system__, __rootdir__, __pyinstall__
from .utils.log import logger, set_debug_mode
from .utils import config
from .solvers import *


class ParamError(Exception):
    """
    参数错误
    """


def mail(args):
    """
    mail
        自动收取邮件
    """
    MailSolver().run()


def base(args):
    """
    base [plan] [-c] [-d[F][N]]
        自动处理基建的信赖/货物/订单/线索/无人机
        plan 表示选择的基建干员排班计划（需要搭配配置文件使用）
        -c 是否自动使用线索
        -d 是否自动消耗无人机，F 表示第几层（1-3），N 表示从左往右第几个房间（1-3），仅支持制造站
    """
    clue_collect = config.BASE_CONSTRUCT_CLUE
    drone_room = config.BASE_CONSTRUCT_DRONE
    arrange = None

    try:
        for p in args:
            if p[0] == '-':
                if p[1] == 'c':
                    clue_collect = True
                elif p[1] == 'd':
                    assert '1' <= p[2] <= '3'
                    assert '1' <= p[3] <= '3'
                    drone_room = f'room_{p[2]}_{p[3]}'
            elif arrange is None:
                arrange = config.BASE_CONSTRUCT_PLAN.get(p)
    except:
        raise ParamError

    BaseConstructSolver().run(clue_collect, drone_room, arrange)


def credit(args):
    """
    credit
        自动访友获取信用点
    """
    CreditSolver().run()


def shop(args):
    """
    shop [items ...]
        自动前往商店消费信用点
        items 优先考虑的物品，默认为从上到下从左到右购买
    """
    if len(args) == 0:
        ShopSolver().run()
    else:
        ShopSolver().run(args)


def recruit(args):
    """
    recruit [agents ...]
        自动进行公共招募
        agents 优先考虑的公招干员，默认为火神和因陀罗
    """
    if len(args) == 0:
        RecruitSolver().run()
    else:
        RecruitSolver().run(args)


def mission(args):
    """
    mission
        收集每日任务和每周任务奖励
    """
    MissionSolver().run()


def schedule(args):
    """
    schedule
        执行配置文件中的计划任务
    """

    if config.SCHEDULE_PLAN is not None:
        sd.every().hour.do(task, tag='per_hour')
        for tag in config.SCHEDULE_PLAN.keys():
            if tag[:4] == 'day_':
                sd.every().day.at(tag.replace('_', ':')[4:]).do(task, tag=tag)
        task()
        while True:
            sd.run_pending()
            time.sleep(60)
    else:
        logger.warning('计划任务为空')


def task(tag='start_up'):
    plan = config.SCHEDULE_PLAN.get(tag)
    if plan is not None:
        for args in plan:
            args = args.split()
            if 'schedule' in args:
                logger.error('schedule 里套 schedule，你就是测试工程师？')
                raise NotImplementedError
            try:
                target_cmd = match_cmd(args[0], global_cmds)
                if target_cmd is not None:
                    target_cmd(args[1:])
            except Exception as e:
                logger.error(e)


def operation(args):
    """
    operation [level] [n] [-r[N]] [-R[N]] [-e]
        自动进行作战，可指定次数或直到理智不足
        level 指定关卡名称，未指定则默认前往上一次关卡
        n 指定作战次数，未指定则默认作战直到理智不足
        -r 是否自动回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -R 是否使用源石回复理智，最多回复 N 次，N 未指定则表示不限制回复次数
        -e 是否优先处理未完成的每周剿灭
    """
    level = None
    times = config.OPE_TIMES
    potion = config.OPE_POTION
    originite = config.OPE_ORIGINITE
    eliminate = config.OPE_ELIMINATE
    plan = config.OPE_PLAN

    try:
        for p in args:
            if p[0] == '-':
                val = -1
                if len(p) > 2:
                    val = int(p[2:])
                if p[1] == 'r':
                    assert potion == 0
                    potion = val
                elif p[1] == 'R':
                    assert originite == 0
                    originite = val
                elif p[1] == 'e':
                    assert eliminate == False
                    eliminate = True
            elif p.find('-') == -1:
                assert times == -1
                times = int(p)
            else:
                assert level is None
                level = p
    except:
        raise ParamError

    remain_plan = OpeSolver().run(times, potion, originite, level, plan, eliminate)
    config.update_ope_plan(remain_plan)


def version(args=None):
    """
    version
        输出版本信息
    """
    print(f'arknights-mower: version: {__version__}')


def help(args=None):
    """
    help
        输出本段消息
    """
    print('usage: arknights-mower command [command args] [--config filepath] [--debug]')
    print('commands (prefix abbreviation accepted):')
    for cmd in global_cmds:
        if cmd.__doc__:
            print('    ' + str(cmd.__doc__.strip()))
        else:
            print('    ' + cmd.__name__)
    print(f'    --debug\n        启用调试功能，调试信息将会输出到 {config.LOGFILE_PATH} 中')
    print(f'    --config filepath\n        指定配置文件，默认使用 {config.PATH}')


global_cmds = [base, credit, mail, mission, shop, recruit, operation, version, help, schedule]


def match_cmd(prefix, avail_cmds):
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


def main(module=True):
    args = sys.argv[1:]
    if not args and __pyinstall__:
        logger.info('参数为空，默认执行 schedule 模式，按下 Ctrl+C 以结束脚本运行')
        args.append('schedule')
    config_path = None
    debug_mode = False
    while True:
        if len(args) > 1 and args[-2] == '--config':
            config_path = Path(args[-1])
            args = args[:-2]
            continue
        if len(args) > 0 and args[-1] == '--debug':
            debug_mode = True
            args = args[:-1]
            continue
        break
        
    if config_path is None:
        if __pyinstall__:
            config_path = Path(sys.executable).parent.joinpath('config.yaml')
        elif module:
            print('A')
            config_path = Path.home().joinpath('.ark_mower.yaml')
        else:
            print('B')
            config_path = __rootdir__.parent.joinpath('config.yaml')
        if not config_path.exists():
            config.build_config(config_path, module)
    else:
        if not config_path.exists():
            logger.error(f'配置文件路径有误或不存在：{config_path}')
            return
    try:
        logger.info(f'读取配置文件：{config_path}')
        config.load_config(config_path)
    except Exception as e:
        logger.error('加载配置文件出现错误')
        raise e

    if debug_mode and not config.DEBUG_MODE:
        config.DEBUG_MODE = True
    set_debug_mode()
        
    logger.debug(args)
    if len(args) == 0:
        help()
    else:
        target_cmd = match_cmd(args[0], global_cmds)
        if target_cmd is not None:
            try:
                target_cmd(args[1:])
            except ParamError:
                logger.debug(traceback.format_exc())
                help()
        else:
            help()


if __name__ == '__main__':
    main(module=True)
