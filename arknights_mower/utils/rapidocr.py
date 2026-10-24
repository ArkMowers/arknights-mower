import gc
import math
import os
from pathlib import Path
from threading import Lock

SMALL_TEXT_EDGE = 736
MAX_DETECTION_EDGE = 1920
DETECTION_ALIGN = 32
DEFAULT_TEXT_SCORE = 0.3
DEFAULT_BOX_THRESH = 0.5
DEFAULT_UNCLIP_RATIO = 1.6
DEFAULT_OCR_OPTIONS = {
    "text_score": DEFAULT_TEXT_SCORE,
    "box_thresh": DEFAULT_BOX_THRESH,
    "unclip_ratio": DEFAULT_UNCLIP_RATIO,
}

# auto 在存活 Mower 实例数达到两个时使用共享客户端，否则在进程内加载模型。
OCR_MODE_ENV = "MOWER_OCR_MODE"
OCR_MODES = ("auto", "local", "shared")
# 心跳每秒原子替换登记文件，扫描可能恰好撞上暂时不可读的瞬间。给 instances()
# 一个短预算，让它在这个窗口内重试出完整快照；判定只发生在任务初始化边界，
# 200 ms 可以忽略，而不完整快照会少算实例并因此多构造一次本地模型。
INSTANCE_SCAN_TIMEOUT = 0.2
_OCR_OPTION_NAMES = frozenset(
    {"use_det", "use_cls", "use_rec", "text_score", "box_thresh", "unclip_ratio"}
)

engine = None
_initialize_lock = Lock()


class _BoundedDetectionInput:
    """保留小文字放大，同时限制检测模型输入的长边。"""

    def __init__(self, preprocess):
        self.preprocess = preprocess

    def __call__(self, image):
        import cv2

        height, width = image.shape[:2]
        scale = min(
            max(1, SMALL_TEXT_EDGE / min(height, width)),
            MAX_DETECTION_EDGE / max(height, width),
        )
        target = tuple(
            max(
                DETECTION_ALIGN,
                round(side * scale / DETECTION_ALIGN) * DETECTION_ALIGN,
            )
            for side in (width, height)
        )
        if target != (width, height):
            image = cv2.resize(image, target)
        return self.preprocess(image)


def create_engine(score=DEFAULT_TEXT_SCORE, *, threads=None):
    from rapidocr_onnxruntime import RapidOCR

    options = (
        {}
        if threads is None
        else {"intra_op_num_threads": threads, "inter_op_num_threads": 1}
    )
    result = RapidOCR(
        text_score=score,
        det_limit_type="max",
        det_limit_side_len=MAX_DETECTION_EDGE,
        # 本地模型与服务端每次请求重置使用同一组默认阈值。
        det_box_thresh=DEFAULT_BOX_THRESH,
        det_unclip_ratio=DEFAULT_UNCLIP_RATIO,
        **options,
    )
    # 依赖 rapidocr_onnxruntime==1.3.24 的私有结构：text_det.preprocess_op
    # 以单张图像调用并返回检测张量。升级该依赖前必须复核这一调用约定，
    # 回归见 runtime_memory_tests.test_production_ocr_bounds_detector_tensor。
    result.text_det.preprocess_op = _BoundedDetectionInput(
        result.text_det.preprocess_op
    )
    return result


def _checked_text_score(score):
    if type(score) not in (int, float) or not 0 <= score <= 1:
        raise ValueError("OCR 文本置信度阈值必须在 0 到 1 之间")


def _checked_call_options(options):
    """校验与 ocr_shared.checked_options 相同的六个选项并补齐默认阈值。

    本地路径等价支持协议中的三个阈值，而不是忽略它们：每次调用都用
    text_score、DEFAULT_BOX_THRESH 与 DEFAULT_UNCLIP_RATIO 重置 RapidOCR，
    与服务端每次请求的默认值一致。生产调用点只使用三个布尔开关。
    """
    if options.keys() - _OCR_OPTION_NAMES:
        raise ValueError("OCR 参数无效")
    for name in ("text_score", "box_thresh", "unclip_ratio"):
        if name not in options:
            continue
        value = options[name]
        upper = 10 if name == "unclip_ratio" else 1
        if (
            type(value) not in (int, float)
            or not math.isfinite(value)
            or not 0 <= value <= upper
        ):
            raise ValueError("OCR 阈值无效")
    for name in ("use_det", "use_cls", "use_rec"):
        value = options.get(name)
        if value is not None and type(value) is not bool:
            raise ValueError("OCR 开关必须是布尔值")
    return {
        "use_det": options.get("use_det"),
        "use_cls": options.get("use_cls"),
        "use_rec": options.get("use_rec"),
        "text_score": options.get("text_score", DEFAULT_TEXT_SCORE),
        "box_thresh": options.get("box_thresh", DEFAULT_BOX_THRESH),
        "unclip_ratio": options.get("unclip_ratio", DEFAULT_UNCLIP_RATIO),
    }


class _LocalOCREngine:
    """进程内 OCR 引擎，调用约定与 SharedOCREngine 一致。

    构造时通过 create_engine(score) 加载模型；调用参数接受与共享客户端相同的
    use_det/use_cls/use_rec 与 text_score/box_thresh/unclip_ratio，并在每次调用
    重置阈值，避免上一次调用的阈值影响下一次。实例内调用串行，对应
    SharedOCREngine 的实例内串行约定；生产调用点只传三个布尔开关。
    """

    def __init__(self, score=DEFAULT_TEXT_SCORE):
        _checked_text_score(score)
        self.score = score
        self._engine = create_engine(score)
        self._lock = Lock()

    def __call__(self, image, use_det=None, use_cls=None, use_rec=None, **kwargs):
        options = _checked_call_options(
            {
                "use_det": use_det,
                "use_cls": use_cls,
                "use_rec": use_rec,
                "text_score": self.score,
                **kwargs,
            }
        )
        with self._lock:
            return self._engine(
                image,
                use_det=options["use_det"],
                use_cls=options["use_cls"],
                use_rec=options["use_rec"],
                text_score=options["text_score"],
                box_thresh=options["box_thresh"],
                unclip_ratio=options["unclip_ratio"],
            )


def _default_data_root():
    """安装默认数据根：未设置 MOWER_DATA_DIR 时 @app 指向的目录。

    直接复用 path 模块初始化时算好的 _app_dir，而不是复制冻结包 macOS 的
    默认目录规则，避免与 path.py 漂移。
    """
    from arknights_mower.utils import path as mower_path

    return Path(mower_path._app_dir).expanduser().resolve()


def _registered_data_root(record, default_root, current_cwd):
    """把登记携带的原始 data_dir 解析成绝对数据根。

    空值表示安装默认数据根；相对值按实例启动时的 cwd 解析，登记缺少 cwd 时
    退回当前 cwd。
    """
    override = record.get("data_dir") or ""
    if not override:
        return default_root
    value = Path(override).expanduser()
    if not value.is_absolute():
        value = Path(record.get("cwd") or current_cwd) / value
    return value.resolve()


def _live_mower_instance_count():
    """统计当前安装与数据根下存活的 Mower 实例。

    只统计 update_runtime.instances() 中 kind=="instance" 的登记：管理器进程和
    共享 OCR 协调/工作进程都不是识别调用方。读取一次且不在这里重试；
    INSTANCE_SCAN_TIMEOUT 让 instances() 在短预算内重试瞬时不可读的登记，
    strict=False 在预算用尽后接受可用部分。

    数据根按解析后的绝对路径比较：登记里的空 data_dir 表示安装默认数据根，
    相对值按登记 cwd 解析。Windows 上路径比较大小写不敏感，POSIX 上保持
    大小写敏感，与文件系统语义一致。
    """
    from arknights_mower.utils import path as mower_path
    from arknights_mower.utils import update_runtime as runtime

    records = runtime.instances(timeout=INSTANCE_SCAN_TIMEOUT, strict=False)
    current_root = Path(mower_path.get_path("@app", space="")).resolve()
    default_root = _default_data_root()
    current_cwd = os.getcwd()
    count = 0
    for record in records:
        if record.get("kind") != "instance":
            continue
        root = _registered_data_root(record, default_root, current_cwd)
        if os.path.normcase(str(root)) == os.path.normcase(str(current_root)):
            count += 1
    return count


def _engine_mode_choice():
    """返回目标模式与判定依据；非法 MOWER_OCR_MODE 显式报错而不是回退 auto。"""
    raw = os.environ.get(OCR_MODE_ENV, "")
    override = raw.strip().lower() or "auto"
    if override not in OCR_MODES:
        raise ValueError(
            f"{OCR_MODE_ENV} 只能设为 auto、local 或 shared，当前值为 {raw!r}"
        )
    if override != "auto":
        return override, f"{OCR_MODE_ENV}={override}"
    try:
        count = _live_mower_instance_count()
    except Exception as exc:
        # 实例登记是选择依据而不是识别依赖：读取失败时按单实例本地模式处理，
        # 不在这里重试，下一次 initialize_ocr 调用会重新评估。
        return "local", f"读取 Mower 实例登记失败，按本地模式处理：{exc}"
    if count >= 2:
        return "shared", f"存活 Mower 实例数 {count}"
    return "local", f"存活 Mower 实例数 {count}"


def _engine_mode(value):
    if value is None:
        return None
    if isinstance(_LocalOCREngine, type) and isinstance(value, _LocalOCREngine):
        return "local"
    from arknights_mower.utils import ocr_shared

    shared_class = getattr(ocr_shared, "SharedOCREngine", None)
    if isinstance(shared_class, type) and isinstance(value, shared_class):
        return "shared"
    # 调用方注入的引擎（测试或家具识别夹具）按本地引擎对待；目标仍为 local 时
    # 保留其已加载的模型，避免静默丢弃。
    return "local"


def _build_engine(mode, score):
    if mode == "local":
        return _LocalOCREngine(score)
    from arknights_mower.utils.ocr_shared import SharedOCREngine

    return SharedOCREngine(score)


def _log_engine_choice(mode, evidence, previous_mode):
    try:
        from arknights_mower.utils.log import logger

        if previous_mode is None:
            logger.info("OCR 引擎初始化为 %s：%s", mode, evidence)
        else:
            logger.info("OCR 引擎从 %s 切换为 %s：%s", previous_mode, mode, evidence)
    except Exception:
        # 诊断日志不能阻断 OCR 初始化。
        pass


def initialize_ocr(score=DEFAULT_TEXT_SCORE):
    """按当前 Mower 实例数选择进程内或共享 OCR 引擎。

    MOWER_OCR_MODE=auto（默认）在存活实例数达到两个时发布 SharedOCREngine，
    否则发布进程内 _LocalOCREngine；local 与 shared 强制指定，其他值抛
    ValueError。每次调用都重新读取环境变量，auto 还读取实例登记，因此实例
    后启动、退出或运维切换后，下一次调用会收敛到新目标；没有后台轮询或重试。

    并发首次调用由 _initialize_lock 串行化，只有一个调用方构造引擎。模式切换
    先构造并发布新引擎，再释放旧引用，因此构造失败会保留旧引擎；发布后调用
    gc.collect()。ONNX Runtime 的原生内存仍可能保留到进程退出，回收只保证本
    模块不再引用旧对象。在途请求持有自己的引用，不受切换影响。
    """
    _checked_text_score(score)
    mode, evidence = _engine_mode_choice()
    global engine
    with _initialize_lock:
        previous_mode = _engine_mode(engine)
        if engine is not None and previous_mode == mode:
            return
        previous = engine
        built = _build_engine(mode, score)
        engine = built
        _log_engine_choice(mode, evidence, previous_mode)
        if previous is not None:
            previous = None
            gc.collect()
