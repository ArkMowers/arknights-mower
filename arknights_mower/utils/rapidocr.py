engine = None


def initialize_ocr(score=0.3):
    global engine
    if not engine:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR(text_score=score)
