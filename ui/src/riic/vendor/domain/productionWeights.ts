export interface ProductionWeights {
  exp: number
  gold: number
  orders: number
  fragments: number
  orundum: number
}

export const DEFAULT_PRODUCTION_WEIGHTS: Readonly<ProductionWeights> = Object.freeze({
  exp: 1, gold: .8, orders: .2, fragments: 0, orundum: 0,
})

export function normalizeProductionWeights(input?: Partial<ProductionWeights>): ProductionWeights {
  const result = { ...DEFAULT_PRODUCTION_WEIGHTS, ...input }
  for (const key of Object.keys(DEFAULT_PRODUCTION_WEIGHTS) as (keyof ProductionWeights)[]) {
    if (typeof result[key] !== 'number' || !Number.isFinite(result[key]) || result[key] < 0) {
      throw new Error('产出加权系数必须是有限的非负数')
    }
  }
  return result
}
