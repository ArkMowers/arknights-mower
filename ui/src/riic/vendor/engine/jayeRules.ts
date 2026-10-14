/**
 * Highest-phase Jaye only. Inputs are already-resolved per-operator values;
 * this module intentionally does not parse descriptions or rebuild global state.
 * Source: building.tradingData.phases; cc.t.strong2; scratch/jaye-audit.md.
 */
export const TRADING_BASE_ORDER_LIMIT = [6, 8, 10] as const

export interface JayePartnerContribution {
  operatorId: string
  /** Net personal efficiency, including personal central support (e.g. Gnosis). */
  efficiency: number
  /** Signed capacity contribution, including personal central support. */
  orderLimitDelta: number
  /** The resolved subset Snowsant may copy; excludes room-wide central bonuses. */
  snowsantCopyableEfficiency: number
  /** Order-limit-to-efficiency rules need a separately verified evaluation order. */
  dependsOnOrderLimit?: boolean
  /** Any bonus efficiency that is derived from order limit, which does not affect Jaye's capacity deduction. */
  orderLimitDerivedEfficiency?: number
}

export interface HighestPhaseJayeInput {
  roomLevel: number
  /** Excludes Jaye and Snowsant; includes every other active colleague. */
  partners: readonly JayePartnerContribution[]
  /** A separate recipient, so her copy never recursively reads Jaye's efficiency. */
  snowsant?: { operatorId: string; cap: 25 | 35 }
  /** Must be true only when both independent Jaye skills are unlocked and active. */
  hasBothJayeSkills: boolean
  /** When true, evaluates Jaye as Elite 0 (first skill only, 0 capacity deduction). */
  isElite0?: boolean
  /** Shamare clearing removes the entire Jaye and Snowsant efficiency result. */
  clearedByShamare?: boolean
  /** Optional runtime check; omission means ordinary legal queue state (0 in shift-run). */
  queuedOrders?: number
}

export type JayeUnsupportedReason =
  | 'JAYE_REQUIRES_BOTH_ACTIVE_SKILLS'
  | 'JAYE_INVALID_INPUT'
  | 'JAYE_ORDER_LIMIT_EFFICIENCY_DEPENDENCY'
  | 'JAYE_NEGATIVE_EFFICIENCY_UNVERIFIED'
  | 'JAYE_QUEUE_EXCEEDS_EFFECTIVE_LIMIT'

export type HighestPhaseJayeResult =
  | { supported: false; reason: JayeUnsupportedReason; detail: string }
  | {
      supported: true
      jayeEfficiency: number
      snowsantEfficiency: number
      /** Null for cleared output: no claim is made about live queue capacity. */
      effectiveOrderLimit: number | null
      capacityReduction: number | null
      otherEfficiency: number
    }

/** Resolves only Jaye + optional Snowsant; caller adds colleagues/staff/room bonuses once. */
export function evaluateHighestPhaseJaye(input: HighestPhaseJayeInput): HighestPhaseJayeResult {
  if (!input.hasBothJayeSkills && !input.isElite0) {
    return { supported: false, reason: 'JAYE_REQUIRES_BOTH_ACTIVE_SKILLS', detail: '精零或失效孑不能使用双技能队列抵消公式。' }
  }
  if (!Number.isInteger(input.roomLevel) || input.roomLevel < 1 || input.roomLevel > 3 ||
      (input.queuedOrders !== undefined && (!Number.isInteger(input.queuedOrders) || input.queuedOrders < 0)) ||
      new Set(input.partners.map(partner => partner.operatorId)).size !== input.partners.length ||
      (input.snowsant !== undefined && (input.partners.some(partner => partner.operatorId === input.snowsant!.operatorId) ||
        ![25, 35].includes(input.snowsant.cap))) ||
      input.partners.some(partner => !Number.isFinite(partner.efficiency) ||
        !Number.isFinite(partner.snowsantCopyableEfficiency) || !Number.isInteger(partner.orderLimitDelta))) {
    return { supported: false, reason: 'JAYE_INVALID_INPUT', detail: '需要合法站等级、唯一干员、有限效率、整数容量及非负整数订单数。' }
  }
  // Clearing settles this efficiency question without guessing any unresolved capacity.
  if (input.clearedByShamare) {
    return { supported: true, jayeEfficiency: 0, snowsantEfficiency: 0,
      effectiveOrderLimit: null, capacityReduction: null, otherEfficiency: 0 }
  }
  const partnerBaseEff = (partner: JayePartnerContribution) =>
    partner.orderLimitDerivedEfficiency !== undefined
      ? Math.max(0, partner.efficiency - partner.orderLimitDerivedEfficiency)
      : partner.efficiency
  const partnerBaseCopyable = (partner: JayePartnerContribution) =>
    partner.orderLimitDerivedEfficiency !== undefined
      ? Math.max(0, partner.snowsantCopyableEfficiency - partner.orderLimitDerivedEfficiency)
      : partner.snowsantCopyableEfficiency

  if (input.partners.some(partner => partnerBaseEff(partner) < 0 || partnerBaseCopyable(partner) < 0)) {
    return { supported: false, reason: 'JAYE_NEGATIVE_EFFICIENCY_UNVERIFIED', detail: '负的干员净效率参与孑扣容量时的取整规则尚未验证。' }
  }
  const copiedSource = input.partners.reduce((sum, partner) => sum + partnerBaseCopyable(partner), 0)
  const snowsantEfficiency = input.snowsant ? Math.min(input.snowsant.cap, Math.floor(copiedSource / 5) * 5) : 0
  const otherEfficiency = input.partners.reduce((sum, partner) => sum + partnerBaseEff(partner), 0) + snowsantEfficiency
  const capacityReduction = input.isElite0 ? 0 : Math.floor(otherEfficiency / 10)
  const effectiveOrderLimit = Math.max(1, TRADING_BASE_ORDER_LIMIT[input.roomLevel - 1]! +
    input.partners.reduce((sum, partner) => sum + partner.orderLimitDelta, 0) - capacityReduction)
  if (input.queuedOrders !== undefined && input.queuedOrders > effectiveOrderLimit) {
    return { supported: false, reason: 'JAYE_QUEUE_EXCEEDS_EFFECTIVE_LIMIT', detail: '现存订单超过换班后上限，双技能在该暂态下的钳制语义未验证。' }
  }
  const queued = input.queuedOrders ?? 0
  const jayeEfficiency = input.isElite0
    ? Math.max(0, effectiveOrderLimit - queued) * 4
    : effectiveOrderLimit * 4
  return { supported: true, jayeEfficiency, snowsantEfficiency,
    effectiveOrderLimit, capacityReduction, otherEfficiency }
}
