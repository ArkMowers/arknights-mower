import type { TimelineInterval } from './timelineModel'

export interface TimelineDisplayInterval extends TimelineInterval {
  condensedCount?: number
}

/** Keep every raw interval in the dataset, but bound chart nodes to visible pixels. */
export function visibleTimelineIntervals(
  intervals: readonly TimelineInterval[],
  windowStart: number,
  windowEnd: number,
  widthPixels: number,
): TimelineDisplayInterval[] {
  const result: TimelineDisplayInterval[] = []
  const minHours = (windowEnd - windowStart) * 2 / Math.max(1, widthPixels)
  let pending: TimelineInterval[] = []
  const flush = () => {
    if (!pending.length) return
    if (pending.length === 1) {
      result.push(pending[0]!)
    } else {
      const first = pending[0]!
      const last = pending[pending.length - 1]!
      result.push({
        ...first,
        id: `${first.id}_dense_${pending.length}`,
        end: last.end,
        duration: last.end - first.start,
        operatorId: '',
        operatorName: `密集切换（${pending.length} 段）`,
        avatarUrl: '',
        roomName: '多次切换',
        startMorale: undefined,
        endMorale: undefined,
        efficiencyPercent: undefined,
        condensedCount: pending.length,
      })
    }
    pending = []
  }
  for (const interval of intervals) {
    if (interval.end <= windowStart) continue
    if (interval.start >= windowEnd) break
    if (interval.duration >= minHours) {
      flush()
      result.push(interval)
      continue
    }
    if (pending.length && (interval.start - pending[pending.length - 1]!.end > 1e-6 || interval.end - pending[0]!.start >= minHours)) flush()
    pending.push(interval)
  }
  flush()
  return result
}
