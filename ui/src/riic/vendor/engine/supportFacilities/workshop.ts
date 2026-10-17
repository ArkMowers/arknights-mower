import rules from '../../data/support-facilities.generated.json'
import { operatorFor } from '../../domain/operatorContext'
import type { AppConfig } from '../../domain/types'
import { isSupportOperatorWorking, SUPPORT_OPERATOR_IDS } from './conditions'

export const WORKSHOP_FORMULAS = rules.workshop.formulas
const HOMEBOUND = SUPPORT_OPERATOR_IDS.homebound
const HOMEBOUND_PRODUCTS = new Set(['31094', '30165'])
const HOMEBOUND_BUFF = 'workshop_formula_device[080]'

/** This formula-specific bonus is relative to its base chance, not percentage points. */
export function evaluateHomeboundByproduct(
  config: AppConfig,
  itemId: string,
): { baseProbability: number; probability: number; bonusPercent: number } {
  const formula = WORKSHOP_FORMULAS.find(formula => formula.itemId === itemId)
  if (!formula) throw new Error(`Unknown workshop product: ${itemId}`)
  let bonusPercent = 0
  if (config.facilities.workshop && config.facilityOperatorIds.workshop.includes(HOMEBOUND) &&
      isSupportOperatorWorking(config, HOMEBOUND)) {
    for (const skill of operatorFor(config, HOMEBOUND)?.skills ?? []) {
      if (skill.roomType !== 'WORKSHOP') continue
      if (skill.buffId !== HOMEBOUND_BUFF) {
        throw new Error(`Unquantified workshop skill: ${HOMEBOUND}/${skill.buffId}`)
      }
      if (HOMEBOUND_PRODUCTS.has(itemId)) bonusPercent += 90
    }
  }
  return {
    baseProbability: formula.baseByproductRate,
    probability: Math.min(1, formula.baseByproductRate * (1 + bonusPercent / 100)),
    bonusPercent,
  }
}
