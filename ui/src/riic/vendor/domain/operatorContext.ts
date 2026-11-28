import { OPERATOR_MAP, type OperatorRecord } from './operators'
import type { OperatorInventory } from './operatorInventory'

export interface OperatorContext { operatorRecords?: Readonly<Record<string, OperatorRecord>> }

/** Per-calculation snapshots: never mutate the shared maximum-skill catalog. */
export function inventoryOperatorRecords(inventory: OperatorInventory): Record<string, OperatorRecord> {
  return Object.fromEntries(inventory.operators.map(o => [o.charId, {
    ...OPERATOR_MAP.get(o.charId)!, skills: o.skills,
  }]))
}

export function operatorFor(context: OperatorContext, id: string): OperatorRecord | undefined {
  return context.operatorRecords?.[id] ?? OPERATOR_MAP.get(id)
}

export function hasOperatorSkill(context: OperatorContext, id: string, buffId: string): boolean {
  return operatorFor(context, id)?.skills.some(s => s.buffId === buffId) ?? false
}

export function runOrderSkillRank(context: OperatorContext, id: string, kind: 'proviso' | 'tequila'): 0 | 1 | 2 {
  const prefix = kind === 'proviso' ? 'trade_ord_against' : 'trade_ord_long'
  if (hasOperatorSkill(context, id, prefix + '[010]')) return 2
  return hasOperatorSkill(context, id, prefix + '[000]') ? 1 : 0
}
