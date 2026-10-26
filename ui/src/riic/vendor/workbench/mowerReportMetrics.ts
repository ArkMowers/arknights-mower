import type { ScheduleSimulationReport } from '../simulator/scheduleSimulation'
import { scoreSimulationProduction, simulationOutputOrders } from '../simulator/productionScore'
import { virtualGoldEquivalent } from '../rules/orderValue'

/** Shared weighted report; the default 82 coefficients value order premiums at 0.8.
 * Virtual gold is a reporting convention, never a physical gold inventory inflow.
 */
export function mowerReportMetrics(report: ScheduleSimulationReport) {
  const production = report.production
  if (!report.success || !production?.success || report.observedHours <= 0) return null
  const factor = 24 / report.observedHours
  const orders = simulationOutputOrders(report).filter(order => order.kind !== 'orundum')
  const virtualGoldCount = orders.reduce((n, o) => n + virtualGoldEquivalent(o), 0)
  const score = scoreSimulationProduction(report)
  return {
    exp: score.exp, goldValue: score.goldValue, orderLmd: score.orderValue,
    virtualGoldCount: virtualGoldCount * factor,
    virtualGoldValue: virtualGoldCount * 500 * factor,
    mower82: score.total,
    scoreBreakdown: score,
    meanOrderValue: orders.length ? orders.reduce((n, o) => n + o.lmdReward, 0) / orders.length : null,
    orderCount: orders.length,
    orderDistribution: Object.fromEntries([...new Set(orders.map(o => o.kind))].map(kind => [kind, {
      count: orders.filter(o => o.kind === kind).length,
      lmd: orders.filter(o => o.kind === kind).reduce((n, o) => n + o.lmdReward, 0),
    }])),
  }
}
