import { runCalculationBridge } from './vendor/workbench/calculationBridge'
import { incomeRequest } from './income'
import { incomeEventLog } from './incomeLogs'
import { incomeOrderDistribution } from './incomeOrders'
import { createRecruitmentObservation } from './incomeRecruitment'
import { createClueObservation } from './incomeClues'
import { buildTimelineData } from './vendor/workbench/timeline/timelineModel'

export function calculateIncome(plan, settings, onProgress) {
  const { workspace, options } = incomeRequest(plan, settings)
  const recruitment = createRecruitmentObservation(settings.warmupDays * 24)
  const clues = createClueObservation(
    settings.warmupDays * 24,
    options.simulationOptions.operatorInventory
  )
  options.simulationOptions.observeInterval = (config, start, end) => {
    recruitment.observe(config, start, end)
    clues.observe(config, start, end)
  }
  const result = runCalculationBridge(workspace, options, (p) =>
    onProgress?.({
      label: `${p.phase === 'warmup' ? '预热' : '统计'} ${(p.phase === 'warmup'
        ? p.elapsedHours
        : p.elapsedHours - p.warmupHours
      ).toFixed(1)} / ${p.phase === 'warmup' ? p.warmupHours : p.totalHours - p.warmupHours} 小时`,
      fraction: Math.min(0.99, p.elapsedHours / p.totalHours),
      activity: p.activity
    })
  )
  const simulation = result.simulationReport
  const diagnostics = [...(result.validation?.issues ?? []), ...(simulation?.diagnostics ?? [])]
    .slice(0, 200)
    .map((d) => ({
      code: d.code,
      message:
        (d.code === 'MOWER_CLUE_OBSERVATION_MODEL'
          ? '线索产量按交流固定开启计算；调度侧 Party Time 仍为空，不执行线索待办及交流任务。'
          : d.message) +
        (d.code === 'FINITE_INVENTORY_MODEL' && settings.allowGoldDebt
          ? ' 本次允许赤金透支，赤金不足不阻止交付；其他材料仍受库存约束。'
          : '')
    }))
  if (!result.success || !result.report)
    return {
      success: false,
      error: result.error || diagnostics.map((d) => d.message).join('；') || '演算未完成',
      diagnostics
    }
  const days = simulation.observedHours / 24
  const production = simulation.production
  const potentialLmdCost = production.events
    .filter(
      (e) =>
        e.type === 'manufacture-cost' &&
        e.time >= simulation.assumptions.warmupHours &&
        e.time <= simulation.elapsedHours
    )
    .reduce((sum, e) => sum - (e.delta?.lmd ?? 0), 0)
  const netLmd =
    production.assumptions.outputMode === 'potential'
      ? result.report.summary.orderLmd - potentialLmdCost / days
      : (production.sample.net.lmd ?? 0) / days
  return {
    success: true,
    eventLog: incomeEventLog(simulation),
    orderDistribution: incomeOrderDistribution(simulation),
    simulationReport: simulation,
    timelineData: buildTimelineData(simulation),
    resources: production.sample,
    droneRooms: [
      ...new Set(
        production.events
          .filter((e) => e.roomId && /(?:^|-)drone$/.test(e.type) && e.amount > 0)
          .map((e) => e.roomId)
      )
    ],
    clueExchangeMode: 'always-on',
    summary: {
      ...result.report.summary,
      netLmd,
      recruitmentCount: recruitment.result().completed / days,
      clueCount: clues.result().completed / days,
      lmdConsumed:
        production.assumptions.outputMode === 'potential'
          ? potentialLmdCost / days
          : (production.sample.outflows.lmd ?? 0) / days,
      recycleCount:
        (simulation.production?.recycle?.sampleCompletedItems ?? 0) /
        (simulation.observedHours / 24)
    },
    diagnostics,
    observedHours: simulation.observedHours,
    rooms: simulation.rooms.map((r) => ({
      roomId: r.roomId,
      averageEfficiencyPercent: r.averageEfficiencyPercent,
      occupiedHours: r.occupiedHours
    })),
    assumptions: simulation.assumptions,
    inventoryMode: simulation.production?.assumptions.inventoryMode,
    goldInventory: {
      initial: simulation.production?.ledger.initial.gold ?? 0,
      sampleOpening: simulation.production?.sample.opening.gold ?? 0,
      closing: simulation.production?.sample.closing.gold ?? 0
    }
  }
}

if (typeof self !== 'undefined' && typeof document === 'undefined') {
  self.onmessage = ({ data }) => {
    try {
      self.postMessage({ type: 'progress', progress: { label: '正在准备排班数据', fraction: 0 } })
      const result = calculateIncome(data.plan, data.settings, (progress) =>
        self.postMessage({ type: 'progress', progress })
      )
      self.postMessage({ type: 'complete', result })
    } catch (error) {
      self.postMessage({ type: 'error', error: error.message || String(error) })
    }
  }
}
