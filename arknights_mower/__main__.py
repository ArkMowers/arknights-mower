import argparse

from .__init__ import __version__
from .utils.log import logger, init_fhlr
from .utils.adb import ADBConnector
from .strategy import Solver
from .utils import config

ap = argparse.ArgumentParser(prog='arknights-mower')

ap.add_argument('-v', '--version', action='store_true',
                help='show version')
ap.add_argument('-d', '--debug', action='store_true',
                help='debug mode')

task_args = ap.add_argument_group('tasks arguments')
task_args.add_argument('-b', '--base', action='store_true',
                       help='collect productions in base')
task_args.add_argument('-c', '--credit', action='store_true',
                       help='collect credits by clue exchange')
task_args.add_argument('-s', '--shop', action='store_true',
                       help='clear credits by shopping')
task_args.add_argument('-f', '--fight', action='store_true',
                       help='clear sanity by fighting')
task_args.add_argument('-r', '--recruit', action='store_true',
                       help='recruit automatically')
task_args.add_argument('-m', '--mission', action='store_true',
                       help='collect mission rewards')


fight_args = ap.add_argument_group('fight task arguments')
fight_args.add_argument('-fp', '--fight-potion', type=int, metavar='N',
                        help='how many potions do you want to use. default is 0')
fight_args.add_argument('-fo', '--fight-originite', type=int, metavar='N',
                        help='how many originites do you want to use. default is 0')


def main():
    args = ap.parse_args()
    logger.debug(args)

    if args.version:
        print(f'arknights-mower: version: {__version__}')
        exit()

    if args.fight:
        if args.fight_potion is None:
            args.fight_potion = 0
        if args.fight_originite is None:
            args.fight_originite = 0
    else:
        if args.fight_potion is not None:
            print(
                f'arknights-mower: error: argument -fp/--fight-potion: expected -f/--fight')
            exit()
        if args.fight_originite is not None:
            print(
                f'arknights-mower: error: argument -fo/--fight-originite: expected -f/--fight')
            exit()

    if args.debug:
        config.LOGFILE_PATH = '/var/log/arknights-mower'
        config.SCREENSHOT_PATH = '/var/log/arknights-mower/screenshot'
        init_fhlr()

    adb = ADBConnector()
    cli = Solver(adb)

    if args.base:
        cli.base()
    if args.credit:
        cli.credit()
    if args.fight:
        cli.ope(args.fight_potion, args.fight_originite)
    if args.shop:
        cli.shop()
    if args.recruit:
        cli.recruit()
    if args.mission:
        cli.mission()

    if cli.run_once == False:
        ap.print_help()


if __name__ == '__main__':
    main()
