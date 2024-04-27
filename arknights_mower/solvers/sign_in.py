from arknights_mower.utils.log import logger
from arknights_mower.utils.solver import BaseSolver


class SignInSolver(BaseSolver):
    def run(self) -> None:
        logger.info("Start: 签到活动")
        self.back_to_index()
        super().run()

    def transition(self) -> bool:
        failure = 0

        if self.recog.detect_connecting_scene():
            self.sleep()
        elif self.recog.detect_index_scene():
            if pos := self.find("sign_in/entry"):
                self.sleep()
                orange_dot = (255, 104, 1)
                x, y = pos[0]
                x += 238
                y += 14
                if all(self.get_color((x, y)) == orange_dot):
                    self.tap(pos)
                else:
                    msg = "五周年专享月卡已领取"
                    logger.info(msg)
                    self.send_message(msg)
                    return True
            else:
                msg = "未检测到五周年月卡领取入口！"
                logger.info(msg)
                self.send_message(msg)
        elif self.find("sign_in/banner"):
            if pos := self.find("sign_in/button_ok"):
                self.tap(pos)
            else:
                self.back()
        elif self.find("materiel_ico", scope=((860, 60), (1072, 217))):
            self.tap((960, 960))
        else:
            failure += 1
            if failure > 15:
                msg = "签到任务执行失败！"
                logger.info(msg)
                self.send_message(msg)
                return True
            self.sleep()
