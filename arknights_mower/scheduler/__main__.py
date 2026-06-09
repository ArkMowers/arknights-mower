import sys
import time

from arknights_mower.scheduler.bootstrap import run


def test_scene():
    from arknights_mower.utils.device.device import Device

    device = Device()
    from arknights_mower.utils.recognize import Recognizer

    recog = Recognizer(device)

    for i in range(20):
        recog.update()
        scene = recog.get_scene()
        from arknights_mower.utils.scene import SceneComment

        comment = SceneComment.get(scene, "UNKNOWN")
        print(f"[{i}] scene={scene} ({comment})")
        time.sleep(5)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test-scene":
        test_scene()
    elif len(sys.argv) > 1 and sys.argv[1] == "test-arrange":
        from arknights_mower.scheduler.bootstrap import run as _run
        _run(start_type="test")
    else:
        run()
