"""官方导航步骤录制脚本（维护者工具，不随程序分发）。

用法：:

    python scripts/record_official_nav_steps.py               # 自动选最新活动关
    python scripts/record_official_nav_steps.py PA-1 PA-2      # 或显式指定关卡
    python scripts/record_official_nav_steps.py -o my.json --notes-output notes.md

连模拟器后，对目标关卡调现有 AI 自学导航（``NavigationSolver.run``）走一遍，
成功且记录到步骤的关卡导出成标准 ``nav_steps.json``（stages + patterns，条目结构与
``nav_trie_steps.json`` 一致），并生成 ``release_notes.md``（#198 Release notes 用，
tag 上有它则原样采用）与推荐发布 tag（v北京日期-内容哈希，匹配客户端 _TAG_RE）。
录制默认**复用优先**：先回放既有路由并记录步骤——同一 zone 的兄弟关（如 AT-*）共享
前置步骤，命中即省去重新构建；回放失败（旧路由已失效）才回退 OCR+LLM 在线构建。
``--force-record`` 则跳过复用、每关全量冷构建。

不传关卡时自动选关：拉 MowerHotUpdate 最新 ``stage_data.json``，按刷理智周计划同一套
规则（``weekly_stage.select_latest_activity_stages``：最新活动普通关后三关 + 掉固源岩/
装置）选出要录制的关。脚本只准备文件 + 打印发布 git 命令，**不自动推送**。

注意：每关跑完 ``NavigationSolver.run`` 内部的 ``persist_nav_steps`` 也会把这一步刷新到
本机 ``nav_trie_steps.json``（对维护者本机无害——官方导出是另一份文件，两者互不覆盖）。
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 直接 `python scripts/record_official_nav_steps.py` 运行：脚本在 scripts/ 下，
# sys.path[0] 是 scripts/ 而非仓库根，手动把仓库根加进去才能 import arknights_mower
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from arknights_mower.utils.hot_update import HOT_UPDATE_REPO
from arknights_mower.utils.log import logger
from arknights_mower.utils.nav_steps import (
    build_official_steps,
    load_nav_file,
    merge_official_steps,
)
from arknights_mower.utils.weekly_stage import _materials, select_latest_activity_stages

RAW_BASE = f"https://raw.githubusercontent.com/{HOT_UPDATE_REPO}/main"


def collect_records(
    stages: list[str], navigate
) -> tuple[list[dict], list[dict], list[dict]]:
    """逐关导航，收集成功记录 / 失败清单 / 无步骤跳过清单。

    ``navigate(stage)`` 返回记录 dict（含 stage / stage_type / steps）表示该关跑完；返回
    None 或抛异常视为该关失败。成功但无步骤（命中快捷入口、本就在目标）归入 skipped——
    不算失败：官方没录到步骤可由现有 AI 自学兜底。返回 (成功记录, 失败清单, 跳过清单)。
    """
    ok: list[dict] = []
    failed: list[dict] = []
    skipped: list[dict] = []
    now = datetime.now().isoformat(timespec="seconds")
    for stage in stages:
        logger.info(f"录制导航步骤：{stage}")
        try:
            rec = navigate(stage)
        except Exception as e:
            logger.exception(f"导航失败：{stage}")
            failed.append({"stage": stage, "reason": str(e)})
            continue
        if rec and rec.get("steps"):
            rec["updated_at"] = rec.get("updated_at") or now
            ok.append(rec)
        elif rec:
            skipped.append(
                {
                    "stage": stage,
                    "reason": "导航成功但未记录到步骤（可能命中快捷入口/已在目标），由 AI 自学兜底",
                }
            )
        else:
            failed.append({"stage": stage, "reason": "navigation failed"})
    return ok, failed, skipped


def fetch_raw(url: str) -> bytes | None:
    """拉公开 raw 文件到内存；任何失败返回 None（不抛）。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mower-nav-recorder"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except Exception as e:
        logger.warning(f"拉取失败 {url}: {e}")
        return None


def pull_public() -> tuple | None:
    """拉 MowerHotUpdate main 的 stage_data.json + key_mapping.json；任一失败返回 None。"""
    stage_data = fetch_raw(f"{RAW_BASE}/stage_data.json")
    key_mapping = fetch_raw(f"{RAW_BASE}/key_mapping.json")
    if stage_data is None or key_mapping is None:
        return None
    try:
        return json.loads(stage_data), json.loads(key_mapping)
    except ValueError as e:
        logger.warning(f"拉取的数据解析失败: {e}")
        return None


def build_index(stage_data: list) -> dict:
    """按 id 建 stage 索引，供掉落/活动名反查。"""
    return {s.get("id"): s for s in stage_data if isinstance(s, dict) and s.get("id")}


def auto_select(stage_data: list, key_mapping: dict) -> tuple[list[str], str]:
    """按刷理智周计划规则选最新活动的普通关，返回 (关卡代码列表, 活动名)。"""
    selected = select_latest_activity_stages(stage_data, key_mapping, int(time.time()))
    codes = [s["code"] for s in selected]
    activity = ""
    if codes:
        entry = build_index(stage_data).get(codes[0]) or {}
        activity = entry.get("zoneNameSecond") or ""
    return codes, activity


def beijing_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def compute_tag(nav_steps_path: Path, date_dot: str) -> str:
    """推荐发布 tag：v北京日期-内容哈希（nav_steps.json 字节 sha256，机器无关）。"""
    digest = hashlib.sha256(nav_steps_path.read_bytes()).hexdigest()[:7]
    return f"v{date_dot}-{digest}"


def stage_materials(code: str, stage_index: dict, key_mapping: dict) -> list[str]:
    """该关展示的掉落名（固源岩/装置优先，语义同 weekly_stage）；查不到返回空。"""
    entry = stage_index.get(code)
    if not entry:
        return []
    return [m["name"] for m in _materials(entry, key_mapping)]


def build_release_notes(
    ok: list[dict],
    skipped: list[dict],
    failed: list[dict],
    stage_index: dict,
    key_mapping: dict,
    activity_name: str,
    date_str: str,
) -> str:
    """生成 release_notes.md（#198 原样用作 Release notes；不含 tag 防 hash 循环）。"""
    lines = [
        "# 导航步骤更新",
        "",
        f"更新活动：{activity_name or '未知'}",
        f"录制日期：{date_str}",
        "",
        "## 录制结果",
        f"- 成功：{len(ok)}　跳过（无步骤，AI 兜底）：{len(skipped)}　失败：{len(failed)}",
        "",
        "## 关卡与掉落",
    ]

    def fmt(code: str, status: str) -> str:
        mats = stage_materials(code, stage_index, key_mapping)
        suffix = f"（{status}）" + (f"：{'、'.join(mats)}" if mats else "")
        return f"- {code}{suffix}"

    lines += [fmt(rec.get("stage", ""), "成功") for rec in ok]
    lines += [fmt(rec.get("stage", ""), "失败") for rec in failed]
    lines += ["", "数据 ©上海鹰角网络科技有限公司，仅用于学习与交流，侵删。"]
    return "\n".join(lines)


def print_publish_commands(
    nav_steps_path: Path,
    notes_path: Path,
    tag: str,
    activity_name: str,
    ok: list,
    skipped: list,
    failed: list,
) -> None:
    """打印发布到 MowerHotUpdate 的 git 命令（推 upstream，维护者手动执行）。"""
    print("\n已生成：")
    print(f"  {nav_steps_path}")
    print(f"  {notes_path}")
    print(f"推荐 tag：{tag}")
    print(f"\n发布到 {HOT_UPDATE_REPO}（推 upstream，别推 fork）：")
    print(
        f"  git clone git@github.com:{HOT_UPDATE_REPO}.git mowerhotupdate   # 已克隆则跳过"
    )
    print("  cd mowerhotupdate")
    print(
        "  git checkout main && git pull --rebase origin main   # 与管线并发改 main 时先 rebase"
    )
    print(f"  cp {nav_steps_path} ./nav_steps.json")
    print(f"  cp {notes_path} ./release_notes.md")
    print("  git add nav_steps.json release_notes.md")
    print(
        f'  git commit -m "build(hotupdate): 更新导航步骤 {tag}"'
        f' -m "活动「{activity_name or "未知"}」：成功{len(ok)} 跳过{len(skipped)} 失败{len(failed)}"'
        ' -m "Refs: #171"'
    )
    print("  git push origin main")
    print(f"  git tag {tag} && git push origin {tag}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="官方导航步骤录制脚本：连模拟器走 AI 自学导航并导出 nav_steps.json。"
    )
    parser.add_argument(
        "stages",
        nargs="*",
        help="目标关卡代码列表（例如 PA-1 EP-EX-3）；不传则自动选最新活动关",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="nav_steps.json",
        help="导出的官方步骤文件路径（默认 ./nav_steps.json）",
    )
    parser.add_argument(
        "--notes-output",
        default="release_notes.md",
        help="生成的 Release notes 文件路径（默认 ./release_notes.md）",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="跳过 OCR 初始化（无 OCR 资源时降级，导航可能变慢）",
    )
    parser.add_argument(
        "--force-record",
        action="store_true",
        help="忽略既有路由，每关全量冷构建（默认复用优先：回放既有共享前置并记录，失败才构建）",
    )
    args = parser.parse_args(argv)

    # 1. 确定要录制的关卡（自动选关网络先行，不碰模拟器）
    stage_index: dict = {}
    key_mapping: dict = {}
    activity_name = ""
    if args.stages:
        stages = list(args.stages)
    else:
        pulled = pull_public()
        if pulled is None:
            logger.error(
                "拉取 MowerHotUpdate 最新 stage_data 失败；检查网络，或显式传关卡代码"
            )
            return 1
        stage_data, key_mapping = pulled
        if not isinstance(stage_data, list) or not isinstance(key_mapping, dict):
            logger.error("拉取的数据形状不对（stage_data 应列表、key_mapping 应字典）")
            return 1
        stage_index = build_index(stage_data)
        stages, activity_name = auto_select(stage_data, key_mapping)
        if not stages:
            logger.error("没有可录制的活动关（最新活动可能已结束或无普通关）")
            return 1
        logger.info(f"自动选关：{activity_name or '未知活动'} → {' '.join(stages)}")

    from arknights_mower.utils import rapidocr

    if not args.no_ocr:
        try:
            rapidocr.initialize_ocr()
        except Exception as e:
            logger.warning(f"OCR 初始化失败（已降级继续）：{e}")

    from arknights_mower.solvers.navigation import NavigationSolver

    try:
        solver = NavigationSolver()
    except Exception as e:
        logger.error(f"连接模拟器失败：{e}")
        print("请先启动模拟器并确保 adb 已注册目标设备。", file=sys.stderr)
        return 1

    # 录制官方步骤：默认复用优先——回放既有路由（同一 zone 的兄弟关共享前置步骤）并记录，
    # 命中即省去重新构建，回放失败才回退在线构建；--force-record 则每关全量冷构建。
    if args.force_record:
        solver.force_record = True
    else:
        solver.reuse_record = True

    def navigate(stage: str) -> dict | None:
        if solver.run(stage):
            return {
                "stage": solver.name,
                "stage_type": solver.stageType,
                "steps": solver.nav_steps,
            }
        return None

    ok, failed, skipped = collect_records(stages, navigate)

    fresh = build_official_steps(ok)
    out_path = Path(args.output)
    existing = load_nav_file(out_path) if out_path.exists() else {}
    result = merge_official_steps(existing, fresh)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for s in skipped:
        logger.info(f"  {s['stage']}: {s['reason']}")
    for f in failed:
        logger.warning(f"  {f['stage']}: {f['reason']}")

    if not ok:
        logger.info("没有成功录制的关卡，无新内容可发布")
        return 0

    # 2. notes 用数据（显式传关时尽力拉）
    if not stage_index:
        pulled = pull_public()
        if pulled:
            stage_data, key_mapping = pulled
            if isinstance(stage_data, list):
                stage_index = build_index(stage_data)
            if not isinstance(key_mapping, dict):
                key_mapping = {}

    now = beijing_now()
    notes = build_release_notes(
        ok,
        skipped,
        failed,
        stage_index,
        key_mapping,
        activity_name,
        now.strftime("%Y-%m-%d"),
    )
    notes_path = Path(args.notes_output)
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes, encoding="utf-8")

    tag = compute_tag(out_path, now.strftime("%Y.%m.%d"))
    print_publish_commands(
        out_path, notes_path, tag, activity_name, ok, skipped, failed
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
