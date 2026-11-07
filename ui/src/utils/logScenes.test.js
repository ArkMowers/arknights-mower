import { describe, expect, it } from 'vitest'
import { WAIT_DISPLAY_DELAY, formatWaitDuration, matchScene, scanSceneWaits } from './logScenes'

const line = (text, at = null) => ({ text, at })

describe('log scene waits', () => {
  it('matches the two scene line shapes used by the live log', () => {
    expect(matchScene('Scene 9998: 场景跳转时的等待界面')).toEqual({
      scene: 9998,
      comment: '场景跳转时的等待界面'
    })
    expect(matchScene('Scene: 801: 公招主界面')).toEqual({ scene: 801, comment: '公招主界面' })
    expect(matchScene('Scene -1: 未知')).toEqual({ scene: -1, comment: '未知' })
    expect(matchScene('场景图导航：back_to_index')).toBeNull()
  })

  it('records the dwell time of a waiting scene until the next different scene', () => {
    const lines = [
      line('Scene 201: 基建全局视角', 1000),
      line('Scene 9998: 场景跳转时的等待界面', 5000),
      line('本次【场景跳转时的等待界面】使用联网等待补偿', 5200),
      line('Scene 1: 首页', 13000)
    ]

    const { durations, active } = scanSceneWaits(lines)

    expect(durations.get(1)).toBe(8000)
    expect(durations.has(2)).toBe(false)
    expect(active).toBeNull()
  })

  it('keeps waiting across non-scene lines and repeated reports of the same scene', () => {
    const lines = [
      line('Scene 9998: 场景跳转时的等待界面', 1000),
      line('本次【场景跳转时的等待界面】使用联网等待补偿', 1200),
      line('场景图导航：back_to_index', 2000),
      line('Scene 9998: 场景跳转时的等待界面', 61000)
    ]

    const { durations, active } = scanSceneWaits(lines)

    expect(durations.size).toBe(0)
    expect(active).toEqual({
      index: 0,
      scene: 9998,
      comment: '场景跳转时的等待界面',
      at: 1000
    })
  })

  it('records the total dwell across repeated reports of the same waiting scene', () => {
    const lines = [
      line('Scene 9998: 场景跳转时的等待界面', 1000),
      line('Scene 9998: 场景跳转时的等待界面', 61000),
      line('Scene 201: 基建全局视角', 63000)
    ]

    const { durations } = scanSceneWaits(lines)

    expect(durations.get(0)).toBe(62000)
    expect(durations.has(1)).toBe(false)
  })

  it('does not treat ordinary scene changes as waiting', () => {
    const lines = [
      line('Scene 1: 首页', 1000),
      line('Scene 201: 基建全局视角', 9000),
      line('Scene 202: 基建待办事项', 12000)
    ]

    expect(scanSceneWaits(lines).durations.size).toBe(0)
    expect(scanSceneWaits(lines).active).toBeNull()
  })

  it('skips waits shorter than the display delay', () => {
    const lines = [
      line('Scene 9998: 场景跳转时的等待界面', 1000),
      line('Scene 1: 首页', 1000 + WAIT_DISPLAY_DELAY - 1)
    ]

    expect(scanSceneWaits(lines).durations.size).toBe(0)
  })

  it('ignores scene lines without a usable timestamp', () => {
    const lines = [line('Scene 9998: 场景跳转时的等待界面', null), line('Scene 1: 首页', null)]

    expect(scanSceneWaits(lines).durations.size).toBe(0)
    expect(scanSceneWaits(lines).active).toBeNull()
  })

  it('formats durations without changing width unnecessarily', () => {
    expect(formatWaitDuration(0)).toBe('0.0s')
    expect(formatWaitDuration(6200)).toBe('6.2s')
    expect(formatWaitDuration(59940)).toBe('59.9s')
    expect(formatWaitDuration(59960)).toBe('1分0秒')
    expect(formatWaitDuration(60000)).toBe('1分0秒')
    expect(formatWaitDuration(96000)).toBe('1分36秒')
    expect(formatWaitDuration(119600)).toBe('2分0秒')
  })
})
