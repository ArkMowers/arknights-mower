import { MOWER_INVENTORY_ITEMS } from './vendor/domain/simulationInventory'

export function applyIncomeCache(settings, cache) {
  settings.cachedOperators = cache.has_roster
    ? cache.operators
        .filter((op) => op.owned === true)
        .map((op) => ({
          operator: op.name,
          elitePhase: op.phase,
          level: op.level
        }))
    : null
  settings.cachedInventory = cache.has_inventory
    ? Object.fromEntries(
        MOWER_INVENTORY_ITEMS.map(({ resource }) => [resource, cache.inventory[resource] ?? null])
      )
    : null
  settings.cacheObservedAt = cache.observed_at ?? null
}

export function incomeInitialInventory(settings) {
  if (settings.inventorySource === 'manual') return settings.initialInventory
  if (settings.inventorySource !== 'cache') throw new Error('库存来源无效')
  if (!settings.cachedInventory) throw new Error('没有可用的森空岛库存缓存，请先同步或选择手动设定')
  const missing = MOWER_INVENTORY_ITEMS.filter(
    ({ resource }) => settings.cachedInventory[resource] == null
  )
  if (missing.length)
    throw new Error(`森空岛未提供 ${missing.map((item) => item.label).join('、')}，请补填数量`)
  return settings.cachedInventory
}
