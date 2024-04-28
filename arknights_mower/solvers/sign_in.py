from arknights_mower.utils.log import logger
from arknights_mower.utils.solver import BaseSolver


class SignInSolver(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 签到活动")
        self.back_to_index()
        self.materiel = False
        super().run()

    def notify(self, msg):
        logger.info(msg)
        self.recog.save_screencap("sign_in")
        if hasattr(self, "send_message_config") and self.send_message_config:
            self.send_message(msg)

    def transition(self) -> bool:
        failure = 0

        if self.recog.detect_index_scene():
            if self.materiel:
                return True
            if pos := self.find("sign_in/entry"):
                self.tap(pos)
            else:
                self.notify("未检测到五周年月卡领取入口！")
                return True
        elif self.find("sign_in/banner"):
            if self.materiel:
                self.back()
                return
            if pos := self.find("sign_in/button_ok"):
                self.tap(pos)
                return
            self.materiel = True
            self.notify("今天的五周年专享月卡已经领取过了")
            self.back()
        elif self.find("materiel_ico"):
            if not self.materiel:
                self.notify("成功领取五周年专享月卡")
                self.materiel = True
            self.tap((960, 960))
        else:
            failure += 1
            if failure > 15:
                self.notify("签到任务执行失败！")
                self.back_to_index()
                return True
            self.sleep()
