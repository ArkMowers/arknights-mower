import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
import sys
import threading
from queue import Queue, Empty
import time


class OverlayWindow:
    def __init__(self):
        self.root = None
        self.is_running = False
        self.command_queue = Queue()
        self.after_id = None
        self.geometry_x = 0
        self.geometry_y = 0

    def _run_tkinter_loop(self):
        """运行在Tkinter线程中的主循环"""
        self.root = tk.Tk()
        try:
            if sys.platform == "win32":
                from ctypes import windll

                windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

        self.root.withdraw()  # 初始隐藏窗口
        self._process_commands()
        self.root.mainloop()

    def _process_commands(self):
        """处理命令队列"""
        try:
            while True:
                command, *args = self.command_queue.get_nowait()
                if command == "create":
                    self._create_window(*args)
                elif command == "update":
                    self._update_window(*args)
                elif command == "close":
                    self._close_window()
                elif command == "exit":
                    self._exit()
                    return
        except Empty:
            pass

        if self.root:
            self.root.after(100, self._process_commands)

    def _create_window(self, task_type, task_time, remarks):
        """创建窗口"""
        if self.root is None:
            self.root = tk.Tk()
            self.root.withdraw()

        self.is_running = True
        self.task_type = task_type
        self.task_time = task_time
        self.remarks = remarks

        # 显示窗口
        self.root.deiconify()
        self.root.overrideredirect(True)
        ScaleFactor = 1
        if sys.platform == "win32":
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
            ScaleFactor = windll.shcore.GetScaleFactorForDevice(0) / 100
        self.root.tk.call("tk", "scaling", ScaleFactor)

        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.85)

        # 设置窗口大小和位置
        window_width = int(400 * ScaleFactor)
        window_height = int(30 * ScaleFactor)
        screen_width = self.root.winfo_screenwidth() * ScaleFactor
        screen_height = self.root.winfo_screenheight() * ScaleFactor
        self.geometry_x = int(screen_width - window_width) // 2
        self.geometry_y = int(screen_height - window_height - 10)
        self.root.geometry(
            f"{window_width}x{window_height}+{self.geometry_x}+{self.geometry_y}"
        )

        # 设置窗口背景色
        self.root.configure(bg="lightgreen")

        # 清除之前的组件（如果有的话）
        for widget in self.root.winfo_children():
            widget.destroy()

        # 主标签文本，包含任务类型
        self.remaining_label = ttk.Label(
            self.root,
            text=f"{self.task_type}{task_time.strftime('%H:%M:%S')}启动,剩余00:00:00",
            background="lightgreen",
            font=("Microsoft YaHei", 22, "bold"),
        )
        self.remaining_label.place(relwidth=1, height=30 * ScaleFactor, y=0)

        # 备注标签文本
        self.remark_label = ttk.Label(
            self.root,
            text=remarks if remarks else "",
            background="lightgreen",
            font=("Microsoft YaHei", 18, "bold"),
            foreground="blue",
        )
        self.remark_label.place(
            relx=1.0, x=-30 * ScaleFactor, height=30 * ScaleFactor, anchor="ne"
        )

        close_btn = tk.Button(
            self.root,
            text="×",
            command=self._request_close,
            font=("Arial", 16, "bold"),
            width=2,
            height=1,
            bd=1,
            bg="lightcoral",
            fg="white",
            activebackground="red",
        )
        close_btn.place(
            relx=0.93,
            y=5 * ScaleFactor,
            width=20 * ScaleFactor,
            height=20 * ScaleFactor,
        )

        # 添加拖动功能
        self.root.bind("<Button-1>", self.start_move)
        self.root.bind("<B1-Motion>", self.do_move)

        if sys.platform == "win32":
            try:
                from ctypes import windll
                # 获取窗口句柄
                hwnd = windll.user32.GetParent(self.root.winfo_id())
                # 设置窗口扩展样式，添加WS_EX_NOACTIVATE和WS_EX_APPWINDOW标志
                # 0x8000000 = WS_EX_NOACTIVATE, 0x40000 = WS_EX_APPWINDOW
                ex_style = windll.user32.GetWindowLongPtrW(hwnd, -20)
                windll.user32.SetWindowLongPtrW(hwnd, -20, ex_style | 0x8000000 | 0x40000)
            except:
                pass
        # 开始更新剩余时间
        self._update_remaining_time()

    def _update_window(self, task_type, task_time, remarks):
        """更新窗口"""
        if self.is_running:
            self.task_type = task_type
            self.task_time = task_time
            if remarks != "":
                self.remarks = remarks 

    def _update_remaining_time(self):
        """更新剩余时间显示"""
        if not self.is_running:
            return

        if hasattr(self, "remaining_label") and self.remaining_label and self.task_time:
            now = datetime.now()
            if self.task_time > now:
                remaining = self.task_time - now
                days = remaining.days
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)

                if remaining.total_seconds() > 0:
                    hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                    minutes, seconds = divmod(remainder, 60)
                    remaining_text = f"{self.task_type}{self.task_time.strftime('%H:%M:%S')}启动,剩余{hours:01d}:{minutes:02d}:{seconds:02d}"
                else:
                    remaining_text = "运行中。。。"
            else:
                remaining_text = "运行中。。。"

            self.remaining_label.config(text=remaining_text)
            self.remark_label.config(text=self.remarks if self.remarks else "")

        # 每秒更新一次
        if self.is_running and self.root:
            self.root.lift()
            self.after_id = self.root.after(1000, self._update_remaining_time)

    def start_move(self, event):
        """开始移动窗口"""
        self.x = event.x
        self.y = event.y

    def do_move(self, event):
        """移动窗口"""
        deltax = event.x - self.x
        deltay = event.y - self.y
        self.geometry_x = self.root.winfo_x() + deltax
        self.geometry_y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{self.geometry_x}+{self.geometry_y}")

    def _close_window(self):
        """关闭窗口"""
        if not self.is_running:
            return

        # self.is_running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None

        if self.root:
            self.root.geometry("+10000+10000")  # 移动到屏幕外面

    def _exit(self):
        """退出应用"""
        self.is_running = False
        if self.after_id:
            self.root.after_cancel(self.after_id)
        if self.root:
            try:
                self.root.quit()
            except:
                pass
            try:
                self.root.destroy()
            except:
                pass
        self.root = None  # 重置root引用

    def _request_close(self):
        """请求关闭窗口"""
        self.command_queue.put(("close",))


# 全局单例
_overlay = None
_tkinter_thread = None


def _get_overlay():
    global _overlay
    if _overlay is None:
        _overlay = OverlayWindow()
    return _overlay


def _ensure_tkinter_thread():
    """确保Tkinter线程正在运行"""
    global _tkinter_thread

    if _tkinter_thread is None or not _tkinter_thread.is_alive():
        overlay = _get_overlay()
        _tkinter_thread = threading.Thread(
            target=overlay._run_tkinter_loop, daemon=True
        )
        _tkinter_thread.start()
        # 等待线程初始化
        time.sleep(0.1)


def show_task_window(task_type, task_time, remarks=""):
    """
    显示任务悬浮窗（非阻塞）

    :param task_type: 任务类型
    :param task_time: 任务时间 (datetime对象)
    :param remarks: 备注信息
    """
    _ensure_tkinter_thread()
    overlay = _get_overlay()
    overlay.command_queue.put(("create", task_type, task_time, remarks))


def close_task_window():
    """关闭任务悬浮窗"""
    if _overlay is not None:
        _overlay.command_queue.put(("close",))


def update_task_window(task_type, task_time, remarks=""):
    """
    更新任务悬浮窗

    :param task_type: 任务类型
    :param task_time: 任务时间 (datetime对象)
    :param remarks: 备注信息
    """
    if task_type in ["下班", "上班", "用尽下班"]:
        task_type = "换班"
    elif task_type == "肥鸭":
        task_type = "菲亚"
    elif task_type != "跑单":
        task_type = ""
    if _overlay is not None:
        _overlay.command_queue.put(("update", task_type, task_time, remarks))


def is_task_window_open():
    """检查任务悬浮窗是否打开"""
    if _overlay is not None:
        return _overlay.is_running
    return False


def exit_overlay():
    """完全退出悬浮窗系统"""
    if _overlay is not None:
        _overlay.command_queue.put(("exit",))


# 使用示例
if __name__ == "__main__":
    print("悬浮窗程序使用示例:")
    print("=" * 50)

    # 1. 显示悬浮窗
    print("1. 显示悬浮窗")
    show_task_window("跑单", datetime.now() - timedelta(minutes=30), "yk")
    print("   悬浮窗已显示")

    # 等待2秒
    time.sleep(5)

    # 2. 更新悬浮窗内容
    print("2. 更新悬浮窗")
    show_task_window("肥鸭", datetime.now() + timedelta(hours=2), "理智")
    print("   悬浮窗已更新")

    # 等待2秒
    time.sleep(5)

    # 3. 检查悬浮窗状态
    print("3. 检查悬浮窗状态")
    if is_task_window_open():
        print("   悬浮窗已打开")
        update_task_window("跑单", datetime.now() + timedelta(minutes=30), "测试开")
    else:
        update_task_window("跑单", datetime.now() + timedelta(minutes=30), "测试关")

    # 等待2秒
    time.sleep(10)

    # 4. 关闭悬浮窗
    print("4. 关闭悬浮窗")
    # close_task_window()
    # print("   悬浮窗已关闭")

    # 等待1秒
    # time.sleep(1)
