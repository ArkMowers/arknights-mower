"""Order mastery plans by operator, alternating professions where possible."""


def interleave_mastery_plans(
    plans: list[dict], professions: dict[str, str]
) -> list[dict]:
    active_groups: dict[str, list[dict]] = {}
    idle_groups: dict[str, list[dict]] = {}
    failed: list[dict] = []
    for plan in plans:
        status = plan["status"]
        if status == "failed":
            failed.append(plan)
            continue
        groups = idle_groups if status == "idle" else active_groups
        groups.setdefault(plan["char_id"], []).append(plan)

    ordered: list[dict] = []
    previous = None
    for char_id, group in active_groups.items():
        ordered.extend(group)
        ordered.extend(idle_groups.pop(char_id, []))
        previous = professions.get(char_id) or "unknown"

    queues: dict[str, list[list[dict]]] = {}
    for char_id, group in idle_groups.items():
        profession = professions.get(char_id) or "unknown"
        queues.setdefault(profession, []).append(group)

    while queues:
        candidates = [key for key in queues if key != previous] or list(queues)
        # max keeps the first-seen profession when remaining group counts tie.
        profession = max(candidates, key=lambda key: len(queues[key]))
        ordered.extend(queues[profession].pop(0))
        if not queues[profession]:
            del queues[profession]
        previous = profession
    return ordered + failed
