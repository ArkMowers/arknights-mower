import os

from arknights_mower.__main__ import main
from arknights_mower.__init__ import __system__

if __name__ == '__main__':
    try:
        main(executable=True)
    except Exception as e:
        print(e)
        print('脚本发生错误')
        if __system__ == 'windows':
            os.system('pause')
        else:
            input()
        raise e
    # Use sys.frozen to check if run through pyinstaller frozen exe, and sys._MEIPASS to get temp path.
