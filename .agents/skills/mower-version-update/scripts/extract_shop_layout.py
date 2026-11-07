"""Extract verified shop-button RectTransforms from ArknightsStudio dumps."""

import argparse
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from arknights_mower.utils.event_shop_data import (  # noqa: E402
    LAYOUTS,
    compile_activity_shops,
)


def field(text, name):
    match = re.search(r"^\t[^\n]+ " + re.escape(name) + r"\s*$", text, re.M)
    if not match:
        raise ValueError(f"客户端布局缺少字段：{name}")
    return re.split(r"\n\t[^\t\n]", text[match.end() :], maxsplit=1)[0]


def pointer(text, name):
    return int(re.search(r"m_PathID = (-?\d+)", field(text, name))[1])


def extract_chains(dump, asset_list, container, button_name="btn_shop"):
    records = {
        int(asset.findtext("PathID")): asset
        for asset in ET.parse(asset_list).getroot().findall("Asset")
    }

    def read(path_id, transform=None):
        asset = records[path_id]
        parent = PurePosixPath(asset.findtext("Container")).parent
        if parent.is_absolute() or ".." in parent.parts:
            raise ValueError("客户端资源路径无效")
        directory = Path(dump).joinpath(*parent.parts)
        name = asset.findtext("Name")
        candidates = [directory / (name + ".txt"), *directory.glob(name + "_#*.txt")]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            text = candidate.read_text("utf-8-sig")
            # Duplicate GameObject names get suffixed filenames in Studio exports.
            if transform is None or str(transform) in re.findall(
                r"m_PathID = (-?\d+)", field(text, "m_Component")
            ):
                return text
        raise ValueError(f"客户端布局导出文件缺失：{path_id} {name}")

    transforms_by_object = {}
    for path_id, asset in records.items():
        if (
            asset.findtext("Type") == "RectTransform"
            and asset.findtext("Container") == container
        ):
            transforms_by_object.setdefault(
                pointer(read(path_id), "m_GameObject"), []
            ).append(path_id)

    chains = []
    for path_id, asset in records.items():
        if (
            asset.findtext("Type") != "GameObject"
            or asset.findtext("Name") != button_name
            or asset.findtext("Container") != container
        ):
            continue
        transforms = transforms_by_object.get(path_id, [])
        if len(transforms) != 1:
            raise ValueError("商店按钮没有唯一 RectTransform")
        chain, seen = [], set()
        current = transforms[0]
        while current:
            if current in seen or len(seen) >= 64:
                raise ValueError("客户端布局层级循环或过深")
            seen.add(current)
            text = read(current)
            game_object = read(pointer(text, "m_GameObject"), current)
            node = {
                "id": current,
                "name": re.search(r'm_Name = "(.*)"', game_object)[1],
            }
            for key in (
                "m_AnchorMin",
                "m_AnchorMax",
                "m_SizeDelta",
                "m_AnchoredPosition",
                "m_Pivot",
                "m_LocalScale",
                "m_LocalRotation",
            ):
                node[key] = {
                    axis: float(value)
                    for axis, value in re.findall(
                        r"float ([xyzw]) = ([^\n]+)", field(text, key)
                    )
                }
            chain.append(node)
            current = pointer(text, "m_Father")
        chains.append(list(reversed(chain)))
    if not chains:
        raise ValueError("指定活动 prefab 中没有商店按钮")
    return chains


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in (
        "dump",
        "asset-list",
        "activity-table",
        "source-json",
        "downloaded-asset",
    ):
        parser.add_argument("--" + argument, required=True, type=Path)
    for argument in ("activity-id", "container", "confirm-text"):
        parser.add_argument("--" + argument, required=True)
    parser.add_argument("--button-name", default="btn_shop")
    parser.add_argument("--output", type=Path, default=LAYOUTS)
    args = parser.parse_args()
    source = json.loads(args.source_json.read_text("utf-8"))
    asset = args.downloaded_asset.read_bytes()
    with zipfile.ZipFile(io.BytesIO(asset)) as archive:
        bundle = archive.read(source["manifest"]["name"])
    if (
        len(asset) != source["manifest"]["totalSize"]
        or len(bundle) != source["manifest"]["abSize"]
        or hashlib.md5(bundle).hexdigest() != source["manifest"]["md5"]
        or source["prefab"] != args.container
        or not re.fullmatch(r"[0-9a-f]{40}", source["revision"])
    ):
        raise ValueError("客户端资源大小、摘要、prefab 或固定提交不匹配")
    activity = json.loads(args.activity_table.read_text("utf-8"))
    layouts = json.loads(args.output.read_text("utf-8")) if args.output.exists() else {}
    layouts[args.activity_id] = {
        "shop_id": activity["basicInfo"][args.activity_id]["templateShopId"],
        "confirm_text": args.confirm_text,
        "source": source,
        "chains": extract_chains(
            args.dump, args.asset_list, args.container, args.button_name
        ),
    }
    shops = compile_activity_shops(activity, layouts)
    args.output.write_text(
        json.dumps(layouts, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )
    print(json.dumps(shops, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
