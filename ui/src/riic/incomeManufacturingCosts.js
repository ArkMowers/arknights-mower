export function incomeManufacturingCosts(simulation) {
  const production = simulation?.production
  const days = simulation?.observedHours / 24
  if (!production || !(days > 0) || !Number.isFinite(days)) return null
  let costs
  if (production.assumptions?.expectationMode && production.expected) {
    costs = production.expected.costs
  } else if (production.assumptions?.outputMode === 'potential') {
    const start = simulation.assumptions?.warmupHours
    const end = simulation.elapsedHours
    if (!Array.isArray(production.events) || !Number.isFinite(start) || !Number.isFinite(end))
      return null
    costs = { lmd: 0, orirock: 0, device: 0 }
    for (const event of production.events) {
      if (event.type !== 'manufacture-cost' || event.time < start || event.time > end) continue
      for (const resource of Object.keys(costs)) costs[resource] -= event.delta?.[resource] ?? 0
    }
  } else {
    if (!production.sample?.outflows) return null
    costs = production.sample.outflows
  }
  return {
    lmdConsumed: (costs.lmd ?? 0) / days,
    orirockConsumed: (costs.orirock ?? 0) / days,
    deviceConsumed: (costs.device ?? 0) / days
  }
}
