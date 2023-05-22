import logging
import os
import zipfile
import requests
from .. import __version__


# 编写bat脚本，删除旧程序，运行新程序
def __write_restart_cmd(new_name, old_name):
    b = open("upgrade.bat", 'w')
    TempList = "@echo off\n"
    TempList += "if not exist " + new_name + " exit \n"  # 判断是否有新版本的程序，没有就退出更新。
    TempList += "echo 正在更新至最新版本...\n"
    TempList += "timeout /t 5 /nobreak\n"  # 等待5秒
    TempList += "if exist " + old_name + ' del "' + old_name.replace("/", "\\\\") + '"\n'  # 删除旧程序
    TempList += 'copy  "' + new_name.replace("/", "\\\\") + '" "' + old_name.replace("/", "\\\\") + '"\n'  # 复制新版本程序
    TempList += "echo 更新完成，正在启动...\n"
    TempList += "timeout /t 3 /nobreak\n"
    TempList += 'start  ' + old_name + ' \n'  # "start 1.bat\n"
    TempList += "exit"
    b.write(TempList)
    b.close()
    # subprocess.Popen("upgrade.bat") #不显示cmd窗口
    os.system('start upgrade.bat')  # 显示cmd窗口
    os._exit(0)


def compere_version():
    """
        与github上最新版比较
        :return res: str | None, 若需要更新 返回版本号, 否则返回None
    """
    newest_version = __get_newest_version()

    v1 = [str(x) for x in str(__version__).split('.')]
    v2 = [str(x) for x in str(newest_version).split('.')]

    # 如果2个版本号位数不一致，后面使用0补齐，使2个list长度一致，便于后面做对比
    if len(v1) > len(v2):
        v2 += [str(0) for x in range(len(v1) - len(v2))]
    elif len(v1) < len(v2):
        v1 += [str(0) for x in range(len(v2) - len(v1))]
    list_sort = sorted([v1, v2])
    if list_sort[0] == list_sort[1]:
        return None
    elif list_sort[0] == v1:
        return newest_version
    else:
        return None


def update_version():
    if os.path.isfile("upgrade.bat"):
        os.remove("upgrade.bat")
    __write_restart_cmd("tmp/mower.exe", "./mower.exe")


def __get_newest_version():
    response = requests.get("https://api.github.com/repos/ArkMowers/arknights-mower/releases/latest")
    return response.json()["tag_name"]


def download_version(version):
    if not os.path.isdir("./tmp"):
        os.makedirs("./tmp")
    r = requests.get(f"https://github.com/ArkMowers/arknights-mower/releases/download/{version}/mower.zip",stream=True)
    # r = requests.get(
    #     f"https://github.com/ArkMowers/arknights-mower/releases/download/{version}/arknights-mower-3.0.4.zip",
    #     stream=True)
    total = int(r.headers.get('content-length', 0))
    index = 0
    with open('./tmp/mower.zip', 'wb') as f:
        for chunk in r.iter_content(chunk_size=10485760):
            if chunk:
                f.write(chunk)
                index += len(chunk)
                print(f"更新进度：{'%.2f%%' % (index*100 / total)}({index}/{total})")
    zip_file = zipfile.ZipFile("./tmp/mower.zip")
    zip_list = zip_file.namelist()

    for f in zip_list:
        zip_file.extract(f, './tmp/')
    zip_file.close()
    os.remove("./tmp/mower.zip")


def main():
    # 新程序启动时，删除旧程序制造的脚本
    if os.path.isfile("upgrade.bat"):
        os.remove("upgrade.bat")
    __write_restart_cmd("newVersion.exe", "Version.exe")


if __name__ == '__main__':
    compere_version()
