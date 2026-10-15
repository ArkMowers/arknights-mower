import { getOrderDistribution } from './vendor/rules/orderRules'

// Completion snapshots retain acquisition workload even after reward conversions.
const goldByWorkload = new Map(
  getOrderDistribution(3).map((order) => [order.baseMinutes, order.goldCost])
)

export function incomeOrderDistribution(report) {
  if (!Array.isArray(report?.production?.events)) return null
  const start = report.assumptions?.warmupHours
  const end = report.elapsedHours
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start) return null
  const counts = { 2: 0, 3: 0, 4: 0 }
  let total = 0
  let other = 0
  for (const event of report.production.events) {
    if (event.type !== 'order-completed' || !(event.time > start && event.time <= end)) continue
    total++
    const gold =
      event.order?.mode === 'gold' ? goldByWorkload.get(event.order.baseMinutes) : undefined
    if (gold === undefined) other++
    else counts[gold]++
  }
  return {
    total,
    other,
    rows: [2, 3, 4].map((gold) => ({
      gold,
      count: counts[gold],
      ratio: total > 0 ? counts[gold] / total : 0
    }))
  }
}
