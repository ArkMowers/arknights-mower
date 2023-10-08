from .path import get_path

ocr = None

def initialize_ocr():
    global ocr
    if not ocr:
        from paddleocr import PaddleOCR

        det_model_dir = get_path("@app/tmp/paddle/det/ch", space='')
        rec_model_dir = get_path("@app/tmp/paddle/rec/ch", space='')
        cls_model_dir = get_path("@app/tmp/paddle/cls", space='')
        ocr = PaddleOCR(
            enable_mkldnn=False,
            use_angle_cls=False,
            cls=False,
            show_log=False,
            det_model_dir=str(det_model_dir),
            rec_model_dir=str(rec_model_dir),
            cls_model_dir=str(cls_model_dir),
        )
