/** Keep each profession's original order while spreading its plans across the queue. */
export function interleaveMasteryPlans(entries) {
  const active = entries.filter((entry) => entry.status !== 'idle' && entry.status !== 'failed')
  const failed = entries.filter((entry) => entry.status === 'failed')
  const queues = new Map()

  for (const entry of entries) {
    if (entry.status !== 'idle') continue
    const profession = entry.profession || 'unknown'
    if (!queues.has(profession)) queues.set(profession, [])
    queues.get(profession).push(entry)
  }

  const ordered = [...active]
  let previous = active.length ? active.at(-1).profession || 'unknown' : undefined
  while (queues.size) {
    const candidates = [...queues.entries()].filter(([profession]) => profession !== previous)
    const available = candidates.length ? candidates : [...queues.entries()]
    // Prefer the largest remaining group. Map insertion order breaks ties by the
    // first appearance in the current plan order.
    const [profession, queue] = available.reduce((best, candidate) =>
      candidate[1].length > best[1].length ? candidate : best
    )
    ordered.push(queue.shift())
    if (!queue.length) queues.delete(profession)
    previous = profession
  }
  return [...ordered, ...failed]
}
