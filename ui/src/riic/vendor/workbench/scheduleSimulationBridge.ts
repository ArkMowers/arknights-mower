import { compileRosterSchedule } from '../scheduler/compileRosterSchedule'
import type { SimulationAssumptions } from '../scheduler/types'
import { simulateSchedule, type ScheduleSimulationOptions, type ScheduleSimulationReport, type ScheduleSimulationProgress } from '../simulator/scheduleSimulation'
import type { RosterWorkspace } from '../domain/roster'
import { validateRosterWorkspace } from './validate'
import { normalizeProductionWeights } from '../domain/productionWeights'

export function runScheduleSimulationBridge(
  workspace: RosterWorkspace,
  options: ScheduleSimulationOptions = {},
  assumptions: Partial<SimulationAssumptions> = {},
  onProgress?: (progress: ScheduleSimulationProgress) => void,
): { report: ScheduleSimulationReport | null; error?: string } {
  const cleanWorkspace: RosterWorkspace = JSON.parse(JSON.stringify(workspace))
  const cleanOptions: ScheduleSimulationOptions = { schedulingModel: 'mower-alpha', ...JSON.parse(JSON.stringify(options)) }
  cleanOptions.observeInterval = options.observeInterval
  const cleanAssumptions: Partial<SimulationAssumptions> = JSON.parse(JSON.stringify(assumptions))

  const validation = validateRosterWorkspace(cleanWorkspace)
  if (!validation.isValid) {
    return {
      report: null,
      error: `排班存在阻断错误：${validation.criticalErrors.map(d => d.message).join('；')}`,
    }
  }

  try {
    cleanOptions.productionWeights = normalizeProductionWeights(options.productionWeights ?? workspace.productionWeights)
    const report = simulateSchedule(compileRosterSchedule(cleanWorkspace, cleanAssumptions), cleanOptions, onProgress)
    return { report }
  } catch (error) {
    return {
      report: null,
      error: error instanceof Error ? error.message : String(error),
    }
  }
}
