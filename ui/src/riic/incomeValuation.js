import { incomeWeights } from './income'
import { calculateIncomeSanity } from './incomeSanity'
import { scoreProduction } from './vendor/domain/productionScore'

export function revalueIncome(result, settings) {
  if (!result?.success) throw new Error('演算完成后才能切换收益算法')
  const previous = result.summary
  if (!['exp', 'goldCount', 'orderLmd'].every((key) => Number.isFinite(previous?.[key])))
    throw new Error('这份历史记录缺少产出明细，无法切换收益算法')
  const weights = incomeWeights(settings)
  const scoreBreakdown = scoreProduction(
    {
      exp: previous.exp,
      gold: previous.goldCount,
      orderLmd: previous.orderLmd,
      virtualGold: previous.virtualGoldCount ?? (previous.virtualGoldValue ?? 0) / 500,
      fragments: previous.fragments ?? 0,
      orundum: previous.orundum ?? 0
    },
    24,
    weights
  )
  const summary = { ...previous, scoreBreakdown, totalScore82: scoreBreakdown.total }
  delete summary.sanity
  if (settings.weightMode === 'sanity') {
    if (!result.simulationReport?.production)
      throw new Error('这份历史记录缺少材料消耗明细，无法切换理智算法')
    summary.sanity = calculateIncomeSanity(
      summary,
      settings.sanityValuation,
      result.simulationReport
    )
  }
  const valuation = JSON.parse(
    JSON.stringify({
      weightMode: settings.weightMode,
      mowerAlgorithm: settings.mowerAlgorithm,
      mowerWeights: settings.mowerWeights,
      productionWeights: settings.productionWeights,
      sanityValuation: settings.sanityValuation
    })
  )
  return { result: { ...result, summary }, valuation }
}
