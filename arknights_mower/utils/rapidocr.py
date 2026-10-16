from threading import Lock

engine = None
_initialize_lock = Lock()


class _BoundedDetectionInput:
    """保留小文字放大，同时限制检测模型输入的长边。"""

    def __init__(self, preprocess):
        self.preprocess = preprocess

    def __call__(self, image):
        import cv2

        height, width = image.shape[:2]
        scale = min(max(1, 736 / min(height, width)), 1920 / max(height, width))
        target = tuple(
            max(32, round(side * scale / 32) * 32) for side in (width, height)
        )
        if target != (width, height):
            image = cv2.resize(image, target)
        return self.preprocess(image)


def create_engine(score=0.3):
    from rapidocr_onnxruntime import RapidOCR

    result = RapidOCR(text_score=score, det_limit_type="max", det_limit_side_len=1920)
    result.text_det.preprocess_op = _BoundedDetectionInput(
        result.text_det.preprocess_op
    )
    return result


def initialize_ocr(score=0.3):
    global engine
    with _initialize_lock:
        if engine is None:
            engine = create_engine(score)
