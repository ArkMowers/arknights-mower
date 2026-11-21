# -*- coding: utf-8 -*-
"""
卫戍协议 · 极速模拟 自动刷策略角标（GarrisonFarm）

只依赖本机已安装的 MAA：
  - 从 MAA 的 config/gui.new.json（或 gui.json）读取当前配置的 adb 路径与连接地址
  - 使用 MAA 自带的 OCR 模型 resource/PaddleOCR
  对 MAA 目录只读，不写入任何文件；本程序的设置、日志都保存在本程序自己的目录。

用法:
  GarrisonFarm.exe [--runs 20] [--attempts 0] [--maa "D:/MAA"] [--adb ...] [--address ...]
  在游戏"卫戍协议"主界面、"请选择模拟难度"界面或任意局内界面启动均可。
坐标基于 1920x1080 横屏（模拟器分辨率 1920x1080 / 1080x1920）。
"""
import argparse, json, os, subprocess, sys, time
import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
SETTINGS = os.path.join(HERE, "settings.json")
DONE_FILE = os.path.join(HERE, "strategies_done.json")
LOG_DIR = os.path.join(HERE, "farm_logs")
FALLBACK = os.path.join(HERE, "fallback")   # 内置备用：OCR 模型 + adb（仅在读取 MAA 失败时使用）
NOWIN = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW

ADB = "adb"
DEV = ""
ocr_engine = None

# ---------------- MAA 发现与配置（只读） ----------------
def is_maa_dir(d):
    return bool(d) and os.path.isfile(os.path.join(d, "MAA.exe"))


def find_maa():
    # 1. 上次保存的位置
    try:
        d = json.load(open(SETTINGS, encoding="utf-8")).get("maa_dir")
        if is_maa_dir(d):
            return d
    except Exception:
        pass
    # 2. 正在运行的 MAA.exe
    for line in running_paths(["MAA"]):
        d = os.path.dirname(line)
        if is_maa_dir(d):
            return d
    # 3. 本程序上级目录、各盘符下 3 层以内搜索
    roots = [os.path.dirname(HERE), HERE] + [f"{c}:\\" for c in "CDEFGHIJK" if os.path.exists(f"{c}:\\")]
    for root in roots:
        for cur, dirs, files in os.walk(root):
            if cur[len(root):].count(os.sep) >= 3:
                dirs[:] = []
                continue
            dirs[:] = [x for x in dirs if not x.startswith(("$", ".")) and x.lower() not in
                       ("windows", "programdata", "appdata", "node_modules", "system volume information")]
            if "MAA.exe" in files and is_maa_dir(cur):
                return cur
    return None


def running_paths(names):
    """正在运行的指定进程的 exe 路径"""
    try:
        cmd = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Process " + ",".join(names) + " -ErrorAction SilentlyContinue | ForEach-Object { $_.Path }"
        out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                             capture_output=True, text=True, encoding="utf-8", errors="ignore", creationflags=NOWIN, timeout=20).stdout
        return [l.strip() for l in out.splitlines() if l.strip()]
    except Exception:
        return []


def read_maa_connect(maa):
    """兼容多版本 MAA 的连接设置，返回 (adb路径, 地址, 是否自动检测, 来源说明)
    - v5.x ~ v6.x：config/gui.new.json → Configurations/<当前配置>/Gui/ConnectSettings/{AdbPath, Address, AutoDetect}
    - 较早版本：  config/gui.json → Configurations/<当前配置>/{Connect.AdbPath, Connect.Address, Connect.AutoDetect}
    - 更早版本：  config/gui.json 顶层直接是 {Connect.AdbPath, ...}"""
    def load(name):
        try:
            return json.load(open(os.path.join(maa, "config", name), encoding="utf-8"))
        except Exception:
            return None

    d = load("gui.new.json")
    if isinstance(d, dict):
        cfgs = d.get("Configurations", {}) or {}
        cur = d.get("Current", "Default")
        for key in [cur] + [k for k in cfgs if k != cur]:
            cs = ((cfgs.get(key) or {}).get("Gui") or {}).get("ConnectSettings") or {}
            if cs:
                return (cs.get("AdbPath", ""), cs.get("Address", ""), bool(cs.get("AutoDetect", False)),
                        f"gui.new.json（配置 {key}）")
    d = load("gui.json")
    if isinstance(d, dict):
        cfgs = d.get("Configurations")
        cur = d.get("Current", "Default")
        if isinstance(cfgs, dict):
            for key in [cur] + [k for k in cfgs if k != cur]:
                c = cfgs.get(key) or {}
                if c.get("Connect.AdbPath") or c.get("Connect.Address"):
                    return (c.get("Connect.AdbPath", ""), c.get("Connect.Address", ""),
                            str(c.get("Connect.AutoDetect", "False")).lower() == "true", f"gui.json（配置 {key}）")
        for c in (d, d.get("Global") or {}):
            if isinstance(c, dict) and (c.get("Connect.AdbPath") or c.get("Connect.Address")):
                return (c.get("Connect.AdbPath", ""), c.get("Connect.Address", ""),
                        str(c.get("Connect.AutoDetect", "False")).lower() == "true", "gui.json（旧格式）")
    return "", "", True, ""


# 常见模拟器的 adb 端口（MuMu12 多开：16384 + 32*n）
COMMON_ADDRS = ([f"127.0.0.1:{16384 + 32 * i}" for i in range(8)] +
                ["127.0.0.1:7555", "127.0.0.1:5555", "127.0.0.1:5557", "127.0.0.1:5565",
                 "127.0.0.1:62001", "127.0.0.1:62025", "127.0.0.1:59865", "127.0.0.1:21503"])
EMU_PROCS = ["MuMuNxDevice", "MuMuPlayer", "MuMuNxMain", "dnplayer", "LDPlayer", "Nox", "NoxVMHandle",
             "HD-Player", "MEmu"]


def find_adb(maa):
    """adb 候选：MAA 自带的 → 正在运行的模拟器目录里的 → 系统 PATH（不含内置备用）"""
    cands = []
    if maa:
        cands += [os.path.join(maa, "adb", "platform-tools", "adb.exe"),
                  os.path.join(maa, "platform-tools", "adb.exe"), os.path.join(maa, "adb.exe")]
    for exe in running_paths(EMU_PROCS):
        d = os.path.dirname(exe)
        for sub in ("", "shell", os.path.join("..", "shell"), "..", os.path.join("..", "vmonitor", "bin")):
            for n in ("adb.exe", "nox_adb.exe", "HD-Adb.exe", "dnadb.exe"):
                cands.append(os.path.normpath(os.path.join(d, sub, n)))
    import shutil
    w = shutil.which("adb")
    if w:
        cands.append(w)
    return [c for c in dict.fromkeys(cands) if os.path.isfile(c)]


def adb_online(adb_exe):
    try:
        out = subprocess.run([adb_exe, "devices"], capture_output=True, text=True, encoding="utf-8", errors="ignore",
                             creationflags=NOWIN, timeout=20).stdout
    except Exception:
        return []
    return [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]


def try_connect(adb_exe, address, autodetect):
    """按 MAA 地址 → 已在线的唯一设备 → 常见模拟器端口 的顺序连接，返回设备序列号或 None"""
    if address and ":" in address:
        subprocess.run([adb_exe, "connect", address], capture_output=True, creationflags=NOWIN, timeout=20)
    online = adb_online(adb_exe)
    if address and address in online:
        return address
    if len(online) == 1 and (autodetect or not address):
        return online[0]
    for addr in COMMON_ADDRS:
        try:
            r = subprocess.run([adb_exe, "connect", addr], capture_output=True, text=True, encoding="utf-8", errors="ignore",
                               creationflags=NOWIN, timeout=6).stdout
        except Exception:
            continue
        if r and "connected" in r and "cannot" not in r and "failed" not in r:
            return addr
    online = adb_online(adb_exe)
    return online[0] if len(online) == 1 else None


CHECKS = []   # (状态 ✔/⚠/✘, 项目, 说明)


def check(status, item, msg=""):
    CHECKS.append((status, item, msg))
    print(f"  [{status}] {item}" + (f"：{msg}" if msg else ""), flush=True)


def fatal_box(msg):
    print(msg, flush=True)
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "GarrisonFarm 启动自检未通过", 0x10 | 0x1000 | 0x10000 | 0x40000)
        except Exception:
            pass
    sys.exit(1)


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """以管理员身份重新启动自己（弹出 UAC 确认），原进程退出"""
    import ctypes
    if getattr(sys, "frozen", False):
        exe, params = sys.executable, sys.argv[1:]
    else:
        exe, params = sys.executable, [os.path.abspath(__file__)] + sys.argv[1:]
    arg = " ".join(f'"{x}"' if (" " in x or not x) else x for x in params)
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, arg, HERE, 1)
    if r <= 32:
        fatal_box("PC 端模式需要以管理员身份运行（与 MAA 的 PC 端相同），但没有获得管理员权限。")
    print("已在新的管理员窗口中继续运行，本窗口可以关闭。", flush=True)
    sys.exit(0)


WIN_ORIG = [None]


def restore_window():
    if WIN_ORIG[0]:
        try:
            import ctypes
            h, x, y = WIN_ORIG[0]
            ctypes.windll.user32.SetWindowPos(h, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)
        except Exception:
            pass


def setup_pc(args):
    """PC 端自检：管理员权限 → MAA 设置（截图/鼠标方式） → 游戏窗口 → 截图 → 文字识别模型"""
    global PCW, ocr_engine, BACKEND
    BACKEND = "pc"
    print("========== 启动自检（PC 端） ==========", flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        check("✔", "程序目录可写")
    except Exception as e:
        fatal_box(f"程序所在文件夹无法写入（{e}），请解压到普通目录后再运行。")
    if not is_admin():
        fatal_box("PC 端模式需要以管理员身份运行（明日方舟 PC 端以管理员权限运行，与 MAA 的 PC 端要求相同）。\n"
                  "请右键「开始刷角标.bat」→「以管理员身份运行」，或在弹出的 UAC 窗口中点「是」。")
    check("✔", "管理员权限")
    maa = None if args.no_maa else (args.maa if is_maa_dir(args.maa) else find_maa())
    sc, mouse, src = "PrintWindow", "PostMessageWithCursorPos", "默认"
    if maa:
        check("✔", "找到 MAA", maa)
        try:
            d = json.load(open(os.path.join(maa, "config", "gui.new.json"), encoding="utf-8"))
            cs = d["Configurations"][d.get("Current", "Default")]["Gui"]["ConnectSettings"]
            wx = (cs.get("Extras") or {}).get("Win32Extra") or {}
            if wx:
                sc, mouse, src = wx.get("ScreencapMethod", sc), wx.get("MouseMethod", mouse), "MAA 设置"
        except Exception:
            pass
    else:
        check("⚠", "未找到 MAA", "使用默认的 PC 端方式和内置文字识别模型")
    if args.pc_screencap:
        sc, src = args.pc_screencap, "命令行"
    if args.pc_mouse:
        mouse, src = args.pc_mouse, "命令行"
    global MC
    if not args.no_maafw:
        try:
            MC, scn, imn = maafw_pc(sc, mouse)
            check("✔", "控制方式", f"MaaFramework（maafw）：截图 {scn}，鼠标 {imn}（来源：{src}）")
        except Exception as e:
            MC = None
            print("MaaFramework 加载失败详情：", repr(e), flush=True)
            check("⚠", "MaaFramework 不可用", f"{str(e)[:60]}；改用内置 PC 控制")
    PCW = PCWin(sc, mouse)
    try:                                    # 记录窗口原始位置，退出时还原（PostMsg-WindowPos 会移动窗口）
        import ctypes, ctypes.wintypes as _W
        r = _W.RECT(); ctypes.windll.user32.GetWindowRect(PCW.hwnd, ctypes.byref(r))
        WIN_ORIG[0] = (PCW.hwnd, r.left, r.top)
    except Exception:
        pass
    note = ""
    if PCW.mouse_method != mouse or PCW.screencap_method != sc:
        note = f"（MAA 中的 {sc} / {mouse} 本程序暂不支持或实测无效，已改用 {PCW.screencap_method} / {PCW.mouse_method}）"
    if MC is None:
        check("✔", "PC 端方式", f"截图 {PCW.screencap_method}，鼠标 {PCW.mouse_method}（来源：{src}）{note}")
    if not PCW.hwnd:
        fatal_box("没有找到明日方舟 PC 端的游戏窗口。请先启动游戏（鹰角启动器），进入卫戍协议界面后再运行。")
    w, h = PCW.client_size()
    check("✔" if (w, h) == (1920, 1080) else "⚠", "游戏窗口", f"{w}x{h}" + (
        "" if (w, h) == (1920, 1080) else "（建议把游戏分辨率设为 1920x1080，其他 16:9 分辨率会自动缩放但未充分测试）"))
    if abs(w / max(h, 1) - 16 / 9) > 0.02:
        fatal_box(f"游戏窗口比例不是 16:9（{w}x{h}），请在游戏设置里改为 1920x1080 等 16:9 分辨率。")
    img = MC.shot() if MC is not None else PCW.shot()
    if img is None or img.mean() < 1:
        fatal_box("无法截取游戏画面（PrintWindow 返回黑屏）。请确认游戏窗口没有最小化，并以管理员身份运行本程序。")
    check("✔", "截图", "maafw" if MC is not None else PCW.screencap_method)
    tried = []
    if maa:
        tried.append(("MAA", os.path.join(maa, "resource", "PaddleOCR")))
    tried.append(("内置", os.path.join(FALLBACK, "PaddleOCR")))
    ocr_engine = None
    for tag, m in tried:
        try:
            eng = RapidOCR(det_model_path=os.path.join(m, "det", "inference.onnx"),
                           rec_model_path=os.path.join(m, "rec", "inference.onnx"),
                           rec_keys_path=os.path.join(m, "rec", "keys.txt"), use_cls=False)
            if not eng(img)[0]:
                raise RuntimeError("测试识别没有结果")
            ocr_engine = eng
            check("✔" if tag == "MAA" else "⚠", "文字识别模型", f"使用{tag}模型")
            break
        except Exception as e:
            if tag == "MAA":
                check("⚠", "MAA 文字识别模型不可用", str(e)[:60])
    if ocr_engine is None:
        fatal_box("文字识别模型无法加载，请重新完整解压程序包。")
    print("==============================", flush=True)
    mm = args.pc_mouse or mouse
    moves = MC is None or any(k in mm for k in ("CursorPos", "Seize", "LegacyEvent"))
    if MC is not None and "WindowPos" in mm:
        print("提示：PostMsg-WindowPos 操作时会移动游戏窗口（窗口会乱飞），属正常现象。", flush=True)
    if moves:
        print("提示：当前鼠标方式会移动你的鼠标来点击游戏，运行期间请不要使用鼠标。", flush=True)
    else:
        print("提示：当前鼠标方式为全后台（不移动鼠标），可以正常使用电脑；游戏窗口不要最小化。", flush=True)


def setup(args):
    """启动自检 + 连接。优先使用 MAA 的配置与 OCR 模型；读取失败时才改用内置备用，并提醒"""
    global ADB, DEV, ocr_engine
    print("========== 启动自检 ==========", flush=True)
    # 1. 程序目录可写
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        t = os.path.join(LOG_DIR, ".write_test")
        open(t, "w").write("ok"); os.remove(t)
        check("✔", "程序目录可写")
    except Exception as e:
        fatal_box(f"程序所在文件夹无法写入（{e}）。\n请把整个文件夹解压到普通目录（如 D:\\GarrisonFarm）后再运行，"
                  "不要放在 Program Files、压缩包内或只读位置。")
    # 2. 必要文件
    miss = [n for n in ("tiles.json", "_internal") if getattr(sys, "frozen", False) and
            not os.path.exists(os.path.join(HERE, n))]
    if miss:
        fatal_box("缺少文件：" + "、".join(miss) + "。请重新完整解压程序包。")
    check("✔", "程序文件完整")

    warnings = []
    # 3. MAA
    maa = None if args.no_maa else (args.maa if is_maa_dir(args.maa) else find_maa())
    if maa:
        check("✔", "找到 MAA", maa)
        try:
            json.dump({"maa_dir": maa}, open(SETTINGS, "w", encoding="utf-8"), ensure_ascii=False)
        except Exception:
            pass
    else:
        check("⚠", "未找到 MAA", "将使用内置的 adb 和文字识别模型")
        warnings.append("未找到 MAA")
    # 4. 连接配置
    adb_path, address, autodetect, src = read_maa_connect(maa) if maa else ("", "", True, "")
    adb_path = args.adb or adb_path
    address = args.address or address
    if maa and src:
        check("✔", "读取 MAA 连接设置", f"{src}，地址 {address or '自动检测'}")
    elif maa:
        check("⚠", "读取 MAA 连接设置失败", "可能是 MAA 版本格式不同，将自动查找模拟器")
        warnings.append("读取 MAA 连接设置失败")
    if adb_path and not os.path.isabs(adb_path) and maa:
        adb_path = os.path.normpath(os.path.join(maa, adb_path))
    cands = ([adb_path] if adb_path and os.path.isfile(adb_path) else []) + find_adb(maa)
    fb_adb = os.path.join(FALLBACK, "adb", "adb.exe")
    if os.path.isfile(fb_adb):
        cands.append(fb_adb)
    cands = list(dict.fromkeys(cands))
    if not cands:
        fatal_box("找不到 adb。请先在 MAA 中完成「连接设置」，或确认程序包里的 fallback 文件夹完整。")
    if not (adb_path and os.path.isfile(adb_path)):
        warnings.append("未使用 MAA 配置的 adb")
    # 5. 连接设备
    DEV = None
    for exe in cands:
        dev = try_connect(exe, address, autodetect)
        if dev:
            ADB, DEV = os.path.normpath(exe), dev
            break
    if not DEV:
        fatal_box("无法连接模拟器。\n请确认：模拟器已启动；MAA 能正常连接它；没有其他程序占用 adb。\n"
                  f"已尝试的 adb：{len(cands)} 个；地址：{address or '自动检测'} 及常见模拟器端口。")
    if ADB == os.path.normpath(fb_adb):
        check("⚠", "连接模拟器", f"{DEV}（使用内置 adb）")
        warnings.append("使用内置 adb")
    else:
        check("✔", "连接模拟器", f"{DEV}（adb：{ADB}）")
    # 5.5 MaaFramework（maafw）：截图/输入自动测速选最快方式（MaaTouch、MuMu 截图增强等）
    global MC
    if not args.no_maafw:
        try:
            t0 = time.time()
            MC = maafw_adb(ADB, DEV)
            check("✔", "控制方式", f"MaaFramework（maafw），自动选择最快的截图/触控方式（{time.time() - t0:.0f}s）")
        except Exception as e:
            MC = None
            print("MaaFramework 加载失败详情：", repr(e), flush=True)
            check("⚠", "MaaFramework 不可用", f"{str(e)[:60]}；改用 adb 命令")
    # 6. 截图
    raw = subprocess.run([ADB, "-s", DEV, "exec-out", "screencap", "-p"], capture_output=True,
                         creationflags=NOWIN, timeout=30).stdout
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR) if raw else None
    if img is None:
        fatal_box("无法从模拟器截图（adb screencap 失败）。请重启模拟器后再试，或在模拟器设置中开启 ADB 调试。")
    h, w = img.shape[:2]
    check("✔" if (w, h) == (1920, 1080) else "⚠", "截图", f"{w}x{h}" + ("" if (w, h) == (1920, 1080)
          else "（本程序按 1920x1080 横屏设计，请在模拟器里改为 1920x1080）"))
    # 7. 拖拽支持
    helptxt = subprocess.run([ADB, "-s", DEV, "shell", "input"], capture_output=True, text=True, encoding="utf-8", errors="ignore",
                             creationflags=NOWIN, timeout=20)
    if MC is not None or "motionevent" in (helptxt.stdout + helptxt.stderr):
        check("✔", "拖拽支持（input motionevent）")
    else:
        fatal_box("模拟器的安卓版本不支持拖拽指令（input motionevent），无法摆放干员。\n请使用安卓 12 的模拟器（如 MuMu 模拟器 12）。")
    # 8. OCR 模型：优先 MAA 的，失败再用内置
    tried = []
    if maa:
        tried.append(("MAA", os.path.join(maa, "resource", "PaddleOCR")))
    tried.append(("内置", os.path.join(FALLBACK, "PaddleOCR")))
    ocr_engine = None
    for tag, m in tried:
        try:
            eng = RapidOCR(det_model_path=os.path.join(m, "det", "inference.onnx"),
                           rec_model_path=os.path.join(m, "rec", "inference.onnx"),
                           rec_keys_path=os.path.join(m, "rec", "keys.txt"), use_cls=False)
            res, _ = eng(img)
            if not res:
                raise RuntimeError("测试识别没有结果")
            ocr_engine = eng
            if tag == "MAA":
                check("✔", "文字识别模型", "使用 MAA 的模型")
            else:
                check("⚠", "文字识别模型", "使用内置模型（MAA 的模型读取失败或不存在）")
                warnings.append("使用内置文字识别模型")
            break
        except Exception as e:
            if tag == "MAA":
                check("⚠", "MAA 文字识别模型不可用", str(e)[:60])
    if ocr_engine is None:
        fatal_box("文字识别模型无法加载（MAA 的和内置的都失败）。请重新完整解压程序包。")
    print("==============================", flush=True)
    if warnings:
        msg = ("自检发现以下情况，已自动改用内置/自动查找的方式继续运行：\n  - " + "\n  - ".join(warnings) +
               "\n\n一般不影响使用；如果之后连接或识别出错，请先在 MAA 中确认能正常连接模拟器。")
        print(msg, flush=True)
        if os.name == "nt" and not args.yes:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, msg, "GarrisonFarm 自检提醒", 0x30 | 0x1000 | 0x10000 | 0x40000)
            except Exception:
                pass


# ---------------- PC 端（Win32）后端 ----------------
# 参照 MAA / MaaFramework 的 Win32 控制方案（MAA「连接设置 → PC 端」中的 截图方式 / 鼠标输入方式）：
#   截图：PrintWindow（默认，窗口被遮挡也能截）/ ScreenDC（窗口须在最前且不被遮挡）
#   鼠标：PostMessageWithCursorPos（默认，会移动真实鼠标）/ SendMessageWithCursorPos / Seize（前台真实鼠标）
# 明日方舟 PC 端以管理员权限运行，本程序在 PC 模式下也必须以管理员身份运行（与 MAA 相同）。
BACKEND = "adb"


class PCWin:
    WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x200, 0x201, 0x202

    def __init__(self, screencap="PrintWindow", mouse="PostMessageWithCursorPos"):
        import ctypes, ctypes.wintypes as W
        self.ct, self.W = ctypes, W
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
        self.u, self.g = ctypes.windll.user32, ctypes.windll.gdi32
        self.hwnd = self.find_window()
        self.screencap_method = screencap if screencap in ("PrintWindow", "ScreenDC") else "PrintWindow"
        known = ("PostMessageWithCursorPos", "SendMessageWithCursorPos", "Seize")
        self.mouse_method = mouse if mouse in known else "PostMessageWithCursorPos"
        self.saved_cursor = None

        class BMI(ctypes.Structure):
            _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                        ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                        ("a", W.LONG), ("b", W.LONG), ("c", W.DWORD), ("d", W.DWORD)]
        self.BMI = BMI

    def find_window(self):
        h = self.u.FindWindowW("UnityWndClass", "明日方舟")
        if not h:
            h = self.u.FindWindowW("UnityWndClass", "Arknights")
        return h

    def client_size(self):
        r = self.W.RECT()
        self.u.GetClientRect(self.hwnd, self.ct.byref(r))
        return r.right, r.bottom

    def to_screen(self, x, y):
        pt = self.W.POINT(int(x), int(y))
        self.u.ClientToScreen(self.hwnd, self.ct.byref(pt))
        return pt.x, pt.y

    def shot(self):
        if not self.u.IsWindow(self.hwnd):
            self.hwnd = self.find_window()
        w, h = self.client_size()
        if w <= 0 or h <= 0:
            return None
        if self.screencap_method == "ScreenDC":
            src = self.u.GetDC(0)
        else:
            src = self.u.GetDC(self.hwnd)
        mdc = self.g.CreateCompatibleDC(src)
        bmp = self.g.CreateCompatibleBitmap(src, w, h)
        self.g.SelectObject(mdc, bmp)
        if self.screencap_method == "ScreenDC":
            x0, y0 = self.to_screen(0, 0)
            self.g.BitBlt(mdc, 0, 0, w, h, src, x0, y0, 0x00CC0020)
        else:
            self.u.PrintWindow(self.hwnd, mdc, 3)          # PW_CLIENTONLY | PW_RENDERFULLCONTENT
        bi = self.BMI(); bi.biSize = self.ct.sizeof(self.BMI); bi.biWidth = w; bi.biHeight = -h
        bi.biPlanes = 1; bi.biBitCount = 32
        buf = self.ct.create_string_buffer(w * h * 4)
        self.g.GetDIBits(mdc, bmp, 0, h, buf, self.ct.byref(bi), 0)
        self.g.DeleteObject(bmp); self.g.DeleteDC(mdc)
        self.u.ReleaseDC(0 if self.screencap_method == "ScreenDC" else self.hwnd, src)
        img = np.frombuffer(buf, np.uint8).reshape(h, w, 4)[:, :, :3].copy()
        if (w, h) != (1920, 1080):
            img = cv2.resize(img, (1920, 1080))      # 统一到 1920x1080 坐标系
        return img

    def _scale(self, x, y):
        w, h = self.client_size()
        return int(x * w / 1920), int(y * h / 1080)

    def _send(self, msg, wparam, x, y):
        cx, cy = self._scale(x, y)
        if self.mouse_method == "Seize":
            return
        sx, sy = self.to_screen(cx, cy)
        self.u.SetCursorPos(sx, sy)
        lp = (cy << 16) | (cx & 0xFFFF)
        if self.mouse_method == "SendMessageWithCursorPos":
            self.u.SendMessageW(self.hwnd, msg, wparam, lp)
        else:
            self.u.PostMessageW(self.hwnd, msg, wparam, lp)

    def _seize(self, kind, x, y):
        cx, cy = self._scale(x, y)
        sx, sy = self.to_screen(cx, cy)
        self.u.SetCursorPos(sx, sy)
        flag = {"DOWN": 0x0002, "UP": 0x0004}.get(kind)
        if flag:
            self.u.mouse_event(flag, 0, 0, 0, 0)

    def touch(self, kind, x, y):
        if kind == "DOWN":
            old = self.W.POINT(); self.u.GetCursorPos(self.ct.byref(old)); self.saved_cursor = (old.x, old.y)
            if self.mouse_method == "Seize":
                self.u.SetForegroundWindow(self.hwnd)
        if self.mouse_method == "Seize":
            self._seize(kind, x, y)
        elif kind == "DOWN":
            self._send(self.WM_MOUSEMOVE, 0, x, y); time.sleep(0.03)
            self._send(self.WM_LBUTTONDOWN, 1, x, y)
        elif kind == "MOVE":
            self._send(self.WM_MOUSEMOVE, 1, x, y)
        else:
            self._send(self.WM_LBUTTONUP, 0, x, y)
        if kind in ("UP", "CANCEL"):
            time.sleep(0.03)
            if self.saved_cursor:
                self.u.SetCursorPos(*self.saved_cursor)      # 操作完成后把鼠标放回原处
                self.saved_cursor = None

    def tap(self, x, y):
        self.touch("DOWN", x, y); time.sleep(0.06); self.touch("UP", x, y)

    def drag(self, x1, y1, x2, y2, steps=12, step_sleep=0.012):
        for k in range(1, steps + 1):
            self.touch("MOVE", x1 + (x2 - x1) * k / steps, y1 + (y2 - y1) * k / steps)
            time.sleep(step_sleep)


PCW = None

# ---------------- MaaFramework（maafw）控制器：首选方案 ----------------
# 直接使用 MaaFramework 官方 Python 包（MAA 的底层框架），截图/点击/拖拽都走它的正式接口：
#   PC 端：Win32Controller（截图 PrintWindow 等，鼠标 AnchoredTouch 等，读取 MAA 的 PC 端设置）
#   模拟器：AdbController（自动测速选最快的截图方式，MuMu 截图增强；输入 MaaTouch / Minitouch）
MC = None          # maafw 控制器


class MaaCtl:
    def __init__(self, ctl):
        self.c = ctl
        try:
            ctl.set_screenshot_use_raw_size(True)
        except Exception:
            pass

    def shot(self):
        img = self.c.post_screencap().wait().get()
        if img is None or getattr(img, "size", 0) == 0:
            return None
        if img.shape[1] < img.shape[0]:          # 竖屏截图转横屏
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if img.shape[:2] != (1080, 1920):
            img = cv2.resize(img, (1920, 1080))
        return img

    def tap(self, x, y):
        self.c.post_click(int(x), int(y)).wait()

    def touch(self, kind, x, y):
        if kind == "DOWN":
            self.c.post_touch_down(int(x), int(y)).wait()
        elif kind == "MOVE":
            self.c.post_touch_move(int(x), int(y)).wait()
        else:
            self.c.post_touch_up().wait()

    def drag(self, x1, y1, x2, y2, steps=12, step_sleep=0.012):
        for k in range(1, steps + 1):
            self.c.post_touch_move(int(x1 + (x2 - x1) * k / steps), int(y1 + (y2 - y1) * k / steps)).wait()
            time.sleep(step_sleep)

    def swipe(self, x1, y1, x2, y2, ms):
        self.c.post_swipe(int(x1), int(y1), int(x2), int(y2), int(ms)).wait()


_MAA_DLL = [False]


def maafw_dll_dirs():
    """打包后 Windows 不会在 maa\bin 里找 MaaToolkit 等的依赖 DLL，需要手动加入搜索路径"""
    if _MAA_DLL[0]:
        return
    base = getattr(sys, "_MEIPASS", None)
    cands = [os.path.join(base, "maa", "bin")] if base else []
    try:
        import importlib.util
        spec = importlib.util.find_spec("maa")
        if spec and spec.submodule_search_locations:
            cands.append(os.path.join(list(spec.submodule_search_locations)[0], "bin"))
    except Exception:
        pass
    for d in cands:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
    _MAA_DLL[0] = True


def maafw_init():
    from maa.toolkit import Toolkit
    Toolkit.init_option(os.path.join(HERE, "maafw_data"))
    return Toolkit


def maafw_pc(sc_name, mouse_name):
    """用 maafw 绑定明日方舟 PC 端窗口；方式名与 MAA 设置里的一致"""
    maafw_dll_dirs()
    from maa.controller import Win32Controller
    from maa.define import MaaWin32ScreencapMethodEnum as SC, MaaWin32InputMethodEnum as IM
    tk = maafw_init()
    wins = [w for w in tk.find_desktop_windows() if w.window_name in ("明日方舟", "Arknights")
            and w.class_name == "UnityWndClass"]
    if not wins:
        raise RuntimeError("没有找到明日方舟 PC 端的游戏窗口")
    alias = {"PostMsg-CursorPos": "PostMessageWithCursorPos", "PostMsg-WindowPos": "PostMessageWithWindowPos",
             "PostMsg": "PostMessage", "SendMsg": "SendMessage"}
    mouse_name = alias.get(mouse_name, mouse_name)
    im = getattr(IM, mouse_name, None) or IM.AnchoredTouch
    if im in (IM.PostMessage, IM.SendMessage):        # 纯后台消息对明日方舟无效（只认真实鼠标位置）
        im = IM.AnchoredTouch
    sc = getattr(SC, sc_name, None) or SC.PrintWindow
    if im == IM.PostMessageWithWindowPos:
        sc = SC.PrintWindow                             # WindowPos 只能配 PrintWindow（与 MAA 一致）
    ctl = Win32Controller(wins[0].hwnd, sc, im, IM.PostMessage)
    if not ctl.post_connection().wait().succeeded:
        raise RuntimeError("maafw 连接游戏窗口失败")
    return MaaCtl(ctl), sc.name, im.name


def maafw_adb(adb_path, address):
    """用 maafw 连接模拟器（自动测速选择截图/输入方式；MuMu 12 / 雷电 9 开启截图增强）"""
    maafw_dll_dirs()
    from maa.controller import AdbController
    from maa.define import MaaAdbScreencapMethodEnum as SC, MaaAdbInputMethodEnum as IM
    tk = maafw_init()
    sc, im, cfg = SC.Default, IM.Default, {}
    for d in tk.find_adb_devices(specified_adb=adb_path):
        if d.address == address:
            sc, im, cfg = d.screencap_methods, d.input_methods, d.config      # 含 MuMu 截图增强配置
            break
    ctl = AdbController(adb_path, address, sc, im, cfg)
    if not ctl.post_connection().wait().succeeded:
        raise RuntimeError("maafw 连接模拟器失败")
    return MaaCtl(ctl)


# ---------------- 基础 ----------------
def adb(*args, capture=False):
    cmd = [ADB, "-s", DEV] + list(args)
    r = subprocess.run(cmd, capture_output=True, creationflags=NOWIN)
    return r.stdout if capture else None

def shot():
    if MC is not None:
        for _ in range(5):
            img = MC.shot()
            if img is not None and img.mean() > 1:
                return img
            time.sleep(0.5)
        raise RuntimeError("截图失败（maafw）")
    if BACKEND == "pc":
        for _ in range(5):
            img = PCW.shot()
            if img is not None and img.mean() > 1:
                return img
            time.sleep(0.5)
        raise RuntimeError("PC 端截图失败（游戏窗口是否被最小化？）")
    for _ in range(5):
        raw = adb("exec-out", "screencap", "-p", capture=True)
        img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img
        time.sleep(0.5)
    raise RuntimeError("截图失败")

def tap(x, y, wait=0.6):
    if MC is not None:
        MC.tap(x, y)
    elif BACKEND == "pc":
        PCW.tap(x, y)
    else:
        adb("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)

def swipe(x1, y1, x2, y2, ms=500, wait=0.8):
    if MC is not None:
        MC.touch("DOWN", x1, y1)
        MC.drag(x1, y1, x2, y2, max(6, int(ms / 30)), ms / 1000 / max(6, int(ms / 30)))
        time.sleep(0.1)
        MC.touch("UP", x2, y2)
    elif BACKEND == "pc":
        steps = max(6, int(ms / 30))
        PCW.touch("DOWN", x1, y1)
        PCW.drag(x1, y1, x2, y2, steps, ms / 1000 / steps)
        time.sleep(0.1)
        PCW.touch("UP", x2, y2)
    else:
        adb("shell", "input", "swipe", *map(str, map(int, (x1, y1, x2, y2, ms))))
    time.sleep(wait)

def touch(kind, x, y):
    if MC is not None:
        MC.touch(kind, x, y)
        return
    if BACKEND == "pc":
        PCW.touch(kind, x, y)
        return
    adb("shell", "input", "motionevent", kind, str(int(x)), str(int(y)))

def ocr(img, box=None):
    """返回 [(cx, cy, text)]，坐标为全图坐标"""
    ox = oy = 0
    if box:
        x1, y1, x2, y2 = box
        P = 40   # MAA 的检测模型对紧贴边缘的小裁剪识别差，加边框
        img = cv2.copyMakeBorder(img[y1:y2, x1:x2], P, P, P, P, cv2.BORDER_REPLICATE)
        ox, oy = x1 - P, y1 - P
    res, _ = ocr_engine(img)
    out = []
    for b, t, c in (res or []):
        xs = [p[0] for p in b]; ys = [p[1] for p in b]
        out.append((ox + sum(xs) / 4, oy + sum(ys) / 4, t))
    return out

def find(items, *kw):
    for x, y, t in items:
        if any(k in t for k in kw):
            return x, y, t
    return None

def numrec(img, box):
    """只用识别模型读固定位置的数字（MAA 的检测模型常漏掉单个数字）"""
    x1, y1, x2, y2 = box
    try:
        res, _ = ocr_engine(img[y1:y2, x1:x2], use_det=False, use_cls=False, use_rec=True)
    except Exception:
        return None
    t, conf = (res[0][0], res[0][1]) if res else ("", 0)
    d = "".join(ch for ch in t if ch in "0123456789")
    if d and conf >= 0.4:
        return int(d)
    return num(img, box)   # 置信度低时退回"检测+识别"

def num(img, box):
    best = ""
    for _, _, t in ocr(img, box):
        d = "".join(ch for ch in t if ch in "0123456789")
        if len(d) > len(best):
            best = d
    return int(best) if best else None

def log(*a):
    line = " ".join([time.strftime("%H:%M:%S")] + [str(x) for x in a])
    print(line, flush=True)
    try:
        with open(os.path.join(LOG_DIR, "run.log"), "a", encoding="utf-8") as f:
            print(time.strftime("%Y-%m-%d"), line, file=f)
    except Exception:
        pass

def save(img, tag):
    p = os.path.join(LOG_DIR, f"{time.strftime('%H%M%S')}_{tag}.png")
    cv2.imwrite(p, img)
    return p

def load_done():
    try:
        with open(DONE_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()

def save_done(s):
    with open(DONE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f, ensure_ascii=False, indent=1)

def yellow_ratio(img, box):
    x1, y1, x2, y2 = box
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (8, 120, 150), (35, 255, 255))
    return m.mean() / 255

# ---------------- 开局流程 ----------------
GRID_X = [680, 890, 1100, 1310]      # 选中任意策略后网格左移后的列中心
GRID_Y = [370, 580, 790, 1000]

def has_color_badge(img, gx, gy):
    """格子右上角的彩色（镀层）角标：青蓝色系、不是金色（游戏内实测：彩标 0.37，金标 0）"""
    x1, y1, x2, y2 = gx + 40, max(0, gy - 110), gx + 95, gy - 45
    hsv = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2HSV)
    cyan = cv2.inRange(hsv, (70, 40, 150), (140, 255, 255)).mean() / 255
    return cyan > 0.15 and yellow_ratio(img, (x1, y1, x2, y2)) < 0.05


def has_badge(img, gx, gy):
    """格子右上角的金色角标"""
    return yellow_ratio(img, (gx + 40, gy - 100, gx + 90, gy - 50)) > 0.12 or         yellow_ratio(img, (gx + 30, max(0, gy - 130), gx + 100, gy - 30)) > 0.10

def passed_count(panel):
    """右侧面板"已通过模拟N次"中的 N；没有则 0"""
    for _, _, t in panel:
        if "通过" in t:
            d = "".join(ch for ch in t.split("通过")[-1] if ch in "0123456789")
            return int(d) if d else 1
    return 0

GRID_TOP, GRID_BOTTOM = 250, 1050       # 策略网格可见区域（纵向）
ROW_H = 210                              # 行间距


def grid_shift(before, after):
    """滚动后网格移动了多少像素（向上为正），用模板匹配测量"""
    strip = before[560:700, 600:1400]
    area = after[GRID_TOP:GRID_BOTTOM, 600:1400]
    res = cv2.matchTemplate(area, strip, cv2.TM_CCOEFF_NORMED)
    _, mx, _, loc = cv2.minMaxLoc(res)
    if mx < 0.6:
        return None
    return 560 - (GRID_TOP + loc[1])


def detect_rows(img):
    """滚动后网格行位置不规则（有分组标题），按第一列的立绘纹理找出每行中心"""
    band = cv2.cvtColor(img[:, 620:740], cv2.COLOR_BGR2GRAY).astype(np.float32)
    on = band.std(axis=1) > 18
    rows, start = [], None
    for y in range(GRID_TOP - 60, GRID_BOTTOM + 20):
        if on[y] and start is None:
            start = y
        if (not on[y] or y == GRID_BOTTOM + 19) and start is not None:
            if y - start >= 60:
                c = (start + y) // 2
                if GRID_TOP <= c <= GRID_BOTTOM - 20:
                    rows.append(c)
            start = None
    return rows


def scroll_grid():
    """慢速向上拖动策略列表约两行，结束前停顿以消除惯性"""
    x = 1000
    touch("DOWN", x, 900)
    drag_path(x, 900, x, 480, 14)
    time.sleep(0.5)
    touch("UP", x, 480)
    time.sleep(0.8)


def strategy_name(panel):
    cand = [(y, t) for x, y, t in panel if 520 < y < 650
            and any("\u4e00" <= ch <= "\u9fff" for ch in t)
            and "生命" not in t and "通过" not in t and "【" not in t]
    return cand[0][1] if cand else ""


def pick_strategy(done):
    """选择策略：角标需要通过 3 次。
    按网格顺序取第一个"无金色角标且通过次数 < 3"的策略（进行中的策略总在最前面），
    当前页都不可用时向下滚动继续找；不再逐个遍历所有策略。"""
    tap(1500, 580, 1.0)   # 先点一个格子，让网格左移到固定布局
    rows = list(GRID_Y)
    tried = set()
    for page in range(8):
        img = shot()
        for gy in rows:
            if not (GRID_TOP + 60 <= gy <= GRID_BOTTOM - 40):
                continue
            for gx in GRID_X:
                if has_color_badge(img, gx, gy) or (TARGET <= 3 and has_badge(img, gx, gy)):
                    continue
                tap(gx, gy, 0.7)
                panel, sname = [], ""
                for _try in range(3):        # 右侧面板有切换动画，读不到名字就稍等重读
                    panel = ocr(shot(), (1440, 150, 1920, 800))
                    sname = strategy_name(panel)
                    if sname:
                        break
                    time.sleep(0.6)
                if not sname:
                    log("策略面板读取失败，跳过该格", (gx, gy))
                    continue
                name = sname
                if name in tried:
                    continue
                tried.add(name)
                n = passed_count(panel)
                if n >= TARGET:
                    continue
                # 确认前再点一次并核对右侧面板名字，避免点击没生效而确认了别的策略
                ok_sel = False
                for _v in range(3):
                    time.sleep(0.4)
                    if strategy_name(ocr(shot(), (1440, 150, 1920, 800))) == name:
                        ok_sel = True
                        break
                    tap(gx, gy, 0.9)      # 只在面板名字不一致时再点（再点已选中的格子会取消选中）
                if not ok_sel:
                    log("核对策略名不一致，跳过该格", name)
                    continue
                log(f"选择策略: {name}（已通过 {n} 次" + (f"，继续凑满 {TARGET} 次）" if n else "，新策略）"))
                return name
        # 本页没有可用策略：向下滚动
        scroll_grid()
        after = shot()
        sh = grid_shift(img, after)
        if sh is not None and abs(sh) < 20:
            break                      # 列表不再移动 = 已到底
        rows = detect_rows(after)
        if not rows:
            break
        log(f"策略列表下滑，继续查找（本页 {len(rows)} 行）")
    log("没有找到未获得角标的策略，全部完成？")
    return None


# 优先干员（权重从高到低；只有多名同时出现、需要取舍时才按权重比较）
# 每项: (匹配关键字, 显示名)
# 标准模式：使用玩家自选编队中的干员（维什戴尔、望等需要玩家自己拥有）
PRIORITY_FULL = [("塔露拉", "塔露拉"), ("维什戴尔", "维什戴尔"), ("星熊", "斩业星熊"),
                 ("安洁莉娜", "予愿安洁莉娜"), ("能天使", "新约能天使"), ("凯尔希", "凯尔希·思衡托"),
                 ("望", "望"), ("初雪", "圣聆初雪"), ("逻各斯", "逻各斯"), ("蕾缪安", "蕾缪安"),
                 ("贝洛内", "贝洛内"), ("冻河", "冻河"), ("明霄陈", "赤刃明霄陈"), ("结城理", "结城理")]
SAFE_KEYS_FULL = ["维什戴尔", "望", "能天使", "初雪", "蕾缪安", "逻各斯", "冻河"]

# 低配模式：不需要自选编队，只用游戏预设干员（没有的可在「选配助战」里借用，最多 30 名）。
# 依据：用户实测认为较强的 24 名预设干员 + 本程序 10 连胜对局中实际发挥好的干员。
# Ⅵ 阶整体强于 Ⅴ 阶，排在前面；同阶内输出核心在前，辅助在后。
PRIORITY_LOW = [("塔露拉", "塔露拉"), ("史尔特尔", "史尔特尔"), ("耀骑士", "耀骑士临光"),
                ("逻各斯", "逻各斯"), ("克莱门莎", "克莱门莎"), ("锏", "锏"), ("帕拉斯", "帕拉斯"),
                ("真言", "真言"), ("蕾缪安", "蕾缪安"), ("烛煌", "烛煌"),
                ("艾丽妮", "艾丽妮"), ("薇薇安娜", "薇薇安娜"), ("维娜", "维娜·维多利亚"),
                ("乌尔比安", "乌尔比安"), ("棘刺", "棘刺"), ("凛冬", "怒潮凛冬"), ("初雪", "圣聆初雪"),
                ("迷迭香", "迷迭香"), ("鸿雪", "鸿雪"), ("贝洛内", "贝洛内"), ("佩佩", "佩佩"),
                ("隐德来希", "隐德来希"), ("冻河", "冻河"), ("酒神", "酒神")]
# 远程输出/辅助：优先放安全位（木框高台，敌人不经过）
SAFE_KEYS_LOW = ["逻各斯", "真言", "蕾缪安", "烛煌", "初雪", "迷迭香", "鸿雪", "冻河", "酒神"]

PRIORITY = PRIORITY_FULL
SAFE_KEYS = SAFE_KEYS_FULL
PROFILE = "full"
TARGET = 3          # 3 = 金色角标；6 = 彩色（镀层）角标


def set_profile(name):
    global PRIORITY, SAFE_KEYS, PROFILE
    PROFILE = name
    PRIORITY, SAFE_KEYS = (PRIORITY_LOW, SAFE_KEYS_LOW) if name == "low" else (PRIORITY_FULL, SAFE_KEYS_FULL)


def match_key(name, key):
    if not name:
        return False
    if len(key) == 1:   # "望"、"锏" 这种单字名只做精确/短名匹配
        return name.strip() == key or (len(name.strip()) <= 2 and key in name)
    return key in name


def prio_index(name):
    for i, (k, _) in enumerate(PRIORITY):
        if match_key(name, k):
            return i
    return None


def is_safe_op(name):
    return any(match_key(name, k) for k in SAFE_KEYS)


def rank(name, tier):
    """干员价值：优先干员 > 其他 V/VI 输出 > 其他 V/VI > 低星"""
    i = prio_index(name)
    if i is not None:
        return 1000 - i
    if tier >= 5:
        return 500 + (50 if is_dps(name) else 0)
    return tier


def pick_squad():
    """确定自选编队：每个等阶按权重选 2 名（优先干员 > 输出 > 其他）"""
    img = shot()
    items = ocr(img, (560, 80, 1720, 960))
    names = [(x, y, t) for x, y, t in items
             if any("\u4e00" <= ch <= "\u9fff" for ch in t) and "盟约" not in t
             and "阵容" not in t and "确定" not in t and "编队" not in t]
    banned = [(x, y) for x, y, t in items if "禁用" in t]       # "本局禁用"的干员不能选
    picked = []
    for lo, hi in ((380, 520), (760, 900)):          # 上排 Ⅴ 阶、下排 Ⅵ 阶的名字所在高度
        row = [(x, y, t) for x, y, t in names if lo <= y <= hi and "禁用" not in t
               and not any(abs(x - bx) < 90 and 0 < by - y < 80 for bx, by in banned)]
        row.sort(key=lambda c: -(rank(c[2], 6) + (5 if is_dps(c[2]) else 0)))
        for x, y, t in row[:2]:
            tap(x, y - 170, 0.4)
            picked.append(t)
    log("自选编队选择:", picked or "无（自选编队为空，直接开始）")
    tap(1686, 986, 1.5)


# ---------------- 局内 ----------------
CARD_X = [304, 550, 790, 1034, 1274, 1520]   # 商店卡牌中心（右对齐）
CARD_Y = 920
GOLD_BOX = (1785, 768, 1850, 816)
UPX = 100
CARDS = list(CARD_X)
SELL = (1760, 900)
REFRESH = (1786, 686)
READY = (1780, 170)

class Board:
    def __init__(self):
        self.ops = []          # [(x, y, tier)] 常规视角下的位置
        self.round_done = -1
        self.used = []         # 已占用的拖拽视角格子坐标
        self.pending = False   # 备战席上还有没部署的干员
        self.hi_tiles = []     # 放了 V/VI 干员的格子（不作为交换目标）
        self.prep_done = False
        self.last_ready = 0.0   # 上次点击"准备就绪"的时间  # 本次休整期是否已处理（回合数识别失败时使用）
        self.owned = {}        # 已购买的 V/VI 干员名 -> 数量（凑3个晋升）
        self.healers = 0       # 已购买的医疗干员数（前期最多 1 个）
        self.occ = {}          # 固定格子名 -> (干员名, 等阶, 是否高台)  —— 使用 tiles.json 布局时

def read_shop(img):
    gold = numrec(img, GOLD_BOX)
    global UPX, CARDS
    bottom = ocr(img, (0, 820, 760, 1010))
    hit = find(bottom, "满级", "升级")
    UPX = int(hit[0]) if hit else 100
    CARDS = [x for x in CARD_X if x > UPX + 150]
    maxed = bool(find(bottom, "满级"))
    up_cost = None if maxed else numrec(img, (UPX - 22, 780, UPX + 22, 822))
    rnd = numrec(img, (728, 32, 778, 68))
    return gold, up_cost, maxed, rnd

# 5/6 级输出干员（PRTS 卫戍协议规程干员表 + 职业：近卫/术师/狙击/输出型特种）
DPS = set("""
怒潮凛冬 艾丽妮 棘刺 佩佩 圣聆初雪 乌尔比安 薇薇安娜 贝洛内 维娜·维多利亚 维娜 迷迭香 鸿雪 阿米娅
赤刃明霄陈 司霆惊蛰 维什戴尔 斩业星熊 丰川祥子 结城理 凛御银灰 歌蕾蒂娅
Sharp 领主·Sharp Pith Stormeye 预备干员-近卫 预备干员-术师
引星棘刺 克莱门莎 耀骑士临光 荒芜拉普兰德 逻各斯 真言 史尔特尔 锏 塔露拉 夕 蕾缪安 帕拉斯 望 塑心
""".split())

# 医疗干员（PRTS 卫戍协议规程 干员表，职业=医疗）：前期最多只买 1 个
HEALERS = ["褐果", "莎草", "哈洛德", "瑰盐", "乌啾", "风絮", "流明", "夜莺", "华法琳",
           "纯烬艾雅法拉", "Mon3tr", "Touch"]

def is_healer(name):
    return bool(name) and any(h in name or (len(name) >= 2 and name in h) for h in HEALERS)

def is_dps(name):
    import difflib
    if not name:
        return False
    for d in DPS:
        if d in name or name in d or difflib.SequenceMatcher(None, d, name).ratio() >= 0.6:
            return True
    return False

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}

def shop_cards(img):
    """一次 OCR 解析整排商店卡牌 -> [dict(i, x, empty, cost, hi, op)]"""
    items = ocr(img, (180, 770, 1700, 1060))
    out = []
    for i, x in enumerate(CARDS):
        mine = [(cx, cy, t) for cx, cy, t in items if abs(cx - x) < 115]
        empty = any("INFO" in t.upper() for _, _, t in mine)
        cost = None
        for cx, cy, t in mine:
            if cy < 830 and abs(cx - x) < 45 and (t.strip() and all(ch in "0123456789" for ch in t.strip())):
                cost = int(t.strip())
        if cost is None and not empty:
            cost = numrec(img, (x - 22, 780, x + 22, 822))
        # 干员卡在立绘下方有盟约标签文字；装备卡没有
        op = any(930 < cy < 1000 and any("一" <= ch <= "鿿" for ch in t)
                 for cx, cy, t in mine)
        r = 0
        for cx, cy, t in mine:
            tt = t.strip().upper().replace("1", "I").replace("L", "I")
            if cy < 840 and cx < x - 50 and tt in ROMAN:
                r = ROMAN[tt]
        hi = r >= 5 if r else yellow_ratio(img, (x - 104, 800, x - 78, 826)) > 0.1
        names = [t for cx, cy, t in mine if cy >= 1000 and any("一" <= ch <= "鿿" or ch.isalpha() for ch in t)]
        name = names[-1].strip() if names else ""
        labels = [t.strip() for cx, cy, t in mine if 930 < cy < 1000 and t.strip()]
        out.append(dict(i=i, x=x, empty=empty, cost=cost, hi=hi, op=op and not empty,
                        name=name, dps=is_dps(name), tier=r, labels=labels))
    return out

def buy(i, cost=None):
    """点两次购买；确认是干员（左侧面板有'阻挡'）才买"""
    x = CARDS[i]
    g0 = numrec(shot(), GOLD_BOX)
    tap(x, CARD_Y, 0.8)
    img = shot()
    if find(ocr(img, (x - 120, 980, x + 120, 1060)), "无法购买") or             find(ocr(img, (1400, 120, 1920, 260)), "资金不足"):
        tap(960, 600, 0.4)
        return False
    left = ocr(img, (0, 250, 700, 620))
    is_op = bool(find(left, "特质", "天赋", "特性"))
    if not is_op:
        tap(x, CARD_Y, 0.4)  # 取消选中
        tap(960, 600, 0.4)
        return False
    tap(x, CARD_Y + 106, 1.2)
    g1 = numrec(shot(), GOLD_BOX)
    if cost != 0 and g0 is not None and g1 is not None and g1 >= g0:   # 0 费（晋升赠送）资金不变
        tap(960, 600, 0.4)
        return False
    return True

def green_tiles(img):
    """可部署格（拖拽时高亮为绿色）中心点，最右优先"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (35, 100, 100), (85, 255, 255)).astype(np.float32) / 255
    m[:120] = 0; m[760:] = 0; m[:, :180] = 0; m[:, 1650:] = 0
    f = cv2.blur(m, (61, 61))
    ys, xs = np.where(f > 0.93)
    order = np.argsort(-xs)
    pts = []
    for k in order:
        x, y = int(xs[k]), int(ys[k])
        if all(abs(x - px) > 105 or abs(y - py) > 75 for px, py in pts):
            pts.append((x, y))
        if len(pts) >= 40:
            break
    return pts

def right3(tiles, img):
    """只保留全图最右侧3列：以整个可部署区域的右边界为准（随行高做透视修正）"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (35, 100, 100), (85, 255, 255))
    m[:120] = 0; m[760:] = 0; m[:, 1650:] = 0
    ys, xs = np.where(m > 0)
    if len(xs) == 0:
        return []
    # 每一行的右边界拟合成随 y 线性变化（透视），取各行最右值的上包络
    edges = []
    for y0 in range(140, 760, 40):
        sel = xs[(ys >= y0) & (ys < y0 + 40)]
        if len(sel) > 200:
            edges.append((y0 + 20, np.percentile(sel, 99.5)))
    if not edges:
        return []
    ey = np.array([e[0] for e in edges]); ex = np.array([e[1] for e in edges])
    if len(edges) >= 2:
        k, c = np.polyfit(ey, ex, 1)
        # 上包络：把拟合线平移到覆盖所有行的最右值
        c += max(0, (ex - (k * ey + c)).max())
    else:
        k, c = 0.0, ex[0]
    keep = []
    for x, y in tiles:
        edge = k * y + c
        tile_w = 100 + (y - 140) * 0.06       # 越靠下格子越宽
        if x >= edge - 3 * tile_w:
            keep.append((x, y))
    return keep

def drag_path(x1, y1, x2, y2, steps=12):
    if MC is not None:
        MC.drag(x1, y1, x2, y2, steps)
        return
    if BACKEND == "pc":
        PCW.drag(x1, y1, x2, y2, steps)
        return
    cmds = [f"input motionevent MOVE {int(x1 + (x2 - x1) * k / steps)} {int(y1 + (y2 - y1) * k / steps)}"
            for k in range(1, steps + 1)]
    adb("shell", "; ".join(cmds))

def bench_ops(img):
    """备战席上的干员：在木板区找'干员'差分不可靠，改用固定扫描点"""
    return None

LAST_TIER = [1]
LAST_TILE = [None]
LAST_NAME = [""]

# 固定格子布局（拖拽视角坐标），由校准生成 tiles.json：
# {"safe": [[x,y],[x,y]], "path": [[x,y],...按优先顺序], "rest": [[x,y],...],
#  "probe_high": [[x,y],...], "probe_ground": [[x,y],...]}
LAYOUT = None


def load_layout():
    global LAYOUT
    for d in (HERE, os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(d, "tiles.json")
        if os.path.isfile(p):
            try:
                LAYOUT = json.load(open(p, encoding="utf-8"))
                return
            except Exception:
                pass


def is_green(img, pt, r=22):
    x, y = int(pt[0]), int(pt[1])
    hsv = cv2.cvtColor(img[y - r:y + r, x - r:x + r], cv2.COLOR_BGR2HSV)
    return cv2.inRange(hsv, (35, 100, 100), (85, 255, 255)).mean() / 255 > 0.8


def drag_name(img):
    """拖拽时左侧面板显示的干员名"""
    for _, _, t in ocr(img, (0, 262, 330, 322)):
        if any("\u4e00" <= ch <= "\u9fff" or ch.isalpha() for ch in t) and "LV" not in t.upper():
            return t.strip()
    return ""

def near(t, lst, d=95):
    return any(abs(t[0] - u[0]) <= d and abs(t[1] - u[1]) <= d for u in lst)

def deploy_from_bench(bench_xy, quiet=False, board=None, hi=False):
    if LAYOUT and board is not None:
        return deploy_layout(bench_xy, board, tier_hint=5 if hi else 0)
    return deploy_from_bench_old(bench_xy, quiet, board, hi)


def deploy_from_bench_old(bench_xy, quiet=False, board=None, hi=False):
    """按住备战席干员 -> 找最右3列的空格放下 -> 朝右。
    hi=True 且右3列已满时：直接拖到低星干员的格子上交换，换下来的干员卖掉"""
    bx, by = bench_xy
    before = shot()
    left0 = slots_left(before)
    used = board.used if board else []
    hi_tiles = board.hi_tiles if board else []
    for attempt in range(3):
        touch("DOWN", bx, by)
        drag_path(bx, by, bx, by - 180, 9)
        time.sleep(0.8)
        img = shot()
        LAST_TIER[0] = 5 if yellow_ratio(img, (20, 328, 58, 362)) > 0.08 else 1
        is_hi = hi or LAST_TIER[0] >= 5
        cand = right3(green_tiles(img), img)
        free = [t for t in cand if not near(t, used)]
        swap = False
        if free:
            tx, ty = free[min(attempt, len(free) - 1)]
        else:
            # 有干员的格子拖拽时不显示绿色，所以交换目标取自"自己放过低星干员的格子"记录
            targets = ([t for t in used if not near(t, hi_tiles)] +
                       [t for t in cand if not near(t, hi_tiles)]) if is_hi else []
            targets.sort(key=lambda p: -p[0])
            if not targets:
                touch("UP", bx, by - 180); time.sleep(0.8)
                if not quiet:
                    log("最右3列没有可用格"); save(img, "no_tiles")
                return None
            tx, ty = targets[0]
            swap = True
        drag_path(bx, by - 180, tx, ty, 10)
        touch("UP", tx, ty); time.sleep(1.0)
        im = shot()
        if find(ocr(im, (300, 0, 1700, 820)), "点击取消", "取消"):
            LAST_TILE[0] = (tx, ty)
            set_facing(tx, ty)   # 朝右
            after = shot()
            if not near((tx, ty), used):
                used.append((tx, ty))
            left1 = slots_left(after)
            swapped = left0 is not None and left1 is not None and left1 >= left0
            if swapped and not (swap or is_hi):
                log("该格已有干员（发生交换），标记为占用", (tx, ty))
                return None
            if swapped:
                # 换下来的低星干员回到备战席 -> 卖掉
                out = new_bench_slot(before, after) or (bx, by)
                swipe(out[0], out[1], *SELL, 900, 1.3)
                log("V/VI 替换低星干员", (tx, ty), "，已卖出换下的干员")
            if is_hi:
                hi_tiles.append((tx, ty))
            log("部署到", (tx, ty), "V/VI" if is_hi else "")
            LAST_TILE[0] = (tx, ty)
            return (tx, ty)
        log("放置失败，重试", (tx, ty))
    return None

def tile_order(name):
    """按干员类型给出格子优先顺序（格子名）"""
    safe = [f"safe{i}" for i in range(len(LAYOUT["safe"]))]
    path = [f"path{i}" for i in range(len(LAYOUT["path"]))]
    rest = [f"rest{i}" for i in range(len(LAYOUT.get("rest", [])))]
    return safe + path + rest if is_safe_op(name) else path + rest + safe


def tile_xy(tn):
    kind = tn.rstrip("0123456789")
    return tuple(LAYOUT[kind][int(tn[len(kind):])])


def deploy_layout(bench_xy, board, name_hint="", tier_hint=0, depth=0):
    """固定布局部署：安全位给维什戴尔/望/能天使/初雪，其余优先放敌人路径；
    位置不够时按权重把价值更低的干员换下来（低星卖掉，高星重新安排）"""
    bx, by = bench_xy
    lx, ly = LAYOUT.get("lift", [760, 650])     # 拿起后先移到不挡住目标格子的位置
    before = shot()
    left0 = slots_left(before)
    touch("DOWN", bx, by)
    drag_path(bx, by, bx, by - 120, 6)
    drag_path(bx, by - 120, lx, ly, 8)
    time.sleep(0.8)
    img = shot()
    all_pts = LAYOUT["safe"] + LAYOUT["path"] + LAYOUT.get("rest", [])
    tabs = [t for _, y, t in ocr(img, (0, 520, 700, 600)) if t.strip() in ("特质", "技能", "特性", "天赋")]
    picked = (len(tabs) >= 1 or bool(drag_name(img)) or bool(find(ocr(img, (0, 262, 330, 380)), "LV"))
              or any(is_green(img, p) for p in all_pts))
    if not picked:
        touch("UP", lx, ly); time.sleep(0.8)   # 在不可部署的岩石处松手 = 放回备战席
        return None          # 没拿起东西（空位）
    _nm = drag_name(img)
    if not any(t.strip() in ("特质", "天赋") for t in tabs) or (_nm and _nm[0] in "“\"「『"):
        touch("UP", lx, ly); time.sleep(0.8)
        log("拿起的是装备，放回:", drag_name(img) or "?")
        return None          # 装备（拖拽时会把有干员的格子标绿，不能当干员处理）
    name = drag_name(img) or name_hint
    tier = 5 if yellow_ratio(img, (20, 328, 58, 362)) > 0.08 else 1
    if prio_index(name) is not None:
        tier = max(tier, 5)          # 优先干员都是 Ⅴ/Ⅵ 阶，永不当作低星卖掉
    if depth >= 1 and tier < 5:
        # 换下来的其实是低星干员：直接卖掉
        drag_path(lx, ly, *SELL, 10); touch("UP", *SELL); time.sleep(1.0)
        log("换下的是低星干员，卖掉:", name or "?")
        return None
    tier = max(tier, tier_hint if depth == 0 else 0)
    my = rank(name, tier)
    order = tile_order(name)
    ranged = False      # 本图近战/远程可部署格相同

    def occupant(tn):
        """格子上的干员 (名, 等阶)；空格返回 None。没有记录但不是绿色 -> 视为未知低星干员"""
        if tn in board.occ:
            return board.occ[tn][:2]
        return None if is_green(img, tile_xy(tn)) else ("?", 5)   # 未知干员按普通 V 处理，避免误卖高星

    def value(tn, occ):
        r = rank(occ[0], occ[1])
        if tn.startswith("safe") and is_safe_op(name) and not is_safe_op(occ[0]):
            r -= 2000            # 安全位被非安全干员占着时，安全干员优先换下它
        return r

    safe = [t for t in order if t.startswith("safe")]
    other = [t for t in order if not t.startswith("safe")]
    # 安全干员：安全位(空)→安全位(换)→路径(空)→路径(换)；其他干员：路径(空)→路径(换)→安全位(空)→安全位(换)
    groups = [safe, other] if is_safe_op(name) else [other, safe]
    target, swap_out = None, None
    for grp in groups:
        occs = {tn: occupant(tn) for tn in grp}
        free = [tn for tn in grp if occs[tn] is None]
        if free:
            target = free[0]
            break
        # 只换下已知的低星（Ⅰ~Ⅳ）干员；场上的 Ⅴ/Ⅵ 干员（含未知占位者）一律不换
        cands = sorted((value(tn, occs[tn]), grp.index(tn), tn) for tn in grp
                       if occs[tn][1] < 5 and occs[tn][0] != "?" and value(tn, occs[tn]) < my)
        if cands:
            target = cands[0][2]
            swap_out = occs[target]
            break
    if target is None:
        touch("UP", lx, ly); time.sleep(0.8)   # 在不可部署的岩石处松手 = 放回备战席
        log("没有可用位置，留在备战席:", name or "?")
        return None
    tx, ty = tile_xy(target)
    drag_path(lx, ly, tx, ty, 10)
    touch("UP", tx, ty); time.sleep(1.0)
    if not find(ocr(shot(), (300, 0, 1700, 820)), "点击取消", "取消"):
        log("放置失败", name, target)
        return None
    LAST_TILE[0] = (tx, ty)
    set_facing(tx, ty)           # 朝右
    after = shot()
    board.occ[target] = (name, tier, ranged)
    left1 = slots_left(after)
    if not swap_out and left0 is not None and left1 is not None and left1 >= left0:
        # 意外交换：目标格其实有人（未记录的干员）。把换下来的干员重新安排
        log("意外交换：", target, "上原本有干员，重新安排被换下的干员")
        swap_out = ("?", 5)
    log("部署", name or "?", f"T{tier}", "->", target,
        f"（换下 {swap_out[0]}）" if swap_out else "")
    if swap_out:
        board.pending = True      # 回合结束前再扫一遍备战席，确保换下的高星干员重新上场
        out = new_bench_slot(before, after)
        if out:
            if swap_out[1] < 5:
                ok = sell_at(*out)
                log("卖掉换下的干员", swap_out[0], "成功" if ok else "（未确认）")
            elif depth == 0:
                deploy_layout(out, board, swap_out[0], swap_out[1], depth + 1)
            # depth>=1 时换下的高星干员留在备战席，回合末再扫一次
    LAST_TIER[0], LAST_NAME[0], LAST_TILE[0] = tier, name, (tx, ty)
    return (tx, ty)


def sell_at(x, y):
    """把 (x, y) 处的备战席干员拖到右下角出售区（慢速拖拽），返回是否卖出（资金增加）"""
    g0 = numrec(shot(), GOLD_BOX)
    touch("DOWN", x, y)
    drag_path(x, y, x, y - 120, 6)
    drag_path(x, y - 120, SELL[0], SELL[1], 10)
    time.sleep(0.4)
    touch("UP", SELL[0], SELL[1]); time.sleep(1.0)
    g1 = numrec(shot(), GOLD_BOX)
    return g0 is not None and g1 is not None and g1 > g0

def in_facing_mode(img=None):
    """是否停在「选择朝向」界面（出现「点击取消」）"""
    return bool(find(ocr(img if img is not None else shot(), (300, 0, 1700, 820)), "点击取消"))


def set_facing(tx, ty, tries=3):
    """慢速拖拽设置朝向（朝右），确认「点击取消」消失；失败则加长距离重试"""
    for k in range(tries):
        dist = 300 + 60 * k
        touch("DOWN", tx, ty)
        drag_path(tx, ty, tx + dist, ty, 10)
        time.sleep(0.3)
        touch("UP", tx + dist, ty)
        time.sleep(1.2)
        if not in_facing_mode():
            return True
        log("设置朝向未生效，重试", (tx, ty))
    save(shot(), "facing_failed")
    log("设置朝向多次失败，截图已保存")
    return False


def slots_left(img):
    """剩余可放置角色数"""
    n = numrec(img, (1862, 566, 1897, 607))
    return n % 10 if n is not None else None   # 最多 8，只取个位

def locate_new(before, after):
    d = cv2.absdiff(before[100:560, 300:1700], after[100:560, 300:1700])
    g = cv2.cvtColor(d, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(g, 40, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    k = 1 + int(np.argmax(st[1:, 4]))
    return int(cen[k][0]) + 300, int(cen[k][1]) + 100

def new_bench_slot(before, after):
    """找出刚出现在备战席（木板区）的干员位置"""
    d = cv2.absdiff(before[560:770, 200:1500], after[560:770, 200:1500])
    g = cv2.cvtColor(d, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(g, 40, 255, cv2.THRESH_BINARY)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    if n <= 1:
        return None
    k = 1 + int(np.argmax(st[1:, 4]))
    return int(cen[k][0]) + 200, int(cen[k][1]) + 560

def sell_lowest(board):
    low = [o for o in board.ops if o[2] < 5]
    if not low:
        return False
    o = min(low, key=lambda o: o[2])
    n0 = slots_left(shot())
    swipe(o[0], o[1], *SELL, 900, 1.3)
    n1 = slots_left(shot())
    if n0 is not None and n1 is not None and n1 <= n0:
        log("卖出可能失败（可放置数未增加）", o[:3])
    board.ops.remove(o)
    if o[3] in board.used:
        board.used.remove(o[3])
    log("卖掉低星干员", o[:3])
    return True

def buy_and_deploy(board, i, tier, cost=None):
    before = shot()
    if not buy(i, cost):
        return False
    after = shot()
    slot = new_bench_slot(before, after)
    if not slot:
        log("没找到新买的干员（可能合成晋升了）")
        handle_popups()
        board.pending = True
        return True
    pos = deploy_from_bench(slot, board=board, hi=tier >= 5)
    if pos:
        board.ops.append((pos[0], pos[1], max(tier, LAST_TIER[0]), LAST_TILE[0]))
    else:
        board.pending = True
    return True

BENCH_ROWS = [[(x, 700) for x in (1390, 1300, 1210, 1120, 1030, 940)],
              [(x, 600) for x in (1260, 1150, 1040, 930, 820)]]

def deploy_bench(board):
    """把备战席上剩下的干员部署（朝右、尽量靠右）。每行从右往左，连续2个空位就停"""
    for _ in range(6):
        placed = False
        for row in BENCH_ROWS:
            empty = 0
            for xy in row:
                pos = deploy_from_bench(xy, quiet=True, board=board)
                if pos:
                    board.ops.append((pos[0], pos[1], LAST_TIER[0], LAST_TILE[0]))
                    placed = True
                    break
                empty += 1
                if empty >= 2:
                    break
            if placed:
                break
        if not placed:
            break

def handle_popups():
    img = shot()
    items = ocr(img)
    if find(items, "确认准备", "资金将在"):
        tap(860, 602, 0.5); tap(1410, 728, 1.5)
        return True
    return False

def read_gold(img=None, tries=3):
    """读取资金。失败时换新截图重试，并用更宽的识别框兜底；仍失败返回 None（表示"未知"，不是 0）"""
    for k in range(tries):
        im = img if (k == 0 and img is not None) else shot()
        g = numrec(im, GOLD_BOX)
        if g is None:
            g = num(im, (1760, 760, 1880, 825))
        if g is not None and 0 <= g <= 99:
            return g
        time.sleep(0.4)
    return None


GOLD_FAIL = [0]


def gold_now():
    g = read_gold()
    if g is None:
        GOLD_FAIL[0] += 1
        if GOLD_FAIL[0] <= 3:
            save(shot(), "gold_unreadable")
        log("警告：资金数字读取失败，按「未知」处理继续尝试（截图已保存到 farm_logs）")
    return g


def shop_signature(cards):
    return tuple((c["name"], c["cost"]) for c in cards)

def prep_phase(board, img):
    gold, up_cost, maxed, rnd = read_shop(img)
    if rnd is None:
        if board.prep_done:
            return
        rnd = max(1, board.round_done + 1)
    if rnd == board.round_done:
        return
    t0 = time.time()
    log(f"回合{rnd} 资金{gold} 升级费用{up_cost} 满级{maxed}")
    save(img, f"shop_r{rnd}")
    if board.round_done < 0 and rnd == 1:
        # 第一回合：买2个干员（不买装备）
        bought = 0
        for c in shop_cards(img):
            g = gold_now()
            if bought >= 2:
                break
            if c["op"] and c["cost"] is not None and (g is None or c["cost"] <= g):
                if is_healer(c["name"]) and board.healers >= 1:
                    log("跳过第二个医疗干员:", c["name"])
                    continue
                if buy_and_deploy(board, c["i"], 5 if c["hi"] else 1, c["cost"]):
                    bought += 1
                    board.healers += is_healer(c["name"])
    if not maxed:
        # 能升级就升级
        for _ in range(4):
            img = shot()
            gold, up_cost, maxed, _ = read_shop(img)
            if maxed or (gold is not None and up_cost is not None and gold < up_cost):
                break
            ux0 = UPX
            tap(UPX, 920, 0.6); tap(UPX, 920, 1.0)
            g2, c2, maxed, _ = read_shop(shot())
            # 升级成功的判断：资金减少 / 升级费用变化（0 费升级时资金不变）/ 按钮位置变化 / 满级
            ok = maxed or UPX != ux0 or (gold is not None and g2 is not None and g2 < gold) or                 (up_cost is not None and c2 is not None and c2 != up_cost)
            if not ok:
                break
            log("商店升级，资金", gold, "->", g2, "，升级费用", up_cost, "->", "满级" if maxed else c2)
        if not maxed:
            # 剩余资金买干员（资金不跨回合，不买装备）
            for c in shop_cards(shot()):
                im = shot()
                g = read_gold(im)
                sl = slots_left(im)
                if g == 0 or sl == 0:
                    log("停止购买：", "资金为 0" if g == 0 else "部署位已满")
                    break
                if g is None:
                    log("警告：资金读取失败，仍尝试购买（买不起时游戏会提示）")
                if c["op"] and c["cost"] is not None and (g is None or c["cost"] <= g):
                    if is_healer(c["name"]) and board.healers >= 1:
                        log("跳过第二个医疗干员:", c["name"])
                        continue
                    if buy_and_deploy(board, c["i"], 5 if c["hi"] else 1, c["cost"]):
                        board.healers += is_healer(c["name"])
    if maxed:
        # 只买 V/VI 干员，没有就刷新
        refreshes, same_count, last_sig = 0, 0, None
        for _ in range(40):
            img = shot()
            gold = read_gold(img)
            got = False
            allc = shop_cards(img)
            sig = shop_signature(allc)
            if last_sig is not None:
                if sig == last_sig:
                    same_count += 1
                    if same_count >= 2:
                        save(img, "refresh_no_effect")
                        log("停止刷新：连续刷新后商店没有变化（可能资金不足或刷新按钮没点到），截图已保存")
                        break
                else:
                    same_count = 0
            last_sig = sig
            if gold is None:
                GOLD_FAIL[0] += 1
                if GOLD_FAIL[0] <= 3:
                    save(img, "gold_unreadable")
                log("警告：资金数字读取失败，按「未知」处理（尝试购买和刷新，由游戏提示判断是否买得起）")
            gold_v = 99 if gold is None else gold
            free = [c for c in allc if c["op"] and c["cost"] == 0]   # 晋升后的免费干员
            cards = [c for c in allc
                     if c["hi"] and c["op"] and c["cost"] is not None and c["cost"] <= gold_v]
            def owned(c):
                return any(n and (n in c["name"] or c["name"] in n) for n in board.owned)
            # 优先级：免费 > 已拥有的（凑晋升）> 输出型 > 买不起4费时的非输出
            prio = sorted([c for c in cards if prio_index(c["name"]) is not None],
                          key=lambda c: prio_index(c["name"]))
            if free:
                pick = sorted(free, key=lambda c: -rank(c["name"], 5 if c["hi"] else 1))[:1]
            else:
                # 优先干员（按权重）> 已拥有（凑晋升）> 输出 > 买不起4费时的非输出
                pick = (prio or [c for c in cards if owned(c)] or [c for c in cards if c["dps"]]
                        or (cards if gold is not None and gold - 1 < 4 else []))
            failed = False
            for c in pick:
                tag = "优先" if prio_index(c["name"]) is not None else ("输出" if c["dps"] else "非输出")
                log("购买 V/VI:", c["name"], tag, f"费用{c['cost']}")
                if buy_and_deploy(board, c["i"], 5 if c["hi"] else 1, c["cost"]):
                    board.owned[c["name"]] = board.owned.get(c["name"], 0) + 1
                    got = True
                else:
                    failed = True   # 购买失败（资金不足/识别错误），结束本回合购买，避免死循环
                break
            if failed:
                log("购买失败，结束本回合购买")
                break
            if got:
                last_sig = None
                continue
            if gold is not None and gold < 4:
                log(f"停止刷新：资金 {gold} 不足 4（本回合刷新 {refreshes} 次）")
                break
            refreshes += 1
            hi_n = sum(1 for c in allc if c["hi"] and c["op"])
            log(f"刷新商店（第 {refreshes} 次）：资金 {gold if gold is not None else '未知'}，"
                f"当前 5/6 级干员 {hi_n} 张，可买 {len(cards)} 张")
            tap(*REFRESH, 1.0)
    if board.pending:
        deploy_bench(board)
        board.pending = False
    board.round_done = rnd
    board.prep_done = True
    time.sleep(1.5)            # 等"资金不足"等提示消失，避免挡住准备按钮
    tap(*READY, 1.5)
    board.last_ready = time.time()
    handle_popups()
    log(f"回合{rnd} 准备耗时 {time.time() - t0:.0f}s")

# ---------------- 主循环 ----------------
GENERIC = ["点击任意", "继续", "返回", "确认", "确定", "领取", "下一步", "完成"]
# 出现这些文字说明仍在卫戍协议内
GARRISON = ["极速模拟", "卫戍", "STRONGHOLD", "同盟模拟", "个人模拟", "确认准备", "资金将在", "选择策略", "确认本局信息",
            "确定自选编队", "返回主页", "模拟完成", "模拟中断", "COUNTDOWN", "断线重连", "放弃模拟"]
ERRS = [0]
LEAVE_TIMEOUT = 30   # 连续这么多秒看不到卫戍协议界面就停止
STALL_TIMEOUT = 600  # 这么多秒没有任何进展（回合推进/结算/选策略）就判定卡死并停止

def main():
    global DEV
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20, help="目标通关局数")
    ap.add_argument("--attempts", type=int, default=0, help="总局数上限（成功失败都算），0=不限")
    ap.add_argument("--maa", default="", help="MAA 目录（默认自动查找）")
    ap.add_argument("--adb", default="", help="覆盖 MAA 配置中的 adb 路径")
    ap.add_argument("--address", default="", help="覆盖 MAA 配置中的连接地址")
    ap.add_argument("--check", action="store_true", help="只检查 MAA/设备/OCR 是否正常，然后退出")
    ap.add_argument("--yes", action="store_true", help="跳过启动时的优先干员提醒")
    ap.add_argument("--no-maa", action="store_true", help="（测试用）不使用 MAA，直接使用内置 adb 与文字识别模型")
    ap.add_argument("--show-doc", default="", help="启动时显示该文件中以 :: 开头的说明文字（用于 bat）")
    ap.add_argument("--profile", choices=["full", "low"], default="", help="full=标准（自选编队），low=低配（只用预设干员）")
    ap.add_argument("--target", type=int, choices=[3, 6], default=0, help="3=金色角标，6=彩色角标")
    ap.add_argument("--menu", action="store_true", help="启动时显示模式选择菜单")
    ap.add_argument("--no-maafw", action="store_true", help="不使用 MaaFramework，改用内置的 adb 命令 / PC 控制")
    ap.add_argument("--device", choices=["emulator", "pc"], default="", help="emulator=模拟器（adb），pc=明日方舟 PC 端")
    ap.add_argument("--pc-screencap", default="", help="PC 端截图方式：PrintWindow / ScreenDC（默认读取 MAA 设置）")
    ap.add_argument("--pc-mouse", default="", help="PC 端鼠标方式：AnchoredTouch / PostMessageWithWindowPos / PostMessageWithCursorPos（默认读取 MAA 设置）")
    a = ap.parse_args()
    if a.show_doc:
        try:
            for line in open(a.show_doc, encoding="utf-8").read().splitlines():
                if line.startswith("::"):
                    print(line[3:] if len(line) > 2 else "")
            print()
        except Exception as e:
            print("（说明文字读取失败：", e, "）")
    if a.menu and not a.device:
        print("请选择设备（输入数字后按回车）：")
        print("  1. 安卓模拟器（MuMu 等，通过 adb）")
        print("  2. 明日方舟 PC 端（需要管理员权限，运行时会移动鼠标）")
        dch = ""
        while dch not in ("1", "2"):
            try:
                dch = input("请输入 1 或 2：").strip()
            except EOFError:
                dch = "1"
        a.device = "pc" if dch == "2" else "emulator"
    if a.menu and a.device == "pc" and not a.pc_mouse:
        print("请选择 PC 端鼠标操作方式（直接回车 = 使用 MAA 里的设置）：")
        print("  1. AnchoredTouch      全后台，不抢鼠标，合成触控注入；需 Win10 1809+，窗口被遮挡时可能短暂闪烁")
        print("  2. PostMsg-WindowPos  全后台，不抢鼠标；操作时会移动游戏窗口（窗口会乱飞），截图仅 PrintWindow，建议最小化其他窗口")
        print("  3. PostMsg-CursorPos  半后台，操作时会短暂移动你的鼠标")
        mch = None
        while mch not in ("", "1", "2", "3"):
            try:
                mch = input("请输入 1~3 或直接回车：").strip()
            except EOFError:
                mch = ""
        a.pc_mouse = {"1": "AnchoredTouch", "2": "PostMessageWithWindowPos", "3": "PostMessageWithCursorPos"}.get(mch, "")
    if a.menu and not (a.profile and a.target):
        print("请选择运行模式（输入数字后按回车）：")
        print("  1. 标准模式 · 刷金色角标（每个策略通关 3 次）   需要配置自选编队")
        print("  2. 标准模式 · 刷彩色角标（每个策略通关 6 次）   需要配置自选编队")
        print("  3. 低配模式 · 刷金色角标（每个策略通关 3 次）   不需要自选编队")
        print("  4. 低配模式 · 刷彩色角标（每个策略通关 6 次）   不需要自选编队")
        choice = ""
        while choice not in ("1", "2", "3", "4"):
            try:
                choice = input("请输入 1~4：").strip()
            except EOFError:
                choice = "1"
        a.profile = a.profile or ("full" if choice in ("1", "2") else "low")
        a.target = a.target or (3 if choice in ("1", "3") else 6)
    set_profile(a.profile or "full")
    global TARGET
    TARGET = a.target or 3
    print(f"运行模式：{'低配模式' if PROFILE == 'low' else '标准模式'} · "
          f"{'彩色角标（通关 6 次）' if TARGET == 6 else '金色角标（通关 3 次）'}", flush=True)
    if a.device == "pc":
        if not is_admin():
            # 把已选的模式带到管理员进程里，免得再选一次
            extra = ["--device", "pc", "--profile", PROFILE, "--target", str(TARGET)]
            if a.pc_mouse:
                extra += ["--pc-mouse", a.pc_mouse]
            sys.argv = [x for x in sys.argv if x != "--menu"] + extra
            relaunch_as_admin()
        setup_pc(a)
    else:
        setup(a)
    if a.check:
        t = time.time()
        txt = "".join(t_ for _, _, t_ in ocr(shot()))
        print(f"OCR 正常（{time.time() - t:.1f}s）：{txt[:60]}")
        return
    load_layout()
    log("格子布局:", "已加载 tiles.json（安全位/敌人路径）" if LAYOUT else "未找到 tiles.json，使用最右3列自动识别")
    names = "、".join(n for _, n in PRIORITY)
    safe = "、".join(n for k, n in PRIORITY if any(match_key(n, sk) for sk in SAFE_KEYS))
    head = (f"当前模式：{'低配模式' if PROFILE == 'low' else '标准模式'} · "
            f"{'刷彩色角标（同一策略通关 6 次）' if TARGET == 6 else '刷金色角标（同一策略通关 3 次）'}" + chr(10) + chr(10))
    if PROFILE == "low":
        tail = ("低配模式不需要配置自选编队（为空即可），只使用游戏预设干员。" + chr(10) +
                "建议在「选配助战」里为自己没有的上述干员借用助战（最多 30 名），胜率更高；不借用也能运行。")
    else:
        tail = "请确认游戏「自选编队」中已配置推荐干员（每局开局会自动从中选 Ⅴ、Ⅵ 阶各 2 名）。"
    remind = (head + "本程序会优先购买以下干员（按权重从高到低）：" + chr(10) + names + chr(10) +
              safe + " 优先放在两个安全位，其余干员优先放在敌人路径上。" + chr(10) + tail)
    log(remind.replace(chr(10), " "))
    if not a.yes and os.name == "nt":
        try:
            import ctypes
            if ctypes.windll.user32.MessageBoxW(None, remind + chr(10) + chr(10) + "点击「确定」开始运行。",
                                                "GarrisonFarm 使用前提醒", 0x41 | 0x1000 | 0x10000 | 0x40000) != 1:
                log("用户取消运行")
                return
        except Exception:
            pass
    # 启动检查：必须处于带有"极速模拟"的卫戍协议界面
    ok_start = False
    for _ in range(3):
        _items = ocr(shot())
        _t = "".join(t for _, _, t in _items)
        if ("同盟模拟" in _t or "搜寻队友" in _t) and "个人模拟" in _t:
            hit = find(_items, "个人模拟")          # 停在「联合模拟」页：切换到「个人模拟」
            tap(hit[0], hit[1], 2.5)
            continue
        if "极速模拟" in _t or "断线重连" in _t:
            ok_start = True
            break
        time.sleep(2)
    if not ok_start:
        msg = ("【提示】当前不是卫戍协议的极速模拟界面，程序已停止。" + chr(10) +
               "请先在游戏中进入「卫戍协议」主界面（能看到“极速模拟”按钮），"
               "或「请选择模拟难度」界面，或已在进行中的极速模拟对局，然后重新运行。")
        log(msg.replace(chr(10), " "))
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(None, msg, "GarrisonFarm", 0x30 | 0x1000 | 0x10000 | 0x40000)
            except Exception:
                pass
        return
    done = load_done()
    board = Board()
    last_seen = time.time()
    last_progress = time.time()
    last_round = None
    runs = 0
    attempts = 0
    results = []
    current = None
    idle = 0
    run_t0 = time.time()
    while runs < a.runs:
        img = shot()
        items = ocr(img)
        txt = "".join(t for _, _, t in items)
        if time.time() - last_progress > STALL_TIMEOUT:
            save(img, "stalled")
            log(f"已有 {STALL_TIMEOUT // 60} 分钟没有进展，判定为卡死，停止运行。")
            break
        if any(k in txt.upper() for k in GARRISON):
            last_seen = time.time()
        elif time.time() - last_seen > LEAVE_TIMEOUT:
            save(img, "left_garrison")
            log(f"已有 {LEAVE_TIMEOUT} 秒检测不到卫戍协议界面，立即停止。")
            break
        if "点击取消" in txt and "准备就绪" in txt:
            # 停在选择朝向界面（朝向拖拽没生效）：按上次部署的格子补设朝向
            t = LAST_TILE[0]
            log("检测到停在选择朝向界面，自动补设朝向", t)
            if t:
                set_facing(*t)
            else:
                hit = find(items, "点击取消")
                tap(hit[0], hit[1], 1.0)
            continue
        if "返回主页" in txt:
            save(img, "result")
            ok = "模拟完成" in txt
            if True:
                if ok and current:
                    done.add(current); save_done(done)
                if ok:
                    runs += 1
                attempts += 1
                results.append((current, ok, int(time.time() - run_t0)))
                log(f"本局{'通关' if ok else '失败'}，策略 {current}，用时 {int(time.time() - run_t0)}s，"
                    f"已通关 {runs}/{a.runs}，已打 {attempts} 局")
                current = None
            last_progress = time.time()
            hit = find(items, "返回主页")
            tap(hit[0], hit[1], 4)
            board = Board()
            if runs >= a.runs or (a.attempts and attempts >= a.attempts):
                break
        elif "请选择模拟难度" in txt or ("开始模拟" in txt and "极速模拟" in txt and "回合" not in txt):
            hit = find(items, "开始模拟")
            tap(*(hit[:2] if hit else (1700, 986)), 3)
            board = Board()
        elif "确认准备" in txt or "资金将在" in txt:
            tap(860, 602, 0.5)     # 本局不再提示
            tap(1410, 728, 2)      # 确认
        elif "断线重连" in txt:
            hit = find(items, "断线重连")
            log("检测到未完成的对局，断线重连")
            tap(*(hit[:2] if hit else (1660, 970)), 5)
            board = Board()
        elif ("同盟模拟" in txt or "搜寻队友" in txt) and "个人模拟" in txt:
            hit = find(items, "个人模拟")
            log("卫戍协议主界面在「联合模拟」页，切换到「个人模拟」")
            tap(hit[0], hit[1], 2.5)
        elif "独立模拟" in txt and "极速模拟" in txt:
            hit = find(items, "极速模拟")
            tap(*(hit[:2] if hit else (1280, 1000)), 3)
        elif "确认本局信息" in txt:
            tap(1686, 986, 3)
        elif "选择策略" in txt:
            run_t0 = time.time()
            last_progress = time.time()
            current = pick_strategy(done)
            save_done(done)
            if current is None:
                break
            tap(1680, 990, 3)
        elif "确定自选编队" in txt:
            pick_squad()
        elif "回合" in txt and "准备就绪" in txt and ("刷新" in txt or "升级" in txt or "满级" in txt):
            try:
                prep_phase(board, img)
            except Exception:
                import traceback
                ERRS[0] += 1
                log("休整期处理出错（已记录，继续运行）:", traceback.format_exc().strip().splitlines()[-1])
                save(shot(), "error")
                if ERRS[0] >= 20:
                    log("出错次数过多，停止运行。")
                    break
            if board.prep_done and time.time() - board.last_ready > 10:
                # 已处理过本回合但仍停在休整期：准备按钮可能被提示挡住，重新点击
                log("仍在休整期，重新点击准备就绪")
                tap(*READY, 1.5)
                handle_popups()
                board.last_ready = time.time()
            if board.round_done != last_round:
                last_round = board.round_done
                last_progress = time.time()
            idle = 0
            continue
        elif "回合" in txt or ("查看" in txt and "极速模拟" in txt) or "COUNTDOWN" in txt.upper():
            board.prep_done = False
            time.sleep(4)   # 战斗中（含领袖回合）
            idle = 0
            continue
        else:
            # 只在仍处于卫戍协议界面时才做通用点击，不在界面外乱点
            hit = find(items, *GENERIC) if any(k in txt.upper() for k in GARRISON) else None
            if hit:
                log("通用点击:", hit[2]); tap(hit[0], hit[1], 2)
                idle = 0
            else:
                idle += 1
                if idle % 5 == 0:
                    save(img, "unknown")
                time.sleep(2)
            continue
        time.sleep(1)
    log("结束。本次结果:", results)
    log("已获得角标的策略:", sorted(done))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("已手动停止")
    except SystemExit as e:
        if e.code not in (None, 0):
            print(e.code)
    except Exception:
        import traceback; traceback.print_exc()
    restore_window()
    if getattr(sys, "frozen", False):
        try:
            input("按回车键退出…")
        except Exception:
            pass
