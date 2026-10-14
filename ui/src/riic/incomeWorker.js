import { runCalculationBridge } from './vendor/workbench/calculationBridge'
import { incomeRequest } from './income'

export function calculateIncome(plan, settings, onProgress) {
  const { workspace, options } = incomeRequest(plan, settings)
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
  const diagnostics = [
    ...(result.validation?.criticalErrors ?? []),
    ...(simulation?.diagnostics ?? [])
  ]
    .slice(0, 200)
    .map((d) => ({
      code: d.code,
      message:
        d.message +
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
  return {
    success: true,
    summary: {
      ...result.report.summary,
      recycleCount:
        (simulation.production?.recycle?.sampleCompletedItems ?? 0) /
        (simulation.observedHours / 24)
    },
    diagnostics,
    observedHours: simulation.observedHours,
    rooms: simulation.rooms.map((r) => ({
      roomId: r.roomId,
      averageEfficiencyPercent: r.averageEfficiencyPercent
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
