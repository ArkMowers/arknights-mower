import { inventoryOperatorRecords } from '../domain/operatorContext'
import { compileOperatorInventory } from '../domain/operatorInventory'
import type { AppConfig, CalculationReport, SummaryOutput } from '../domain/types'
import { createDefaultConfig } from '../domain/defaults'
import { calculate } from '../engine/calculate'
import type { SimulationAssumptions } from '../scheduler/types'
import { compileMainPlanToAppConfig } from './adapter'
import type { RosterWorkspace } from '../domain/roster'
import { validateRosterWorkspace, type ValidationResult } from './validate'
import { runScheduleSimulationBridge } from './scheduleSimulationBridge'
import { scoreSimulationProduction, simulationOutputAmounts, simulationOutputOrders } from '../simulator/productionScore'
import { scoreProductionAdjustment } from '../domain/productionScore'
import { normalizeProductionWeights } from '../domain/productionWeights'
import type { ScheduleSimulationOptions, ScheduleSimulationReport, ScheduleSimulationProgress } from '../simulator/scheduleSimulation'

export type CalculationEngineKind = 'legacy' | 'simulation'

export interface CalculationDiagnostic {
  code: string
  severity: 'error' | 'warning' | 'info'
  message: string
}

export interface CalculationBridgeOptions {
  engine?: CalculationEngineKind
  baseConfig?: AppConfig
  jayeElite0?: boolean
  simulationOptions?: ScheduleSimulationOptions
  simulationAssumptions?: Partial<SimulationAssumptions>
}

export interface CalculationBridgeResult {
  success: boolean
  report: CalculationReport | null
  simulationReport?: ScheduleSimulationReport | null
  validation: ValidationResult
  engine?: CalculationEngineKind
  diagnostics?: CalculationDiagnostic[]
  error?: string
}

export function simulationReportToCalculationReport(
  workspace: RosterWorkspace,
  simReport: ScheduleSimulationReport,
  baseConfig: AppConfig = createDefaultConfig(),
): CalculationReport {
  const days = simReport.observedHours > 0 ? simReport.observedHours / 24 : 1
  const output = simulationOutputAmounts(simReport)
  const potential = simReport.production?.assumptions.outputMode === 'potential'
  const outflows = simReport.production?.sample.outflows
  const inflows = simReport.production?.sample.inflows

  const exp = output.exp / days
  const goldCount = output.gold / days
  const goldValue = goldCount * 500
  const orderLmd = output.orderLmd / days

  const ordersGoldCost = simulationOutputOrders(simReport).reduce((n, order) => n + order.goldCost, 0) / days
  const goldConsumed = potential && !(outflows?.gold ?? 0) ? ordersGoldCost : (outflows?.gold ?? 0) / days
  const netGoldCount = goldCount - goldConsumed

  // A report equivalent, not a physical gold inflow. Closure and Pepe also have premiums.
  const virtualGoldCount = (output.virtualGold ?? 0) / days
  const virtualGoldValue = virtualGoldCount * 500

  const scoreBreakdown = scoreSimulationProduction(simReport)
  const totalScore82 = scoreBreakdown.total
  const totalEquivalentLmd = orderLmd + exp + (netGoldCount + virtualGoldCount) * 500

  const fragments = (output.fragments ?? 0) / days
  const orundum = (output.orundum ?? 0) / days
  const drones = (inflows?.drone ?? 0) / days

  const compiledConfig = compileMainPlanToAppConfig(workspace.mainPlan, workspace, baseConfig)
  compiledConfig.productionWeights = normalizeProductionWeights(simReport.inputs.options.productionWeights)
  if(simReport.inputs.options.operatorInventory)compiledConfig.operatorRecords=inventoryOperatorRecords(compileOperatorInventory(simReport.inputs.options.operatorInventory))
  if(simReport.inputs.options.jayeElite0 || baseConfig.jayeElite0)compiledConfig.jayeElite0=true
  const legacyReport = calculate(compiledConfig)

  const summary: SummaryOutput = {
    exp,
    goldCount,
    goldValue,
    virtualGoldCount,
    virtualGoldValue,
    orderLmd,
    fragments,
    orundum,
    goldConsumed,
    fragmentsConsumed: potential ? 0 : (outflows?.fragment ?? 0) / days,
    netGoldCount,
    netGoldValue: netGoldCount * 500,
    totalScore82,
    ...(simReport.production?.valuation?{valuation:(()=>{
      const v=simReport.production!.valuation!
      const value=(amounts:typeof v.adjustment)=>{const daily=scoreProductionAdjustment(amounts,simReport.observedHours,simReport.inputs.options.productionWeights).total;return {amounts:{...amounts},score:{daily,total:daily*days}}}
      const completedDaily=scoreBreakdown.completed!.total
      return {policy:v.policy,opening:value(v.opening.amounts),closing:value(v.closing.amounts),adjustment:value(v.adjustment),completedScore:{daily:completedDaily,total:completedDaily*days}}
    })()}:{}),
    scoreBreakdown,
    totalEquivalentLmd,
  }

  return {
    ...legacyReport,
    summary,
    drones: simReport.production ? drones : legacyReport.drones,
    validationMessages: simReport.diagnostics.map(d => d.message),
  }
}

/**
 * Pure calculation bridge helper:
 * Supports 'legacy' (default) and 'simulation' engines.
 */
export function runCalculationBridge(
  workspace: RosterWorkspace,
  optionsOrBaseConfig?: CalculationBridgeOptions | AppConfig,
  onProgress?: (progress: ScheduleSimulationProgress) => void,
): CalculationBridgeResult {
  const options: CalculationBridgeOptions = (optionsOrBaseConfig && 'schemaVersion' in optionsOrBaseConfig)
    ? { baseConfig: optionsOrBaseConfig, engine: 'legacy' }
    : (optionsOrBaseConfig ?? {})

  const engine = options.engine ?? 'legacy'
  const validation = validateRosterWorkspace(workspace)
  if (!validation.isValid) {
    return {
      success: false,
      report: null,
      validation,
      engine,
      error: '排班存在阻断错误，无法进行收益计算',
    }
  }

  // Deep clone to strip any Vue reactive proxies before simulation / structuredClone
  const cleanWorkspace: RosterWorkspace = JSON.parse(JSON.stringify(workspace))
  cleanWorkspace.productionWeights ??= options.baseConfig?.productionWeights

  if (engine === 'simulation') {
    const simBridge = runScheduleSimulationBridge(
      cleanWorkspace,
      options.simulationOptions ? {
        ...options.simulationOptions,
        jayeElite0: options.jayeElite0 ?? options.simulationOptions.jayeElite0 ?? options.baseConfig?.jayeElite0,
        production: options.simulationOptions.production ?? { outputMode: 'potential', runOrderMode: 'ideal', droneTarget: 'gold' },
        recordSegments: options.simulationOptions.recordSegments ?? true,
      } : {
        warmupHours: 72,
        sampleHours: 168,
        warmupModel: 'hourly',
        recordSegments: true,
        jayeElite0: options.jayeElite0 ?? options.baseConfig?.jayeElite0,
        production: {
          outputMode: 'potential',
          runOrderMode: 'ideal',
          droneTarget: 'gold',
        },
      },
      options.simulationAssumptions ?? {},
      onProgress,
    )

    if (simBridge.report?.success && simBridge.report.production?.success) {
      const report = simulationReportToCalculationReport(
        cleanWorkspace,
        simBridge.report,
        options.baseConfig ?? createDefaultConfig(),
      )
      return {
        success: true,
        report,
        simulationReport: simBridge.report,
        validation,
        engine: 'simulation',
      }
    }

    return {
      success: false,
      report: null,
      validation,
      engine: 'simulation',
      simulationReport: simBridge.report,
      error: simBridge.error ?? ('动态模拟未完成：' + (simBridge.report?.diagnostics.map(d => d.message).join('；') || '未取得完整生产报告')),
    }
  }

  const compiledConfig = compileMainPlanToAppConfig(
    workspace.mainPlan,
    workspace,
    options.baseConfig ?? createDefaultConfig(),
  )
  if (options.jayeElite0 || options.baseConfig?.jayeElite0) {
    compiledConfig.jayeElite0 = true
  }

  const report = calculate(compiledConfig)
  return {
    success: true,
    report,
    validation,
    engine: 'legacy',
  }
}
