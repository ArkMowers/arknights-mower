from arknights_mower.utils.log import logger
from arknights_mower.utils.solver import BaseSolver


class TaskManager:
    def __init__(self, task_list):
        self.task_list = task_list + ["back_to_index"]
        self.task = self.task_list[0]

    def complete(self, task):
        task = task or self.task
        if task in self.task_list:
            self.task_list.remove(task)
        self.task = self.task_list[0] if self.task_list else None


class SignInSolver(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 签到活动")
        self.back_to_index()
        self.tm = TaskManager(
            [
                "monthly_card",  # 五周年专享月卡
                "orundum",  # 限时开采许可
                "headhunting",  # 每日赠送单抽
            ]
        )

        self.failure = 0
        self.in_progress = False
        super().run()

    def notify(self, msg):
        logger.info(msg)
        self.recog.save_screencap("sign_in")
        if hasattr(self, "send_message_config") and self.send_message_config:
            self.send_message(msg)

    def transition(self) -> bool:
        if not self.tm.task:
            return True

        if self.recog.detect_index_scene():
            if self.tm.task == "back_to_index":
                self.tm.complete("back_to_index")
                return True
            elif self.tm.task == "monthly_card":
                if pos := self.find("sign_in/monthly_card/entry"):
                    self.tap(pos)
                else:
                    self.notify("未检测到五周年月卡领取入口！")
                    self.tm.complete("monthly_card")
            elif self.tm.task == "orundum":
                if pos := self.find("sign_in/orundum/entry"):
                    self.tap(pos)
                else:
                    self.notify("未检测到限时开采许可入口！")
                    self.tm.complete("orundum")
            elif self.tm.task == "headhunting":
                self.tap_index_element("headhunting")
            else:
                return True
        elif self.find("sign_in/monthly_card/banner"):
            if self.tm.task == "monthly_card":
                if pos := self.find("sign_in/monthly_card/button_ok"):
                    self.tap(pos)
                else:
                    self.notify("今天的五周年专享月卡已经领取过了")
                    self.tm.complete("monthly_card")
                    self.back()
            else:
                self.back()
        elif self.find("materiel_ico"):
            if self.tm.task == "monthly_card":
                self.notify("成功领取五周年专享月卡")
                self.tm.complete("monthly_card")
            elif self.tm.task == "orundum":
                self.notify("成功开采合成玉")
                self.in_progress = False
                self.tm.complete("orundum")
            self.tap((960, 960))
        elif self.find("sign_in/orundum/banner"):
            if self.tm.task == "orundum":
                if pos := self.find("sign_in/orundum/button_start"):
                    self.in_progress = True
                    self.tap(pos)
                elif self.find("sign_in/orundum/button_complete"):
                    if self.in_progress:
                        self.sleep()
                    else:
                        self.notify("今天的限时开采活动已经做完了")
                        self.tm.complete("orundum")
                        self.back()
                else:
                    self.sleep()
            else:
                self.back()
        elif self.find("sign_in/headhunting/banner"):
            if self.tm.task == "headhunting":
                if self.find("sign_in/headhunting/available"):
                    self.tap((1355, 975))
                else:
                    self.notify("今天的赠送单抽已经抽完了")
                    self.tm.complete("headhunting")
                    self.back()
            else:
                self.back()
        elif self.find("sign_in/headhunting/banner_exclusive"):
            if self.tm.task == "headhunting":
                self.tap((1880, 590))
            else:
                self.back()
        elif self.find("sign_in/headhunting/dialog"):
            if self.tm.task == "headhunting":
                self.tap((1263, 744))
            else:
                self.tap((663, 741))
        elif pos := self.find("skip"):
            self.tap(pos)
        elif self.find("agent_token"):
            if self.tm.task == "headhunting":
                self.notify("成功抽完赠送单抽")
                self.tm.complete("headhunting")
            self.tap((960, 540))
        else:
            self.failure += 1
            if self.failure > 15:
                self.notify("签到任务执行失败！")
                self.back_to_index()
                return True
            self.sleep()
