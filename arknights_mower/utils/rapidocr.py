engine = None


def initialize_ocr():
    global engine
    if not engine:
        from rapidocr_onnxruntime import RapidOCR

        engine = RapidOCR(text_score=0.3)
