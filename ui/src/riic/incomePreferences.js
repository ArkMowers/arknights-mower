import { defaultIncomeSettings } from './income'
import { MOWER_INVENTORY_ITEMS, MOWER_RAW_MATERIALS } from './vendor/domain/simulationInventory'

export const INCOME_PREFERENCES_KEY = 'mower-income-preferences-v1'

const numericFields = { warmupDays: [0, 30], sampleDays: [1, 90], tailorSeed: [0, 0xffffffff] }
const enumFields = {
  inventorySource: ['cache', 'manual'],
  operatorMode: ['cache', 'maximum', 'custom'],
  weightMode: ['mower', 'custom']
}
const booleanFields = ['finiteInventory', 'allowMaterialDebt', 'jayeElite0', 'expectationMode']

function quantities(value, keys, integer = true) {
  return Object.fromEntries(
    keys
      .filter(
        (key) =>
          typeof value?.[key] === 'number' &&
          Number.isFinite(value[key]) &&
          value[key] >= 0 &&
          (!integer || Number.isSafeInteger(value[key]))
      )
      .map((key) => [key, value[key]])
  )
}

function sanitize(value) {
  const settings = {}
  for (const [key, [min, max]] of Object.entries(numericFields)) {
    if (
      Number.isInteger(value?.settings?.[key]) &&
      value.settings[key] >= min &&
      value.settings[key] <= max
    )
      settings[key] = value.settings[key]
  }
  for (const [key, options] of Object.entries(enumFields)) {
    if (options.includes(value?.settings?.[key])) settings[key] = value.settings[key]
  }
  for (const key of booleanFields) {
    if (typeof value?.settings?.[key] === 'boolean') settings[key] = value.settings[key]
  }
  if (
    settings.allowMaterialDebt === undefined &&
    typeof value?.settings?.allowGoldDebt === 'boolean'
  )
    settings.allowMaterialDebt = value.settings.allowGoldDebt
  settings.dailyExternalResources = quantities(
    value?.settings?.dailyExternalResources,
    MOWER_RAW_MATERIALS.map((item) => item.resource),
    false
  )
  for (const key of ['droneRoom', 'operatorText']) {
    if (typeof value?.settings?.[key] === 'string') settings[key] = value.settings[key]
  }
  const inventoryKeys = MOWER_INVENTORY_ITEMS.map(({ resource }) => resource)
  settings.initialInventory = quantities(value?.settings?.initialInventory, inventoryKeys)
  settings.productionWeights = {
    ...defaultIncomeSettings().productionWeights,
    ...quantities(
      value?.settings?.productionWeights,
      Object.keys(defaultIncomeSettings().productionWeights),
      false
    )
  }
  return {
    settings,
    cachedInventoryOverrides: quantities(value?.cachedInventoryOverrides, inventoryKeys)
  }
}

export function loadIncomePreferences() {
  try {
    const stored = JSON.parse(globalThis.localStorage.getItem(INCOME_PREFERENCES_KEY))
    return sanitize(stored?.version === 1 ? stored : null)
  } catch {
    return sanitize(null)
  }
}

export function saveIncomePreferences(settings, cachedInventoryOverrides) {
  try {
    globalThis.localStorage.setItem(
      INCOME_PREFERENCES_KEY,
      JSON.stringify({ version: 1, ...sanitize({ settings, cachedInventoryOverrides }) })
    )
    return true
  } catch {
    return false
  }
}

export function clearIncomePreferences() {
  try {
    globalThis.localStorage.removeItem(INCOME_PREFERENCES_KEY)
    return true
  } catch {
    return false
  }
}
