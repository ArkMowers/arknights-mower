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

export function currentMasteryLevel(plan) {
  const runtime = plan.support_runtime || {}
  const confirmed = runtime.carry_from_skill === undefined ? (runtime.level ?? 1) - 1 : 0
  return plan.current_level ?? Math.max(plan.support_plan?.current ?? 0, confirmed)
}

/** Separate shared assistants; continuity is optional except for existing mastery. */
export function interleaveMasteryPlans(entries, { consecutiveSkills = false } = {}) {
  const level = currentMasteryLevel
  const byOperator = new Map()
  for (const entry of entries) {
    if (
      entry.kind === 'goal' ||
      entry.skill_index === undefined ||
      entry.status === 'failed' ||
      level(entry) >= (entry.target_level ?? 3)
    )
      continue
    if (!byOperator.has(entry.char_id)) byOperator.set(entry.char_id, [])
    byOperator.get(entry.char_id).push(entry)
  }
  const grouped = new Map(
    [...byOperator].filter(
      ([, group]) =>
        new Set(group.map((entry) => entry.skill_index)).size > 1 &&
        (consecutiveSkills || group.some((entry) => level(entry) >= 1))
    )
  )
  const active = [],
    idle = [],
    failed = [],
    seen = new Set()
  for (const entry of entries) {
    if (entry.status === 'failed') {
      failed.push(entry)
      continue
    }
    if (seen.has(entry)) continue
    const group = grouped.get(entry.char_id) || []
    const unit = group.includes(entry)
      ? [...group].sort(
          (a, b) => Number(a.status === 'idle') - Number(b.status === 'idle') || level(a) - level(b)
        )
      : [entry]
    unit.forEach((member) => seen.add(member))
    ;(unit.every((member) => member.status === 'idle') ? idle : active).push(unit)
  }

  const ordered = []
  let previous = new Set()
  const recent = new Map()
  const assistants = (group) => new Set(group.flatMap((entry) => [...masteryAssistants(entry)]))
  for (const unit of active) {
    ordered.push(...unit)
    if (unit.some((entry) => entry.kind !== 'goal')) {
      previous = assistants(unit)
      recent.set(unit[0].char_id, ordered.length)
    }
  }
  const queues = new Map()
  for (const unit of idle) {
    const names = [...assistants(unit)].sort(),
      key = JSON.stringify(names)
    if (!queues.has(key)) queues.set(key, { names, units: [] })
    queues.get(key).units.push(unit)
  }
  while (queues.size) {
    const overlap = (queue) => queue.names.filter((name) => previous.has(name)).length
    const choices = [...queues].map(([key, queue]) => ({
      key,
      queue,
      unit: queue.units.reduce((best, unit) =>
        (recent.get(unit[0].char_id) ?? -1) > (recent.get(best[0].char_id) ?? -1) ? unit : best
      )
    }))
    const proximity = (choice) => -(recent.get(choice.unit[0].char_id) ?? -1)
    const selected = choices.reduce((best, candidate) => {
      const difference =
        overlap(candidate.queue) - overlap(best.queue) ||
        proximity(candidate) - proximity(best) ||
        best.queue.units.length - candidate.queue.units.length
      return difference < 0 ? candidate : best
    })
    const { key, queue, unit } = selected
    ordered.push(...unit)
    queue.units.splice(queue.units.indexOf(unit), 1)
    if (!queue.units.length) queues.delete(key)
    if (unit.some((entry) => entry.kind !== 'goal')) {
      previous = new Set(queue.names)
      recent.set(unit[0].char_id, ordered.length)
    }
  }
  return [...ordered, ...failed]
}
