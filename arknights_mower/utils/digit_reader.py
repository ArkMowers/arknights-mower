import cv2
import numpy as np
from pathlib import Path
import os
from .image import loadres


class DigitReader:
    def __init__(self, template_dir=None):
        if not template_dir:
            template_dir = Path(os.path.dirname(os.path.abspath(__file__))) / Path(
                "templates"
            )
        if not isinstance(template_dir, Path):
            template_dir = Path(template_dir)
        self.time_template = []
        self.drone_template = []
        self.report_template = []
        self.report_template_white = []
        self.recruit_template = []
        self.spent_creidt_number = []
        for i in range(10):
            self.time_template.append(loadres(f"orders_time/{i}", True))
            self.drone_template.append(loadres(f"drone_count/{i}", True))
            self.report_template.append(loadres(f"report_number/{i}", False))
            self.report_template_white.append(loadres(f"report_number/{i}", True))
            self.recruit_template.append(loadres(f"recruit_ticket/{i}", True))
            self.spent_creidt_number.append(loadres(f"spent_creidt_number/{i}", True))

    def get_drone(self, img_grey, h=1080, w=1920):
        drone_part = img_grey[
            h * 32 // 1080 : h * 76 // 1080, w * 1144 // 1920 : w * 1225 // 1920
        ]
        drone_part = cv2.resize(drone_part, (81, 44), interpolation=cv2.INTER_AREA)
        result = {}
        for j in range(10):
            res = cv2.matchTemplate(
                drone_part,
                self.drone_template[j],
                cv2.TM_CCORR_NORMED,
            )
            threshold = 0.95
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                offset = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - offset) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j
        ch = [str(result[k]) for k in sorted(result)]
        return int("".join(ch))

    def get_time(self, img_grey, h, w):
        digit_part = img_grey[h * 510 // 1080 : h * 543 // 1080, w * 499 // 1920 : w]
        digit_part = cv2.resize(digit_part, (1421, 33), interpolation=cv2.INTER_AREA)
        result = {}
        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.time_template[j],
                cv2.TM_CCOEFF_NORMED,
            )
            threshold = 0.85
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    if len(result) == 0:
                        digit_part = digit_part[:, loc[1][i] - 5 : loc[1][i] + 116]
                        offset = loc[1][0] - 5
                        for m in range(len(loc[1])):
                            loc[1][m] -= offset
                    result[loc[1][i]] = j
        ch = [str(result[k]) for k in sorted(result)]
        return f"{ch[0]}{ch[1]}:{ch[2]}{ch[3]}:{ch[4]}{ch[5]}"

    def get_report_number(self, digit_part):
        result = {}
        digit_part = cv2.cvtColor(digit_part, cv2.COLOR_BGR2RGB)
        # digit_part = cv2.resize(digit_part, (width*2, height*2), interpolation=cv2.INTER_AREA)
        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.report_template[j],
                cv2.TM_CCORR_NORMED,
            )
            threshold = 0.9
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
            # print(max_val, j)
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        ch = [str(result[k]) for k in sorted(result)]
        return int("".join(ch))

    def get_report_number_white(self, digit_part):
        result = {}
        digit_part = cv2.cvtColor(digit_part, cv2.COLOR_RGB2GRAY)

        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.report_template_white[j],
                cv2.TM_CCOEFF_NORMED,
            )

            threshold = 0.93
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        ch = [str(result[k]) for k in sorted(result)]
        return int("".join(ch))

    def get_recruit_ticket(self, digit_part):
        result = {}
        digit_part = cv2.cvtColor(digit_part, cv2.COLOR_RGB2GRAY)

        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.recruit_template[j],
                cv2.TM_CCORR_NORMED,
            )
            threshold = 0.94
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        ch = [str(result[k]) for k in sorted(result)]
        return int("".join(ch))

    def get_credict_number(self, digit_part):
        result = {}
        digit_part = cv2.cvtColor(digit_part, cv2.COLOR_RGB2GRAY)

        for j in range(10):
            res = cv2.matchTemplate(
                digit_part,
                self.spent_creidt_number[j],
                cv2.TM_CCOEFF_NORMED,
            )
            threshold = 0.95
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                x = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - x) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j

        ch = [str(result[k]) for k in sorted(result)]

        return int("".join(ch))

    def 识别制造加速总剩余时间(self, img_grey, h, w):
        时间部分 = img_grey[
            h * 665 // 1080 : h * 709 // 1080, w * 750 // 1920 : w * 960 // 1920
        ]
        时间部分 = cv2.resize(
            时间部分, (210 * 58 // 71, 44 * 58 // 71), interpolation=cv2.INTER_AREA
        )
        result = {}
        for j in range(10):
            res = cv2.matchTemplate(
                时间部分,
                self.drone_template[j],
                cv2.TM_CCOEFF_NORMED,
            )
            threshold = 0.85
            loc = np.where(res >= threshold)
            for i in range(len(loc[0])):
                offset = loc[1][i]
                accept = True
                for o in result:
                    if abs(o - offset) < 5:
                        accept = False
                        break
                if accept:
                    result[loc[1][i]] = j
        ch = [str(result[k]) for k in sorted(result)]
        print(ch)
        if len(ch) == 6:
            return (
                int(f"{ch[0]}{ch[1]}"),
                int(f"{ch[2]}{ch[3]}"),
                int(f"{ch[4]}{ch[5]}"),
            )
        else:
            return (
                int(f"{ch[0]}{ch[1]}{ch[2]}"),
                int(f"{ch[3]}{ch[4]}"),
                int(f"{ch[5]}{ch[6]}"),
            )
