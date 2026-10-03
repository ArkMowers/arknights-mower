"""Build the training-room name/skill template resource from skill_data.json."""

import argparse
import json
import os
from pathlib import Path

from arknights_mower.utils.mastery_panel_model import build_model

ROOT = Path(__file__).resolve().parent
DEFAULT_FONT = ROOT / "arknights_mower/fonts/SourceHanSansCN-Medium-mastery.ttf"
DEFAULT_CHARSET = ROOT / "arknights_mower/fonts/mastery-charset.txt"


def build_default_model(skill_data=None, output=None, font=None):
    skill_data = skill_data or ROOT / "arknights_mower/data/skill_data.json"
    output = output or ROOT / "arknights_mower/models/mastery_panel.model"
    font = font or Path(os.environ.get("MOWER_MASTERY_FONT", DEFAULT_FONT))
    charset = DEFAULT_CHARSET if font.resolve() == DEFAULT_FONT.resolve() else None
    data = json.loads(Path(skill_data).read_text(encoding="utf-8"))
    return build_model(data, font, output, charset)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skill-data",
        type=Path,
        default=ROOT / "arknights_mower/data/skill_data.json",
    )
    parser.add_argument("--font", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "arknights_mower/models/mastery_panel.model",
    )
    args = parser.parse_args()
    model = build_default_model(args.skill_data, args.output, args.font)
    print(
        f"训练室模板：{len(model['entries'])} 个干员，"
        f"{sum(len(entry['skills']) for entry in model['entries'].values())} 个技能，"
        f"{args.output.stat().st_size} 字节"
    )


if __name__ == "__main__":
    main()
