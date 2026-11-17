"""The first credential format uses one persistent hybrid recipient private key."""

import base64
import builtins
import hashlib
import json
import os
from types import SimpleNamespace

import pytest
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hpke
from cryptography.hazmat.primitives.asymmetric import mlkem, x25519

from arknights_mower.utils import credential_store as store

SUITE_NAME = "HPKE-X-Wing-HKDF-SHA256-AES-256-GCM"


@pytest.fixture
def private_key(tmp_path, monkeypatch):
    directory = tmp_path / "private-keys"
    directory.mkdir()
    path = directory / "private.key"
    path.write_bytes(base64.b64encode(os.urandom(96)))
    path.chmod(0o600)
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(path))
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    return path


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def _independent_decrypt(raw, key):
    envelope = json.loads(raw)
    private_bytes = base64.b64decode(key, validate=True)
    assert len(private_bytes) == 96
    mlkem_private = mlkem.MLKEM768PrivateKey.from_seed_bytes(private_bytes[:64])
    x25519_private = x25519.X25519PrivateKey.from_private_bytes(private_bytes[64:])
    private = hpke.MLKEM768X25519PrivateKey(mlkem_private, x25519_private)
    public = (
        mlkem_private.public_key().public_bytes_raw()
        + x25519_private.public_key().public_bytes_raw()
    )
    header = {
        "version": 1,
        "suite": SUITE_NAME,
        "provider": "key-file",
        "key_id": hashlib.sha256(public).hexdigest(),
    }
    assert set(envelope) == {*header, "ciphertext"}
    assert all(envelope[name] == value for name, value in header.items())
    context = b"Arknights Mower credentials v1\x00" + json.dumps(
        header, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    suite = hpke.Suite(
        hpke.KEM.MLKEM768_X25519,
        hpke.KDF.HKDF_SHA256,
        hpke.AEAD.AES_256_GCM,
    )
    plaintext = suite.decrypt(
        base64.b64decode(envelope["ciphertext"], validate=True), private, info=context
    )
    return json.loads(plaintext)


def test_repeated_save_uses_same_private_key_and_fresh_hpke_ciphertext(
    tmp_path, private_key
):
    path = tmp_path / "mower.secrets.json"
    values = {
        "token": "synthetic-hybrid-token",
        "accounts": [{"name": "测试账号", "enabled": False}],
        "empty": "",
    }
    original_key = private_key.read_bytes()
    store.write_credentials(path, values)
    first = path.read_bytes()
    store.write_credentials(path, values)
    second = path.read_bytes()
    assert _independent_decrypt(first, original_key) == values
    assert _independent_decrypt(second, original_key) == values
    assert first != second
    assert json.loads(first)["key_id"] == json.loads(second)["key_id"]
    assert base64.b64decode(original_key) not in first + second
    assert original_key not in first + second
    assert b"synthetic-hybrid-token" not in first + second
    assert private_key.read_bytes() == original_key
    store.write_credentials(path, {})
    assert _independent_decrypt(path.read_bytes(), original_key) == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", True),
        ("version", 0),
        ("version", 2),
        ("suite", "HPKE-X-Wing-HKDF-SHA256-AES-128-GCM"),
        ("provider", "local-key"),
        ("provider", "unknown"),
        ("key_id", "0" * 64),
        ("key_id", "malformed"),
        ("ciphertext", "not base64!"),
        ("wrapped_key", "unexpected"),
    ],
)
def test_envelope_metadata_changes_refuse_reads_and_empty_writes(
    tmp_path, private_key, field, value
):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "keep-original-token"})
    envelope = json.loads(path.read_bytes())
    envelope[field] = value
    damaged = _json_bytes(envelope)
    path.write_bytes(damaged)
    original_key = private_key.read_bytes()
    for operation in (
        lambda: store.read_credentials(path),
        lambda: store.write_credentials(path, {}),
    ):
        with pytest.raises(store.CredentialStoreError):
            operation()
        assert path.read_bytes() == damaged
        assert private_key.read_bytes() == original_key


@pytest.mark.parametrize(
    "offset", [0, 1088, 1120, -1], ids=["mlkem", "x25519", "payload", "tag"]
)
def test_hybrid_ciphertext_tampering_preserves_file(tmp_path, private_key, offset):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "keep-original-token"})
    envelope = json.loads(path.read_bytes())
    damaged = bytearray(base64.b64decode(envelope["ciphertext"]))
    damaged[offset] ^= 1
    envelope["ciphertext"] = base64.b64encode(damaged).decode("ascii")
    original = _json_bytes(envelope)
    path.write_bytes(original)
    with pytest.raises(store.CredentialStoreError):
        store.read_credentials(path)
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {})
    assert path.read_bytes() == original


def test_provider_header_is_authenticated_even_with_the_same_private_key(
    tmp_path, private_key, monkeypatch
):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "context-bound-token"})
    envelope = json.loads(path.read_bytes())
    envelope["provider"] = "keychain"
    monkeypatch.setattr(store, "_mac_key", lambda create: private_key.read_bytes())
    path.write_bytes(_json_bytes(envelope))
    with pytest.raises(store.CredentialStoreError, match="解密失败"):
        store.read_credentials(path)


def test_replacement_key_id_cannot_make_an_unrelated_private_key_decrypt(
    tmp_path, private_key
):
    path = tmp_path / "mower.secrets.json"
    store.write_credentials(path, {"token": "original"})
    envelope = json.loads(path.read_bytes())
    replacement = os.urandom(96)
    private_key.write_bytes(base64.b64encode(replacement))
    with pytest.raises(store.CredentialStoreError, match="不匹配"):
        store.read_credentials(path)
    public = (
        mlkem.MLKEM768PrivateKey.from_seed_bytes(replacement[:64])
        .public_key()
        .public_bytes_raw()
        + x25519.X25519PrivateKey.from_private_bytes(replacement[64:])
        .public_key()
        .public_bytes_raw()
    )
    envelope["key_id"] = hashlib.sha256(public).hexdigest()
    path.write_bytes(_json_bytes(envelope))
    with pytest.raises(store.CredentialStoreError):
        store.read_credentials(path)


@pytest.mark.parametrize("failure", ["missing_module", "suite", "key_generation"])
def test_unsupported_runtime_never_writes_credentials_or_provisions_private_key(
    tmp_path, monkeypatch, failure
):
    monkeypatch.delenv("MOWER_CREDENTIAL_KEY_FILE")
    directory = tmp_path / "private-keys"
    monkeypatch.setattr(store, "_private_directory", lambda: directory)
    monkeypatch.setattr(store, "_provider", lambda: "local-key")

    def unavailable(*args, **kwargs):
        raise UnsupportedAlgorithm("synthetic unavailable backend")

    if failure == "missing_module":
        original_import = builtins.__import__

        def without_hpke(name, *args, **kwargs):
            if name == "cryptography.hazmat.primitives.hpke":
                raise ImportError("synthetic older cryptography")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", without_hpke)
    elif failure == "suite":
        monkeypatch.setattr(hpke, "Suite", unavailable)
    else:
        monkeypatch.setattr(
            mlkem, "MLKEM768PrivateKey", SimpleNamespace(generate=unavailable)
        )
    path = tmp_path / "mower.secrets.json"
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {"token": "must-not-be-written"})
    assert not path.exists()
    assert not (directory / "private.key").exists()
    assert not (directory / "local-key.initialized").exists()


def test_missing_explicit_private_key_is_never_created(tmp_path, monkeypatch):
    private = tmp_path / "deployment/private.key"
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(private))
    path = tmp_path / "mower.secrets.json"
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(path, {"token": "original"})
    assert not private.parent.exists()
    assert not path.exists()


@pytest.mark.parametrize("length", [0, 32, 95, 97, 2048])
def test_explicit_key_requires_exactly_96_decoded_bytes(tmp_path, monkeypatch, length):
    private = tmp_path / "private.key"
    private.write_bytes(base64.b64encode(os.urandom(length)))
    private.chmod(0o600)
    monkeypatch.setenv("MOWER_CREDENTIAL_KEY_FILE", str(private))
    with pytest.raises(store.CredentialStoreError):
        store.write_credentials(tmp_path / "mower.secrets.json", {"token": "original"})


def test_same_private_key_reads_multiple_files_without_changing_them(
    tmp_path, private_key
):
    paths = [tmp_path / name for name in ("mower.secrets.json", "network.secrets.json")]
    for index, path in enumerate(paths):
        store.write_credentials(path, {"token": f"synthetic-{index}"})
    before = [path.read_bytes() for path in paths]
    key = private_key.read_bytes()
    for index, path in enumerate(paths):
        assert store.read_credentials(path) == {"token": f"synthetic-{index}"}
    assert [path.read_bytes() for path in paths] == before
    assert private_key.read_bytes() == key
