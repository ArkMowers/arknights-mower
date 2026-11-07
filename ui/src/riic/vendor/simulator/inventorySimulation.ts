import { MOWER_INVENTORY_ITEMS, normalizeSimulationInventory } from '../domain/simulationInventory'
import { compileBackupExpression } from '../scheduler/backupExpression'
import type { CompiledSchedule } from '../scheduler/types'
import type { ProductionOptions } from './productionTimeline'

/** Inventory conditions always observe a finite ledger, including headless callers. */
export function resolveInventoryProduction(schedule: CompiledSchedule, options?: ProductionOptions): ProductionOptions | undefined {
  let usesInventory = false, usesProduct = false
  for (const plan of schedule.sourceWorkspace.compatibility.backupPlans) {
    if (!plan || typeof plan !== 'object') continue
    try {
      const expression = compileBackupExpression((plan as Record<string, unknown>).trigger, new Set())
      usesInventory ||= expression.usesInventory
      usesProduct ||= expression.usesFacilityProduct
    } catch { /* The backup compiler reports invalid conditions with their plan name. */ }
  }
  if (!usesInventory && options?.inventoryMode !== 'finite') return options ?? (usesProduct ? {} : undefined)
  const supplied = options?.initialResources ?? {}
  const inventory = normalizeSimulationInventory(Object.fromEntries(
    MOWER_INVENTORY_ITEMS.filter(item => Object.prototype.hasOwnProperty.call(supplied, item.resource)).map(item => [item.resource, supplied[item.resource]]),
  ))!
  return { ...options, outputMode: 'settled', inventoryMode: 'finite', initialResources: { ...supplied, ...inventory } }
}
