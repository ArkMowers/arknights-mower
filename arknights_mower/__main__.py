import argparse

from utils.adb import ADBConnector
from utils.recognize import Recognizer
import task


# ap = argparse.ArgumentParser(prog='arknights-mower')
# required_args = ap.add_argument_group('required args')
# optional_args = ap.add_argument_group('optional args')
# required_args.add_argument('-s', '--stage', nargs='+',
#                            help='manually add stage(s) to farm task (e.g. 1-7:100 4-4:25 (separated by whitespace))')
# required_args.add_argument('-c', '--cont', action='store_true',
#                            help='continue from the most recent farming session')
# optional_args.add_argument('-r', '--refill', default=0, type=int, metavar='AMOUNT',
#                            help='how many times you want to refill. default is 0')
# optional_args.add_argument('-l', '--list-task', action='store_true',
#                            help='list unfinished task(s) from recent farming session')
# optional_args.add_argument('-v', '--version', action='store_true',
#                            help='show version')
# optional_args.add_argument('-m', '--manual', type=int, metavar='AMOUNT',
#                            help='manual mode (good for single stage farming like event stages)')


def main():
    adb = ADBConnector()
    print('Hello')
    # task.start_game(adb)
    # task.login(adb)
    # task.credit(adb)
    # task.operate(adb)
    # task.infrastructure(adb)
    # task.mission(adb)
    # task.recruit(adb)


if __name__ == '__main__':
    main()
