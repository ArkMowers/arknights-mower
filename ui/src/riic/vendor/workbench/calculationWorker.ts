import { runCalculationBridge, type CalculationBridgeOptions, type CalculationBridgeResult } from './calculationBridge'
import type { RosterWorkspace } from '../domain/roster'
import { buildTimelineData, type TimelineDataset } from './timeline/timelineModel'
import type { SimulationActivity } from '../simulator/simulationActivity'

export interface CalculationProgress { label: string; fraction: number; activity?: SimulationActivity }
export type CalculationWorkerMessage =
  | { type: 'progress'; progress: CalculationProgress }
  | { type: 'complete'; result: CalculationBridgeResult; timelineData: TimelineDataset | null }
  | { type: 'error'; error: string }

self.onmessage = (event: MessageEvent<{ workspace: RosterWorkspace; options: CalculationBridgeOptions }>) => {
  const send = (message: CalculationWorkerMessage) => self.postMessage(message)
  try {
    send({ type: 'progress', progress: { label: '正在准备排班与干员数据…', fraction: 0 } })
    const result = runCalculationBridge(event.data.workspace, event.data.options, p => {
      const warmup = p.phase === 'warmup'
      const done = warmup ? p.elapsedHours : p.elapsedHours - p.warmupHours
      const total = warmup ? p.warmupHours : p.totalHours - p.warmupHours
      send({ type: 'progress', progress: {
        label: `正在${warmup ? '预热' : '采样'} ${done.toFixed(1)} / ${total.toFixed(1)} 小时`,
        fraction: Math.min(.99, p.elapsedHours / p.totalHours),
        activity: p.activity,
      } })
    })
    send({ type: 'progress', progress: { label: '正在汇总产出报告…', fraction: .99 } })
    const timelineData = result.simulationReport ? buildTimelineData(result.simulationReport) : null
    send({ type: 'complete', result, timelineData })
  } catch (error) {
    send({ type: 'error', error: error instanceof Error ? error.message : String(error) })
  }
}
