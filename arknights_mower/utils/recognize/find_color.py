import cv2
from skimage.metrics import structural_similarity

from arknights_mower.utils.image import cmatch, cropimg, loadres
from arknights_mower.utils.recognize.constants import COLOR, TEMPLATE_MATCHING_SCORE


class ColorMatcher:
    def match(self, res: str, draw: bool, recognizer) -> object:
        if res not in COLOR:
            return None
        res_img = loadres(res)
        h, w, _ = res_img.shape
        pos_list = COLOR[res]
        if not isinstance(pos_list[0], tuple):
            pos_list = [COLOR[res]]
        for pos in pos_list:
            from arknights_mower.utils.vector import va

            scope = pos, va(pos, (w, h))
            img = cropimg(recognizer.img, scope)
            if cmatch(img, res_img, draw=draw):
                gray = cropimg(recognizer.gray, scope)
                res_img_gray = cv2.cvtColor(res_img, cv2.COLOR_RGB2GRAY)
                ssim = structural_similarity(gray, res_img_gray)
                threshold = 0.9
                if res in TEMPLATE_MATCHING_SCORE:
                    threshold = TEMPLATE_MATCHING_SCORE[res]
                if ssim >= threshold:
                    return scope
        return None
