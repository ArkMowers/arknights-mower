import recycleTemplate from '../../../arknights_mower/resources/room/recycle.png?url'
import { importMowerJson } from './vendor/workbench/compat/mowerJson'
import { droneFacilities } from './vendor/workbench/droneTargets'
import { mowerAdvancedAssumptions } from './vendor/scheduler/mowerAdvancedSettings'
import { workspaceUsesInventoryConditions } from './vendor/scheduler/backupInventory'
import { normalizeSimulationInventory } from './vendor/domain/simulationInventory'
import { normalizeProductionWeights } from './vendor/domain/productionWeights'
import { incomeInitialInventory } from './incomeCache'
import { parseOperatorInventory, compileOperatorInventory } from './vendor/domain/operatorInventory'

export const CALCULATOR_REVISION = '9c0b53c'
export const MOWER_REFERENCE = 'ab0a4e5'
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
    masteryPlanPresent: false,
    operatorMode: 'cache',
    operatorText: '',
    productionWeights: normalizeProductionWeights()
  }
}
export function incomeWorkspace(plan) {
  return importMowerJson(JSON.stringify(plan))
}
export function incomeFacilities(plan) {
  return droneFacilities(incomeWorkspace(plan))
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
        `${key === 'warmupDays' ? '预热' : '统计'}天数必须为 ${minimum}–${maximum} 的整数`
      )
    }
  }
  if (!Number.isSafeInteger(settings.seed) || settings.seed < 0 || settings.seed > 0xffffffff) {
    throw new Error('随机种子必须为 0–4294967295 的整数')
  }
  const workspace = incomeWorkspace(plan)
  const target = droneFacilities(workspace).find((f) => f.roomId === settings.droneRoom)
  if (settings.droneRoom && !target) throw new Error('无人机目标不在本次排班中')
  const inventory = normalizeSimulationInventory(
    settings.finiteInventory || workspaceUsesInventoryConditions(workspace)
      ? incomeInitialInventory(settings)
      : undefined
  )
  let operators
  if (settings.operatorMode === 'cache') {
    if (!settings.cachedOperators)
      throw new Error('没有可用的森空岛练度缓存，请先同步或选择其他练度来源')
    const parsed = compileOperatorInventory(settings.cachedOperators)
    if (!parsed.valid || !parsed.operators.length)
      throw new Error(
        parsed.diagnostics.map((d) => d.message).join('；') || '森空岛缓存中没有已拥有干员'
      )
    operators = settings.cachedOperators
  } else if (settings.operatorMode === 'custom') {
    const parsed = parseOperatorInventory(settings.operatorText)
    if (!parsed.valid || !parsed.entries.length)
      throw new Error(parsed.diagnostics.map((d) => d.message).join('；') || '请填写干员和练度')
    operators = parsed.entries
  } else if (settings.operatorMode !== 'maximum') throw new Error('干员练度选项无效')
  return {
    workspace,
    options: {
      engine: 'simulation',
      jayeElite0: settings.jayeElite0,
      simulationAssumptions: {
        ...mowerAdvancedAssumptions(workspace),
        masteryPlanPresent: settings.masteryPlanPresent
      },
      simulationOptions: {
        schedulingModel: 'mower-alpha',
        warmupHours: settings.warmupDays * 24,
        sampleHours: settings.sampleDays * 24,
        maxStepHours: 0.25,
        maxEvents: 200000,
        warmupModel: 'hourly',
        recordSegments: false,
        recordMorale: true,
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
    if (!settings.mowerWeights)
      throw new Error('Mower 收益算法尚未读取，请重试或选择本次自定义权重')
    return normalizeProductionWeights(settings.mowerWeights)
  }
  if (settings.weightMode !== 'custom') throw new Error('产出权重来源无效')
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

export function incomeMetrics(summary, days) {
  return [
    ['经验', summary.exp, '经验值'],
    ['赤金产量', summary.goldCount, '个'],
    ['赤金消耗', summary.goldConsumed, '个'],
    ['赤金净增', summary.netGoldCount, '个'],
    ['贸易龙门币', summary.orderLmd, '龙门币'],
    ['龙门币消耗', summary.lmdConsumed, '龙门币'],
    ['龙门币净增', summary.netLmd, '龙门币'],
    ['源石碎片', summary.fragments, '个'],
    ['合成玉', summary.orundum, '个'],
    ['回收站产出', summary.recycleCount, '次']
  ].map(([label, daily, unit]) => ({ label, daily: daily ?? 0, total: (daily ?? 0) * days, unit }))
}

export function incomeImageMetrics(summary, days) {
  return [
    { key: 'exp', icon: '/product/exp3.png', daily: summary.exp, unit: '经验值' },
    {
      key: 'gold',
      icon: '/product/gold.png',
      daily: summary.netGoldCount,
      unit: '个',
      signed: true,
      present: summary.goldCount || summary.goldConsumed
    },
    {
      key: 'lmd',
      icon: '/product/lmd.png',
      daily: summary.netLmd,
      unit: '龙门币',
      signed: true,
      present: summary.orderLmd || summary.lmdConsumed
    },
    { key: 'fragment', icon: '/product/orirock.png', daily: summary.fragments, unit: '个' },
    { key: 'orundum', icon: '/product/orundum.png', daily: summary.orundum, unit: '个' },
    { key: 'recycle', icon: recycleTemplate, daily: summary.recycleCount, unit: '次' }
  ]
    .filter((row) => Math.abs(row.daily ?? 0) > 1e-8 || Math.abs(row.present ?? 0) > 1e-8)
    .map((row) => ({ ...row, daily: row.daily ?? 0, total: (row.daily ?? 0) * days }))
}
