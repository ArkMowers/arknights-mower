import sys
import traceback
from pathlib import Path

from . import __rootdir__, __pyinstall__
from .command import *
from .utils import config
from .utils.device import Device
from .utils.log import logger, set_debug_mode


def main(module: bool = True) -> None:
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
            config_path = Path.home().joinpath('.ark_mower.yaml')
        else:
            config_path = __rootdir__.parent.joinpath('config.yaml')
        if not config_path.exists():
            config.build_config(config_path, module)
    else:
        if not config_path.exists():
            logger.error(
                f'The configuration file does not exist: {config_path}')
            return
    try:
        logger.info(f'Loading the configuration file: {config_path}')
        config.load_config(config_path)
    except Exception as e:
        logger.error('An error occurred when loading the configuration file')
        raise e

    if debug_mode and not config.DEBUG_MODE:
        config.DEBUG_MODE = True
    set_debug_mode()

    device = Device()

    logger.debug(args)
    if len(args) == 0:
        help()
    else:
        target_cmd = match_cmd(args[0])
        if target_cmd is not None:
            try:
                target_cmd(args[1:], device)
            except ParamError:
                logger.debug(traceback.format_exc())
                help()
        else:
            help()


if __name__ == '__main__':
    main(module=True)
