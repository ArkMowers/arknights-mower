import { importMowerJson } from './vendor/workbench/compat/mowerJson'
import { resolveOperatorCharId } from './vendor/domain/operatorIdentifiers'
import { compileOperatorInventory, parseOperatorInventory } from './vendor/domain/operatorInventory'
import { inventoryOperatorRecords } from './vendor/domain/operatorContext'
import { qualitySkillWarmupHours } from './vendor/engine/timeDependentSkills'

// Inspect possible trade rosters before choosing this run's order model.
export function incomeHasTailor(plan, settings) {
  if (!plan?.[plan.default || 'plan1']) return false
  const workspace = importMowerJson(JSON.stringify(plan))
  const tradeRooms = Object.values(workspace.mainPlan.facilities).filter(
    (room) => room.type === 'trading'
  )
  const ids = new Set()
  const add = (name) => {
    if (typeof name === 'string') ids.add(resolveOperatorCharId(name))
  }
  const list = (value) => (Array.isArray(value) ? value : [])
  const rawSlot = (slot) => {
    add(slot?.agent)
    for (const name of list(slot?.replacement)) add(name)
    for (const binding of list(slot?.group_bindings))
      for (const name of list(binding?.replacement)) add(name)
  }
  for (const room of tradeRooms) {
    for (const slot of room.slots) {
      if (slot.occupant.kind === 'operator') add(slot.occupant.operatorId)
      for (const name of slot.replacements) add(name)
      for (const binding of slot.groupBindings ?? [])
        for (const name of binding.replacements) add(name)
    }
    for (const backup of workspace.compatibility.backupPlans) {
      for (const slot of list(backup?.plan?.[room.roomId]?.plans)) rawSlot(slot)
      for (const name of list(backup?.task?.[room.roomId])) add(name)
    }
  }
  let inputs
  if (settings.operatorMode === 'cache') {
    if (!settings.cachedOperators) return false
    inputs = settings.cachedOperators
  } else if (settings.operatorMode === 'custom') {
    const parsed = parseOperatorInventory(settings.operatorText)
    if (!parsed.valid) return false
    inputs = parsed.entries
  }
  let context = {}
  if (inputs) {
    const inventory = compileOperatorInventory(inputs)
    if (!inventory.valid) return false
    context = { operatorRecords: inventoryOperatorRecords(inventory) }
  }
  return [...ids].some(
    (id) =>
      (!inputs || Object.hasOwn(context.operatorRecords, id)) &&
      qualitySkillWarmupHours(id, context) > 0
  )
}
