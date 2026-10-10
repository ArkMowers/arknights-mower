"""Write-ahead physical display preparation and guarded compensation.

The serial lease covers the whole run, including read-only runs. A pending
record is always compensated before a new run may use that serial.
"""

import time
import uuid
from datetime import datetime, timezone

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.preflight import parse_display_size


class PreparationError(MowerExit):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class PreparationSession:
    def __init__(self, io, store, locks):
        self.io = io
        self.store = store
        self.locks = locks
        self._lease = None
        self._record = None
        self._target_size = None
        self._physical = None
        self._adb_path = ""
        self._serial = ""
        self._status = None

    @property
    def prepared_size(self):
        return self._target_size

    def status(self):
        return dict(self._status) if self._status else None

    def begin(self, profile, authorized_serial=None):
        serial = profile.last_serial.strip()
        if not serial:
            raise PreparationError("target_required", "请选择明确的设备 serial。")
        if authorized_serial is not None and (
            profile.preset_id != "manual.physical" or authorized_serial != serial
        ):
            raise PreparationError(
                "preparation_not_authorized",
                "临时整备授权必须对应本次选择的实体设备 serial。",
            )
        if self._lease is not None:
            raise PreparationError("preparation_locked", "当前整备会话尚未结束。")
        try:
            self._lease = self.locks.acquire(serial)
        except Exception as exc:
            raise PreparationError(
                "preparation_locked",
                f"设备 {serial} 正由另一个进程使用，无法开始任务。",
            ) from exc
        self._serial, self._adb_path = serial, profile.adb_path
        self._status = None
        try:
            self._record = self.store.load(serial)
            if self._record is not None:
                self._restore()
            if authorized_serial is None:
                return
            dimensions = self._observe()
            physical = dimensions["Physical"]
            if min(physical) < 1080 or max(physical) < 1920:
                raise PreparationError(
                    "preparation_size_unsupported",
                    "设备 Physical 尺寸无法容纳 1920×1080。",
                )
            target = [1920, 1080] if physical[0] > physical[1] else [1080, 1920]
            self._target_size, self._physical = target, physical
            if dimensions.get("Override", physical) == target:
                # Do not manufacture an unobservable forced-size setting when
                # wm size already reports the target. Keep the lease and still
                # validate the actual frame and input surface for this run.
                return
            now = self._now()
            record = {
                "schema": 1,
                "serial": serial,
                "run_id": uuid.uuid4().hex,
                "physical": physical,
                "override_existed": "Override" in dimensions,
                "original_override": dimensions.get("Override"),
                "written": target,
                "stage": "intent",
                "created_at": now,
                "updated_at": now,
                "last_error": None,
            }
            self.store.save(record)
            self._record = record
            self._publish()
            # Recheck immediately before writing, after the durable intent.
            if self._observe() != dimensions:
                raise PreparationError(
                    "recovery_conflict", "写入前设备显示状态发生变化，请确认后重试。"
                )
            self.io.set_size(self._adb_path, serial, target)
            self._stage("written")
            self.verify_display()
        except MowerExit:
            raise
        except Exception as exc:
            raise PreparationError(
                "preparation_failed", f"无法安全建立临时整备会话：{exc}"
            ) from exc

    def _observe(self):
        states = [
            state
            for serial, state in self.io.devices(self._adb_path, self._serial)
            if serial == self._serial
        ]
        if states != ["device"]:
            raise PreparationError(
                "recovery_pending",
                f"设备 {self._serial} 不唯一或未在线；恢复记录会保留，禁止新任务。",
            )
        try:
            return parse_display_size(
                self.io.display_size(self._adb_path, self._serial)
            )
        except ValueError as exc:
            raise PreparationError(
                "invalid_size", "无法明确解析 Physical 和 Override。"
            ) from exc

    def verify_display(self):
        if self.prepared_size is None:
            return
        dimensions = self._observe()
        if dimensions["Physical"] != self._physical or self._observable_override(
            dimensions.get("Override"), self._physical
        ) != self._observable_override(self.prepared_size, self._physical):
            raise PreparationError(
                "recovery_conflict", "临时尺寸已被其他程序修改，请人工确认显示状态。"
            )

    def validate(self):
        if self.prepared_size is None:
            return
        self.verify_display()
        try:
            surface = self.io.input_surface(self._adb_path, self._serial)
        except MowerExit:
            raise
        except Exception as exc:
            raise PreparationError(
                "input_surface_mismatch", f"无法验证默认显示的输入面：{exc}"
            ) from exc
        if tuple(surface) != (1920, 1080):
            raise PreparationError(
                "input_surface_mismatch",
                "默认显示的输入面不是横屏 1920×1080，请在设备上打开横屏游戏后重试。",
            )
        if self._record is not None:
            self._stage("validated")
        else:
            self._status = {
                "serial": self._serial,
                "stage": "validated",
                "last_error": None,
            }

    @staticmethod
    def _observable_override(value, physical):
        # Android omits Override when base size equals Physical. Compare the
        # observable state without mistaking our native-size write for a conflict.
        return None if value == physical else value

    def _restore(self):
        try:
            dimensions = self._observe()
            record = self._record
            current = self._observable_override(
                dimensions.get("Override"), record["physical"]
            )
            original = self._observable_override(
                record["original_override"], record["physical"]
            )
            if dimensions["Physical"] != record["physical"] or current not in (
                self._observable_override(record["written"], record["physical"]),
                original,
            ):
                raise PreparationError(
                    "recovery_conflict",
                    f"设备 {self._serial} 存在恢复冲突；不会覆盖第三方显示修改，请人工确认。",
                )
            if current != original:
                self._stage("restoring")
                # Writing the journal can take time; keep the guard adjacent
                # to the device mutation, not merely before filesystem I/O.
                if self._observe() != dimensions:
                    raise PreparationError(
                        "recovery_conflict", "恢复前显示状态发生变化，请人工确认。"
                    )
                self.io.set_size(
                    self._adb_path, self._serial, record["original_override"]
                )
            restored = self._observe()
            if (
                restored["Physical"] != record["physical"]
                or self._observable_override(
                    restored.get("Override"), record["physical"]
                )
                != original
            ):
                raise PreparationError(
                    "recovery_conflict", "恢复后的显示状态与原值不一致，请人工确认。"
                )
            self.store.clear(self._serial)
            self._record = None
            self._status = {
                "serial": self._serial,
                "stage": "restored",
                "last_error": None,
            }
        except Exception as exc:
            code = getattr(exc, "code", "recovery_pending")
            stage = "conflict" if code == "recovery_conflict" else "pending"
            try:
                self._stage(stage, str(exc))
            except Exception as store_error:
                exc.add_note(f"保留恢复记录时出错：{store_error}")
            if isinstance(exc, PreparationError):
                raise
            raise PreparationError(
                "recovery_pending", f"设备恢复未完成，记录已保留：{exc}"
            ) from exc

    def close(self):
        if self._lease is None:
            return
        try:
            if self._record is not None:
                # Cancellation and an exhausted startup budget must not prevent
                # compensation. Restoration has its own bounded I/O deadline.
                deadline = time.monotonic() + 30

                def remaining():
                    seconds = deadline - time.monotonic()
                    if seconds <= 0:
                        raise TimeoutError("恢复显示状态超时")
                    return seconds

                with device_io_budget(remaining):
                    self._restore()
        finally:
            lease, self._lease = self._lease, None
            self._record = None
            self._target_size = None
            self._physical = None
            lease.close()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _stage(self, stage, error=None):
        record = {
            **self._record,
            "stage": stage,
            "updated_at": self._now(),
            "last_error": error,
        }
        self.store.save(record)
        self._record = record
        self._publish()

    def _publish(self):
        self._status = {
            key: self._record[key] for key in ("serial", "stage", "last_error")
        }
