import { describe, expect, it, vi } from 'vitest'

import {
  buildMasteryRoutePayload,
  normalizeMasterySwapBuffers,
  normalizeMasteryRouteDefaults,
  parseMasteryRoute,
  prepareMasteryRoutes,
  syncMasteryRouteDefaults
} from './masteryRoute.js'

describe('mastery handoff buffers', () => {
  it('uses separate defaults for the three conditions', () => {
    expect(normalizeMasterySwapBuffers()).toEqual({
      no_central: 10,
      central: 15,
      central_unhalved_m2: 30
    })
  })
  it('retains a smaller legacy custom value for every condition', () => {
    expect(normalizeMasterySwapBuffers({ mastery_swap_buffer: 5 })).toEqual({
      no_central: 5,
      central: 5,
      central_unhalved_m2: 5
    })
  })
  it('keeps independent custom values including zero', () => {
    const values = { no_central: 0, central: 4, central_unhalved_m2: 9 }
    expect(
      normalizeMasterySwapBuffers({ mastery_swap_buffers: values, mastery_swap_buffer: 10 })
    ).toEqual(values)
  })
  it('fills only missing conditions with defaults', () => {
    expect(normalizeMasterySwapBuffers({ mastery_swap_buffers: { central: 6 } })).toEqual({
      no_central: 10,
      central: 6,
      central_unhalved_m2: 30
    })
  })
})

describe('mastery route contracts', () => {
  it('waits for roster sync before asking for fresh defaults', async () => {
    let finishSync
    const sync = new Promise((resolve) => {
      finishSync = resolve
    })
    const fresh = {
      defaults: { 重装: { supports: [{ name: '望', skill_level: 3, efficiency: 70 }] } }
    }
    const http = { get: vi.fn().mockReturnValueOnce(sync).mockResolvedValueOnce({ data: fresh }) }
    const calculating = syncMasteryRouteDefaults(http, '/api')
    expect(http.get.mock.calls).toEqual([['/api/cultivate-fetch']])
    finishSync({ data: { success: true } })
    expect(await calculating).toEqual(fresh)
    expect(http.get.mock.calls).toEqual([['/api/cultivate-fetch'], ['/api/mastery-route']])
  })

  it('does not calculate from stale roster data when sync fails', async () => {
    const http = {
      get: vi.fn().mockResolvedValue({ data: { success: false, message: '登录已过期' } })
    }
    await expect(syncMasteryRouteDefaults(http, '')).rejects.toThrow('登录已过期')
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('stops when the sync request fails', async () => {
    const http = { get: vi.fn().mockRejectedValue(new Error('连接超时')) }
    await expect(syncMasteryRouteDefaults(http, '')).rejects.toThrow('连接超时')
    expect(http.get).toHaveBeenCalledTimes(1)
  })

  it('surfaces missing training rules instead of applying incomplete defaults', async () => {
    const http = {
      get: vi
        .fn()
        .mockResolvedValueOnce({ data: { success: true } })
        .mockResolvedValueOnce({ data: { defaults: {}, defaults_error: '请更新资源包' } })
    }
    await expect(syncMasteryRouteDefaults(http, '')).rejects.toThrow('请更新资源包')
  })

  const personalDefaults = {
    近卫: {
      supports: [{ name: '杜宾', skill_level: 1, efficiency: 25, match: false }],
      half_off: false
    }
  }

  it('prepares untouched personal defaults for explicit save and reload', () => {
    const { routes, suggestedProfessions } = prepareMasteryRoutes([], personalDefaults, ['近卫'])
    const payloads = suggestedProfessions.map((p) => buildMasteryRoutePayload(p, routes[p]))
    expect(payloads).toHaveLength(1)
    expect(JSON.parse(payloads[0].supports)[0].name).toBe('杜宾')
    expect(payloads[0].half_off).toBe(false)
    const reloaded = prepareMasteryRoutes(payloads, personalDefaults, ['近卫'])
    expect(reloaded.suggestedProfessions).toEqual([])
    expect(reloaded.routes.近卫.supports).toEqual(routes.近卫.supports)
  })

  it('keeps saved manual choices even when absent from the owned defaults', () => {
    const manual = buildMasteryRoutePayload('近卫', {
      supports: [{ name: '赤冬', skill_level: 1, efficiency: 75 }],
      half_off: false
    })
    const result = prepareMasteryRoutes([manual], personalDefaults, ['近卫'])
    expect(result.routes.近卫.supports[0].name).toBe('赤冬')
    expect(result.suggestedProfessions).toEqual([])
  })

  it('does not mutate the reset source when editing a suggested route', () => {
    const { routes } = prepareMasteryRoutes([], personalDefaults, ['近卫'])
    routes.近卫.supports[0].name = '赤冬'
    expect(routes._jsonDefaults.近卫[0].name).toBe('杜宾')
    expect(personalDefaults.近卫.supports[0].name).toBe('杜宾')
  })

  it('does not invent trainers when the roster is missing or has no eligible operators', () => {
    for (const defaults of [{}, { 近卫: { supports: [], half_off: false } }]) {
      const result = prepareMasteryRoutes([], defaults, ['近卫'])
      expect(result.routes.近卫).toBeUndefined()
      expect(result.suggestedProfessions).toEqual([])
    }
  })

  it('buildMasteryRoutePayload preserves route flags and an empty support list', () => {
    const payload = buildMasteryRoutePayload('近卫', {
      supports: [],
      optimal: true,
      half_off: false
    })

    expect(payload).toEqual({
      profession: '近卫',
      supports: '[]',
      optimal: true,
      half_off: false
    })
  })

  it('parseMasteryRoute reads persisted columns and normalizes match values', () => {
    const route = parseMasteryRoute({
      profession: '近卫',
      supports: JSON.stringify([{ name: '赤冬', match: true }]),
      optimal: 1,
      half_off: 0
    })

    expect(route).toEqual({
      profession: '近卫',
      supports: [{ name: '赤冬', match: 'yes' }],
      optimal: true,
      half_off: false
    })
  })

  it('parseMasteryRoute remains compatible with wrapped legacy settings', () => {
    const route = parseMasteryRoute({
      profession: '近卫',
      supports: JSON.stringify({
        supports: [{ name: '赤冬', match: false }],
        optimal: true,
        half_off: false,
        controlCenter: 'ascalon'
      }),
      optimal: 0,
      half_off: 1
    })

    expect(route.optimal).toBe(true)
    expect(route.half_off).toBe(false)
  })

  it('normalizeMasteryRouteDefaults accepts the legacy DEFAULT_ROUTES object', () => {
    const defaults = normalizeMasteryRouteDefaults({
      近卫: {
        level_1: {
          operator: '赤冬',
          efficiency: 75,
          job_match: true,
          swap_target: '艾丽妮'
        }
      }
    })

    expect(defaults).toEqual({
      近卫: [
        {
          name: '赤冬',
          skill_level: 1,
          efficiency: 75,
          swap: true,
          swap_name: '艾丽妮',
          match: 'yes'
        }
      ]
    })
  })
})

it('provides three editable stages without inventing an owned trainer', async () => {
  const { completeMasterySupports } = await import('./masteryRoute')
  const rows = completeMasterySupports([])
  expect(rows.map((row) => row.skill_level)).toEqual([1, 2, 3])
  expect(rows.every((row) => row.name === '' && row.efficiency === 0)).toBe(true)
  rows.forEach((row, i) => {
    row.name = `教官${i + 1}`
  })
  const restored = parseMasteryRoute(buildMasteryRoutePayload('近卫', { supports: rows }))
  expect(restored.supports.map((row) => row.name)).toEqual(['教官1', '教官2', '教官3'])
})

it('fills only missing stages and keeps saved manual values independent', async () => {
  const { completeMasterySupports } = await import('./masteryRoute')
  const saved = [{ skill_level: 2, name: '赤冬', efficiency: 75, match: true }]
  const rows = completeMasterySupports(saved)
  expect(rows.map((row) => row.skill_level)).toEqual([1, 2, 3])
  expect(rows[1]).toMatchObject({ name: '赤冬', efficiency: 75, match: 'yes' })
  rows[1].name = '其他'
  expect(saved[0].name).toBe('赤冬')
})

it('uses legacy defaults for missing stages while preserving saved manual choices', async () => {
  const { completeMasterySupports } = await import('./masteryRoute.js')
  const defaults = {
    近卫: {
      half_off: true,
      level_1: { operator: '赤冬', efficiency: 75, job_match: true, swap_target: '艾丽妮' },
      level_2: { operator: '燧石', efficiency: 75, job_match: true, swap_target: '艾丽妮' },
      level_3: { operator: '百炼嘉维尔', efficiency: 95, job_match: true, swap_target: null }
    }
  }
  const { routes } = prepareMasteryRoutes([], defaults, ['近卫'])
  expect(routes.近卫.half_off).toBe(true)
  const fallback = routes._jsonDefaults.近卫
  const original = completeMasterySupports([], fallback)
  expect(original.map((row) => row.name)).toEqual(['赤冬', '燧石', '百炼嘉维尔'])
  expect(original[0]).toMatchObject({
    efficiency: 75,
    swap: true,
    swap_name: '艾丽妮',
    match: 'yes'
  })
  const partial = completeMasterySupports(
    [
      { name: '杜宾', skill_level: 2, efficiency: 30, swap: false },
      { name: '', skill_level: 3, efficiency: 0 }
    ],
    fallback
  )
  expect(partial.map((row) => row.name)).toEqual(['赤冬', '杜宾', '百炼嘉维尔'])
  expect(partial[1]).toMatchObject({ efficiency: 30, swap: false })
  expect(JSON.parse(buildMasteryRoutePayload('近卫', { supports: partial }).supports)).toHaveLength(
    3
  )
})
