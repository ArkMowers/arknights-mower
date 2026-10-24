import { describe, expect, it, vi } from 'vitest'
import {
  calculateMoodIntervals,
  describeMoodEvent,
  describeMoodInterval,
  formatMoodRate,
  MAX_MOOD_RATE_INTERVAL_MS,
  MAX_NORMAL_MOOD_RATE_PER_HOUR,
  MIN_MOOD_RATE_INTERVAL_MS,
  setAllMoodDatasetsVisible,
  summarizeMoodRates
} from './mood_rate'

const point = (minutes, mood, event) => ({
  x: new Date(Date.UTC(2026, 8, 22, 0, minutes)).toISOString(),
  y: mood,
  ...(event ? { moodEvent: event } : {})
})

describe('mood history segment rates', () => {
  it('computes adjacent consumption and recovery rates from real timestamps', () => {
    const intervals = calculateMoodIntervals([point(0, 24), point(120, 22), point(180, 23)])
    expect(intervals).toEqual([
      null,
      { hours: 2, delta: -2, rate: 1, kind: 'consumption' },
      { hours: 1, delta: 1, rate: 1, kind: 'recovery' }
    ])
  })

  it('keeps stable intervals distinct from recovery and consumption', () => {
    const intervals = calculateMoodIntervals([point(0, 12), point(120, 12)])
    expect(intervals[1]).toEqual({ hours: 2, delta: 0, rate: 0, kind: 'stable' })
    expect(summarizeMoodRates([point(0, 12), point(120, 12)])).toEqual({
      consumption: null,
      recovery: null,
      consumptionSamples: 0,
      recoverySamples: 0
    })
  })

  it('excludes charge and special-event jumps, including adjacent event intervals', () => {
    const points = [
      point(0, 3),
      point(60, 2, 'fiammetta_before'),
      point(61, 24, 'fiammetta_after'),
      point(180, 23),
      point(300, 22)
    ]
    expect(calculateMoodIntervals(points)).toEqual([
      null,
      null,
      null,
      null,
      { hours: 2, delta: -1, rate: 0.5, kind: 'consumption' }
    ])
    expect(summarizeMoodRates(points).consumption).toBe(0.5)
  })

  it('does not divide by zero or infer unrealistic rates from very close observations', () => {
    const points = [point(0, 5), point(0, 12), point(1, 13), point(6, 14)]
    expect(calculateMoodIntervals(points)).toEqual([null, null, null, null])
    expect(MIN_MOOD_RATE_INTERVAL_MS).toBe(900000)
  })

  it('skips reversed, missing, non-finite and out-of-range measurements', () => {
    const invalid = [
      [point(120, 12), point(60, 11)],
      [{ x: 'not-a-date', y: 4 }, point(60, 3)],
      [{ x: point(0, 5).x, y: null }, point(60, 4)],
      [{ x: point(0, 5).x, y: Infinity }, point(60, 4)],
      [point(0, 25), point(60, 24)],
      [point(0, -1), point(60, 2)],
      [null, point(60, 1)]
    ]
    for (const points of invalid) expect(calculateMoodIntervals(points)).toEqual([null, null])
    expect(calculateMoodIntervals(null)).toEqual([])
    expect(calculateMoodIntervals([])).toEqual([])
  })

  it('filters abrupt unmarked jumps and retains the fifteen-minute boundary', () => {
    const points = [point(0, 12), point(15, 13), point(30, 24)]
    const intervals = calculateMoodIntervals(points)
    expect(intervals[1].rate).toBe(4)
    expect(intervals[2]).toBeNull()
    expect(MAX_NORMAL_MOOD_RATE_PER_HOUR).toBe(6)
  })

  it('skips intervals longer than a day when historical sampling has gaps', () => {
    const start = { x: '2026-09-20T00:00:00+08:00', y: 24 }
    const end = { x: '2026-09-22T00:00:00+08:00', y: 21 }
    expect(calculateMoodIntervals([start, end])).toEqual([null, null])
    expect(MAX_MOOD_RATE_INTERVAL_MS).toBe(86400000)
  })

  it('accepts backend offset-aware timestamps across a daylight boundary', () => {
    const points = [
      { x: '2026-09-22T10:00:00.000000+08:00', y: 12 },
      { x: '2026-09-22T12:00:00.000000+08:00', y: 11 }
    ]
    expect(calculateMoodIntervals(points)[1].rate).toBe(0.5)
  })

  it('uses duration-weighted rates rather than an arithmetic average of intervals', () => {
    const points = [point(0, 24), point(60, 23), point(240, 19), point(300, 21)]
    const result = summarizeMoodRates(points)
    expect(result.consumption).toBeCloseTo(1.25)
    expect(result.recovery).toBeCloseTo(2)
    expect(result.consumptionSamples).toBe(2)
    expect(result.recoverySamples).toBe(1)
  })

  it('does not mutate API-supplied historical points', () => {
    const points = Object.freeze([Object.freeze(point(0, 24)), Object.freeze(point(120, 22))])
    expect(summarizeMoodRates(points).consumption).toBe(1)
    expect(points[0].y).toBe(24)
  })

  it('renders unavailable rates explicitly rather than NaN or guessed defaults', () => {
    expect(formatMoodRate(null)).toBe('—')
    expect(formatMoodRate(Infinity)).toBe('—')
    expect(formatMoodRate(-1)).toBe('—')
    expect(formatMoodRate(0.754)).toBe('0.75')
    expect(describeMoodInterval(null)).toBe('')
    expect(describeMoodInterval({ hours: 2, rate: 0, kind: 'stable' })).toContain('未变')
    expect(describeMoodInterval({ hours: 2, rate: 0.5, kind: 'recovery' })).toContain('恢复约 0.50')
  })

  it('prioritizes explicit before/after markers over the Fiammetta dataset heuristic', () => {
    expect(
      describeMoodEvent({ moodEvent: 'fiammetta_before', relatedOperator: '阿米娅' }, '菲亚梅塔')
    ).toBe('被肥鸭充能（交换前）')
    expect(
      describeMoodEvent({ moodEvent: 'fiammetta_after', relatedOperator: '阿米娅' }, '菲亚梅塔')
    ).toBe('被肥鸭充能（交换后）')
    expect(
      describeMoodEvent({ moodEvent: 'fiammetta_charge', relatedOperator: '阿米娅' }, '菲亚梅塔')
    ).toBe('被充能干员：阿米娅')
  })

  it('preserves normal related-operator annotations and avoids undefined event labels', () => {
    expect(describeMoodEvent({ relatedOperator: '阿米娅' }, '煌')).toBe('关联干员：阿米娅')
    expect(describeMoodEvent({ relatedOperator: '煌' }, '菲亚梅塔')).toBe('被充能干员：煌')
    expect(describeMoodEvent({ moodEvent: 'fiammetta_charge' }, '菲亚梅塔')).toBe('充能记录')
    expect(describeMoodEvent(null, '阿米娅')).toBe('')
  })

  it('can show/hide every line using the installed Chart.js visibility API', () => {
    const chart = {
      data: { datasets: [{ label: '阿米娅' }, { label: '煌' }] },
      setDatasetVisibility: vi.fn(),
      update: vi.fn()
    }
    expect(setAllMoodDatasetsVisible(chart, false)).toBe(true)
    expect(chart.setDatasetVisibility).toHaveBeenNthCalledWith(1, 0, false)
    expect(chart.setDatasetVisibility).toHaveBeenNthCalledWith(2, 1, false)
    expect(chart.update).toHaveBeenCalledWith('none')
    expect(setAllMoodDatasetsVisible(chart, true)).toBe(true)
    expect(chart.setDatasetVisibility).toHaveBeenNthCalledWith(3, 0, true)
    expect(chart.setDatasetVisibility).toHaveBeenNthCalledWith(4, 1, true)
    expect(setAllMoodDatasetsVisible(null, false)).toBe(false)
    expect(setAllMoodDatasetsVisible({ data: { datasets: [] } }, false)).toBe(false)
  })
})
