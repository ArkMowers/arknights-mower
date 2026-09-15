import cv2

from arknights_mower.utils.graph import SceneGraphSolver
from arknights_mower.utils.image import cropimg, loadres, thres2
from arknights_mower.utils.log import logger
from arknights_mower.utils.recognize import Scene

# 访问下位按钮固定在页面右下角。原先用 ORB 模板匹配找它，但在大片纯橙、纹理很平的
# 按钮上 ORB 关键点不稳，会被判据误判成不存在而提前放弃。这里改用 HSV 计数识别橙色，
# 灰/禁用态用模板 clue_next_black 识别。
CLUE_NEXT_REGION = ((1636, 866), (1920, 1020))
# 橙色亮着时约占区域 3/4，灰/禁用态不到 1%，以 15% 为界区分
ORANGE_RATIO = 0.15


def count_orange(img) -> int:
    """统计访问下位按钮区域内橙色（HSV 色调<=30、饱和度>=200）像素数。"""
    hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
    return int(((hsv[..., 0] <= 30) & (hsv[..., 1] >= 200)).sum())


def region_size(region) -> int:
    """计算矩形区域（((x0, y0), (x1, y1))）的像素面积。"""
    return (region[1][0] - region[0][0]) * (region[1][1] - region[0][1])


class CreditSolver(SceneGraphSolver):
    def run(self) -> None:
        logger.info("Start: 访问好友")
        self.wait_times = 5
        return super().run()

    def transition(self) -> bool:
        if (scene := self.scene()) == Scene.FRIEND_LIST:
            left, top = 1460, 220
            img = cropimg(self.recog.gray, ((left, top), (1800, 1000)))
            img = thres2(img, 245)
            tpl = loadres("friend_visit", True)
            result = cv2.matchTemplate(img, tpl, cv2.TM_SQDIFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            h, w = tpl.shape
            pos = (
                (min_loc[0] + left, min_loc[1] + top),
                (min_loc[0] + left + w, min_loc[1] + top + h),
            )
            logger.debug(f"{min_val=}, {pos=}")
            if min_val < 0.5:
                self.tap(pos)
            else:
                self.sleep()
        elif self.find("visit_limit"):
            logger.info("今日参与交流已达上限")
            return True
        elif scene == Scene.FRIEND_VISITING:
            region = CLUE_NEXT_REGION
            img = cropimg(self.recog.img, region)
            if count_orange(img) >= region_size(region) * ORANGE_RATIO:
                self.wait_times = 5
                self.tap(self.get_pos(region, 0.5, 0.5))
            elif self.find("clue_next_black"):
                logger.info("没有可访问的好友了")
                return True
            else:
                if self.wait_times > 0:
                    self.wait_times -= 1
                    self.sleep()
                else:
                    return True
        elif scene in self.waiting_scene:
            self.waiting_solver()
        else:
            self.scene_graph_navigation(Scene.FRIEND_LIST)
