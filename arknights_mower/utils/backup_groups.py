"""Select backup groups without mutating actual or projected scheduling state."""

from dataclasses import dataclass

DEFAULT_BACKUP_GROUP = "default"


def selected_group_ids(selection):
    """Accept saved single-group state and concurrent group selections."""
    return (selection,) if isinstance(selection, str) else tuple(selection)


def normalize_backup_groups(groups):
    """Preserve legacy exclusions and make explicit exclusions symmetric."""
    result = [dict(group) for group in groups]
    ids = [group["id"] for group in result]
    if len(ids) != len(set(ids)):
        raise ValueError("副表分组标识不能重复")
    legacy = {
        group["id"]
        for group in result
        if group["id"] != DEFAULT_BACKUP_GROUP and "exclusive_with" not in group
    }
    for group in result:
        group.setdefault(
            "trigger",
            {}
            if group["id"] in legacy or group["id"] == DEFAULT_BACKUP_GROUP
            else {"left": "True", "operator": "", "right": ""},
        )
        excluded = list(
            group.get(
                "exclusive_with",
                [
                    key
                    for key in ids
                    if group["id"] != DEFAULT_BACKUP_GROUP
                    and key in legacy
                    and key != group["id"]
                ],
            )
        )
        if len(excluded) != len(set(excluded)):
            raise ValueError("副表分组的互斥对象不能重复")
        if any(key not in ids for key in excluded):
            raise ValueError(f"副表分组 {group['name']} 的互斥对象不存在")
        if group["id"] in excluded:
            raise ValueError("副表分组不能与自身互斥")
        if excluded and (
            group["id"] == DEFAULT_BACKUP_GROUP or DEFAULT_BACKUP_GROUP in excluded
        ):
            raise ValueError("默认分组始终生效，不能配置分组互斥")
        group["exclusive_with"] = excluded
    for group in result:
        for other in result:
            if (
                group["id"] in other["exclusive_with"]
                and other["id"] not in group["exclusive_with"]
            ):
                group["exclusive_with"].append(other["id"])
    if DEFAULT_BACKUP_GROUP not in ids:
        result.insert(
            0,
            {
                "id": DEFAULT_BACKUP_GROUP,
                "name": "默认分组",
                "trigger": {},
                "exclusive_with": [],
            },
        )
    return sorted(result, key=lambda group: group["id"] != DEFAULT_BACKUP_GROUP)


def select_group_ids(groups, eligible):
    selected = [DEFAULT_BACKUP_GROUP]
    for group in groups:
        if group["id"] == DEFAULT_BACKUP_GROUP or group["id"] not in eligible:
            continue
        if not set(group["exclusive_with"]).intersection(selected):
            selected.append(group["id"])
    return tuple(selected)


@dataclass(frozen=True)
class BackupSelection:
    group_id: str | tuple[str, ...]
    conditions: list[bool]

    @property
    def group_ids(self):
        return selected_group_ids(self.group_id)


def backup_group_ids(backup):
    return getattr(backup, "group_ids", [DEFAULT_BACKUP_GROUP])


def select_exclusive_backups(backups, eligible, groups, *, current=()):
    """A shared exclusive backup reserves every selected membership once."""
    flags = list(eligible)
    exclusive = [
        index
        for index, backup in enumerate(backups)
        if flags[index] and getattr(backup, "backup_type", "global") == "exclusive"
    ]
    occupied = set()
    for index in sorted(
        exclusive, key=lambda index: not (index < len(current) and current[index])
    ):
        memberships = set(backup_group_ids(backups[index])).intersection(groups)
        flags[index] = not bool(memberships.intersection(occupied))
        if flags[index]:
            occupied.update(memberships)
    return flags


def select_backup_plans(
    backups, groups, evaluate, *, current_group="default", current=()
):
    groups = normalize_backup_groups(groups)
    selected = select_group_ids(
        groups,
        {
            group["id"]
            for group in groups
            if group["id"] != DEFAULT_BACKUP_GROUP and evaluate(group["trigger"])
        },
    )
    flags = [
        bool(evaluate(backup.trigger))
        if set(selected).intersection(backup_group_ids(backup))
        else False
        for backup in backups
    ]
    flags = select_exclusive_backups(backups, flags, selected, current=current)
    return BackupSelection(selected[0] if len(selected) == 1 else selected, flags)
