import { describe, expect, it } from 'vitest'
import { getTaskActivityItems } from './taskActivity'

const at = '2026-11-05T09:30:00+08:00'
const next = '2026-11-05T10:00:00+08:00'
const status = (activities, source = 'live') => ({
  game_day: '2026-11-05',
  source,
  activities
})
const items = (config, activities, source) =>
  getTaskActivityItems(config, status(activities, source))

describe('task activity facts', () => {
  it('shows enabled periodic tasks without inventing a completed execution', () => {
    const result = items(
      { recruit_enable: true, maa_depot_enable: true, enable_party: true },
      {
        recruit: {},
        depot: {},
        clue: {},
        base: {},
        runorder: {},
        dorm: {},
        drone: {},
        reload: {}
      }
    )
    expect(result.map(({ id, text }) => [id, text])).toEqual([
      ['clue', '暂无执行记录'],
      ['recruit', '暂无执行记录'],
      ['depot', '暂无执行记录']
    ])
    expect(result.every(({ tone }) => tone === 'neutral')).toBe(true)
  })

  it('filters disabled switches and absent facts without using automatic settings as execution', () => {
    expect(
      items(
        { recruit_enable: false, stage_plan_enable: false, maa_recruit: true },
        {
          recruit: { last_checked_at: at },
          'stage-plan': { last_observation: { at, outcome: 'completed' } },
          annihilation: { last_checked_at: at },
          mission: {},
          base: {},
          future: { last_checked_at: at }
        }
      )
    ).toEqual([])
    expect(getTaskActivityItems({ recruit_enable: true }, status({ recruit: {} }, 'none'))).toEqual(
      []
    )
  })

  it('presents cycle dates as observations and earliest checks instead of all-day completion', () => {
    const [item] = items(
      { recruit_enable: true },
      {
        recruit: { last_checked_at: at, next_eligible_at: next }
      }
    )
    expect(item.text).toBe('上次检查 09:30 · 最早可检查 10:00')
    expect(item.detail).toContain('2026-11-05 09:30')
    expect(item.detail).not.toContain('下次执行')
    expect(item.tone).toBe('neutral')
  })

  it('keeps automatic trade drones and blocked task facts visible', () => {
    const result = items(
      { drone_room: '' },
      {
        drone: { last_checked_at: at },
        base: { scheduled_count: 2, blocked_count: 1, next_task_at: next },
        dorm: { blocked_count: 3 },
        reload: { last_checked_at: 'invalid' }
      }
    )
    expect(result.map(({ id }) => id)).toEqual(['base', 'drone', 'dorm'])
    expect(result[0].text).toBe('待执行 2 项 · 暂不可执行 1 项')
    expect(result[0].detail).toContain('计划 10:00')
    expect(result[2].text).toBe('暂不可执行 3 项')
    expect(result[2].detail).toContain('待处理失败或尚未满足执行条件')
  })

  it('presents truncated queue counts as lower bounds instead of exact totals', () => {
    const [item] = items(
      {},
      { base: { scheduled_count: 20, blocked_count: 3, queue_truncated: true } }
    )
    expect(item.text).toBe('待执行至少 20 项 · 暂不可执行至少 3 项')
    expect(item.detail).toContain('实际数量至少为当前显示数量')
    expect(item.detail).not.toContain('等待依赖')
  })

  it('marks only an explicit live observation as running, and saved records as historical', () => {
    const activity = { long: { last_observation: { at, runner: 'maa', outcome: 'running' } } }
    const config = { maa_rg_enable: 1 }
    expect(items(config, activity)[0]).toMatchObject({ text: '运行中 09:30', tone: 'active' })
    const saved = items(config, activity, 'saved')[0]
    expect(saved.text).toBe('上次记录：已中断 09:30')
    expect(saved.detail).toContain('上次保存的记录')
    expect(saved.tone).toBe('neutral')
    expect(saved.text).not.toContain('运行中')
    expect(items(config, { long: {} })[0].text).toBe('暂无执行记录')
  })

  it('does not rename an observed operation count as a daily total', () => {
    const [item] = items(
      { stage_plan_enable: true },
      {
        'stage-plan': {
          last_observation: {
            at,
            runner: 'mower',
            outcome: 'completed',
            stage: '1-7',
            executed_runs: 3
          }
        }
      }
    )
    expect(item.text).toBe('最近完成 09:30，本次 3 次')
    expect(item.detail).toContain('1-7')
    expect(item.detail).toContain('实际执行 3 次')
    expect(item.detail).not.toContain('今日累计')
  })

  it('shows annihilation only for the selected current weekly plan or a real related fact', () => {
    const config = {
      stage_plan_enable: true,
      maa_weekly_plan: [{ weekday: '周四', stage: ['Annihilation'] }]
    }
    expect(items(config, { annihilation: {} }).map(({ id }) => id)).toEqual(['annihilation'])
    expect(
      items({ ...config, maa_weekly_plan: [{ stage: ['1-7'] }] }, { annihilation: {} })
    ).toEqual([])
    const [item] = items(config, {
      annihilation: { week_start: '2026-11-02', last_observation: { at, outcome: 'reward_full' } }
    })
    expect(item.text).toBe('本周奖励已满 09:30')
    expect(item.detail).toContain('2026-11-02')
  })

  it('uses long-task queue items and current item rounds without inventing failure counts', () => {
    const [item] = items(
      { maa_rg_enable: 1 },
      {
        long: {
          progress: { completed: 2, total: 4, failed: true, rounds: 3, round_total: 5 }
        }
      }
    )
    expect(item.text).toBe('队列 2/4，当前项失败待处理 · 当前项 3/5 轮')
    expect(item.tone).toBe('warning')
    expect(item.text).not.toContain('失败 1 次')
    expect(item.text).not.toContain('今日')
  })

  it('does not call old-week rewards current or reinterpret unrelated progress as weekly completion', () => {
    const config = { stage_plan_enable: true, maa_weekly_plan: [{ stage: ['Annihilation'] }] }
    const [item] = items(config, {
      annihilation: {
        week_start: '2026-10-26',
        progress: { completed: 4, total: 5, failed: false },
        last_observation: { at: '2026-10-30T09:30:00+08:00', outcome: 'reward_full' }
      }
    })
    expect(item.text).toBe('奖励已满 10-30 09:30')
    expect(item.text).not.toContain('本周')
    expect(item.text).not.toContain('4/5')
  })

  it('does not expose unknown outcomes or reason codes and ignores malformed fields', () => {
    const [item] = items(
      { recruit_enable: true },
      {
        recruit: {
          last_checked_at: 'invalid',
          scheduled_count: -2,
          blocked_count: '4',
          last_observation: { at, outcome: 'future-state', reason: 'internal-secret' },
          progress: { completed: false, total: -1 }
        }
      }
    )
    expect(item.text).toBe('结果未确认 09:30')
    expect(item.detail).not.toContain('internal-secret')
    expect(item.detail).not.toContain('future-state')
    expect(item.detail).not.toContain('NaN')
    expect(item.detail).toContain('详细原因未确认')
  })

  it('translates only known reasons and safely ignores inherited outcome names', () => {
    const [item] = items(
      { stage_plan_enable: true },
      {
        'stage-plan': {
          last_observation: { at, outcome: 'incomplete', reason: 'inventory_unconfirmed' }
        }
      }
    )
    expect(item.detail).toContain('库存尚未确认')
    expect(item.detail).not.toContain('inventory_unconfirmed')
    const [unknown] = items(
      { recruit_enable: true },
      {
        recruit: {
          last_observation: { at, outcome: 'toString', reason: '__proto__' }
        }
      }
    )
    expect(unknown.text).toBe('结果未确认 09:30')
    expect(unknown.detail).toContain('详细原因未确认')
  })

  it.each([
    'checked',
    'completed',
    'incomplete',
    'error',
    'stopped',
    'reward_full',
    'agency_locked'
  ])('renders the confirmed outcome %s without converting it to daily done', (outcome) => {
    const [item] = items(
      { recruit_enable: true },
      { recruit: { last_observation: { at, outcome } } }
    )
    expect(item.text).not.toBe('暂无执行记录')
    expect(item.text).not.toContain('今日已完成')
    expect(item.text).not.toContain(outcome)
  })

  it('does not mutate API records or configuration', () => {
    const config = Object.freeze({ recruit_enable: true })
    const activity = Object.freeze({ last_checked_at: at })
    const response = Object.freeze(status(Object.freeze({ recruit: activity })))
    expect(getTaskActivityItems(config, response)[0].id).toBe('recruit')
  })
})
