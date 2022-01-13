import os
import traceback

from arknights_mower.__main__ import main
from arknights_mower import __cli__

if __name__ == '__main__':
    try:
        main(module=False)
    except Exception:
        print(traceback.format_exc())
    except SystemExit:
        pass
    finally:
        if not __cli__:
            os.system('pause')
