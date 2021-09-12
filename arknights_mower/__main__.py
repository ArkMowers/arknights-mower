import argparse

from .__init__ import __version__
from .utils.log import logger
from .utils.adb import ADBConnector
from .strategy import Solver

ap = argparse.ArgumentParser(prog='arknights-mower')

ap.add_argument('-v', '--version', action='store_true',
                help='show version')

# subparsers = ap.add_subparsers(help='tasks')

# # Base
# base_parser = subparsers.add_parser(
#     'base', help='collect productions in base')

# # Credit
# credit_parser = subparsers.add_parser(
#     'credit', help='collect credits by clue exchange')

# # Fight
# fight_parser = subparsers.add_parser(
#     'fight', help='clear sanity by fighting')

# # Shop
# shop_parser = subparsers.add_parser(
#     'shop', help='clear credits by shopping')

# # Recruit
# recruit_parser = subparsers.add_parser(
#     'recruit', help='recruit automatically')

# # Mission
# mission_parser = subparsers.add_parser(
#     'mission', help='collect mission rewards')

ap.add_argument('-b', '--base', action='store_true',
                help='collect productions in base')

ap.add_argument('-c', '--credit', action='store_true',
                help='collect credits by clue exchange')

ap.add_argument('-f', '--fight', action='store_true',
                help='clear sanity by fighting')
ap.add_argument('-fp', '--fight-potion', default=0, type=int, metavar='NUM',
                help='how many potions do you want to use. default is 0')
ap.add_argument('-fo', '--fight-originite', default=0, type=int, metavar='NUM',
                help='how many originites do you want to use. default is 0')

ap.add_argument('-s', '--shop', action='store_true',
                help='clear credits by shopping')

ap.add_argument('-r', '--recruit', action='store_true',
                help='recruit automatically')

ap.add_argument('-m', '--mission', action='store_true',
                help='collect mission rewards')


def main():
    args = ap.parse_args()
    logger.debug(args)

    if args.version:
        print(f'arknights-mower version: {__version__}')
        exit()

    adb = ADBConnector()
    cli = Solver(adb)

    if args.base:
        cli.base()
    if args.credit:
        cli.credit()
    if args.fight:
        cli.fight(args.fight_potion, args.fight_originite)
    if args.shop:
        cli.shop()
    if args.recruit:
        cli.recruit()
    if args.mission:
        cli.mission()

    if cli.run_once == False:
        cli.base()
        cli.credit()
        cli.fight(args.fight_potion, args.fight_originite)
        cli.shop()
        cli.recruit()
        cli.mission()


if __name__ == '__main__':
    main()
