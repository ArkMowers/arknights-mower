"""Encrypted local credentials, independent of configuration and GUI imports."""

import base64
import ctypes
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from uuid import uuid4

if __package__:
    from . import update_runtime
else:
    import update_runtime


class CredentialStoreError(RuntimeError):
    """A saved credential cannot be read or safely persisted."""


class _MissingPrivateKey(CredentialStoreError):
    """The system credential service confirmed that its entry does not exist."""


_KEY_ENV = "MOWER_CREDENTIAL_KEY_FILE"
_SERVICE = b"Arknights Mower"
_ACCOUNT = b"configuration-hybrid-private-v1"
_KEY_LOCK = threading.RLock()
_MAX_BYTES = 16 * 1024 * 1024
_SUITE = "HPKE-X-Wing-HKDF-SHA256-AES-256-GCM"
_CONTEXT = b"Arknights Mower credentials v1\x00"
_RUNTIME_ERROR = "当前加密运行库不支持混合凭据加密，请更新 Mower 及其运行环境"


def _private_directory():
    if configured := os.environ.get("XDG_DATA_HOME"):
        base = Path(configured)
    elif sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        base = Path.home() / ".local/share"
    return base / "arknights-mower/credentials"


def _key_lock_directory(provider, directory):
    # System-service entries are shared by the user, even across XDG data roots.
    if provider in ("keychain", "secret-service"):
        return Path.home() / ".local/share/arknights-mower/credential-service-lock"
    return directory


def protected_key_paths():
    directory = _private_directory()
    paths = [directory / name for name in ("private.key", "private.dpapi")]
    paths.extend(directory.glob("private.*.quarantined"))
    if configured := os.environ.get(_KEY_ENV):
        paths.append(Path(configured))
    absolute = {Path(os.path.abspath(path)) for path in paths}
    return frozenset(absolute | {path.resolve(strict=False) for path in absolute})


def _prepare_directory(path):
    if path.is_symlink():
        raise CredentialStoreError("凭据密钥目录不能是符号链接")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        if path.stat().st_uid != os.getuid():
            raise CredentialStoreError("凭据密钥目录不属于当前用户")
        path.chmod(0o700)


def _decode_private_key(encoded):
    key = base64.b64decode(encoded, altchars=b"-_", validate=True)
    if len(key) != 96:
        raise ValueError("Invalid hybrid private key length")
    return key


def _read_private_file(path, *, limit):
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    if path.is_symlink():
        raise CredentialStoreError("凭据密钥不能是符号链接")
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            raise CredentialStoreError("凭据密钥必须是普通文件")
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):
                raise CredentialStoreError("凭据密钥必须是普通文件")
            if os.name != "nt" and (info.st_uid != os.getuid() or info.st_mode & 0o077):
                raise CredentialStoreError(
                    "凭据密钥仅允许当前用户读取，请设置权限为 0600"
                )
            encoded = stream.read(limit + 1)
        if len(encoded) > limit:
            raise ValueError("Oversized private key")
        return encoded
    except (OSError, ValueError):
        raise CredentialStoreError("凭据密钥缺失、损坏或不可读；请恢复原密钥") from None


def _read_key(path, *, protected=False):
    encoded = _read_private_file(path, limit=8192 if protected else 1024)
    try:
        key = (
            _dpapi(encoded, decrypt=True)
            if protected
            else _decode_private_key(encoded.strip())
        )
        if len(key) != 96:
            raise ValueError("Invalid hybrid private key length")
        return key
    except (OSError, ValueError):
        raise CredentialStoreError("凭据密钥缺失、损坏或不可读；请恢复原密钥") from None


def _atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        update_runtime.replace_with_retry(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _dpapi(data, *, decrypt=False):
    if sys.platform != "win32":
        raise CredentialStoreError("这些凭据需要原 Windows 用户解密")
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_char))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.POINTER(Blob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(Blob),
    ]
    function.restype = wintypes.BOOL
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    outgoing = Blob()
    if not function(
        ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)
    ):
        raise CredentialStoreError("Windows 无法解密或保存凭据，请使用原 Windows 用户")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(outgoing.data)


def _mac_key(create):
    if sys.platform != "darwin":
        raise CredentialStoreError("这些凭据需要原 macOS 钥匙串")
    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    find = security.SecKeychainFindGenericPassword
    find.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
    ]
    find.restype = ctypes.c_int32
    free = security.SecKeychainItemFreeContent
    free.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    free.restype = ctypes.c_int32
    size, data = ctypes.c_uint32(), ctypes.c_void_p()
    result = find(
        None,
        len(_SERVICE),
        _SERVICE,
        len(_ACCOUNT),
        _ACCOUNT,
        ctypes.byref(size),
        ctypes.byref(data),
        None,
    )
    if result == 0:
        try:
            return ctypes.string_at(data, size.value)
        finally:
            free(None, data)
    if result == -25300 and not create:
        raise _MissingPrivateKey("macOS 钥匙串中不存在原凭据私钥")
    if result != -25300:
        raise CredentialStoreError("无法读取原 macOS 凭据密钥，请检查钥匙串")
    key = base64.b64encode(_hybrid_private()[1])
    add = security.SecKeychainAddGenericPassword
    add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_char_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    add.restype = ctypes.c_int32
    result = add(
        None, len(_SERVICE), _SERVICE, len(_ACCOUNT), _ACCOUNT, len(key), key, None
    )
    if result not in (0, -25299):
        raise CredentialStoreError("无法在 macOS 钥匙串保存凭据密钥")
    return _mac_key(False)


def _secret_service_key(create):
    executable = shutil.which("secret-tool")
    if not executable:
        raise CredentialStoreError(
            "无法访问原 Linux 密钥服务，请恢复 secret-tool 和登录会话"
        )
    attributes = [
        "application",
        "arknights-mower",
        "purpose",
        "configuration-hybrid-private-v1",
    ]
    try:
        result = subprocess.run(
            [executable, "lookup", *attributes],
            capture_output=True,
            timeout=15,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        missing = result.returncode == 1 and not result.stdout and not result.stderr
        if missing and not create:
            raise _MissingPrivateKey("Linux 密钥服务中不存在原凭据私钥")
        if not missing:
            raise CredentialStoreError("无法读取原 Linux 凭据密钥，请检查密钥服务")
        key = base64.b64encode(_hybrid_private()[1])
        result = subprocess.run(
            [executable, "store", "--label=Arknights Mower", *attributes],
            input=key,
            capture_output=True,
            timeout=15,
            check=False,
        )
        if result.returncode:
            raise CredentialStoreError("无法在 Linux 密钥服务保存凭据密钥")
        return _secret_service_key(False)
    except (OSError, subprocess.TimeoutExpired):
        raise CredentialStoreError("Linux 密钥服务不可用或响应超时") from None


def _key(provider, *, create=False):
    if provider == "key-file":
        value = os.environ.get(_KEY_ENV)
        if not value:
            raise CredentialStoreError(
                "请恢复 MOWER_CREDENTIAL_KEY_FILE 指向的原凭据密钥"
            )
        return _read_key(Path(value))
    directory = _private_directory()
    if directory.is_symlink():
        raise CredentialStoreError("凭据密钥目录不能是符号链接")
    # Reads never create a missing key or change the provider recorded in ciphertext.
    if not create:
        if provider in ("local-key", "dpapi"):
            name = "private.dpapi" if provider == "dpapi" else "private.key"
            return _read_key(directory / name, protected=provider == "dpapi")
        if provider == "keychain":
            return _decode_private_key(_mac_key(False))
        if provider == "secret-service":
            return _decode_private_key(_secret_service_key(False))
        raise CredentialStoreError("不支持此凭据加密方式")
    with _KEY_LOCK:
        _prepare_directory(directory)
        lock_directory = _key_lock_directory(provider, directory)
        _prepare_directory(lock_directory)
        with update_runtime.supervision_lock(lock_directory, timeout=15):
            initialized = lock_directory / f"{provider}.initialized"
            if initialized.is_symlink() or (
                initialized.exists() and not initialized.is_file()
            ):
                raise CredentialStoreError(
                    "凭据密钥初始化标记必须是普通文件，不能是符号链接"
                )
            if provider in ("keychain", "secret-service"):
                lookup = _mac_key if provider == "keychain" else _secret_service_key
                key = _decode_private_key(lookup(not initialized.exists()))
                if not initialized.exists():
                    _atomic_bytes(initialized, b"Mower credential key initialized\n")
                return key
            if provider not in ("local-key", "dpapi"):
                raise CredentialStoreError("不支持此凭据加密方式")
            name = "private.dpapi" if provider == "dpapi" else "private.key"
            path = directory / name
            if not path.exists() and not path.is_symlink():
                if initialized.exists():
                    raise CredentialStoreError("本机凭据密钥已丢失，请恢复原私钥文件")
                key = _hybrid_private()[1]
                encoded = _dpapi(key) if provider == "dpapi" else base64.b64encode(key)
                _atomic_bytes(path, encoded)
            key = _read_key(path, protected=provider == "dpapi")
            if not initialized.exists():
                _atomic_bytes(initialized, b"Mower credential key initialized\n")
            return key


def _provider():
    if os.environ.get(_KEY_ENV):
        return "key-file"
    if sys.platform == "win32":
        return "dpapi"
    if sys.platform == "darwin":
        return "keychain"
    if shutil.which("secret-tool") and os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return "secret-service"
    return "local-key"


def _recovery_result(
    provider, key_id, *, changed=False, created=False, quarantine=None
):
    return {
        "provider": provider,
        "key_id": key_id,
        "changed": changed,
        "created": created,
        "quarantine_path": str(quarantine) if quarantine is not None else None,
        "warning": (
            "其他使用同一私钥的 Mower 实例也受此恢复影响；原密文仍需原私钥才能解密。"
            if changed
            else "已保留现有可用私钥，其他共用该私钥的实例不受影响。"
        ),
    }


def _verify_recovery_key(suite, data=None):
    from cryptography.exceptions import InvalidTag

    private, raw, key_id = _hybrid_private(data)
    probe = b"Mower private key recovery verification"
    context = _CONTEXT + b"recovery"
    encrypted = suite.encrypt(probe, private.public_key(), info=context)
    try:
        valid = suite.decrypt(encrypted, private, info=context) == probe
    except InvalidTag:
        valid = False
    if not valid:
        raise CredentialStoreError("私钥校验失败，已保留原文件")
    return raw, key_id


def recover_private_key():
    """Explicitly recover the current provider without touching credential files."""
    try:
        from cryptography.exceptions import UnsupportedAlgorithm

        suite = _hybrid_suite()
        provider = _provider()
        if provider == "key-file":
            try:
                _, key_id = _verify_recovery_key(suite, _key(provider))
            except (CredentialStoreError, ValueError):
                raise CredentialStoreError(
                    "部署指定的私钥不可用；请管理员恢复 MOWER_CREDENTIAL_KEY_FILE "
                    "指定的文件，或移除该变量后重新打开恢复入口。不会自动改写此文件。"
                ) from None
            return _recovery_result(provider, key_id)

        with _KEY_LOCK:
            directory = _private_directory()
            _prepare_directory(directory)
            lock_directory = _key_lock_directory(provider, directory)
            _prepare_directory(lock_directory)
            with update_runtime.supervision_lock(lock_directory, timeout=15):
                marker = lock_directory / f"{provider}.initialized"
                if marker.is_symlink() or (marker.exists() and not marker.is_file()):
                    raise CredentialStoreError("凭据密钥初始化标记必须是普通文件")
                if provider in ("keychain", "secret-service"):
                    lookup = _mac_key if provider == "keychain" else _secret_service_key
                    changed = False
                    try:
                        encoded = lookup(False)
                    except _MissingPrivateKey:
                        _verify_recovery_key(suite)
                        encoded = lookup(True)
                        changed = True
                    try:
                        _, key_id = _verify_recovery_key(
                            suite, _decode_private_key(encoded)
                        )
                    except ValueError:
                        raise CredentialStoreError(
                            "系统凭据私钥条目损坏，已保留原条目；请先在系统密钥服务中恢复它。"
                        ) from None
                    if not marker.exists():
                        _atomic_bytes(marker, b"Mower credential key initialized\n")
                    return _recovery_result(
                        provider, key_id, changed=changed, created=changed
                    )
                if provider not in ("local-key", "dpapi"):
                    raise CredentialStoreError("不支持此凭据加密方式")
                protected = provider == "dpapi"
                path = directory / ("private.dpapi" if protected else "private.key")
                try:
                    path.lstat()
                except FileNotFoundError:
                    original = None
                else:
                    original = _read_private_file(
                        path, limit=8192 if protected else 1024
                    )
                if original is not None:
                    try:
                        raw = (
                            _dpapi(original, decrypt=True)
                            if protected
                            else _decode_private_key(original.strip())
                        )
                        if len(raw) != 96:
                            raise ValueError("Invalid hybrid private key length")
                    except (CredentialStoreError, ValueError):
                        pass
                    else:
                        _, key_id = _verify_recovery_key(suite, raw)
                        return _recovery_result(provider, key_id)
                raw, key_id = _verify_recovery_key(suite)
                encoded = _dpapi(raw) if protected else base64.b64encode(raw)
                if protected and _dpapi(encoded, decrypt=True) != raw:
                    raise CredentialStoreError("Windows 私钥保护校验失败，已保留原文件")
                quarantine = None
                if original is not None:
                    quarantine = path.with_name(
                        f"{path.name}.{uuid4().hex}.quarantined"
                    )
                    _atomic_bytes(quarantine, original)
                    if _read_private_file(quarantine, limit=8192) != original:
                        raise CredentialStoreError(
                            "原私钥隔离副本校验失败，已保留原文件"
                        )
                try:
                    _atomic_bytes(path, encoded)
                    if _read_key(path, protected=protected) != raw:
                        raise CredentialStoreError("恢复后的私钥校验失败，已保留原文件")
                    if not marker.exists():
                        _atomic_bytes(marker, b"Mower credential key initialized\n")
                except BaseException:
                    restore_credentials(path, original)
                    raise
                return _recovery_result(
                    provider,
                    key_id,
                    changed=True,
                    created=original is None,
                    quarantine=quarantine,
                )
    except ImportError:
        raise CredentialStoreError(_RUNTIME_ERROR) from None
    except UnsupportedAlgorithm:
        raise CredentialStoreError(_RUNTIME_ERROR) from None
    except (OSError, ValueError):
        raise CredentialStoreError(
            "私钥恢复未完成，原配置未更改；请检查文件权限或系统密钥服务"
        ) from None


def _hybrid_suite():
    try:
        from cryptography.hazmat.primitives.hpke import AEAD, KDF, KEM, Suite

        return Suite(KEM.MLKEM768_X25519, KDF.HKDF_SHA256, AEAD.AES_256_GCM)
    except ImportError:
        raise CredentialStoreError(_RUNTIME_ERROR) from None


def _hybrid_private(data=None):
    from cryptography.hazmat.primitives.asymmetric.mlkem import MLKEM768PrivateKey
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.hpke import MLKEM768X25519PrivateKey

    if data is None:
        mlkem = MLKEM768PrivateKey.generate()
        x25519 = X25519PrivateKey.generate()
        data = mlkem.private_bytes_raw() + x25519.private_bytes_raw()
    else:
        if len(data) != 96:
            raise ValueError("Invalid hybrid private key length")
        mlkem = MLKEM768PrivateKey.from_seed_bytes(data[:64])
        x25519 = X25519PrivateKey.from_private_bytes(data[64:])
    public = (
        mlkem.public_key().public_bytes_raw() + x25519.public_key().public_bytes_raw()
    )
    return (
        MLKEM768X25519PrivateKey(mlkem, x25519),
        data,
        hashlib.sha256(public).hexdigest(),
    )


def _header(provider, key_id):
    if provider not in {"dpapi", "keychain", "secret-service", "local-key", "key-file"}:
        raise ValueError("Unknown credential provider")
    if (
        not isinstance(key_id, str)
        or len(key_id) != 64
        or any(character not in "0123456789abcdef" for character in key_id)
    ):
        raise ValueError("Invalid credential key identifier")
    header = {"version": 1, "suite": _SUITE, "provider": provider, "key_id": key_id}
    context = _CONTEXT + json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return header, context


def encode_credentials(values):
    try:
        from cryptography.exceptions import UnsupportedAlgorithm
    except ImportError:
        raise CredentialStoreError(_RUNTIME_ERROR) from None

    try:
        if not isinstance(values, dict) or not all(
            isinstance(key, str) for key in values
        ):
            raise ValueError
        plaintext = json.dumps(values, ensure_ascii=False, allow_nan=False).encode(
            "utf-8"
        )
        if len(plaintext) > _MAX_BYTES:
            raise ValueError
        suite = _hybrid_suite()
        provider = _provider()
        private, _, key_id = _hybrid_private(_key(provider, create=True))
        envelope, context = _header(provider, key_id)
        ciphertext = suite.encrypt(
            plaintext,
            private.public_key(),
            info=context,
        )
        envelope["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        return json.dumps(envelope).encode("utf-8")
    except UnsupportedAlgorithm:
        raise CredentialStoreError(
            "当前加密后端不支持 ML-KEM，请更新 Mower 及其运行环境"
        ) from None
    except ImportError:
        raise CredentialStoreError(_RUNTIME_ERROR) from None
    except (OSError, ValueError, TypeError, RecursionError):
        raise CredentialStoreError("无法加密保存凭据，原配置尚未清除") from None


def decode_credentials(raw):
    try:
        if len(raw) > _MAX_BYTES * 2:
            raise ValueError
        envelope = json.loads(raw)
        if not isinstance(envelope, dict) or type(envelope.get("version")) is not int:
            raise ValueError
        if set(envelope) != {"version", "suite", "provider", "key_id", "ciphertext"}:
            raise ValueError
        if envelope["version"] != 1 or envelope["suite"] != _SUITE:
            raise ValueError
        _, context = _header(envelope["provider"], envelope["key_id"])
        from cryptography.exceptions import InvalidTag, UnsupportedAlgorithm

        try:
            suite = _hybrid_suite()
            provider = "key-file" if os.environ.get(_KEY_ENV) else envelope["provider"]
            private, _, key_id = _hybrid_private(_key(provider))
            if key_id != envelope["key_id"]:
                raise CredentialStoreError("凭据密钥与文件不匹配，请恢复原私钥")
            plaintext = suite.decrypt(
                base64.b64decode(envelope["ciphertext"], validate=True),
                private,
                info=context,
            )
        except UnsupportedAlgorithm:
            raise CredentialStoreError(
                "当前加密后端不支持 ML-KEM，请更新 Mower 及其运行环境"
            ) from None
        except InvalidTag:
            raise CredentialStoreError("凭据解密失败，请恢复原密钥和凭据文件") from None
        if len(plaintext) > _MAX_BYTES:
            raise ValueError
        values = json.loads(plaintext)
        if not isinstance(values, dict):
            raise ValueError
        return values
    except ImportError:
        raise CredentialStoreError(_RUNTIME_ERROR) from None
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise CredentialStoreError("凭据文件损坏或无法解密，已保留原文件") from None


def read_credentials(path):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {}
    except OSError:
        raise CredentialStoreError("凭据文件不可读，请检查文件权限") from None
    if not stat.S_ISREG(info.st_mode):
        raise CredentialStoreError("凭据文件必须是普通文件，不能是符号链接")
    limit = _MAX_BYTES * 2
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise CredentialStoreError("凭据文件必须是普通文件")
            if opened.st_size > limit:
                raise CredentialStoreError("凭据文件超过大小限制")
            raw = stream.read(limit + 1)
    except OSError:
        raise CredentialStoreError("凭据文件不可读，请检查文件权限") from None
    if len(raw) > limit:
        raise CredentialStoreError("凭据文件超过大小限制")
    return decode_credentials(raw)


def write_credentials(path, values):
    path = Path(path)
    # Do not replace unreadable credentials, including when the requested value is empty.
    read_credentials(path)
    previous = path.read_bytes() if path.is_file() else None
    raw = encode_credentials(values)
    if decode_credentials(raw) != values:
        raise CredentialStoreError("加密凭据验证失败，已保留原文件")
    try:
        _atomic_bytes(path, raw)
        if read_credentials(path) != values:
            raise CredentialStoreError("加密凭据写入后校验失败，请保留原配置并重试")
    except BaseException:
        if (path.read_bytes() if path.is_file() else None) != previous:
            restore_credentials(path, previous)
        raise


def restore_credentials(path, snapshot):
    """Restore trusted bytes captured before a multi-file transaction."""
    path = Path(path)
    if snapshot is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_bytes(path, snapshot)
