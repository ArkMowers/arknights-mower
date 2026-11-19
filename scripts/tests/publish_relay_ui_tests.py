import hashlib
import json

from scripts.publish_relay_ui import publication


def test_manifest_selects_exact_entries_and_distinguishes_replaced_public_file(
    tmp_path,
):
    build = "a" * 64
    (tmp_path / "relay-ui.json").write_text(json.dumps({"build": build}))
    (tmp_path / "index.html").write_text(
        '<script type="module" src="/assets/main-123.js"></script><link rel="stylesheet" href="/assets/main-456.css">'
    )
    (tmp_path / "assets").mkdir()
    for name in ("main-123.js", "main-456.css"):
        (tmp_path / "assets" / name).write_text("test")
    logo = tmp_path / "logo.png"
    logo.write_bytes(b"old")
    objects, old = publication(tmp_path)
    assert old["entry"] == "/assets/main-123.js" and old["styles"] == [
        "/assets/main-456.css"
    ]
    key = "files/" + hashlib.sha256(b"old").hexdigest() + ".png"
    assert objects[key] == logo and old["public"]["/logo.png"] == "/" + key
    logo.write_bytes(b"new")
    _, new = publication(tmp_path)
    assert old["public"]["/logo.png"] != new["public"]["/logo.png"]
