import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMasteryRoutePayload,
  normalizeMasteryRouteDefaults,
  parseMasteryRoute
} from './masteryRoute.js'

test('buildMasteryRoutePayload preserves route flags and an empty support list', () => {
  const payload = buildMasteryRoutePayload('近卫', { supports: [], optimal: true, half_off: false })

  assert.deepEqual(payload, {
    profession: '近卫',
    supports: '[]',
    optimal: true,
    half_off: false
  })
})

test('parseMasteryRoute reads persisted columns and normalizes match values', () => {
  const route = parseMasteryRoute({
    profession: '近卫',
    supports: JSON.stringify([{ name: '赤冬', match: true }]),
    optimal: 1,
    half_off: 0
  })

  assert.deepEqual(route, {
    profession: '近卫',
    supports: [{ name: '赤冬', match: 'yes' }],
    optimal: true,
    half_off: false,
    legacyControlCenter: null
  })
})

test('parseMasteryRoute remains compatible with wrapped legacy settings', () => {
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

  assert.equal(route.optimal, true)
  assert.equal(route.half_off, false)
  assert.equal(route.legacyControlCenter, 'ascalon')
})

test('normalizeMasteryRouteDefaults accepts the legacy DEFAULT_ROUTES object', () => {
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

  assert.deepEqual(defaults, {
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
