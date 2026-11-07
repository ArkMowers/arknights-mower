import type {
  AppConfig,
  CalculationReport,
  ManufactureProduct,
  OutputRoom,
  QualityRule,
  SpecialOrder,
  TradeResult,
} from '../domain/types'
import { ROOM_LIMITS } from '../domain/defaults'
import { evaluateOperators } from './operatorRules'
import { simulateMorale } from './morale'
import { buildRiicGlobalContext, type RiicGlobalContext } from './globalContext'
import { virtualGoldEquivalent } from '../rules/orderValue'
import { getOrderDistribution } from '../rules/orderRules'
import { scoreProduction } from '../domain/productionScore'

const OUTPUT_POWER_USE = { 1: 10, 2: 30, 3: 60 } as const
const POWER_GENERATION = { 1: 60, 2: 130, 3: 270 } as const
const STANDARD_POWER_USE = { 0: 0, 1: 10, 2: 30, 3: 60 } as const
const DORM_POWER_USE = { 0: 0, 1: 10, 2: 20, 3: 30, 4: 45, 5: 65 } as const

const MANUFACTURE_FORMULAS: Record<
  ManufactureProduct,
  { minutes: number; value: number }
> = {
  gold: { minutes: 72, value: 500 },
  exp: { minutes: 180, value: 1000 },
  fragment: { minutes: 60, value: 0 },
}

interface OrderTemplate {
  probability: number
  cost: number
  reward: number
  minutes: number
  efficiencyAffected: boolean
}

function distribution(level: number, quality: QualityRule): OrderTemplate[] {
  return getOrderDistribution(level, quality).map(order => ({
    probability: order.probability, cost: order.goldCost, reward: order.lmdReward,
    minutes: order.baseMinutes, efficiencyAffected: order.efficiencyAffected,
  }))
}

function transformSpecial(template: OrderTemplate, special: SpecialOrder, roomLevel: number): OrderTemplate {
  switch (special) {
    case 'pepe':
      return { probability: template.probability, cost: 0, reward: 1000, minutes: 270, efficiencyAffected: false }
    case 'closure':
      return { probability: template.probability, cost: 2, reward: 1200, minutes: 144, efficiencyAffected: true }
    case 'uofficial':
      return { ...template, cost: 2, reward: 1000 }
    case 'provisoAlpha':
      return template.cost < 4 ? { ...template, cost: template.cost + 1, reward: template.reward + 500 } : template
    case 'provisoBeta':
      return template.cost < 4 ? { ...template, cost: template.cost + 2, reward: template.reward + 1000 } : template
    case 'tequilaAlpha':
      return roomLevel === 3 && template.cost > 3 ? { ...template, reward: template.reward + 250 } : template
    case 'tequilaBeta':
      return roomLevel === 3 && template.cost > 3 ? { ...template, reward: template.reward + 500 } : template
    case 'shiftRun':
      // Contract conversion and Tequila are mutually exclusive. Test the BASE cost.
      if (template.cost < 4) return { ...template, cost: template.cost + 2, reward: template.reward + 1000 }
      return roomLevel >= 3 ? { ...template, reward: template.reward + 500 } : template
    default:
      return template
  }
}

function outputRoomPower(room: OutputRoom): number {
  return room.type === 'power' ? 0 : OUTPUT_POWER_USE[room.level]
}

function calculatePower(config: AppConfig) {
  const generation = config.rooms
    .filter((room) => room.type === 'power')
    .reduce((sum, room) => sum + POWER_GENERATION[room.level], 0)
  const outputConsumption = config.rooms.reduce((sum, room) => sum + outputRoomPower(room), 0)
  const facilities = config.facilities
  const functionConsumption =
    STANDARD_POWER_USE[facilities.reception] +
    STANDARD_POWER_USE[facilities.office] +
    STANDARD_POWER_USE[facilities.training] +
    (facilities.workshop > 0 ? 10 : 0) +
    facilities.dormitories.reduce<number>((sum, level) => sum + DORM_POWER_USE[level], 0)
  const consumption = outputConsumption + functionConsumption
  return {
    generation,
    consumption,
    margin: generation - consumption,
    sufficient: generation >= consumption,
  }
}

function calculateDrones(config: AppConfig, averagePowerBonusPercent: number): number {
  const plants = config.rooms.filter((room) => room.type === 'power')
  if (plants.length === 0) return 0
  return (24 * 60) / 6 * (1 + averagePowerBonusPercent / 100)
}

function expectedGoldOrder(room: OutputRoom, quality: QualityRule, specialOrder: SpecialOrder) {
  const transformed = distribution(room.level, quality).map((template) =>
    transformSpecial(template, specialOrder, room.level),
  )
  const virtualGoldPerOrder = transformed.reduce(
    (sum, item) => sum + item.probability * virtualGoldEquivalent({ goldCost: item.cost, lmdReward: item.reward }),
    0,
  )

  return {
    minutes: transformed.reduce((sum, item) => sum + item.probability * item.minutes, 0),
    reward: transformed.reduce((sum, item) => sum + item.probability * item.reward, 0),
    cost: transformed.reduce((sum, item) => sum + item.probability * item.cost, 0),
    efficiencyAffected: transformed.some((item) => item.efficiencyAffected),
    virtualGold: virtualGoldPerOrder,
  }
}

function calculateTrade(
  room: OutputRoom,
  config: AppConfig,
  hours: number,
  droneMinutes: number,
  averageEfficiencyPercent: number,
  shiftDetails: string[],
  globalContext: RiicGlobalContext,
): TradeResult {
  const operatorResult = evaluateOperators(room, config, undefined, undefined, globalContext)
  const efficiency = averageEfficiencyPercent / 100
  const buffDetails = [...operatorResult.details, ...shiftDetails]
  if (Math.abs(averageEfficiencyPercent - operatorResult.efficiencyPercent) > 0.01) {
    buffDetails.push(`计入心情耗尽后的时段平均：${averageEfficiencyPercent.toFixed(1)}%`)
  }
  if (room.strategy === 'orundum') {
    if (room.level < 3) {
      return {
        roomId: room.id,
        strategy: room.strategy,
        efficiency,
        orders: 0,
        lmd: 0,
        goldConsumed: 0,
        orundum: 0,
        fragmentsConsumed: 0,
        droneExtraOrders: 0,
        operatorNames: operatorResult.operatorNames,
        buffDetails,
        unquantifiedSkills: operatorResult.unquantifiedSkills,
      }
    }
    const orders = (hours * 60 * efficiency) / 120
    const extra = droneMinutes / 120
    return {
      roomId: room.id,
      strategy: room.strategy,
      efficiency,
      orders: orders + extra,
      lmd: 0,
      goldConsumed: 0,
      orundum: (orders + extra) * 20,
      fragmentsConsumed: (orders + extra) * 2,
      droneExtraOrders: extra,
      operatorNames: operatorResult.operatorNames,
      buffDetails,
      unquantifiedSkills: operatorResult.unquantifiedSkills,
    }
  }

  const expected = expectedGoldOrder(room, operatorResult.quality, operatorResult.specialOrder)
  const pepe = operatorResult.specialOrder === 'pepe'
  if (pepe) buffDetails.push('佩佩特别独占订单固定 100% 获取效率；贸易无人机加速未核实，未计入')
  const naturalMinutes = hours * 60 * (expected.efficiencyAffected ? efficiency : 1)
  const orders = naturalMinutes / expected.minutes
  const extra = pepe ? 0 : droneMinutes / expected.minutes
  const totalOrders = orders + extra
  const virtualGold = totalOrders * expected.virtualGold
  const virtualGoldValue = virtualGold * 500
  return {
    roomId: room.id,
    strategy: room.strategy,
    efficiency: pepe ? 1 : efficiency,
    orders: totalOrders,
    lmd: totalOrders * expected.reward,
    goldConsumed: totalOrders * expected.cost,
    virtualGold,
    virtualGoldValue,
    orundum: 0,
    fragmentsConsumed: 0,
    droneExtraOrders: extra,
    operatorNames: operatorResult.operatorNames,
    buffDetails,
    unquantifiedSkills: operatorResult.unquantifiedSkills,
  }
}

function validateLayout(config: AppConfig): string[] {
  const messages: string[] = []
  if (config.rooms.length > 9) messages.push('制造站、贸易站与发电站的总数不能超过 9。')
  for (const type of ['manufacture', 'trading', 'power'] as const) {
    const count = config.rooms.filter((room) => room.type === type).length
    if (count > ROOM_LIMITS[type]) messages.push(`${type} 数量超过上限 ${ROOM_LIMITS[type]}。`)
  }
  for (const room of config.rooms) {
    const capacity = room.type === 'power' ? 1 : room.level
    if (room.operatorIds.length > capacity) messages.push(`${room.id} 的进驻人数超过当前等级工位上限。`)
    if (room.type === 'trading' && room.strategy === 'orundum' && room.level < 3) {
      messages.push(`${room.id} 必须升至 3 级才能使用开采协力。`)
    }
  }
  if (config.controlOperatorIds.length > 5) messages.push('控制中枢进驻人数不能超过 5。')
  const assignments = [...config.controlOperatorIds, ...config.rooms.flatMap((room) => room.operatorIds)]
  if (new Set(assignments).size !== assignments.length) messages.push('同一干员不能同时进驻多个设施。')
  const primaryIds = new Set(assignments)
  const workaholicIds = new Set(config.workaholicOperatorIds ?? [])
  const backups = assignments
    .map((primaryId) => ({ primaryId, backupId: config.operatorBackups[primaryId] }))
  for (const { primaryId, backupId } of backups) {
    if (!backupId) {
      if (workaholicIds.has(primaryId)) continue
      messages.push(`${primaryId} 尚未设置替补干员。`)
      continue
    }
    if (primaryIds.has(backupId)) {
      messages.push(`${primaryId} 的替补不能同时作为主力进驻。`)
    }
  }
  const assignedBackups = backups
    .map((item) => item.backupId)
    .filter((id): id is string => Boolean(id))
  if (new Set(assignedBackups).size !== assignedBackups.length) {
    messages.push('同一替补干员不能同时接替多个主力工位。')
  }
  return messages
}

export function calculate(config: AppConfig): CalculationReport {
  const validationMessages = validateLayout(config)
  const power = calculatePower(config)
  const layoutValid = validationMessages.length === 0
  const morale = simulateMorale(config, {
    warmupHours: 24 * 30,
    sampleHours: 24 * 90,
  })
  const globalContext = buildRiicGlobalContext(config)
  const efficiencyNotes = [
    '按最高阶段技能计算；暖机技能使用稳定终值。',
    '长期产出为近似值，尚未逐订单模拟品质暖机、领取与换班。',
  ]
  for (const room of config.rooms) {
    const result = evaluateOperators(room, config, undefined, undefined, globalContext)
    const ambiguous = result.details.filter(detail => detail.startsWith('JAYE_') || detail.includes('训练名单未区分'))
    for (const detail of ambiguous) efficiencyNotes.push(`${room.id}：${detail}`)
  }
  const drones = calculateDrones(config, morale.averagePowerBonusPercent)
  const droneMinutes = drones * 3
  const dailyHours = 24

  const manufacture = config.rooms
    .filter((room) => room.type === 'manufacture')
    .map((room) => {
      const formula = MANUFACTURE_FORMULAS[room.product]
      const operatorResult = evaluateOperators(room, config, undefined, undefined, globalContext)
      const averageEfficiencyPercent = morale.averageEfficiencyPercent[room.id] ?? 100
      const efficiency = averageEfficiencyPercent / 100
      const naturalCount = (dailyHours * 60 * efficiency) / formula.minutes
      const droneExtra = config.droneTarget === room.id ? droneMinutes / formula.minutes : 0
      return {
        roomId: room.id,
        product: room.product,
        efficiency,
        count: naturalCount + droneExtra,
        value: (naturalCount + droneExtra) * formula.value,
        droneExtra,
        operatorNames: operatorResult.operatorNames,
        buffDetails:
          Math.abs(averageEfficiencyPercent - operatorResult.efficiencyPercent) > 0.01
            ? [
                ...operatorResult.details,
                `计入心情耗尽后的时段平均：${averageEfficiencyPercent.toFixed(1)}%`,
                ...(morale.roomShiftDetails[room.id] ?? []),
              ]
            : [...operatorResult.details, ...(morale.roomShiftDetails[room.id] ?? [])],
        unquantifiedSkills: operatorResult.unquantifiedSkills,
      }
    })

  const trading = config.rooms
    .filter((room) => room.type === 'trading')
    .map((room) =>
      calculateTrade(
        room,
        config,
        dailyHours,
        config.droneTarget === room.id ? droneMinutes : 0,
        morale.averageEfficiencyPercent[room.id] ?? 100,
        morale.roomShiftDetails[room.id] ?? [],
        globalContext,
      ),
    )

  if (!power.sufficient || !layoutValid) {
    return {
      power,
      layoutValid,
      validationMessages,
      efficiencyNotes,
      manufacture,
      trading,
      drones,
      morale: morale.operators,
      roomShiftDetails: morale.roomShiftDetails,
      summary: null,
    }
  }

  const exp = manufacture.filter((item) => item.product === 'exp').reduce((sum, item) => sum + item.value, 0)
  const goldCount = manufacture.filter((item) => item.product === 'gold').reduce((sum, item) => sum + item.count, 0)
  const goldValue = manufacture.filter((item) => item.product === 'gold').reduce((sum, item) => sum + item.value, 0)
  const virtualGoldCount = trading.reduce((sum, item) => sum + (item.virtualGold ?? 0), 0)
  const virtualGoldValue = virtualGoldCount * 500
  const orderLmd = trading.reduce((sum, item) => sum + item.lmd, 0)
  const fragments = manufacture.filter((item) => item.product === 'fragment').reduce((sum, item) => sum + item.count, 0)
  const orundum = trading.reduce((sum, item) => sum + item.orundum, 0)
  const goldConsumed = trading.reduce((sum, item) => sum + item.goldConsumed, 0)
  const fragmentsConsumed = trading.reduce((sum, item) => sum + item.fragmentsConsumed, 0)
  const netGoldCount = goldCount - goldConsumed
  const netGoldValue = netGoldCount * 500
  const scoreBreakdown = scoreProduction({ exp, gold: goldCount, virtualGold: virtualGoldCount, orderLmd, fragments, orundum }, 24, config.productionWeights)
  const totalScore82 = scoreBreakdown.total
  const totalEquivalentLmd = orderLmd + netGoldValue + virtualGoldValue

  const summary = {
    exp,
    goldCount,
    goldValue,
    virtualGoldCount,
    virtualGoldValue,
    orderLmd,
    fragments,
    orundum,
    goldConsumed,
    fragmentsConsumed,
    netGoldCount,
    netGoldValue,
    totalScore82,
    scoreBreakdown,
    totalEquivalentLmd,
  }
  return {
    power,
    layoutValid,
    validationMessages,
    efficiencyNotes,
    manufacture,
    trading,
    drones,
    morale: morale.operators,
    roomShiftDetails: morale.roomShiftDetails,
    summary,
  }
}
