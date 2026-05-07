from arknights_mower.utils.image import loadres, thres2
from arknights_mower.utils.matcher import Matcher
from arknights_mower.utils.recognize.constants import FEATURE_MATCH_RES


_FEATURE_SCOPE_OVERRIDES: dict[str, tuple] = {
    "arrange_check_in_on": ((0, 350), (200, 530)),
    "connecting": ((1087, 978), (1430, 1017)),
    "materiel_ico": ((860, 60), (1072, 217)),
    "training_completed": ((550, 900), (800, 1080)),
}

_FEATURE_THRESHOLD_OVERRIDES: dict[str, float] = {
    "connecting": 0.15,
    "training_completed": 0.45,
}


class FeatureMatcher:
    def match(
        self,
        res: str,
        draw: bool,
        scope: object,
        thres: int | None,
        judge: bool,
        threshold: float,
        force_feature: bool,
        recognizer,
    ) -> object:
        dpi_aware = res in FEATURE_MATCH_RES or force_feature

        if scope is None and threshold == 0.0:
            if res in _FEATURE_SCOPE_OVERRIDES:
                scope = _FEATURE_SCOPE_OVERRIDES[res]
            if res in _FEATURE_THRESHOLD_OVERRIDES:
                threshold = _FEATURE_THRESHOLD_OVERRIDES[res]

        res_img = loadres(res, True)
        if thres is not None:
            res_img = thres2(res_img, thres)
            matcher = Matcher(thres2(recognizer.gray, thres))
        else:
            matcher = recognizer.matcher
        return matcher.match(
            res_img,
            draw=draw,
            scope=scope,
            judge=judge,
            prescore=threshold,
            dpi_aware=dpi_aware,
        )
