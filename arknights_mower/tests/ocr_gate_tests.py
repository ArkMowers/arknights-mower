"""OCR 引擎选择门控的离线回归；不加载真实模型。"""

import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

from arknights_mower.utils import ocr_shared, rapidocr


@pytest.fixture(autouse=True)
def isolated_engine(monkeypatch):
    monkeypatch.setattr(rapidocr, "engine", None)
    monkeypatch.delenv(rapidocr.OCR_MODE_ENV, raising=False)
    monkeypatch.setattr(rapidocr, "_log_engine_choice", lambda *args: None)


class _Engines:
    def __init__(self):
        self.local = []
        self.shared = []


@pytest.fixture
def engines(monkeypatch):
    record = _Engines()

    class Local:
        def __init__(self, score):
            self.score = score
            record.local.append(self)

    class Shared:
        def __init__(self, score):
            self.score = score
            record.shared.append(self)

    monkeypatch.setattr(rapidocr, "_LocalOCREngine", Local)
    monkeypatch.setattr(ocr_shared, "SharedOCREngine", Shared)
    return record


def test_single_instance_builds_local_engine(monkeypatch, engines):
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 1)
    rapidocr.initialize_ocr()
    assert engines.local and not engines.shared
    assert rapidocr.engine is engines.local[0]
    assert engines.local[0].score == rapidocr.DEFAULT_TEXT_SCORE


def test_two_instances_build_shared_engine(monkeypatch, engines):
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 2)
    rapidocr.initialize_ocr(0.4)
    assert not engines.local
    assert engines.shared and rapidocr.engine is engines.shared[0]
    assert engines.shared[0].score == 0.4


@pytest.mark.parametrize("mode", ["local", "shared", " LOCAL "])
def test_mode_override_skips_instance_detection(monkeypatch, engines, mode):
    monkeypatch.setenv(rapidocr.OCR_MODE_ENV, mode)
    monkeypatch.setattr(
        rapidocr,
        "_live_mower_instance_count",
        lambda: pytest.fail("显式模式不应读取实例登记"),
    )
    rapidocr.initialize_ocr()
    expected = engines.local if mode.strip().lower() == "local" else engines.shared
    assert len(expected) == 1
    assert rapidocr.engine is expected[0]


def test_blank_mode_falls_back_to_auto(monkeypatch, engines):
    monkeypatch.setenv(rapidocr.OCR_MODE_ENV, "   ")
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 2)
    rapidocr.initialize_ocr()
    assert rapidocr.engine is engines.shared[0]


def test_invalid_mode_raises_and_keeps_existing_engine(monkeypatch, engines):
    existing = object()
    monkeypatch.setattr(rapidocr, "engine", existing)
    monkeypatch.setenv(rapidocr.OCR_MODE_ENV, "bogus")
    with pytest.raises(ValueError, match=rapidocr.OCR_MODE_ENV):
        rapidocr.initialize_ocr()
    assert rapidocr.engine is existing


def test_each_call_reevaluates_and_switches(monkeypatch, engines):
    counts = iter([1, 2, 1])
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: next(counts))

    rapidocr.initialize_ocr()
    first = rapidocr.engine
    assert first is engines.local[0]

    rapidocr.initialize_ocr()
    assert rapidocr.engine is engines.shared[0]

    rapidocr.initialize_ocr()
    assert rapidocr.engine is engines.local[1]
    assert len(engines.local) == 2


def test_switch_releases_previous_engine(monkeypatch):
    refs = []

    class Local:
        def __init__(self, score):
            refs.append(weakref.ref(self))

    class Shared:
        def __init__(self, score):
            self.score = score

    monkeypatch.setattr(rapidocr, "_LocalOCREngine", Local)
    monkeypatch.setattr(ocr_shared, "SharedOCREngine", Shared)
    counts = iter([1, 2])
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: next(counts))

    rapidocr.initialize_ocr()
    first = rapidocr.engine
    assert refs[0]() is first
    del first

    rapidocr.initialize_ocr()
    assert refs[0]() is None


@pytest.mark.parametrize("score", [-0.1, 1.1, "0.3", None, True])
def test_invalid_score_is_rejected_before_mode_detection(monkeypatch, score):
    monkeypatch.setattr(
        rapidocr,
        "_live_mower_instance_count",
        lambda: pytest.fail("score 校验必须先于模式判定"),
    )
    with pytest.raises(ValueError, match="0 到 1"):
        rapidocr.initialize_ocr(score)
    assert rapidocr.engine is None


@pytest.mark.parametrize("score", [0, 1])
def test_score_boundaries_are_accepted(monkeypatch, engines, score):
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 1)
    rapidocr.initialize_ocr(score)
    assert engines.local[0].score == score


def test_local_engine_accepts_shared_client_call_options(monkeypatch):
    created = []
    calls = []

    class Underlying:
        def __call__(self, image, **kwargs):
            calls.append((image, kwargs))
            return ([[[0, 0], "name", 0.9]], [0.1])

    def factory(score):
        created.append(score)
        return Underlying()

    monkeypatch.setattr(rapidocr, "create_engine", factory)
    engine = rapidocr._LocalOCREngine(0.4)
    image = object()

    assert engine(image, use_det=False, use_cls=False, use_rec=True) == (
        [[[0, 0], "name", 0.9]],
        [0.1],
    )
    assert created == [0.4]
    assert calls[0][0] is image
    assert calls[0][1] == {
        "use_det": False,
        "use_cls": False,
        "use_rec": True,
        "text_score": 0.4,
        "box_thresh": rapidocr.DEFAULT_BOX_THRESH,
        "unclip_ratio": rapidocr.DEFAULT_UNCLIP_RATIO,
    }

    engine(image, text_score=0.7, box_thresh=0.6, unclip_ratio=2.0)
    assert calls[1][1]["text_score"] == 0.7
    assert calls[1][1]["box_thresh"] == 0.6
    assert calls[1][1]["unclip_ratio"] == 2.0

    with pytest.raises(ValueError, match="参数无效"):
        engine(image, unknown=True)
    with pytest.raises(ValueError, match="阈值无效"):
        engine(image, text_score=2)
    with pytest.raises(ValueError, match="开关"):
        engine(image, use_det="yes")


def test_failed_initialization_can_retry(monkeypatch):
    attempts = []

    class Local:
        def __init__(self, score):
            attempts.append(score)
            if len(attempts) == 1:
                raise RuntimeError("model unavailable")

    monkeypatch.setattr(rapidocr, "_LocalOCREngine", Local)
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 1)

    with pytest.raises(RuntimeError, match="model unavailable"):
        rapidocr.initialize_ocr()
    assert rapidocr.engine is None

    rapidocr.initialize_ocr()
    assert isinstance(rapidocr.engine, Local)
    assert attempts == [rapidocr.DEFAULT_TEXT_SCORE, rapidocr.DEFAULT_TEXT_SCORE]


def test_failed_switch_keeps_previous_engine(monkeypatch, engines):
    counts = iter([1, 2])
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: next(counts))
    rapidocr.initialize_ocr()
    previous = rapidocr.engine

    class BrokenShared:
        def __init__(self, score):
            raise RuntimeError("service unavailable")

    monkeypatch.setattr(ocr_shared, "SharedOCREngine", BrokenShared)
    with pytest.raises(RuntimeError, match="service unavailable"):
        rapidocr.initialize_ocr()
    assert rapidocr.engine is previous


def test_instance_count_filters_kind_and_data_root(monkeypatch):
    from arknights_mower.utils import path as mower_path
    from arknights_mower.utils import update_runtime as runtime

    root = Path.cwd() / "ocr-gate-data-root"
    records = [
        {"kind": "instance", "data_dir": ""},
        {"kind": "instance", "data_dir": str(root)},
        {"kind": "instance", "data_dir": str(root / "other")},
        {"kind": "manager", "data_dir": ""},
        {"kind": "ocr-service", "data_dir": ""},
        {"kind": "instance", "data_dir": "data", "cwd": str(root)},
    ]
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: records)
    monkeypatch.delenv("MOWER_DATA_DIR", raising=False)
    monkeypatch.setattr(mower_path, "_data_dir", root)
    assert rapidocr._live_mower_instance_count() == 1

    monkeypatch.setenv("MOWER_DATA_DIR", str(root))
    assert rapidocr._live_mower_instance_count() == 1

    monkeypatch.setenv("MOWER_DATA_DIR", "data")
    monkeypatch.setattr(mower_path, "_data_dir", root / "data")
    assert rapidocr._live_mower_instance_count() == 1


def test_instance_count_uses_a_short_scan_budget(monkeypatch):
    from arknights_mower.utils import update_runtime as runtime

    calls = []

    def scan(**kwargs):
        calls.append(kwargs)
        return []

    monkeypatch.setattr(runtime, "instances", scan)
    assert rapidocr._live_mower_instance_count() == 0
    assert rapidocr.INSTANCE_SCAN_TIMEOUT > 0
    assert calls == [{"timeout": rapidocr.INSTANCE_SCAN_TIMEOUT, "strict": False}]


def test_blank_data_dir_counts_as_the_install_default_root(monkeypatch):
    from arknights_mower.utils import path as mower_path
    from arknights_mower.utils import update_runtime as runtime

    root = Path.cwd() / "ocr-gate-default-data-root"
    records = [
        {"kind": "instance", "data_dir": ""},
        {"kind": "instance", "data_dir": str(root)},
    ]
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: records)
    monkeypatch.delenv("MOWER_DATA_DIR", raising=False)
    monkeypatch.setattr(mower_path, "_app_dir", root)
    monkeypatch.setattr(mower_path, "_data_dir", root)

    assert rapidocr._live_mower_instance_count() == 2


def test_distinct_data_roots_count_one_each(monkeypatch):
    from arknights_mower.utils import path as mower_path
    from arknights_mower.utils import update_runtime as runtime

    first = Path.cwd() / "ocr-gate-first-data-root"
    second = Path.cwd() / "ocr-gate-second-data-root"
    records = [
        {"kind": "instance", "data_dir": str(first)},
        {"kind": "instance", "data_dir": str(second)},
    ]
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: records)
    monkeypatch.delenv("MOWER_DATA_DIR", raising=False)

    monkeypatch.setattr(mower_path, "_app_dir", first)
    monkeypatch.setattr(mower_path, "_data_dir", first)
    assert rapidocr._live_mower_instance_count() == 1

    monkeypatch.setattr(mower_path, "_app_dir", second)
    monkeypatch.setattr(mower_path, "_data_dir", second)
    assert rapidocr._live_mower_instance_count() == 1


def test_instance_scan_failure_degrades_to_local(monkeypatch, engines):
    from arknights_mower.utils import update_runtime as runtime

    def fail(**kwargs):
        raise OSError("denied")

    logged = []
    monkeypatch.setattr(runtime, "instances", fail)
    monkeypatch.setattr(
        rapidocr,
        "_log_engine_choice",
        lambda mode, evidence, previous: logged.append((mode, evidence)),
    )

    rapidocr.initialize_ocr()
    assert rapidocr.engine is engines.local[0]
    assert logged[0][0] == "local"
    assert "失败" in logged[0][1]


def test_choice_log_is_not_repeated_without_a_mode_change(monkeypatch, engines):
    logged = []
    monkeypatch.setattr(
        rapidocr,
        "_log_engine_choice",
        lambda mode, evidence, previous: logged.append((mode, evidence, previous)),
    )
    counts = iter([1, 1, 2])
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: next(counts))

    rapidocr.initialize_ocr()
    rapidocr.initialize_ocr()
    assert len(logged) == 1
    assert logged[0][:2] == ("local", "存活 Mower 实例数 1")
    assert logged[0][2] is None

    rapidocr.initialize_ocr()
    assert len(logged) == 2
    assert logged[1][0] == "shared"
    assert logged[1][2] == "local"


def test_concurrent_initialization_builds_one_engine(monkeypatch):
    entered, release = Event(), Event()
    created = []

    class Local:
        def __init__(self, score):
            created.append(self)
            entered.set()
            assert release.wait(3)

    monkeypatch.setattr(rapidocr, "_LocalOCREngine", Local)
    monkeypatch.setattr(rapidocr, "_live_mower_instance_count", lambda: 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(rapidocr.initialize_ocr) for _ in range(4)]
        try:
            assert entered.wait(2)
        finally:
            release.set()
        for future in futures:
            future.result(timeout=5)
    assert len(created) == 1
    assert rapidocr.engine is created[0]
