"""Read fixed scheduling sections from the installed one-stop guide."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path

from arknights_mower import __rootdir__

GUIDE_NAME = "Mower入门指北.html"
SECTION_IDS = frozenset(
    {
        "schedule-design-fields",
        "schedule-design-example",
        "schedule-design-dorm",
        "schedule-design-capacity",
        "schedule-design-bindings",
        "schedule-design-priority",
        "schedule-design-standby",
        "schedule-design-mood",
        "schedule-design-backups",
        "schedule-backup-states",
    }
)
MAX_GUIDE_BYTES = 1024 * 1024


class _Sections(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self.current = None
        self.heading = False
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            anchor = dict(attrs).get("id")
            self.current = None
            self.heading = True
            if anchor in SECTION_IDS:
                self.current = {"anchor": anchor, "title": [], "text": []}
                self.sections.append(self.current)
        elif self.current and tag in {"p", "li", "tr", "td", "th", "br"}:
            self.current["text"].append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading = False

    def handle_data(self, data):
        if self.current and not self.hidden:
            self.current["title" if self.heading else "text"].append(data)


def read_riic_tutorial():
    """Return sourced excerpts, or explicit missing coverage, without network access."""
    root = Path(__rootdir__).parent / "ui"
    # Source checkouts use the maintained HTML; releases ship only the built guide.
    path = next(
        (
            p
            for p in (root / GUIDE_NAME, root / "dist" / "docs" / GUIDE_NAME)
            if p.is_file()
        ),
        None,
    )
    if path is None:
        return {"available": False, "reason": "本机未找到一条龙教程", "sections": []}
    try:
        with path.open("rb") as source:
            raw = source.read(MAX_GUIDE_BYTES + 1)
        if len(raw) > MAX_GUIDE_BYTES:
            raise ValueError("guide size")
        parser = _Sections()
        parser.feed(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return {"available": False, "reason": "本机一条龙教程无法读取", "sections": []}
    sections = []
    budget = 12000
    truncated = False
    for section in parser.sections:
        text = "\n".join(
            line.strip()
            for line in "".join(section["text"]).splitlines()
            if line.strip()
        )
        if len(text) > budget:
            truncated = True
            continue
        budget -= len(text)
        sections.append(
            {
                "title": "".join(section["title"]).strip(),
                "anchor": section["anchor"],
                "url": f"/docs/{GUIDE_NAME}#{section['anchor']}",
                "text": text,
            }
        )
    missing = sorted(SECTION_IDS - {section["anchor"] for section in sections})
    return {
        "available": bool(sections),
        "source": f"ui/{GUIDE_NAME}"
        if path.parent == root
        else f"ui/dist/docs/{GUIDE_NAME}",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "sections": sections,
        "missing_sections": missing,
        "truncated": truncated,
        "scope": "当前软件自带教程的排班章节摘录；不包含实机观测或收益演算结果",
    }
