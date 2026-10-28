import { i18n } from '@/i18n'
import { planDisplayName } from '@/i18n/plans'
const { t } = i18n.global
import receptionTemplate from '../../../arknights_mower/resources/room/meeting.png?url'
import officeTemplate from '../../../arknights_mower/resources/room/contact.png?url'
import recycleTemplate from '../../../arknights_mower/resources/room/recycle.png?url'
import { DEFAULT_DRONE_CAPACITY } from './vendor/domain/droneCapacity'
import { importMowerJson } from './vendor/workbench/compat/mowerJson'
import { droneFacilities } from './vendor/workbench/droneTargets'
import { mowerAdvancedAssumptions } from './vendor/scheduler/mowerAdvancedSettings'
import { workspaceUsesInventoryConditions } from './vendor/scheduler/backupInventory'
import { normalizeSimulationInventory } from './vendor/domain/simulationInventory'
import { normalizeProductionWeights } from './vendor/domain/productionWeights'
import { incomeInitialInventory } from './incomeCache'
import { parseOperatorInventory, compileOperatorInventory } from './vendor/domain/operatorInventory'

export const CALCULATOR_REVISION = '5529403'
export const MOWER_REFERENCE = '80c97ee6'
export function defaultIncomeSettings() {
  return {
    warmupDays: 3,
    sampleDays: 28,
    seed: 42,
    droneRoom: '',
    finiteInventory: true,
    inventorySource: 'cache',
    cachedInventory: null,
    cachedOperators: null,
    cacheObservedAt: null,
    allowGoldDebt: true,
    weightMode: 'mower',
    mowerWeights: null,
    mowerAlgorithm: null,
    initialInventory: {},
    jayeElite0: false,
    operatorMode: 'cache',
    operatorText: '',
    productionWeights: normalizeProductionWeights()
  }
}
export function incomeWorkspace(plan) {
  const workspace = importMowerJson(JSON.stringify(plan))
  workspace.droneCapacity = DEFAULT_DRONE_CAPACITY
  return workspace
}
export function incomeFacilities(plan) {
  const workspace = incomeWorkspace(plan)
  return droneFacilities(workspace).map((target) => {
    const facility = workspace.mainPlan.facilities[target.roomId]
    const parts =
      facility.type === 'trading'
        ? ['贸易站']
        : [
            '制造站',
            facility.product === 'exp'
              ? '作战记录'
              : facility.product === 'fragment'
                ? '源石碎片'
                : '赤金'
          ]
    return {
      ...target,
      label: `${target.label.split(' ')[0]} ${parts.map(planDisplayName).join(' · ')}`
    }
  })
}
export function inventoryRequired(plan) {
  return workspaceUsesInventoryConditions(incomeWorkspace(plan))
}
export function incomeRequest(plan, settings) {
  for (const [key, minimum, maximum] of [
    ['warmupDays', 0, 30],
    ['sampleDays', 1, 90]
  ]) {
    const value = settings[key]
    if (!Number.isInteger(value) || value < minimum || value > maximum) {
      throw new Error(
        t('income.dayRange', {
          period: t(key === 'warmupDays' ? 'income.warmup' : 'income.sample'),
          min: minimum,
          max: maximum
        })
      )
    }
  }
  if (!Number.isSafeInteger(settings.seed) || settings.seed < 0 || settings.seed > 0xffffffff) {
    throw new Error(t('income.seedRange'))
  }
  const workspace = incomeWorkspace(plan)
  const target = droneFacilities(workspace).find((f) => f.roomId === settings.droneRoom)
  if (settings.droneRoom && !target) throw new Error(t('income.missingDrone'))
  const inventory = normalizeSimulationInventory(
    settings.finiteInventory || workspaceUsesInventoryConditions(workspace)
      ? incomeInitialInventory(settings)
      : undefined
  )
  let operators
  if (settings.operatorMode === 'cache') {
    if (!settings.cachedOperators) throw new Error(t('income.noOperatorCache'))
    const parsed = compileOperatorInventory(settings.cachedOperators)
    if (!parsed.valid || !parsed.operators.length)
      throw new Error(
        parsed.diagnostics.map((d) => d.message).join('；') || t('income.emptyOperatorCache')
      )
    operators = settings.cachedOperators
  } else if (settings.operatorMode === 'custom') {
    const parsed = parseOperatorInventory(settings.operatorText)
    if (!parsed.valid || !parsed.entries.length)
      throw new Error(
        parsed.diagnostics.map((d) => d.message).join('；') || t('income.enterOperators')
      )
    operators = parsed.entries
  } else if (settings.operatorMode !== 'maximum') throw new Error(t('income.invalidOperatorMode'))
  return {
    workspace,
    options: {
      engine: 'simulation',
      jayeElite0: settings.jayeElite0,
      simulationAssumptions: mowerAdvancedAssumptions(workspace),
      simulationOptions: {
        schedulingModel: 'mower-alpha',
        warmupHours: settings.warmupDays * 24,
        sampleHours: settings.sampleDays * 24,
        maxStepHours: 0.25,
        maxEvents: 200000,
        warmupModel: 'hourly',
        recordSegments: true,
        operatorInventory: operators,
        productionWeights: incomeWeights(settings),
        production: {
          ...(inventory === undefined
            ? { outputMode: 'potential' }
            : {
                outputMode: 'settled',
                inventoryMode: 'finite',
                initialResources: inventory
              }),
          allowGoldDebt: settings.allowGoldDebt,
          runOrderMode: 'ideal',
          seed: settings.seed,
          droneTarget: target?.target ?? 'none',
          droneRoomId: target?.roomId,
          droneTradingRoomId: target?.target === 'trading' ? target.roomId : undefined
        }
      }
    }
  }
}

export function incomeWeights(settings) {
  if (settings.weightMode === 'mower') {
    if (!settings.mowerWeights) throw new Error(t('income.noWeights'))
    return normalizeProductionWeights(settings.mowerWeights)
  }
  if (settings.weightMode !== 'custom') throw new Error(t('income.invalidWeights'))
  return normalizeProductionWeights(settings.productionWeights)
}

export function applyMowerIncomeSettings(settings, value) {
  settings.mowerAlgorithm = value.base_algorithm
  settings.mowerWeights = normalizeProductionWeights({
    exp: value.ratios.experience,
    gold: value.ratios.gold,
    orders: value.ratios.order,
    fragments: 0,
    orundum: 0
  })
}

export function incomeGoldEquivalentLmd(summary) {
  return (
    (summary.goldValue ?? (summary.goldCount ?? 0) * 500) +
    (summary.virtualGoldValue ?? (summary.virtualGoldCount ?? 0) * 500)
  )
}

export function incomeMetrics(summary, days) {
  return [
    [t('income.experience'), summary.exp, t('income.expUnit')],
    [t('income.goldEquivalent'), incomeGoldEquivalentLmd(summary), t('income.lmdUnit')],
    [t('income.tradeLmd'), summary.orderLmd, t('income.lmdUnit')],
    [t('income.lmdCost'), summary.lmdConsumed, t('income.lmdUnit')],
    [t('income.netLmd'), summary.netLmd, t('income.lmdUnit')],
    [t('income.fragments'), summary.fragments, t('income.itemUnit')],
    [t('income.orundum'), summary.orundum, t('income.itemUnit')],
    [t('income.recycle'), summary.recycleCount, t('income.countUnit')],
    [t('income.recruitment'), summary.recruitmentCount, t('income.countUnit')],
    ...(summary.clueCount == null
      ? []
      : [[t('income.clues'), summary.clueCount, t('income.itemUnit')]])
  ].map(([label, daily, unit]) => ({ label, daily: daily ?? 0, total: (daily ?? 0) * days, unit }))
}

export function incomeImageMetrics(summary, days) {
  return [
    { key: 'exp', icon: '/product/exp3.png', daily: summary.exp, unit: t('income.expUnit') },
    {
      key: 'gold',
      icon: '/product/gold.png',
      daily: incomeGoldEquivalentLmd(summary),
      unit: t('income.lmdUnit')
    },
    {
      key: 'lmd',
      icon: '/product/lmd.png',
      daily: summary.netLmd,
      unit: t('income.lmdUnit'),
      signed: true,
      present: summary.orderLmd || summary.lmdConsumed
    },
    {
      key: 'fragment',
      icon: '/product/orirock.png',
      daily: summary.fragments,
      unit: t('income.itemUnit')
    },
    {
      key: 'orundum',
      icon: '/product/orundum.png',
      daily: summary.orundum,
      unit: t('income.itemUnit')
    },
    {
      key: 'recycle',
      icon: recycleTemplate,
      daily: summary.recycleCount,
      unit: t('income.countUnit')
    },
    {
      key: 'recruitment',
      icon: officeTemplate,
      daily: summary.recruitmentCount,
      unit: t('income.countUnit')
    },
    { key: 'clue', icon: receptionTemplate, daily: summary.clueCount, unit: t('income.itemUnit') }
  ]
    .filter((row) => Math.abs(row.daily ?? 0) > 1e-8 || Math.abs(row.present ?? 0) > 1e-8)
    .map((row) => ({ ...row, daily: row.daily ?? 0, total: (row.daily ?? 0) * days }))
}
