import sys
from pathlib import Path

from .__init__ import __version__, __system__
from .utils.log import logger, init_fhlr
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
    base
        自动处理基建的信赖/货物/订单
    """
    BaseConstructSolver().run()


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
    times = -1
    potion = 0
    originite = 0
    eliminate = False
    plan = None

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

    OpeSolver().run(times, potion, originite, level, plan, eliminate)


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
    print('usage: arknights-mower command [command args] [-d]')
    print('commands (prefix abbreviation accepted):')
    for cmd in global_cmds:
        if cmd.__doc__:
            print('    ' + str(cmd.__doc__.strip()))
        else:
            print('    ' + cmd.__name__)
    print('    -d\n        启用调试功能，调试信息将会输出到 /var/log/arknights-mower/ 中')


global_cmds = [base, credit, mail, mission, shop, recruit, operation, version, help]


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


def main():
    args = sys.argv[1:]
    if len(args) > 0 and args[-1] == '-d':
        args = args[:-1]
        if __system__ == 'windows':
            config.LOGFILE_PATH = Path.home().joinpath('arknights-mower')
            config.SCREENSHOT_PATH = Path.home().joinpath('arknights-mower/screenshot')
        else:
            config.LOGFILE_PATH = '/var/log/arknights-mower'
            config.SCREENSHOT_PATH = '/var/log/arknights-mower/screenshot'
        print(f'开启 Debug 模式，日志将会被保存在 {config.LOGFILE_PATH} 中')
        init_fhlr()
        
    logger.debug(args)
    if len(args) == 0:
        help()
    else:
        target_cmd = match_cmd(args[0], global_cmds)
        if target_cmd is not None:
            try:
                target_cmd(args[1:])
            except ParamError:
                help()
        else:
            help()


if __name__ == '__main__':
    main()
