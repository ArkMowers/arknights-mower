"""RapidOCR 工厂、本地模型与调用协议的离线回归。"""

import builtins
import gc
import importlib.util
import socket
import sys
import weakref
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from rapidocr.ch_ppocr_cls.utils import TextClsOutput
from rapidocr.ch_ppocr_det.utils import TextDetOutput
from rapidocr.ch_ppocr_rec.typings import TextRecOutput
from rapidocr.utils.output import RapidOCROutput

from arknights_mower.utils import rapidocr


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def reject(*args, **kwargs):
        pytest.fail("本地 OCR 模型和推理不得访问网络")

    monkeypatch.setattr(socket, "create_connection", reject)
    monkeypatch.setattr(socket.socket, "connect", reject)


@pytest.fixture
def fake_sdk(monkeypatch, tmp_path):
    models = tmp_path / "models"
    models.mkdir()
    for name in (
        "PP-OCRv6_det_tiny.onnx",
        "PP-OCRv6_rec_tiny.onnx",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ):
        (models / name).touch()
    state = {"created": [], "loaded": [], "models": models}

    class Detector:
        def get_preprocess(self):
            return lambda image: image

    class SDK:
        def __init__(self, *, params):
            state["created"].append(params)
            self.text_det = Detector()

        def _load_det_model(self):
            state["loaded"].append("det")
            return self.text_det

        def _load_cls_model(self):
            state["loaded"].append("cls")

        def _load_rec_model(self):
            state["loaded"].append("rec")
            if state.get("load_error"):
                raise ValueError("fixture model failed")

    monkeypatch.setattr(rapidocr, "_MODEL_DIR", models)
    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        SimpleNamespace(
            RapidOCR=SDK,
            ModelType=SimpleNamespace(TINY="tiny"),
            __file__=str(tmp_path / "__init__.py"),
        ),
    )
    return state


@pytest.mark.parametrize("threads", (None, 2))
def test_factory_loads_explicit_tiny_models_and_real_preprocess_path(fake_sdk, threads):
    engine = rapidocr.create_engine(0.4, threads=threads)
    params = fake_sdk["created"][0]
    models = fake_sdk["models"]
    assert params["Det.model_path"] == str(models / "PP-OCRv6_det_tiny.onnx")
    assert params["Rec.model_path"] == str(models / "PP-OCRv6_rec_tiny.onnx")
    assert params["Cls.model_path"] == str(
        models / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"
    )
    assert params["Det.model_type"] == params["Rec.model_type"] == "tiny"
    assert params["Global.text_score"] == 0.4
    assert params["Global.use_preprocess_img"] is False
    assert params["Det.limit_type"] == "max"
    assert params["Det.limit_side_len"] == 1920
    assert params["Det.box_thresh"] == 0.5
    assert params["Det.unclip_ratio"] == 1.6
    if threads is None:
        assert "EngineConfig.onnxruntime.intra_op_num_threads" not in params
        assert "EngineConfig.onnxruntime.inter_op_num_threads" not in params
    else:
        assert params["EngineConfig.onnxruntime.intra_op_num_threads"] == 2
        assert params["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
    assert fake_sdk["loaded"] == ["det", "cls", "rec"]
    first = engine._sdk.text_det.get_preprocess()
    second = engine._sdk.text_det.get_preprocess()
    assert first is not second
    assert first(np.zeros((80, 100, 3), np.uint8)).shape == (736, 928, 3)


def test_factory_does_not_retain_detector_after_engine_release(fake_sdk):
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        engine = rapidocr.create_engine(threads=2)
        detector = weakref.ref(engine._sdk.text_det)
        del engine
        assert detector() is None
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()


@pytest.mark.parametrize(
    "missing",
    (
        "PP-OCRv6_det_tiny.onnx",
        "PP-OCRv6_rec_tiny.onnx",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ),
)
def test_missing_local_model_fails_before_sdk_construction(fake_sdk, missing):
    (fake_sdk["models"] / missing).unlink()
    with pytest.raises(FileNotFoundError, match="缺少本地 OCR 模型") as error:
        rapidocr.create_engine()
    assert missing in str(error.value)
    assert fake_sdk["created"] == []


def test_factory_surfaces_model_load_failure_during_initialization(fake_sdk):
    fake_sdk["load_error"] = True
    with pytest.raises(ValueError, match="fixture model failed"):
        rapidocr.create_engine()
    assert fake_sdk["loaded"] == ["det", "cls", "rec"]


def test_factory_import_and_model_loading_do_not_import_configuration_or_devices(
    fake_sdk, monkeypatch
):
    original_import = builtins.__import__

    def guarded(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith(
            ("arknights_mower.utils.config", "arknights_mower.utils.device")
        ) or (
            name == "arknights_mower.utils"
            and {"config", "device"}.intersection(fromlist)
        ):
            pytest.fail(f"OCR 工厂不得导入配置或设备：{name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded)
    spec = importlib.util.spec_from_file_location(
        "isolated_ocr_factory", rapidocr.__file__
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._MODEL_DIR = fake_sdk["models"]
    assert module.create_engine(threads=2) is not None
    assert fake_sdk["loaded"] == ["det", "cls", "rec"]


BOXES = np.array([[[1.0, 2.0], [11.0, 2.0], [11.0, 7.0], [1.0, 7.0]]])


@pytest.mark.parametrize(
    "output,expected,elapsed",
    (
        (
            RapidOCROutput(
                boxes=BOXES,
                txts=("测试",),
                scores=(np.float64(0.9),),
                elapse_list=[0.1, 0.2, 0.3],
            ),
            [[[[1.0, 2.0], [11.0, 2.0], [11.0, 7.0], [1.0, 7.0]], "测试", 0.9]],
            [0.1, 0.2, 0.3],
        ),
        (
            RapidOCROutput(
                boxes=BOXES,
                txts=("测试",),
                scores=(np.float64(0.9),),
                elapse_list=[0.1, None, 0.3],
            ),
            [[[[1.0, 2.0], [11.0, 2.0], [11.0, 7.0], [1.0, 7.0]], "测试", 0.9]],
            [0.1, 0.0, 0.3],
        ),
        (
            TextRecOutput(txts=("测试",), scores=[np.float64(0.9)], elapse=0.3),
            [["测试", 0.9]],
            [0.3],
        ),
        (TextDetOutput(boxes=BOXES, elapse=0.1), [BOXES[0].tolist()], [0.1]),
        (
            TextClsOutput(cls_res=[["0", np.float64(0.9)]], elapse=0.2),
            [["0", 0.9]],
            [0.2],
        ),
    ),
)
def test_adapter_preserves_four_result_protocols(output, expected, elapsed):
    adapter = rapidocr._RapidOCRAdapter(lambda image, **options: output)
    result, actual_elapsed = adapter(np.zeros((10, 20, 3), np.uint8))
    assert result == expected
    assert actual_elapsed == elapsed
    assert all(type(value) is float for value in actual_elapsed)
    if not isinstance(output, TextDetOutput):
        assert type(result[0][-1]) is float


@pytest.mark.parametrize(
    "output",
    (
        RapidOCROutput(),
        TextRecOutput(),
        TextDetOutput(),
        TextClsOutput(),
        RapidOCROutput(boxes=np.empty((0, 4, 2)), txts=(), scores=()),
        TextRecOutput(txts=(), scores=[]),
        TextDetOutput(boxes=np.empty((0, 4, 2))),
        TextClsOutput(cls_res=[]),
    ),
)
def test_adapter_normalizes_empty_outputs(output):
    adapter = rapidocr._RapidOCRAdapter(lambda image, **options: output)
    assert adapter(np.zeros((10, 20, 3), np.uint8)) == (None, None)


def test_adapter_resets_mutable_sdk_options_after_explicit_request():
    state = {}

    def sdk(image, **options):
        state.update(options)
        return RapidOCROutput()

    adapter = rapidocr._RapidOCRAdapter(sdk, 0.4)
    image = np.zeros((10, 20, 3), np.uint8)
    adapter(
        image,
        use_det=False,
        use_cls=False,
        use_rec=False,
        text_score=0.7,
        box_thresh=0.6,
        unclip_ratio=2.0,
    )
    assert state == {
        "use_det": False,
        "use_cls": False,
        "use_rec": False,
        "text_score": 0.7,
        "box_thresh": 0.6,
        "unclip_ratio": 2.0,
    }
    for options in (
        {},
        {
            "use_det": None,
            "use_cls": None,
            "use_rec": None,
            "text_score": None,
            "box_thresh": None,
            "unclip_ratio": None,
        },
    ):
        adapter(image, **options)
        assert state == {
            "use_det": True,
            "use_cls": True,
            "use_rec": True,
            "text_score": 0.4,
            "box_thresh": 0.5,
            "unclip_ratio": 1.6,
        }


@pytest.mark.parametrize(
    "options,error",
    (
        ({"use_det": "yes"}, ValueError),
        ({"text_score": float("nan")}, ValueError),
        ({"unknown": 1}, TypeError),
    ),
)
def test_adapter_rejects_invalid_options_before_sdk_call(options, error):
    def sdk(*args, **kwargs):
        pytest.fail("非法选项不得进入模型")

    with pytest.raises(error):
        rapidocr._RapidOCRAdapter(sdk)(np.zeros((10, 20, 3), np.uint8), **options)


@pytest.fixture(scope="module")
def tiny_engine():
    return rapidocr.create_engine(threads=2)


def test_real_tiny_returns_existing_protocol_and_resets_mode_thresholds(tiny_engine):
    fixture = Path(__file__).with_name("fixtures") / "mastery_panel_carnelian.png"
    image = cv2.cvtColor(cv2.imread(str(fixture)), cv2.COLOR_BGR2RGB)
    recognized, elapsed = tiny_engine(image, use_det=False, use_cls=False, use_rec=True)
    assert recognized and recognized[0][0] == "[卡涅利安]沙缚镣锁"
    assert len(elapsed) == 1
    assert type(recognized[0][1]) is float
    full, elapsed = tiny_engine(image)
    assert full and full[0][1] == "[卡涅利安]沙缚镣锁"
    assert len(full[0][0]) == 4
    assert len(elapsed) == 3
    tiny_engine(
        image,
        use_det=False,
        use_cls=False,
        text_score=0.7,
        box_thresh=0.6,
        unclip_ratio=2.0,
    )
    restored, _ = tiny_engine(image)
    assert restored == full
    sdk = tiny_engine._sdk
    assert sdk.use_det is sdk.use_cls is sdk.use_rec is True
    assert sdk.text_score == 0.3
    assert sdk.text_det.postprocess_op.box_thresh == 0.5
    assert sdk.text_det.postprocess_op.unclip_ratio == 1.6


def test_real_tiny_blank_detection_returns_no_result(tiny_engine):
    assert tiny_engine(np.zeros((48, 441, 3), np.uint8), use_cls=False) == (None, None)
