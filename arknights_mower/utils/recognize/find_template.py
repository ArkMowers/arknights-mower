import cv2

from arknights_mower.utils.image import cropimg, loadres
from arknights_mower.utils.recognize.constants import TEMPLATE_MATCHING, TEMPLATE_MATCHING_SCORE


class TemplateMatcher:
    def match(self, res: str, recognizer) -> object:
        if res not in TEMPLATE_MATCHING:
            return None
        threshold = 0.9
        if res in TEMPLATE_MATCHING_SCORE:
            threshold = TEMPLATE_MATCHING_SCORE[res]
        pos = TEMPLATE_MATCHING[res]
        template = loadres(res, True)
        h, w = template.shape

        if isinstance(pos[0], tuple):
            scope = pos
        else:
            from arknights_mower.utils.vector import va

            scope = pos, va(pos, (w, h))

        img = cropimg(recognizer.gray, scope)
        result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        top_left = (max_loc[0] + scope[0][0], max_loc[1] + scope[0][1])
        if max_val >= threshold:
            return top_left, (top_left[0] + w, top_left[1] + h)
        return None
