import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defaultIncomeSettings } from './income'
import {
  INCOME_PREFERENCES_KEY,
  loadIncomePreferences,
  saveIncomePreferences,
  clearIncomePreferences
} from './incomePreferences'

beforeEach(() => {
  const saved = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
    removeItem: (key) => saved.delete(key)
  })
})
afterEach(() => vi.unstubAllGlobals())

it('remembers expectation mode while dropping legacy seeds from editable preferences', () => {
  saveIncomePreferences({ ...defaultIncomeSettings(), expectationMode: false, seed: 42 }, {})
  expect(loadIncomePreferences().settings.expectationMode).toBe(false)
  expect(loadIncomePreferences().settings).not.toHaveProperty('seed')
  localStorage.setItem(
    INCOME_PREFERENCES_KEY,
    JSON.stringify({ version: 1, settings: { seed: 42 } })
  )
  const restored = { ...defaultIncomeSettings(), ...loadIncomePreferences().settings }
  expect(restored.expectationMode).toBe(true)
  expect(restored).not.toHaveProperty('seed')
})

it('stores editable parameters and inventory overrides without freezing fetched cache data', () => {
  const settings = defaultIncomeSettings()
  Object.assign(settings, {
    sampleDays: 7,
    operatorText: '阿米娅,2,80',
    operatorMode: 'custom',
    cachedOperators: [{ operator: '阿米娅' }],
    cachedInventory: { gold: 900 },
    cacheObservedAt: 123,
    mowerWeights: { exp: 9 },
    mowerAlgorithm: 0
  })
  settings.initialInventory.gold = 100
  expect(saveIncomePreferences(settings, { gold: 222 })).toBe(true)
  const restored = loadIncomePreferences()
  expect(restored).toMatchObject({
    settings: {
      sampleDays: 7,
      operatorMode: 'custom',
      operatorText: '阿米娅,2,80',
      initialInventory: { gold: 100 }
    },
    cachedInventoryOverrides: { gold: 222 }
  })
  for (const key of [
    'cachedOperators',
    'cachedInventory',
    'cacheObservedAt',
    'mowerWeights',
    'mowerAlgorithm'
  ])
    expect(restored.settings).not.toHaveProperty(key)
})

it('ignores malformed and unsupported stored data', () => {
  for (const value of [
    '{broken',
    'null',
    JSON.stringify({ version: 2, settings: { sampleDays: 7 } })
  ]) {
    localStorage.setItem(INCOME_PREFERENCES_KEY, value)
    expect(loadIncomePreferences().settings).not.toHaveProperty('sampleDays')
  }
})

it('rejects invalid saved fields while keeping valid choices', () => {
  localStorage.setItem(
    INCOME_PREFERENCES_KEY,
    JSON.stringify({
      version: 1,
      settings: {
        warmupDays: -1,
        sampleDays: 7,
        seed: 2 ** 40,
        operatorMode: 'invalid',
        finiteInventory: 'false',
        productionWeights: { exp: -2, orders: 0.3 },
        initialInventory: { gold: 1.5, lmd: 42, unsupported: 9 }
      },
      cachedInventoryOverrides: { gold: 222, lmd: -1 }
    })
  )
  const restored = loadIncomePreferences()
  expect(restored.settings).toMatchObject({
    sampleDays: 7,
    productionWeights: { exp: 1, orders: 0.3 },
    initialInventory: { lmd: 42 }
  })
  expect(restored.cachedInventoryOverrides).toEqual({ gold: 222 })
  for (const key of ['warmupDays', 'seed', 'operatorMode', 'finiteInventory'])
    expect(restored.settings).not.toHaveProperty(key)
})

it('clears stored choices and tolerates unavailable browser storage', () => {
  saveIncomePreferences({ ...defaultIncomeSettings(), sampleDays: 7 }, {})
  expect(clearIncomePreferences()).toBe(true)
  expect(localStorage.getItem(INCOME_PREFERENCES_KEY)).toBeNull()
  vi.stubGlobal('localStorage', undefined)
  expect(() => loadIncomePreferences()).not.toThrow()
  expect(saveIncomePreferences(defaultIncomeSettings(), {})).toBe(false)
  expect(clearIncomePreferences()).toBe(false)
})
