import { describe, expect, it } from 'vitest'
import { visibleTimelineIntervals } from './timelineDisplay'
import type { TimelineInterval } from './timelineModel'

const interval = (index: number): TimelineInterval => ({
  id: String(index), start: index / 3600, end: (index + 1) / 3600, duration: 1 / 3600,
  operatorId: `op-${index % 2}`, operatorName: `干员 ${index % 2}`, avatarUrl: '',
  roomId: 'dormitory_1', roomName: '宿舍 1', roomType: 'dormitory', slotIndex: 0,
  slotKey: 'dormitory_1_0', isDormitory: true, status: 'resting',
})

describe('visibleTimelineIntervals', () => {
  it('bounds dense chart nodes while retaining the raw timeline', () => {
    const raw = Array.from({ length: 3600 }, (_, index) => interval(index))
    const shown = visibleTimelineIntervals(raw, 0, 1, 900)
    expect(shown.length).toBeLessThan(1000)
    expect(shown.some(item => item.condensedCount && item.condensedCount > 1)).toBe(true)
    expect(shown[0]?.start).toBe(0)
    expect(shown[shown.length - 1]?.end).toBe(1)
    expect(raw).toHaveLength(3600)
    expect(raw[0]?.operatorName).toBe('干员 0')
  })

  it('keeps isolated and long intervals intact', () => {
    const first = interval(0)
    const long = { ...interval(1), start: 1, end: 2, duration: 1 }
    expect(visibleTimelineIntervals([first, long], 0, 2, 900)).toEqual([first, long])
  })
})
