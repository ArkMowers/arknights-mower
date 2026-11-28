import { matchesRiicIdentity } from '../domain/riicIdentity'
import type { AppConfig } from '../domain/types'
import type { OperatorRecord, OperatorSkill } from '../domain/operators'

/** Inputs distinguish physical presence from active skill providers. */
export interface TradeConditionalContext {
  config: AppConfig
  roomOperators: readonly OperatorRecord[]
  presentOperators: readonly OperatorRecord[]
  eliteFacilities: number
  woodCatnip: number
}

export interface ConditionalTradeBonus {
  value: number
  /** The result already contains any named same-room partner bonus. */
  includesNamedTarget: boolean
}

/** Source-backed additions that must be evaluated before a direct-percent parser. */
export function evaluateTradeConditionalSkill(
  skill: OperatorSkill,
  context: TradeConditionalContext,
): ConditionalTradeBonus | null {
  const { config, roomOperators, presentOperators } = context
  const bonus = (value: number, includesNamedTarget = false): ConditionalTradeBonus =>
    ({ value, includesNamedTarget })
  switch (skill.buffId) {
    case 'trade_ord_spd&formula[000]': {
      const recipes = new Set(config.rooms.filter(room => room.type === 'manufacture').map(room => room.product))
      return bonus(30 + recipes.size * 2)
    }
    case 'trade_ord_spd&par[001]':
      return bonus(30 + (roomOperators.some(operator => matchesRiicIdentity(operator, 'groupId', 'glasgow')) ? 10 : 0))
    case 'trade_ord_spd_par[000]':
      return bonus(
        roomOperators.filter(operator => matchesRiicIdentity(operator, 'groupId', 'glasgow')).length * 20 +
          (roomOperators.some(operator => operator.name === '推进之王') ? 35 : 0),
        true,
      )
    case 'trade_ord_spd&tag[010]':
      return bonus(25 + Math.min(10, context.eliteFacilities) * 2)
    case 'trade_ord_spd&limit&bd[000]':
      return bonus(5 + context.woodCatnip * 3)
    case 'trade_ord_spd_ext[020]':
      return bonus(25 + (presentOperators.some(operator => operator.name === '伺夜') ? 5 : 0))
    case 'trade_ord_spd_ext[021]':
      return bonus(30 + (presentOperators.some(operator => operator.name === '伺夜') ? 10 : 0))
    default:
      return null
  }
}

/** This new skill says stationed in manufacture, not merely present anywhere in base. */
export function evaluateAigisPowerSkill(
  skill: OperatorSkill,
  manufactureOperators: readonly OperatorRecord[],
): number | null {
  if (skill.buffId !== 'power_rec_spd_P2[999]') return null
  return 15 + (manufactureOperators.some(operator => operator.name === '结城理') ? 5 : 0)
}

export interface EvaluatedTradeContribution {
  operatorId: string
  /** Evaluated skill value only; no station baseline or room-level bonus. */
  skillBonus: number
}

/**
 * Snowsant resolves after ordinary and conditional skills. Copy skills are
 * excluded from the input sum to prevent recursive/self-referential copying.
 * The caller passes values after room zeroing and tracks unquantified inputs.
 */
export function snowsantCopiedTradeBonus(
  contributions: readonly EvaluatedTradeContribution[],
  copyOperatorIds: ReadonlySet<string>,
  cap: 25 | 35,
): number {
  const supplied = contributions
    .filter(contribution => !copyOperatorIds.has(contribution.operatorId))
    .reduce((sum, contribution) => sum + contribution.skillBonus, 0)
  return Math.min(cap, Math.max(0, Math.floor(supplied / 5) * 5))
}
