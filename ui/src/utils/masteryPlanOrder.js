/** Keep one operator's skills together while alternating operators' professions. */
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
  let previous
  for (const [charId, group] of activeGroups) {
    ordered.push(...group, ...(idleGroups.get(charId) || []))
    idleGroups.delete(charId)
    previous = group[0].profession || 'unknown'
  }

  const queues = new Map()
  for (const group of idleGroups.values()) {
    const profession = group[0].profession || 'unknown'
    if (!queues.has(profession)) queues.set(profession, [])
    queues.get(profession).push(group)
  }

  while (queues.size) {
    const candidates = [...queues.entries()].filter(([profession]) => profession !== previous)
    const available = candidates.length ? candidates : [...queues.entries()]
    // Prefer the largest remaining group. Map insertion order breaks ties by the
    // first appearance in the current plan order.
    const [profession, queue] = available.reduce((best, candidate) =>
      candidate[1].length > best[1].length ? candidate : best
    )
    ordered.push(...queue.shift())
    if (!queue.length) queues.delete(profession)
    previous = profession
  }
  return [...ordered, ...failed]
}
