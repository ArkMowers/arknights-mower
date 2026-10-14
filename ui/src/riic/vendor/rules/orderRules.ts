import type { QualityRule } from '../domain/types'

export type OrderMode = 'gold' | 'orundum' | 'closure' | 'pepe'
export interface BaseOrderChoice {
  probability: number
  baseMinutes: number
  goldCost: number
  lmdReward: number
  fragmentCost: number
  orundumReward: number
  efficiencyAffected: boolean
  mode: OrderMode
}
export interface SpecialCapture {
  proviso?: 0 | 1 | 2
  tequila?: 0 | 1 | 2
  uOfficial?: boolean
  closure?: boolean
  pepe?: boolean
}
export interface OrderSnapshot extends BaseOrderChoice {
  kind: 'gold' | 'proviso' | 'tequila' | 'uOfficial' | 'closure' | 'pepe' | 'orundum'
  completedAt: number
}

const gold = (probability: number, goldCost: number, lmdReward: number, baseMinutes: number): BaseOrderChoice => ({
  probability, goldCost, lmdReward, baseMinutes, fragmentCost: 0, orundumReward: 0,
  efficiencyAffected: true, mode: 'gold',
})

export function getOrderDistribution(level: number, quality: QualityRule = 'normal', mode: OrderMode = 'gold'): BaseOrderChoice[] {
  if (![1, 2, 3].includes(level)) throw new Error('Invalid trading level')
  if (mode === 'orundum') {
    if (level !== 3) throw new Error('Orundum orders require level 3')
    return [{ probability: 1, baseMinutes: 120, goldCost: 0, lmdReward: 0, fragmentCost: 2, orundumReward: 20, efficiencyAffected: true, mode }]
  }
  if (mode === 'closure') return [{ ...gold(1, 2, 1200, 144), mode }]
  if (mode === 'pepe') return [{ ...gold(1, 0, 1000, 270), efficiencyAffected: false, mode }]
  // Fixed quality model: the user requests the L3 alpha/beta probabilities at
  // L1/L2 too. PRTS only verifies these values for L3; this is a model extension.
  if (quality === 'normal' && level === 1) return [gold(1, 2, 1000, 144)]
  if (quality === 'normal' && level === 2) return [gold(0.6, 2, 1000, 144), gold(0.4, 3, 1500, 210)]
  const p = quality === 'alpha' ? [0.15, 0.3, 0.55] : quality === 'beta' ? [0.05, 0.1, 0.85] : [0.3, 0.5, 0.2]
  return [gold(p[0]!, 2, 1000, 144), gold(p[1]!, 3, 1500, 210), gold(p[2]!, 4, 2000, 276)]
}

export function selectBaseOrder(distribution: BaseOrderChoice[], choice: number): BaseOrderChoice {
  if (!Number.isFinite(choice) || choice < 0 || choice >= 1) throw new Error('Order choice must be in [0,1)')
  let cumulative = 0
  for (const item of distribution) {
    cumulative += item.probability
    if (choice < cumulative - 1e-12) return structuredClone(item)
  }
  throw new Error('Order distribution does not cover choice')
}

export function captureOrder(base: BaseOrderChoice, capture: SpecialCapture, completedAt: number): Readonly<OrderSnapshot> {
  if (!Number.isFinite(completedAt) || completedAt < 0) throw new Error('Invalid completion time')
  if (base.mode === 'pepe' && !capture.pepe) throw new Error('Pepe acquisition mode must be fixed at start')
  if (base.mode !== 'pepe' && capture.pepe) throw new Error('Pepe mode must be fixed at acquisition start')
  if (base.mode === 'closure' && !capture.closure) throw new Error('Closure acquisition mode must be fixed at start')
  if (base.mode !== 'closure' && base.mode !== 'pepe' && capture.closure) throw new Error('Closure mode must be fixed at acquisition start')
  let result: OrderSnapshot = { ...base, completedAt, kind: base.mode === 'orundum' ? 'orundum' : base.mode === 'pepe' ? 'pepe' : base.mode === 'closure' ? 'closure' : 'gold' }
  if (base.mode !== 'gold') return Object.freeze(result)
  if (capture.uOfficial) result = { ...result, kind: 'uOfficial', goldCost: 2, lmdReward: 1000 }
  else if ((capture.proviso ?? 0) > 0 && base.goldCost < 4) {
    const rank = capture.proviso!
    result = { ...result, kind: 'proviso', goldCost: base.goldCost + rank, lmdReward: base.lmdReward + rank * 500 }
  } else if ((capture.tequila ?? 0) > 0 && base.goldCost > 3) {
    const extra = capture.tequila === 2 ? 500 : 250
    result = { ...result, kind: 'tequila', lmdReward: base.lmdReward + extra }
  }
  return Object.freeze(result)
}
