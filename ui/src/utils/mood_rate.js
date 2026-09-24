// Rates are estimates between adjacent observations, never instantaneous game values.
// Skip special events (for example Fiammetta charging) and implausibly short / stale spans.
export const MIN_MOOD_RATE_INTERVAL_MS = 15 * 60 * 1000
export const MAX_NORMAL_MOOD_RATE_PER_HOUR = 6
export const MAX_MOOD_RATE_INTERVAL_MS = 24 * 60 * 60 * 1000

function validMood(point) {
  return typeof point?.y === 'number' && Number.isFinite(point.y) && point.y >= 0 && point.y <= 24
}

function pointTime(point) {
  const raw = point?.x
  if (typeof raw !== 'string' && typeof raw !== 'number') return NaN
  return new Date(raw).getTime()
}

// Aligned with the input data indices so Chart.js tooltip dataIndex can reuse these intervals.
export function calculateMoodIntervals(points) {
  if (!Array.isArray(points)) return []

  return points.map((current, index) => {
    if (index === 0) return null
    const previous = points[index - 1]

    // A charging jump should not be interpreted as natural mood recovery or consumption.
    if (previous?.moodEvent || current?.moodEvent) return null
    if (!validMood(previous) || !validMood(current)) return null

    const elapsedMs = pointTime(current) - pointTime(previous)
    if (
      !Number.isFinite(elapsedMs) ||
      elapsedMs < MIN_MOOD_RATE_INTERVAL_MS ||
      elapsedMs > MAX_MOOD_RATE_INTERVAL_MS
    ) {
      return null
    }

    const hours = elapsedMs / 3600000
    const delta = current.y - previous.y
    // Unmarked jumps can be data resets; do not show them as continuous natural changes.
    if (Math.abs(delta) / hours > MAX_NORMAL_MOOD_RATE_PER_HOUR) return null
    return {
      hours,
      delta,
      rate: Math.abs(delta) / hours,
      kind: delta < 0 ? 'consumption' : delta > 0 ? 'recovery' : 'stable'
    }
  })
}

export function summarizeMoodRates(points) {
  const totals = {
    consumption: { change: 0, hours: 0, intervals: 0 },
    recovery: { change: 0, hours: 0, intervals: 0 }
  }

  for (const interval of calculateMoodIntervals(points)) {
    if (!interval || interval.kind === 'stable') continue
    const total = totals[interval.kind]
    total.change += Math.abs(interval.delta)
    total.hours += interval.hours
    total.intervals++
  }

  // A duration-weighted average: short, noisy observations cannot dominate the result.
  return {
    consumption:
      totals.consumption.intervals > 0
        ? totals.consumption.change / totals.consumption.hours
        : null,
    recovery: totals.recovery.intervals > 0 ? totals.recovery.change / totals.recovery.hours : null,
    consumptionSamples: totals.consumption.intervals,
    recoverySamples: totals.recovery.intervals
  }
}

export function formatMoodRate(rate) {
  return typeof rate === 'number' && Number.isFinite(rate) && rate >= 0 ? rate.toFixed(2) : '—'
}

export function describeMoodEvent(point, datasetLabel) {
  const event = point?.moodEvent
  const related = point?.relatedOperator
  // Explicit backend event types override the heuristic applied to Fiammetta points.
  if (event === 'fiammetta_before') return '被肥鸭充能（交换前）'
  if (event === 'fiammetta_after') return '被肥鸭充能（交换后）'
  if (event === 'fiammetta_charge' || (datasetLabel === '菲亚梅塔' && related)) {
    return related ? `被充能干员：${related}` : '充能记录'
  }
  return related ? `关联干员：${related}` : ''
}

export function describeMoodInterval(interval) {
  if (!interval) return ''
  const duration = interval.hours.toFixed(2)
  if (interval.kind === 'stable') return `相邻记录心情未变（间隔 ${duration} 小时）`
  const action = interval.kind === 'consumption' ? '消耗' : '恢复'
  return `本段平均${action}约 ${formatMoodRate(interval.rate)} 点/小时（间隔 ${duration} 小时）`
}

// Bulk show / hide uses the Chart.js visibility API, without changing the data or legend defaults.
export function setAllMoodDatasetsVisible(chart, visible) {
  if (
    !chart ||
    !Array.isArray(chart.data?.datasets) ||
    typeof chart.setDatasetVisibility !== 'function' ||
    typeof chart.update !== 'function'
  ) {
    return false
  }

  chart.data.datasets.forEach((_, index) => chart.setDatasetVisibility(index, visible))
  chart.update('none')
  return true
}
