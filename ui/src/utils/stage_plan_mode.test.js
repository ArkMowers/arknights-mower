import { describe, expect, it } from 'vitest'
import { getStagePlanMode, selectStagePlanMode, STAGE_PLAN_MODES } from './stage_plan_mode'

describe('three-state weekly sanity plan mode', () => {
  it('reads the current backend MAA execution mode without migration', () => {
    expect(getStagePlanMode(true, 'maa')).toBe('maa')
    expect(selectStagePlanMode('maa')).toEqual({
      stage_plan_enable: true,
      stage_plan_runner: 'maa'
    })
  })

  it('reads the current backend Mower execution mode without migration', () => {
    expect(getStagePlanMode(true, 'mower')).toBe('mower')
    expect(selectStagePlanMode('mower', 'maa')).toEqual({
      stage_plan_enable: true,
      stage_plan_runner: 'mower'
    })
  })

  it('maps either disabled backend pair to exactly one visible off state', () => {
    expect(getStagePlanMode(false, 'maa')).toBe('off')
    expect(getStagePlanMode(false, 'mower')).toBe('off')
  })

  it('pauses automatic fighting while preserving the configured executor', () => {
    expect(selectStagePlanMode('off', 'mower')).toEqual({
      stage_plan_enable: false,
      stage_plan_runner: 'mower'
    })
    expect(selectStagePlanMode('off', 'maa')).toEqual({
      stage_plan_enable: false,
      stage_plan_runner: 'maa'
    })
  })

  it('re-enables MAA or Mower explicitly without changing unrelated settings', () => {
    const existing = {
      stage_plan_enable: false,
      stage_plan_runner: 'mower',
      maa_mall_enable: true,
      maa_mall_mode: 'maa',
      medicine_expire_days: 3,
      maa_weekly_plan: [{ weekday: '周一', stage: ['1-7'] }]
    }
    const selected = {
      ...existing,
      ...selectStagePlanMode('maa', existing.stage_plan_runner)
    }
    expect(selected).toEqual({
      ...existing,
      stage_plan_enable: true,
      stage_plan_runner: 'maa'
    })
    expect(getStagePlanMode(selected.stage_plan_enable, selected.stage_plan_runner)).toBe('maa')
  })

  it('only returns backend fields, never a new off executor value', () => {
    for (const mode of Object.values(STAGE_PLAN_MODES)) {
      const fields = selectStagePlanMode(mode, 'mower')
      expect(Object.keys(fields).sort()).toEqual(['stage_plan_enable', 'stage_plan_runner'])
      expect(['maa', 'mower']).toContain(fields.stage_plan_runner)
      expect(fields.stage_plan_enable).toBe(mode !== 'off')
    }
  })

  it('recovers safely when loading older or invalid executor settings', () => {
    expect(getStagePlanMode(true, null)).toBe('maa')
    expect(selectStagePlanMode('off', null)).toEqual({
      stage_plan_enable: false,
      stage_plan_runner: 'maa'
    })
    expect(getStagePlanMode(false, null)).toBe('off')
  })

  it('rejects unknown modes rather than silently enabling a task', () => {
    expect(() => selectStagePlanMode('automatic', 'mower')).toThrow(RangeError)
    expect(() => selectStagePlanMode(null, 'maa')).toThrow(RangeError)
  })
})
