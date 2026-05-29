"""
点选验证码自动求解器

继承 BaseSolver，使用 transition() / run() 状态机模式：
  - 非验证码场景 → 直接返回 True（退出）
  - 验证码场景启动：
    1. OCR 识别题目文字
    2. ddddocr 检测点击区域内的汉字及其坐标
    3. LLM 按题目顺序匹配索引 (复用 agent/tools/captcha_ocr_match.py)
    4. 按顺序点击每个汉字
    5. 验证是否仍然在验证码页
    6. 刷新按钮重新尝试，最多 10 次
    7. 全部失败则发送邮件通知
"""

from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from arknights_mower.agent.tools.captcha_ocr_match import match_captcha_order
from arknights_mower.utils.email import send_message
from arknights_mower.utils.log import logger, save_screenshot
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver

# 默认点击区域 / 题目区域（相对于 1920×1080 分辨率）
DEFAULT_CLICK_AREA = (700, 300, 1230, 655)
DEFAULT_TITLE_AREA = (1070, 230, 1250, 310)

# debug 图片输出目录
DEBUG_OUTPUT_DIR = "solve_captcha"


class CaptchaClickSolver(BaseSolver):
    """
    点选验证码（汉字顺序点击）求解器。

    通过 state machine 在 run() / transition() 中自动完成：
      1. 识别题目区域文字 → 判定需要点击的顺序
      2. ddddocr 检测点击区内所有汉字及坐标
      3. LLM 按题目排序 → 点击
      4. 若未通过则点击刷新 → 重试（最多 10 次）

    Args:
        debug: 为 True 时，每次 LLM 排序后在原图上标注点击顺序，
               保存到 solve_captcha/ 文件夹供审查。
    """

    MAX_ATTEMPTS = 10

    def __init__(
        self,
        device=None,
        recog=None,
        click_area: tuple = DEFAULT_CLICK_AREA,
        title_area: tuple = DEFAULT_TITLE_AREA,
        debug: bool = False,
    ) -> None:
        super().__init__(device, recog)
        self.click_area = click_area
        self.title_area = title_area
        self.debug = debug

        # ---- 状态变量 ----
        self._attempt_count = 0  # 当前尝试次数
        self._title_text = ""  # 题目文字（如"开始征程"）
        self._click_items: list[dict] = []  # 所有检测到的汉字 [{word,coords}]
        self._click_order: list[int] = []  # LLM 算出的点击顺序（索引）
        self._click_idx = 0  # 已点击到第几个
        self._phase = "detect"  # detect → click → verify

    # ─────────────────────────────────────────────
    # run() → 状态机入口
    # ─────────────────────────────────────────────

    def run(self) -> None:
        """启动验证码求解器"""
        logger.info("开始：点选验证码求解")
        super().run()

    # ─────────────────────────────────────────────
    # transition() → 每次循环走一步
    # ─────────────────────────────────────────────

    def transition(self) -> bool:
        """
        状态机主循环。

        Returns:
            True  → 任务完成（无论成功或放弃）
            False → 继续下一轮 transition
        """
        # 等待场景稳定
        self.wait_for_scene_stable()
        logger.info(f"当前阶段：{self._phase}，尝试次数：{self._attempt_count}")
        # 1. 不是验证码 → 退出
        if self.scene() != Scene.LOGIN_CAPTCHA:
            if self._attempt_count > 0:
                logger.info("验证码场景已消失，求解成功")
            return True

        # 2. 超过最大次数 → 发邮件放弃
        if self._attempt_count >= self.MAX_ATTEMPTS:
            logger.error(f"点选验证码已连续失败 {self.MAX_ATTEMPTS} 次，放弃求解")
            send_message("点选验证码自动求解失败，请手动处理", level="ERROR")
            return True

        # 3. 根据不同阶段执行
        if self._phase == "detect":
            return self._do_detect()
        elif self._phase == "click":
            return self._do_click()
        elif self._phase == "verify":
            return self._do_verify()
        return True

    # ═════════════════════════════════════════════
    # 阶段一：检测 → OCR & ddddocr & LLM
    # ═════════════════════════════════════════════

    def _do_detect(self) -> bool:
        """
        阶段一：OCR 题目 + ddddocr 检测汉字 + LLM 排序

        Returns: False（继续下一轮 transition）
        """
        img = self.recog.img

        # 1) OCR 题目文字
        if not self._title_text:
            title = self._recognize_title(img)
            if not title:
                logger.error("无法识别题目文字，刷新重试")
                return self._fail_retry()
            self._title_text = title
            logger.info(f"题目文字：'{self._title_text}'")

        # 2) ddddocr 检测点击区所有汉字
        items = self._detect_click_items(img)
        if not items:
            logger.error("点击区域内未检测到任何汉字，刷新重试")
            return self._fail_retry()
        logger.info(f"检测到 {len(items)} 个汉字, 结果如下：{str(items)}")
        for i, it in enumerate(items):
            logger.debug(f"  [{i}] '{it['word']}' {it['coords']}")
        self._click_items = items

        # 检测到的汉字少于题目字数 → 直接刷新，不调 LLM
        if len(items) < len(self._title_text):
            logger.error(
                f"检测到 {len(items)} 个汉字，少于题目 {len(self._title_text)} 个字，刷新重试"
            )
            return self._fail_retry()

        # 3) LLM 排序（复用 agent/tools/captcha_ocr_match.py）
        order = match_captcha_order(self._title_text, items)
        if not order:
            logger.error("LLM 排序失败，刷新重试")
            return self._fail_retry()

        # 校验索引合法性
        valid = [i for i in order if 0 <= i < len(items)]
        if not valid:
            logger.error("LLM 返回的索引全部越界，刷新重试")
            return self._fail_retry()

        self._click_order = valid
        logger.info(f"点击顺序：{self._click_order}")

        # 4) debug 模式：在截图上标注顺序，保存到 solve_captcha/
        if self.debug:
            self._save_debug_image(img)

        self._click_idx = 0
        self._phase = "click"
        return False

    # ═════════════════════════════════════════════
    # 阶段二：逐个点击汉字
    # ═════════════════════════════════════════════

    def _do_click(self) -> bool:
        """
        阶段二：按顺序点击每个汉字

        Returns: False（继续下一轮 transition）
        """
        if self._click_idx >= len(self._click_order):
            # 所有点击完毕 → 进入验证阶段
            self._phase = "verify"
            return False

        idx = self._click_order[self._click_idx]
        item = self._click_items[idx]
        cx = (item["coords"][0] + item["coords"][2]) // 2
        cy = (item["coords"][1] + item["coords"][3]) // 2
        logger.info(
            f"点击 [{idx}] '{item['word']}'  ({cx},{cy})  "
            f"[{self._click_idx + 1}/{len(self._click_order)}]"
        )
        self.tap((cx, cy), interval=0.3)
        self._click_idx += 1
        return False

    # ═════════════════════════════════════════════
    # 阶段三：验证是否通过
    # ═════════════════════════════════════════════

    def _do_verify(self) -> bool:
        """
        阶段三：验证验证码是否已通过

        重新截图判定 scene；若仍在 LOGIN_CAPTCHA 则刷新重试，
        否则返回 True 表示成功。
        """
        self.tap((970, 720), interval=1)
        self.wait_for_scene_stable()
        if self.scene() == Scene.LOGIN_CAPTCHA:
            logger.warning("验证码点击后仍未通过，刷新重试")
            return self._fail_retry()
        logger.info("点选验证码通过！")
        return True

    # ═════════════════════════════════════════════
    # Debug 图片保存
    # ═════════════════════════════════════════════

    def _save_debug_image(self, img: np.ndarray):
        """
        在点击位置标注 1/2/3 数字，保存到 screenshot/solve_captcha/。
        """
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size=24)
        except Exception:
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

        draw = ImageDraw.Draw(pil_img)
        for i, item in enumerate(self._click_items):
            x1, y1, x2, y2 = item["coords"]
            order_num = None
            for pos, idx in enumerate(self._click_order):
                if idx == i:
                    order_num = pos + 1
                    break
            if order_num is not None:
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2
                label = str(order_num)
                if font:
                    draw.text((cx, cy), label, fill="red", font=font)
                else:
                    draw.text((cx, cy), label, fill="red")

        buf = BytesIO()
        pil_img.save(buf, format="JPEG", quality=95)
        save_screenshot(buf.getvalue(), "solve_captcha")

    # ═════════════════════════════════════════════
    # 失败处理：刷新 + 重置状态重新尝试
    # ═════════════════════════════════════════════

    def _fail_retry(self) -> bool:
        """
        验证码求解失败 → 点击刷新 → 重置状态

        Returns: False（继续下一轮 transition）
        """
        self._attempt_count += 1
        if self._attempt_count >= self.MAX_ATTEMPTS:
            logger.error(f"已达最大尝试次数 {self.MAX_ATTEMPTS}，放弃")
            send_message("点选验证码自动求解失败，请手动处理", level="ERROR")
            return True

        logger.info(f"刷新验证码（第 {self._attempt_count}/{self.MAX_ATTEMPTS} 次）")
        self._refresh_captcha()
        self._reset_state()
        return False

    def _reset_state(self):
        """重置所有状态变量（刷新后重新检测）"""
        self._title_text = ""
        self._click_items = []
        self._click_order = []
        self._click_idx = 0
        self._phase = "detect"

    def _refresh_captcha(self):
        """
        点击验证码的「刷新」按钮
        根据当前截图自动定位刷新按钮位置
        """
        self.tap((785, 825), interval=2)

    # ═════════════════════════════════════════════
    # OCR 题目区域文字
    # ═════════════════════════════════════════════

    def _recognize_title(self, img: np.ndarray) -> str:
        """
        使用 RapidOCR 识别题目区域的文字

        OCR 结果按 x 坐标从左到右排序后拼接
        """
        from arknights_mower.utils import rapidocr

        if not rapidocr.engine:
            logger.error("RapidOCR 未初始化")
            return ""

        x1, y1, x2, y2 = self.title_area
        cropped = img[y1:y2, x1:x2]

        ocr_result = rapidocr.engine(cropped, use_det=True, use_cls=False, use_rec=True)
        items = ocr_result[0] if isinstance(ocr_result, tuple) else ocr_result
        if not items:
            return ""

        sorted_items = sorted(
            items,
            key=lambda it: (
                min(p[0] for p in it[0])
                if isinstance(it[0][0], (list, tuple))
                else it[0][0]
            ),
        )
        texts = [
            it[1].strip()
            for it in sorted_items
            if isinstance(it, (list, tuple)) and len(it) >= 2 and it[1].strip()
        ]
        return "".join(texts)

    # ═════════════════════════════════════════════
    # ddddocr 检测点击区汉字
    # ═════════════════════════════════════════════

    @staticmethod
    def _is_inside(bbox: tuple, area: tuple) -> bool:
        """判断边界框的中心是否在区域内"""
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return area[0] <= cx <= area[2] and area[1] <= cy <= area[3]

    def _detect_click_items(self, img: np.ndarray) -> list[dict]:
        """
        使用 ddddocr 检测点击区域内的所有汉字及其包围盒

        Returns: [{word, coords: (x1,y1,x2,y2)}, ...]
        """
        import ddddocr

        img_pil = Image.fromarray(img)
        buf = BytesIO()
        img_pil.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        det = ddddocr.DdddOcr(det=True)
        text_ocr = ddddocr.DdddOcr()

        bboxes = det.detection(img_bytes)
        if not bboxes:
            return []

        results = []
        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            # 只保留在点击区域内的文字
            if not self._is_inside((x1, y1, x2, y2), self.click_area):
                continue

            cropped = img_pil.crop((x1, y1, x2, y2))
            byte_io = BytesIO()
            cropped.save(byte_io, format="PNG")
            word = text_ocr.classification(byte_io.getvalue())
            if word:
                results.append({"word": word, "coords": (x1, y1, x2, y2)})

        return results

    @staticmethod
    def _split_multi_char(word: str, bbox: tuple) -> list[dict]:
        """
        将多字识别结果按水平宽度等分拆为多个单字

        Args:
            word: 可能含多个字符的字符串
            bbox: (x1, y1, x2, y2)

        Returns: [{word: char, coords: (x1,y1,x2,y2)}, ...]
        """
        if len(word) <= 1:
            return [{"word": word, "coords": tuple(map(int, bbox))}]

        x1, y1, x2, y2 = map(int, bbox)
        width = max(x2 - x1, 1)
        cw = width / len(word)

        result = []
        for i, ch in enumerate(word):
            cx1 = x1 + i * cw
            cx2 = cx1 + cw
            result.append(
                {
                    "word": ch,
                    "coords": (int(cx1), y1, int(cx2), y2),
                }
            )
        return result
