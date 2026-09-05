import { describe, expect, it } from 'vitest'

import {
  buildMasteryRoutePayload,
  normalizeMasteryRouteDefaults,
  parseMasteryRoute
} from './masteryRoute.js'

describe('mastery route contracts', () => {
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
