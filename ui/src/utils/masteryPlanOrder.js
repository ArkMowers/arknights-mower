/** Read remaining assistant occupants from saved and executing stages. */
export function masteryAssistants(plan) {
  const runtime =
    plan.support_runtime?.carry_from_skill !== undefined ? {} : plan.support_runtime || {}
  const current = runtime.level ?? 1
  const target = plan.target_level ?? 3
  const stages = new Map(
    (plan.support_plan?.stages || [])
      .filter((stage) => stage.level >= current && stage.level <= target)
      .map((stage) => [stage.level, stage])
  )
  if (Object.keys(runtime).length && current <= target) {
    stages.set(current, { ...stages.get(current), ...runtime })
  }
  return new Set(
    [...stages.values()]
      .flatMap((stage) => [stage.operator, stage.swap_target, stage.working_operator])
      .filter((name) => name && name !== 'Free' && name !== 'Current')
  )
}

/** Keep one operator's skills together while separating shared assistants. */
export function interleaveMasteryPlans(entries) {
  const active = entries.filter((entry) => entry.status !== 'idle' && entry.status !== 'failed')
  const failed = entries.filter((entry) => entry.status === 'failed')
  const activeGroups = new Map()
  const idleGroups = new Map()
  for (const entry of active) {
    if (!activeGroups.has(entry.char_id)) activeGroups.set(entry.char_id, [])
    activeGroups.get(entry.char_id).push(entry)
  }
  for (const entry of entries) {
    if (entry.status !== 'idle') continue
    if (!idleGroups.has(entry.char_id)) idleGroups.set(entry.char_id, [])
    idleGroups.get(entry.char_id).push(entry)
  }

  const ordered = []
  let previous = new Set()
  const assistants = (group) => new Set(group.flatMap((entry) => [...masteryAssistants(entry)]))
  for (const [charId, group] of activeGroups) {
    const combined = [...group, ...(idleGroups.get(charId) || [])]
    ordered.push(...combined)
    idleGroups.delete(charId)
    previous = assistants(combined)
  }

  const queues = new Map()
  for (const group of idleGroups.values()) {
    const names = [...assistants(group)].sort()
    const key = JSON.stringify(names)
    if (!queues.has(key)) queues.set(key, { names, groups: [] })
    queues.get(key).groups.push(group)
  }

  while (queues.size) {
    const overlap = (queue) => queue.names.filter((name) => previous.has(name)).length
    // Insertion order preserves the first appearance when both counts tie.
    const [key, queue] = [...queues.entries()].reduce((best, candidate) => {
      const difference = overlap(candidate[1]) - overlap(best[1])
      return difference < 0 ||
        (difference === 0 && candidate[1].groups.length > best[1].groups.length)
        ? candidate
        : best
    })
    ordered.push(...queue.groups.shift())
    if (!queue.groups.length) queues.delete(key)
    previous = new Set(queue.names)
  }
  return [...ordered, ...failed]
}
