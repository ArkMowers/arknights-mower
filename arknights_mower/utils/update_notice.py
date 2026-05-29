import re

from arknights_mower import __version__
from arknights_mower.utils.config.app_state import read_app_state, write_app_state
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

CHANGELOG_FILE = get_path("@internal/CHANGELOG.md")
LAST_SEEN_VERSION_KEY = "last_seen_app_version"
LAST_ACKNOWLEDGED_VERSION_KEY = "last_acknowledged_update_version"
PENDING_FROM_VERSION_KEY = "pending_update_from_version"
VERSION_HEADER_RE = re.compile(r"^##\s+v?([0-9A-Za-z.+_-]+)\s*$")


class UpdateNoticeManager:
    def __init__(self):
        self.current_version = __version__

    def _read_full_changelog(self) -> str:
        if not CHANGELOG_FILE.exists():
            logger.warning("CHANGELOG.md is missing: %s", CHANGELOG_FILE)
            return ""
        try:
            return CHANGELOG_FILE.read_text(encoding="utf-8").strip()
        except Exception as exc:
            logger.error("failed to read CHANGELOG.md: %s", exc)
            return ""

    def _read_changelog_sections(self) -> dict[str, str]:
        if not CHANGELOG_FILE.exists():
            logger.warning("CHANGELOG.md is missing: %s", CHANGELOG_FILE)
            return {}
        try:
            with CHANGELOG_FILE.open("r", encoding="utf-8") as file:
                lines = file.read().splitlines()
        except Exception as exc:
            logger.error("failed to read CHANGELOG.md: %s", exc)
            return {}

        sections: dict[str, str] = {}
        current_version = None
        current_lines: list[str] = []
        for line in lines:
            match = VERSION_HEADER_RE.match(line.strip())
            if match:
                if current_version is not None:
                    sections[current_version] = "\n".join(current_lines).strip()
                current_version = match.group(1).strip()
                current_lines = []
                continue
            if current_version is not None:
                current_lines.append(line)

        if current_version is not None:
            sections[current_version] = "\n".join(current_lines).strip()
        return sections

    def _resolve_changelog(self, show_all: bool = False) -> str:
        if show_all:
            full_changelog = self._read_full_changelog()
            if full_changelog:
                return full_changelog
        changelog_sections = self._read_changelog_sections()
        for key in (self.current_version, self.current_version.split("+", 1)[0]):
            entry = str(changelog_sections.get(key, "") or "").strip()
            if entry:
                return entry
        return f"已更新到 {self.current_version}"

    def get_notice(self) -> dict:
        state = read_app_state()
        last_seen_version = str(state.get(LAST_SEEN_VERSION_KEY, "") or "").strip()
        first_run = not last_seen_version

        if first_run:
            state[LAST_SEEN_VERSION_KEY] = self.current_version
            write_app_state(state)
            previous_version = ""
        elif last_seen_version != self.current_version:
            state[PENDING_FROM_VERSION_KEY] = last_seen_version
            state[LAST_SEEN_VERSION_KEY] = self.current_version
            write_app_state(state)
            previous_version = last_seen_version
        else:
            previous_version = str(
                state.get(PENDING_FROM_VERSION_KEY, "") or ""
            ).strip()

        acknowledged_version = str(
            state.get(LAST_ACKNOWLEDGED_VERSION_KEY, "") or ""
        ).strip()
        should_show = acknowledged_version != self.current_version and (
            first_run or bool(previous_version)
        )
        return {
            "current_version": self.current_version,
            "previous_version": previous_version,
            "should_show": should_show,
            "changelog": self._resolve_changelog(show_all=first_run),
        }

    def acknowledge(self, version: str) -> dict:
        version = (version or "").strip()
        if version != self.current_version:
            raise ValueError("version does not match current app version")

        state = read_app_state()
        state[LAST_SEEN_VERSION_KEY] = self.current_version
        state[LAST_ACKNOWLEDGED_VERSION_KEY] = self.current_version
        state[PENDING_FROM_VERSION_KEY] = str(
            state.get(PENDING_FROM_VERSION_KEY, "") or ""
        ).strip()
        write_app_state(state)
        return {
            "ok": True,
            "current_version": self.current_version,
        }
