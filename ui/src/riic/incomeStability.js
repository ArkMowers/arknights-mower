// Read-only comparisons describe this window; they do not establish a steady state.
export function incomeStability(report) {
  const start = report.assumptions.warmupHours
  const end = report.elapsedHours
  const middle = (start + end) / 2
  const windows = [
    [start, middle],
    [middle, end]
  ]
  const rooms = new Map()
  const workers = new Map()
  for (const segment of report.segments ?? []) {
    const working = new Set(
      Object.entries(segment.occupants)
        .filter(([position, id]) => id && !position.startsWith('dormitory_'))
        .map(([, id]) => id)
    )
    windows.forEach(([from, to], index) => {
      const hours = Math.max(0, Math.min(to, segment.end) - Math.max(from, segment.start))
      if (!hours) return
      for (const [id, efficiency] of Object.entries(segment.efficiencyPercent)) {
        if (!rooms.has(id)) rooms.set(id, [0, 0])
        rooms.get(id)[index] += efficiency * hours
      }
      for (const id of working) {
        if (!workers.has(id)) workers.set(id, [0, 0])
        workers.get(id)[index] += hours
      }
    })
  }
  const hours = middle - start
  const roomComparisons =
    hours > 0
      ? [...rooms].map(([roomId, values]) => ({
          roomId,
          firstEfficiency: values[0] / hours,
          secondEfficiency: values[1] / hours
        }))
      : []
  const maxWorkFractionDifference =
    hours > 0
      ? Math.max(
          0,
          ...[...workers.values()].map((values) => Math.abs(values[1] - values[0]) / hours)
        )
      : 0
  const sample = report.production?.sampleDrones
  return {
    halfHours: hours,
    roomComparisons,
    maxWorkFractionDifference,
    ...(sample ? { drones: { ...sample, change: sample.closing - sample.opening } } : {})
  }
}
