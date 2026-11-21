import { OPERATOR_MAP } from '../domain/operators'
import type { SimulationActivity } from '../simulator/simulationActivity'
import type { CalculationProgress } from './calculationWorker'

export type CalculationOutcome = 'completed' | 'cancelled' | 'failed' | 'changed'
export interface BottleneckObservation { activity: SimulationActivity; receivedSeconds: number }
export interface CalculationBottleneckSummary {
  outcome: CalculationOutcome
  elapsedSeconds: number
  progressLabel: string
  latest?: BottleneckObservation
  slowest?: BottleneckObservation
  silence?: { seconds: number; lastProgressSeconds: number | null }
  diagnostics: { code: string; message: string }[]
  error?: string
}
const relevantDiagnostics = new Set([
  'group-blocked', 'mower-shift-bed-conflict', 'mower-backup-cycle', 'mower-backup-deferred',
  'mower-task-exception', 'mower-plan-solver-exception', 'mower-planning-exception',
  'BACKUP_EXECUTION_FAILED', 'SIMULATION_EVENT_LIMIT', 'SIMULATION_SAME_TIME_ACTION',
  'SIMULATION_STALLED', 'SHIFT_DEFERRED_RECOVERED',
])
const readable = (text: string) => text.replace(/\bchar_\d+_[a-zA-Z0-9_]+\b/g, id => OPERATOR_MAP.get(id)?.name ?? id).slice(0, 1000)
const snapshot = (activity: SimulationActivity, receivedSeconds: number): BottleneckObservation => ({
  receivedSeconds,
  activity: {
    ...activity, message: activity.message.slice(0, 1000),
    operators: activity.operators.slice(0, 5).map(operator => ({ ...operator, groups: operator.groups.slice(0, 20) })),
    recentEvents: activity.recentEvents.slice(0, 5).map(event => ({ ...event })),
    task: activity.task ? { ...activity.task, metadata: activity.task.metadata.slice(0, 1000), rooms: activity.task.rooms.slice(0, 20) } : undefined,
    findings: activity.findings?.slice(0, 6).map(finding => ({ ...finding, message: readable(finding.message), operatorIds: finding.operatorIds.slice(0, 20) })),
  },
})

/** Keeps bounded historical observations independently of the live progress UI. */
export function createCalculationBottleneckTracker() {
  let latest: BottleneckObservation | undefined
  let slowest: BottleneckObservation | undefined
  let progressLabel = '正在准备计算…'
  let lastProgressSeconds: number | null = null
  const constraints = new Map<string, { code: string; message: string }>()
  const remember = (diagnostic: { code: string; message: string }) => {
    const key = diagnostic.code + '\0' + diagnostic.message
    constraints.delete(key)
    constraints.set(key, diagnostic)
    if (constraints.size > 12) constraints.delete(constraints.keys().next().value!)
  }
  return {
    observe(progress: CalculationProgress, elapsedSeconds: number) {
      progressLabel = progress.label.slice(0, 500)
      lastProgressSeconds = elapsedSeconds
      if (!progress.activity) return
      latest = snapshot(progress.activity, elapsedSeconds)
      const activity = latest.activity
      if (activity.status === 'slow') {
        const rate = (value: SimulationActivity) => value.advancedHours / Math.max(1, value.windowSeconds)
        if (!slowest || rate(activity) < rate(slowest.activity)
          || (rate(activity) === rate(slowest.activity) && activity.iterations >= slowest.activity.iterations)) slowest = latest
      }
      for (const finding of activity.findings ?? []) if (finding.kind === 'constraint') remember({ code: finding.code, message: finding.message })
    },
    finish(options: { outcome: CalculationOutcome; elapsedSeconds: number; error?: string; diagnostics?: { code: string; message: string }[] }): CalculationBottleneckSummary {
      for (const diagnostic of options.diagnostics ?? []) if (relevantDiagnostics.has(diagnostic.code)) {
        remember({ code: diagnostic.code, message: `演算曾报告：${readable(diagnostic.message)}` })
      }
      const silenceSeconds = Math.floor(options.elapsedSeconds - (lastProgressSeconds ?? 0))
      return {
        outcome: options.outcome, elapsedSeconds: options.elapsedSeconds, progressLabel,
        latest, slowest, diagnostics: [...constraints.values()], error: options.error?.slice(0, 2000),
        ...(silenceSeconds >= 15 ? { silence: { seconds: silenceSeconds, lastProgressSeconds } } : {}),
      }
    },
  }
}
