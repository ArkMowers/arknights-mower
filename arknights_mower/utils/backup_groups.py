"""Select backup groups without mutating actual or projected scheduling state."""

from dataclasses import dataclass

DEFAULT_BACKUP_GROUP = "default"


@dataclass(frozen=True)
class BackupSelection:
    group_id: str
    conditions: list[bool]


def backup_group_ids(backup):
    return getattr(backup, "group_ids", [DEFAULT_BACKUP_GROUP])


def select_backup_plans(
    backups, groups, evaluate, *, current_group="default", current=()
):
    eligible = [
        group["id"]
        for group in groups
        if group["id"] != DEFAULT_BACKUP_GROUP and evaluate(group["trigger"])
    ]
    selected = (
        current_group
        if current_group in eligible
        else next(iter(eligible), DEFAULT_BACKUP_GROUP)
    )
    flags = [
        bool(evaluate(backup.trigger))
        if selected in backup_group_ids(backup)
        else False
        for backup in backups
    ]
    exclusive = [
        index
        for index, backup in enumerate(backups)
        if flags[index] and getattr(backup, "backup_type", "global") == "exclusive"
    ]
    winner = next(
        (index for index in exclusive if index < len(current) and current[index]),
        next(iter(exclusive), None),
    )
    for index in exclusive:
        flags[index] = index == winner
    return BackupSelection(selected, flags)
