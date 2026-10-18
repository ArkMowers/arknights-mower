import { operatorFor, hasOperatorSkill } from '../domain/operatorContext'
import { temporalSkillBonus, temporalTradeQuality, type TimeContext } from './timeDependentSkills'
import { evaluateHighestPhaseJaye } from './jayeRules'
import { matchesRiicIdentity } from '../domain/riicIdentity'
import { evaluateTradeConditionalSkill, evaluateAigisPowerSkill, snowsantCopiedTradeBonus } from './tradeConditionalRules'
import { hasRiicTag } from '../domain/riicTags'
import type { AppConfig, OutputRoom, QualityRule, SpecialOrder } from '../domain/types'
import { OPERATOR_MAP, type OperatorRecord, type OperatorSkill } from '../domain/operators'
import { buildRiicGlobalContext, deriveCentralManufactureBonus, type RiicGlobalContext } from './globalContext'
import { recyclingOccupants } from './supportFacilities/conditions'

export interface OperatorBonusItem {
  name: string
  value: number
  detail?: string
}

export interface OperatorContribution {
  operatorId: string
  operatorName: string
  staffBonus: number
  skillBonus: number
  totalBonus: number
  items: OperatorBonusItem[]
}

export interface RoomBonusItem {
  source: string
  value: number
  detail?: string
}

export interface OperatorEfficiencyResult {
  efficiencyPercent: number
  staffBonus: number
  skillBonus: number
  operatorNames: string[]
  details: string[]
  unquantifiedSkills: string[]
  quality: QualityRule
  qualityWarmup?: number
  specialOrder: SpecialOrder
  operatorContributions: OperatorContribution[]
  roomContributions: RoomBonusItem[]
}

const GAME_ROOM_TYPES = {
  manufacture: 'MANUFACTURE',
  trading: 'TRADING',
  power: 'POWER',
} as const

type SkillClassCounts = Record<string, number>

const MANUFACTURE_WAREHOUSE_CAPACITY: Record<string, number> = {
  'manu_prod_limit&cost[0000]': 8,
  'manu_prod_limit&cost[002]': 8,
}

const STABLE_MANUFACTURE_BONUS: Record<string, number> = {
  'manu_prod_spd_addition[031]': 25,
  'manu_prod_spd_addition[041]': 25,
  'manu_prod_spd_addition[100]': 20,
  'manu_prod_cost_min[001]': 10,
}

function selectedOperators(config: AppConfig, ids: string[]): OperatorRecord[] {
  return ids.map((id) => operatorFor(config, id)).filter((item): item is OperatorRecord => Boolean(item))
}

function activeInContext(id: string, config: AppConfig, activeOperatorIds?: Set<string>): boolean {
  return activeOperatorIds ? activeOperatorIds.has(id) : !config.zeroMoraleOperatorIds.includes(id)
}

function skillClass(skill: OperatorSkill): string | null {
  const match = skill.name.match(/^(.+?)·[αβγ]$/)
  return match?.[1] ?? null
}

function roomClassCounts(operators: OperatorRecord[]): SkillClassCounts {
  const counts: SkillClassCounts = {}
  const skills = operators.flatMap((operator) =>
    operator.skills.filter((skill) => skill.roomType === 'MANUFACTURE'),
  )
  for (const skill of skills) {
    const type = skillClass(skill)
    if (type) counts[type] = (counts[type] ?? 0) + 1
  }
  const convertsToStandard = skills.some(
    (skill) =>
      skill.description.includes('莱茵科技类') &&
      skill.description.includes('红松骑士团类') &&
      skill.description.includes('视作标准化类'),
  )
  if (convertsToStandard) {
    counts.标准化 = (counts.标准化 ?? 0) + (counts.莱茵科技 ?? 0) + (counts.红松骑士团 ?? 0)
  }
  return counts
}

function manufactureWarehouseCapacity(
  skill: OperatorSkill,
  room: OutputRoom,
  operator?: OperatorRecord,
  morale?: number,
  context?: RiicGlobalContext,
  classCounts?: SkillClassCounts | null,
): number {
  if (skill.roomType !== 'MANUFACTURE') return 0
  if (skill.buffId === 'manu_prod_bd[000]') return (context?.ursuSpecialDrink ?? 0) * 2
  if (skill.buffId === 'manu_skill_limit[000]') return (classCounts?.莱茵科技 ?? 0) * 5
  if (skill.buffId === 'manu_prod_spd&manu[000]' || skill.buffId === 'manu_prod_spd&manu[100]') return room.operatorIds.length * 5
  if (skill.buffId === 'manu_formula_limit[0000]') {
    return room.product === 'exp' ? 12 : 0
  }
  if (skill.buffId === 'manu_formula_limit[010]') {
    return room.product === 'exp' ? 15 : 0
  }
  if (skill.buffId === 'manu_formula_limit[020]') {
    return room.product === 'exp' ? 4 : 0
  }
  if (
    skill.buffId === 'manu_prod_spd_addition&cost[000]' ||
    (operator?.charId === 'char_4062_totter' && skill.name === '窗外雪啸')
  ) {
    const gap = Math.max(0, 24 - (morale ?? 24))
    return gap > 12 ? 6 : 0
  }
  const described = skill.description.match(/仓库容量上限([+-])(\d+)/)
  if (described) {
    return Number(described[2]) * (described[1] === '-' ? -1 : 1)
  }
  return MANUFACTURE_WAREHOUSE_CAPACITY[skill.buffId] ?? 0
}

function stableManufactureBonus(skill: OperatorSkill): number | null {
  const described = skill.description.match(/最终达到\+([\d.]+)%/)
  if (described) return Number(described[1])
  return STABLE_MANUFACTURE_BONUS[skill.buffId] ?? null
}

function stablePowerBonus(skill: OperatorSkill): number | null {
  const described = skill.description.match(/最终达到\+([\d.]+)%/)
  return described ? Number(described[1]) : null
}

function orderLimitDelta(
  skill: OperatorSkill,
  room?: OutputRoom,
  operatorNames?: Set<string>,
): number {
  if (skill.buffId === 'trade_ord_limit&trade&lv[000]' || skill.buffId === 'trade_ord_limit&trade&lv[001]') {
    return room ? room.level : 0
  }
  if (skill.buffId === 'trade_ord_limit&cost_P[020]') {
    return operatorNames?.has('伺夜') ? 2 : 0
  }
  if (skill.buffId === 'trade_ord_limit&cost_P[001]' || skill.buffId === 'trade_ord_limit&cost_P[000]') {
    const bonus = skill.buffId.endsWith('[001]') ? 4 : 2
    return operatorNames?.has('德克萨斯') ? bonus : 0
  }
  const match = skill.description.match(/订单上限([+-])(\d+)/)
  if (!match) return 0
  return Number(match[2]) * (match[1] === '-' ? -1 : 1)
}

function directManufactureBonus(skill: OperatorSkill, room: OutputRoom): number | null {
  const description = skill.description
  const categoryMatch = description.match(
    /^进驻制造站时，(?:当前制造站)?(贵金属|作战记录|源石)类配方的生产力([+-])([\d.]+)%/,
  )
  if (categoryMatch) {
    const productMatches =
      (categoryMatch[1] === '贵金属' && room.product === 'gold') ||
      (categoryMatch[1] === '作战记录' && room.product === 'exp') ||
      (categoryMatch[1] === '源石' && room.product === 'fragment')
    const val = Number(categoryMatch[3]) * (categoryMatch[2] === '-' ? -1 : 1)
    return productMatches ? val : 0
  }
  const commonMatch = description.match(/(?:^|，)(?:当前制造站)?生产力([+-])([\d.]+)%/)
  if (commonMatch) {
    return Number(commonMatch[2]) * (commonMatch[1] === '-' ? -1 : 1)
  }
  return null
}

function directTradingBonus(skill: OperatorSkill): number | null {
  const match = skill.description.match(/^进驻贸易站时，订单获取效率\+([\d.]+)%/)
  return match ? Number(match[1]) : null
}

function directPowerBonus(skill: OperatorSkill): number | null {
  const match = skill.description.match(/^进驻发电站时，无人机充能速度\+([\d.]+)%/)
  return match ? Number(match[1]) : null
}

function facilityCountManufactureBonus(
  skill: OperatorSkill,
  room: OutputRoom,
  context: RiicGlobalContext,
): { value: number; detail: string } | null {
  const powerMatch = skill.description.match(/每个发电站为当前制造站\+([\d.]+)%的生产力/)
  if (powerMatch) {
    const stations = context.effectivePowerStations
    return {
      value: stations.count * Number(powerMatch[1]),
      detail: `有效发电站 ${stations.count}（实体 ${stations.physical}、承曦格雷伊 +${stations.greyBonus}、森蚺/Lancet-2 +${stations.eunectesBonus}）`,
    }
  }
  const tradeMatch = skill.description.match(/每个贸易站为当前制造站(?:贵金属类配方的生产力)?\+([\d.]+)%/)
  if (tradeMatch) {
    if (skill.description.includes('贵金属类配方') && room.product !== 'gold') {
      return { value: 0, detail: '仅对贵金属配方生效' }
    }
    const count = context.tradeStationCount
    return { value: count * Number(tradeMatch[1]), detail: `按 ${count} 个贸易站计算` }
  }
  return null
}

function isAutomationSkill(skill: OperatorSkill): boolean {
  return skill.roomType === 'MANUFACTURE' && skill.description.includes('其他干员提供的生产力全部归零')
}

function sameRoomTargetBonus(
  skill: OperatorSkill,
  operatorNames: Set<string>,
  roomType: OutputRoom['type'],
): number | null {
  const roomName = roomType === 'trading' ? '贸易站' : '制造站'
  const match = skill.description.match(
    new RegExp(`当与(.+?)在同一个${roomName}时，.*?(?:生产力|订单获取效率)(?:额外)?\\+([\\d.]+)%`),
  )
  if (!match) return null
  return operatorNames.has(match[1]!) ? Number(match[2]) : 0
}

function classLinkBonus(skill: OperatorSkill, counts: SkillClassCounts): number | null {
  const match = skill.description.match(
    /每个(.+?)类技能为自身\+([\d.]+)%的生产力/,
  )
  if (!match) return null
  return (counts[match[1]!] ?? 0) * Number(match[2])
}

function inferSpecialOrder(operators: OperatorRecord[], fallback: SpecialOrder): SpecialOrder {
  const skill = (buffId: string) => operators.some(operator => operator.skills.some(value => value.buffId === buffId))
  if (skill('trade_ord_pepe[000]')) return 'pepe'
  if (skill('trade_ord_closure[000]')) return 'closure'
  if (skill('trade_ord_spd&wt[000]')) return 'uofficial'
  if (fallback === 'shiftRun') return fallback
  const names = new Set(operators.map((operator) => operator.name))
  if (names.has('但书')) return operators.some(o=>o.skills.some(s=>s.buffId==='trade_ord_against[010]'))?'provisoBeta':'provisoAlpha'
  if (names.has('龙舌兰')) return operators.some(o=>o.skills.some(s=>s.buffId==='trade_ord_long[010]'))?'tequilaBeta':'tequilaAlpha'
  return fallback
}

interface ControlGlobalBonusResult {
  bonus: number
  details: string[]
  unquantifiedSkills: string[]
  operatorBonuses: Map<string, OperatorBonusItem[]>
  roomBonuses: RoomBonusItem[]
}

function controlGlobalBonus(
  room: OutputRoom,
  config: AppConfig,
  roomOperators: OperatorRecord[],
  activeOperatorIds?: Set<string>,
  context?: RiicGlobalContext,
): ControlGlobalBonusResult {
  const controlOperators = selectedOperators(config,
    config.controlOperatorIds.filter((id) => activeInContext(id, config, activeOperatorIds)),
  )
  let bonus = 0
  const details: string[] = []
  const unquantifiedSkills: string[] = []
  const operatorBonuses = new Map<string, OperatorBonusItem[]>()
  const roomBonuses: RoomBonusItem[] = []
  const activeControlIds = new Set(controlOperators.map(op => op.charId))
  const enthusiasm = (activeControlIds.has('char_4186_tmoris') ? 10 : 0)
    + (activeControlIds.has('char_4183_mortis') ? 20 : 0)
    + (activeControlIds.has('char_4185_amoris') ? 10 : 0)
    + (activeControlIds.has('char_4184_dolris') ? config.dormitoryOccupantCount : 0)

  if (room.type === 'manufacture') {
    const staticManufacture =
      context !== undefined
        ? {
            value: context.centralManufactureBonus,
            details: context.centralManufactureDetails,
            unquantifiedSkills: context.unquantifiedControlSkills,
          }
        : deriveCentralManufactureBonus(config, activeOperatorIds)

    if (staticManufacture.value > 0) {
      bonus += staticManufacture.value
      details.push(...staticManufacture.details)
      roomBonuses.push({
        source: `控制中枢：全局制造 +${staticManufacture.value}%（同类取最高）`,
        value: staticManufacture.value,
        detail: '同类取最高',
      })
    }
    if (staticManufacture.unquantifiedSkills.length) {
      unquantifiedSkills.push(...staticManufacture.unquantifiedSkills)
    }

    if (controlOperators.some((operator) => operator.charId === 'char_1034_jesca2' && hasOperatorSkill(config,operator.charId,'control_bd_spd[000]'))) {
      const blacksteelOps = roomOperators.filter((operator) => matchesRiicIdentity(operator, 'groupId', 'blacksteel'))
      if (blacksteelOps.length) {
        const value = blacksteelOps.length * 5
        bonus += value
        details.push(`涤火杰西卡·老友相聚：黑钢干员 ${blacksteelOps.length} 人，+${value}%`)
        for (const op of blacksteelOps) {
          const list = operatorBonuses.get(op.charId) ?? []
          list.push({ name: '涤火杰西卡·老友相聚', value: 5, detail: '黑钢干员制造联动' })
          operatorBonuses.set(op.charId, list)
        }
      }
    }

    if (
      controlOperators.some((operator) => operator.charId === 'char_4182_oblvns') &&
      room.product === 'gold'
    ) {
      const sakikoBonus = (hasOperatorSkill(config,'char_4182_oblvns','control_prod_bd_spd[010]')?1:.5) * (1 + Math.floor(enthusiasm / 20))
      bonus += sakikoBonus
      details.push(`丰川祥子·丰富工作经验：贵金属生产力 +${sakikoBonus}%（热情值 ${enthusiasm}）`)
      roomBonuses.push({
        source: '丰川祥子·丰富工作经验',
        value: sakikoBonus,
        detail: `贵金属生产力 +${sakikoBonus}%（热情值 ${enthusiasm}）`,
      })
    }

    const justiceKnightActive = config.rooms
      .filter((item) => item.type === 'power')
      .some(
        (item) =>
          item.operatorIds.includes('char_4000_jnight') &&
          activeInContext('char_4000_jnight', config, activeOperatorIds),
      )
    if (justiceKnightActive && roomOperators.some((operator) => operator.name === '野鬃')) {
      bonus += 5
      details.push('正义骑士号·“滴滴，启动！”：野鬃 +5%')
      const wildMane = roomOperators.find((op) => op.name === '野鬃')
      if (wildMane) {
        const list = operatorBonuses.get(wildMane.charId) ?? []
        list.push({ name: '正义骑士号·“滴滴，启动！”', value: 5, detail: '野鬃 +5%' })
        operatorBonuses.set(wildMane.charId, list)
      }
    }

    if (controlOperators.some((operator) => operator.charId === 'char_4098_vvana' && hasOperatorSkill(config,operator.charId,'control_prod_fraction[000]'))) {
      const knightOps = roomOperators.filter((operator) => hasRiicTag(operator, 'knight'))
      if (knightOps.length) {
        const value = knightOps.length * 7
        bonus += value
        details.push(`薇薇安娜·烛骑士微光：骑士干员 +${value}%`)
        for (const op of knightOps) {
          const list = operatorBonuses.get(op.charId) ?? []
          list.push({ name: '薇薇安娜·烛骑士微光', value: 7, detail: '骑士干员制造联动' })
          operatorBonuses.set(op.charId, list)
        }
      }
    }

    const gladiiaInControl = controlOperators.find(op => op.name === '歌蕾蒂娅')
    const gladiiaSkill = gladiiaInControl?.skills.find(s => s.buffId === 'control_mp_aegir2[010]' || s.buffId === 'control_mp_aegir2[000]')
    if (gladiiaSkill && !roomOperators.some(operator => operator.skills.some(isAutomationSkill))) {
      // cc.c.abyssal2_2 and 2_3: physical manufacturing residents receive this
      // external grant even at zero morale; their staffing and own skills remain
      // inactive. Automation wins; the stage cap is 45%/90%, and Waai Fu cannot copy it.
      const multiplier = gladiiaSkill.buffId === 'control_mp_aegir2[010]' ? 10 : 5
      const stationCap = multiplier === 10 ? 90 : 45
      const manufacturingAbyssalCount = new Set(
        config.rooms.filter(r => r.type === 'manufacture').flatMap(r => r.operatorIds)
          .filter(id => { const operator = OPERATOR_MAP.get(id); return operator !== undefined && matchesRiicIdentity(operator, 'groupId', 'abyssal') }),
      ).size
      const abyssalInRoom = selectedOperators(config, room.operatorIds)
        .filter(operator => matchesRiicIdentity(operator, 'groupId', 'abyssal'))
      const value = Math.min(stationCap, manufacturingAbyssalCount * abyssalInRoom.length * multiplier)
      if (value > 0) {
        bonus += value
        const perBeneficiaryValue = value / abyssalInRoom.length
        details.push(
          abyssalInRoom.length > 1
            ? `歌蕾蒂娅·集群狩猎：深海猎人制造联动 ${abyssalInRoom.length} 人，+${value}%（每人 +${perBeneficiaryValue}%）`
            : `歌蕾蒂娅·集群狩猎：深海猎人制造联动 +${value}%`,
        )
        for (const op of abyssalInRoom) {
          const list = operatorBonuses.get(op.charId) ?? []
          list.push({ name: '歌蕾蒂娅·集群狩猎', value: perBeneficiaryValue,
            detail: `制造站内共 ${manufacturingAbyssalCount} 名深海猎人，单站最高${stationCap}%` })
          operatorBonuses.set(op.charId, list)
        }
      }
    }

    if (controlOperators.some((operator) => operator.name === '焰尾' && hasOperatorSkill(config,operator.charId,'control_mp_psk[000]'))) {
      const pinusOps = roomOperators.filter((operator) => matchesRiicIdentity(operator, 'groupId', 'pinus'))
      if (pinusOps.length) {
        const val = room.product === 'exp' ? 10 : room.product === 'gold' ? -10 : 0
        const value = pinusOps.length * val
        bonus += value
        if (value) {
          details.push(`焰尾·红松的骑士：${value > 0 ? '+' : ''}${value}%`)
          for (const op of pinusOps) {
            const list = operatorBonuses.get(op.charId) ?? []
            list.push({ name: '焰尾·红松的骑士', value: val, detail: '红松骑士制造联动' })
            operatorBonuses.set(op.charId, list)
          }
        }
      }
    }
  }

  if (room.type === 'trading') {
    let staticMax = 0
    for (const operator of controlOperators) {
      for (const skill of operator.skills.filter((item) => item.roomType === 'CONTROL')) {
        if (operator.name === '望') {
          const external = config.rooms.filter(r => r.type === 'trading' || r.type === 'power').length
          const actual = config.rooms.filter(r => r.type === 'manufacture').length
          if (external >= actual) staticMax = Math.max(staticMax, 7)
          continue
        }
        if (skill.buffId === 'control_token_tra_spd[000]') {
          if (controlOperators.some(other => other.charId !== operator.charId && hasRiicTag(other, 'monsterHunter'))) staticMax = Math.max(staticMax, 7)
          continue
        }
        if (skill.buffId === 'control_mp_bd&trade[000]') {
          staticMax = Math.max(staticMax, Math.floor(enthusiasm / 8))
          continue
        }
        const match = skill.description.match(/所有贸易站订单效率\+([\d.]+)%/)
        if (match) staticMax = Math.max(staticMax, Number(match[1]))
      }
    }
    if (staticMax) {
      bonus += staticMax
      details.push(`控制中枢：全局贸易 +${staticMax}%（同类取最高）`)
      roomBonuses.push({
        source: '控制中枢：全局贸易',
        value: staticMax,
        detail: '同类取最高',
      })
    }
    if (controlOperators.some(operator => operator.name === '戴菲恩' && hasOperatorSkill(config,operator.charId,'control_tra_limit&spd[010]'))) {
      for (const op of roomOperators.filter(operator => matchesRiicIdentity(operator, 'groupId', 'glasgow'))) {
        bonus += 10
        const list = operatorBonuses.get(op.charId) ?? []
        list.push({ name: '戴菲恩·运筹好手', value: 10 })
        operatorBonuses.set(op.charId, list)
        details.push('戴菲恩·运筹好手：' + op.name + ' +10%')
      }
    }
    if (controlOperators.some(operator => operator.name === '凛御银灰') && roomOperators.filter(operator => matchesRiicIdentity(operator, 'nationId', 'kjerag')).length >= 3) {
      bonus += 10
      roomBonuses.push({ source: '凛御银灰·商业版图', value: 10 })
      details.push('凛御银灰·商业版图：本贸易站3名谢拉格干员 +10%')
    }
    if (controlOperators.some((operator) => operator.charId === 'char_4186_tmoris' && hasOperatorSkill(config,operator.charId,'control_tra_limit&spd2[000]'))) {
      const siracusaOps = roomOperators.filter((operator) => matchesRiicIdentity(operator, 'nationId', 'siracusa'))
      if (siracusaOps.length) {
        const value = siracusaOps.length * 5
        bonus += value
        details.push(`八幡海铃·商路开拓：叙拉古干员 ${siracusaOps.length} 人，+${value}%`)
        for (const op of siracusaOps) {
          const list = operatorBonuses.get(op.charId) ?? []
          list.push({ name: '八幡海铃·商路开拓', value: 5, detail: '叙拉古干员贸易联动' })
          operatorBonuses.set(op.charId, list)
        }
      }
    }
    if (controlOperators.some((operator) => operator.charId === 'char_206_gnosis' && hasOperatorSkill(config,operator.charId,'control_tra_limit&spd[000]'))) {
      const kjeragOps = roomOperators.filter((operator) => matchesRiicIdentity(operator, 'nationId', 'kjerag'))
      if (kjeragOps.length) {
        bonus -= kjeragOps.length * 15
        for (const op of kjeragOps) {
          details.push(`灵知·精密计算：${op.name} -15%（订单上限 +6）`)
          const list = operatorBonuses.get(op.charId) ?? []
          list.push({ name: '灵知·精密计算', value: -15, detail: '谢拉格干员订单获取效率 -15%' })
          operatorBonuses.set(op.charId, list)
        }
      }
    }
  }

  return { bonus, details, unquantifiedSkills, operatorBonuses, roomBonuses }
}

/** Exposes the existing warehouse-capacity rule for event timelines without changing efficiency evaluation. */
export function evaluateManufacturingCapacity(
  room: OutputRoom,
  config: AppConfig,
  activeOperatorIds?: Set<string>,
  moraleValues?: Map<string, number>,
  preparedContext?: RiicGlobalContext,
): number {
  if (room.type !== 'manufacture') return 0
  const activeOperators = selectedOperators(config, room.operatorIds).filter((operator) => activeInContext(operator.charId, config, activeOperatorIds))
  const globalContext = preparedContext ?? buildRiicGlobalContext(config, activeOperatorIds, moraleValues)
  const classCounts = roomClassCounts(activeOperators)
  return activeOperators
    .flatMap((operator) => {
      const morale = moraleValues?.get(operator.charId) ?? config.operatorMorale[operator.charId] ?? 24
      return operator.skills.map((skill) => manufactureWarehouseCapacity(skill, room, operator, morale, globalContext, classCounts))
    })
    .reduce((sum, capacity) => sum + capacity, 0)
}
export function evaluateOperators(
  room: OutputRoom,
  config: AppConfig,
  activeOperatorIds?: Set<string>,
  moraleValues?: Map<string, number>,
  preparedContext?: RiicGlobalContext,
  timeContext?: TimeContext,
): OperatorEfficiencyResult {
  const operators = selectedOperators(config, room.operatorIds)
  const activeOperators = operators.filter(
    (operator) => activeInContext(operator.charId, config, activeOperatorIds),
  )
  const operatorNames = new Set(activeOperators.map((operator) => operator.name))
  const details: string[] = []
  const unquantifiedSkills: string[] = []
  const automationOperators = new Set(
    activeOperators
      .filter((operator) => operator.skills.some(isAutomationSkill))
      .map((operator) => operator.charId),
  )
  const staffCount = activeOperators.length
  const staffBonus = staffCount * (room.type === 'power' ? 5 : 1)
  let skillBonus = room.skillBonus
  const globalContext = preparedContext ?? buildRiicGlobalContext(config, activeOperatorIds, moraleValues)
  const global = controlGlobalBonus(room, config, activeOperators, activeOperatorIds, globalContext)
  const classCounts = room.type === 'manufacture' ? roomClassCounts(activeOperators) : null
  const warehouseCapacity =
    room.type === 'manufacture'
      ? activeOperators
          .flatMap((operator) => {
            const opMorale = moraleValues?.get(operator.charId) ?? config.operatorMorale[operator.charId] ?? 24
            return operator.skills.map((skill) =>
              manufactureWarehouseCapacity(skill, room, operator, opMorale, globalContext, classCounts),
            )
          })
          .reduce((sum, skill) => sum + skill, 0)
      : 0
  const manufacturePerceptionInformation = globalContext.thoughtChain.effective
  const tradingPerceptionInformation = globalContext.silentResonance.effective
  const goldProductionLines = globalContext.goldProductionLines.effective
  const kiraraGoldLines = Math.max(
    0,
    goldProductionLines - globalContext.physicalGoldProductionLines - globalContext.durinGoldProductionLines,
  )
  const controlOps = selectedOperators(config,
    config.controlOperatorIds.filter((id) => activeInContext(id, config, activeOperatorIds)),
  )
  const gnosisInControl = controlOps.some((op) => op.charId === 'char_206_gnosis')
  const wisdelInControl = controlOps.some((op) => op.charId === 'char_1035_wisdel')
  const roomOrderLimitIncrease =
    room.type === 'trading'
      ? activeOperators.reduce((sum, op) => {
          let opLimit = op.skills
            .filter((skill) => skill.roomType === 'TRADING')
            .reduce((s, skill) => s + orderLimitDelta(skill, room, operatorNames), 0)
          if (gnosisInControl && matchesRiicIdentity(op, 'nationId', 'kjerag')) {
            opLimit += 6
          }
          if (wisdelInControl && op.name === '赫德雷') {
            opLimit += 2
          }
          return sum + Math.max(0, opLimit)
        }, 0)
      : 0
  const monsterCuisine = globalContext.monsterCuisine
  const worldlyFireworks = globalContext.worldlyFireworks
  const shamareActive =
    room.type === 'trading' &&
    activeOperators.some((item) =>
      item.skills.some((skill) => skill.buffId === 'trade_ord_vodfox[000]'),
    )
  const vivianaActive =
    config.controlOperatorIds.includes('char_4098_vvana') &&
    activeInContext('char_4098_vvana', config, activeOperatorIds)
  // Copy the same resolved, non-facility values that are actually applied below.
  // The copy skill itself is deferred until every colleague has been evaluated.
  let waaiFuCopyableBonus = 0

  if (operators.length) {
    details.push(`进驻基础：${operators.length} 人，+${staffBonus}%`)
    const exhausted = operators.filter((operator) => !activeOperators.includes(operator))
    if (exhausted.length) details.push(`0 心情：进驻基础及自身技能失效：${exhausted.map((operator) => operator.name).join('、')}`)
    if (automationOperators.size > 0) {
      details.push('自动化：仅清零其他干员的技能生产力，不影响每人 1% 进驻基础')
    }
  }
  if (room.skillBonus) details.push(`手动修正：${room.skillBonus > 0 ? '+' : ''}${room.skillBonus}%`)

  const operatorContributions: OperatorContribution[] = []
  const roomContributions: RoomBonusItem[] = [...global.roomBonuses]
  if (room.skillBonus) {
    roomContributions.push({ source: '手动修正', value: room.skillBonus })
  }

  for (const operator of activeOperators) {
    const skills = operator.skills.filter((skill) => skill.roomType === GAME_ROOM_TYPES[room.type])
    const opItems: OperatorBonusItem[] = []
    const opStaff = room.type === 'power' ? 5 : 1
    opItems.push({ name: '进驻基础', value: opStaff })
    let opSkillTotal = 0

    for (const skill of skills) {
      let applied: number | null = null
      let facilityBased = false
      let facilityDetail = ''
      if (room.type === 'manufacture') {
        const morale = moraleValues?.get(operator.charId) ?? config.operatorMorale[operator.charId] ?? 24
        const moraleGap = Math.max(0, 24 - morale)
        if (skill.buffId === 'manu_prod_spd&bd[000]') {
          const count = globalContext.presentOperators.filter(op => hasRiicTag(op, 'sees')).length
          applied = 20 + Math.min(4, count) * 5
          facilityDetail = `S.E.E.S. 入驻人数 ${count}`
        } else if (skill.buffId === 'manu_prod_spd&manu[100]') {
          applied = operators.length * 10
          facilityDetail = '当前站内人数 ' + operators.length
        } else if (skill.buffId === 'manu_prod_spd&limit&bd[000]') {
          applied = 5 + globalContext.woodCatnip
          facilityDetail = '木天蓼 ' + globalContext.woodCatnip
        } else if (skill.buffId === 'manu_formula_spd&bd[001]' || skill.buffId === 'manu_formula_spd&bd[000]') {
          const studentPartner = skill.buffId.endsWith('[001]') && activeOperators.some(item => item.charId !== operator.charId && matchesRiicIdentity(item, 'teamId', 'student'))
          applied = room.product === 'exp' ? 30 + (studentPartner ? 10 : 0) : 0
        } else if (skill.buffId === 'manu_prod_spd_bd[400]') {
          applied = monsterCuisine
          facilityDetail = `monster cuisine ${monsterCuisine}`
        } else if (skill.buffId === 'manu_formula_spd&dorm&lv[000]') {
          applied =
            room.product === 'gold'
              ? config.facilities.dormitories.reduce<number>((sum, level) => sum + level, 0)
              : 0
          facilityBased = true
        } else if (skill.buffId === 'manu_formula_spd&cost_bd[100]') {
          const count = Math.min(5, globalContext.presentOperators.filter((item) => matchesRiicIdentity(item, 'groupId', 'rhine')).length)
          applied = room.product === 'gold' ? count * 3 : 0
          facilityDetail = `Rhine operators ${count}`
        } else if (skill.buffId === 'manu_prod_spd_bd[300]') {
          applied = Math.floor(worldlyFireworks / 3)
          facilityDetail = `worldly fireworks ${worldlyFireworks}`
        } else if (skill.buffId === 'manu_prod_spd_train&lv[000]') {
          applied = Math.min(30, config.facilities.training * 10)
          facilityBased = true
        } else if (skill.buffId === 'manu_token_prod_spd[010]' || skill.buffId === 'manu_token_prod_spd[000]') {
          const platformIds = new Set([
            'char_285_medic2',
            'char_286_cast3',
            'char_376_therex',
            'char_4000_jnight',
            'char_4093_frston',
            'char_4136_phonor',
            'char_4188_confes',
            'char_4227_gallus',
          ])
          const count = config.rooms
            .filter((item) => item.type === 'power')
            .flatMap((item) => item.operatorIds)
            .filter((id) => platformIds.has(id) && activeInContext(id, config, activeOperatorIds)).length
          const rate = skill.buffId.endsWith('[010]') ? 10 : 5
          applied = room.product === 'gold' ? count * rate : 0
          facilityBased = true
          facilityDetail = `work platforms ${count}`
        } else if (skill.buffId === 'manu_prod_spd&fraction[000]') {
          applied = activeOperators.filter((item) => matchesRiicIdentity(item, 'teamId', 'reserve1')).length * 10
        } else if (skill.buffId === 'manu_formula_spd_P[000]') {
          const gummyInTrading = config.rooms
            .filter((item) => item.type === 'trading')
            .flatMap((item) => selectedOperators(config, item.operatorIds))
            .some((item) => item.name === '古米')
          applied = room.product === 'exp' && gummyInTrading ? 35 : 0
        } else if (skill.buffId === 'manu_bd_to_bd[000]') {
          applied = 0
          facilityDetail = `巫术结晶 ${Math.floor(worldlyFireworks / 5)}`
        } else if (skill.buffId === 'manu_prod_spd_bd[200]') {
          applied = Math.floor(worldlyFireworks / 5) * 1
          facilityDetail = `worldly fireworks ${worldlyFireworks}`
        } else if (skill.buffId === 'manu_prod_spd_bd[201]') {
          applied = Math.floor(worldlyFireworks / 5) * 2
          facilityDetail = `worldly fireworks ${worldlyFireworks}`
        } else if (skill.buffId === 'manu_formula_spd&cost_bd[000]') {
          const count = Math.min(
            3,
            globalContext.presentOperators.filter((item) => matchesRiicIdentity(item, 'groupId', 'blacksteel')).length,
          )
          applied = room.product === 'gold' ? count * 2 : 0
          facilityDetail = `Blacksteel operators ${count}`
        } else if (skill.buffId === 'manu_constrLv[000]') {
          // This supplies the robots already derived by the global context. It
          // is not an additional productivity term and must not mark Minimalist unknown.
          applied = 0
          facilityDetail = `engineering robots ${globalContext.engineeringRobots}`
        } else if (skill.buffId === 'manu_prod_spd_bd[110]' || skill.buffId === 'manu_prod_spd_bd[100]') {
          const robots = globalContext.engineeringRobots
          const divisor = skill.buffId.endsWith('[110]') ? 8 : 16
          applied = Math.floor(robots / divisor) * 5
          facilityDetail = `engineering robots ${robots}`
        } else if (skill.buffId === 'manu_prod_spd_variable3[000]') {
          applied = activeOperators.reduce((sum, item) => {
            const itemMorale = moraleValues?.get(item.charId) ?? config.operatorMorale[item.charId] ?? 24
            const capacity = item.skills.reduce(
              (itemSum, itemSkill) =>
                itemSum + manufactureWarehouseCapacity(itemSkill, room, item, itemMorale, globalContext, classCounts),
              0,
            )
            const increasedCapacity = Math.max(0, capacity)
            return sum + increasedCapacity * (increasedCapacity > 16 ? 3 : 1)
          }, 0)
          facilityDetail = `warehouse capacity ${warehouseCapacity}`
        } else if (skill.buffId === 'manu_prod_spd_bd_n1[000]') {
          applied = 0
        } else if (skill.buffId === 'manu_prod_spd_bd[010]' || skill.buffId === 'manu_prod_spd_bd[000]') {
          const divisor = skill.buffId.endsWith('[010]') ? 1 : 2
          applied = Math.floor(manufacturePerceptionInformation / divisor)
          facilityDetail = `perception information ${manufacturePerceptionInformation}`
        } else if (skill.buffId === 'manu_prod_spd_variable2[000]') {
          applied = 0 // Deferred until all colleague skills are resolved.
          facilityDetail = 'copied from other operators'
        } else if (skill.buffId === 'manu_cost_all[000]') {
          applied = 0
        } else if (skill.buffId === 'manu_cost[000]') {
          if (worldlyFireworks === 0 && activeOperators.length <= 1) {
            applied = null
          } else {
            applied = 0
            facilityDetail = '心情减免已由心情计算层结算'
          }
        } else if (skill.buffId === 'manu_prod_spd_variable[000]') {
          applied = activeOperators.some((item) =>
            item.skills.some((itemSkill) => itemSkill.buffId === 'manu_prod_spd_variable3[000]'),
          )
            ? 0
            : warehouseCapacity * 2
          facilityDetail = `warehouse capacity +${warehouseCapacity}`
        } else if (stableManufactureBonus(skill) !== null) {
          applied = temporalSkillBonus(skill.buffId, operator.charId, timeContext) ?? stableManufactureBonus(skill)
        } else if (
          (manufactureWarehouseCapacity(skill, room, operator, morale, globalContext, classCounts) !== 0 ||
            skill.buffId === 'manu_skill_limit[000]' ||
            /仓库(?:容量)?上限/.test(skill.description)) &&
          directManufactureBonus(skill, room) === null
        ) {
          applied = 0
        } else if (operator.charId === 'char_4062_totter' && skill.name === '模糊视线') {
          applied = 30 - Math.floor(moraleGap / 4) * 5
          facilityDetail = `当前心情 ${morale.toFixed(1)}，落差 ${moraleGap.toFixed(1)}`
        } else if (operator.charId === 'char_4062_totter' && skill.name === '窗外雪啸') {
          applied = moraleGap > 12 ? 10 : 0
          facilityDetail = `当前心情 ${morale.toFixed(1)}，落差 ${moraleGap.toFixed(1)}`
        }
        const facility = applied === null
          ? facilityCountManufactureBonus(skill, room, globalContext)
          : null
        if (facility) {
          applied = facility.value
          facilityBased = true
          facilityDetail = facility.detail
        } else if (applied === null) {
          applied = directManufactureBonus(skill, room)
        }
        const link = classCounts ? classLinkBonus(skill, classCounts) : null
        if (link !== null) applied = (applied ?? 0) + link
        const partnerProductMatches =
          (!skill.description.includes('贵金属类配方') || room.product === 'gold') &&
          (!skill.description.includes('作战记录类配方') || room.product === 'exp') &&
          (!skill.description.includes('源石类配方') || room.product === 'fragment')
        const target = partnerProductMatches ? sameRoomTargetBonus(skill, operatorNames, room.type) : 0
        if (target !== null) applied = (applied ?? 0) + target
        if (
          skill.description.includes('莱茵科技类') &&
          skill.description.includes('红松骑士团类') &&
          skill.description.includes('视作标准化类')
        ) {
          applied = applied ?? 0
          details.push(`${operator.name}·${skill.name}：莱茵/红松技能计入标准化`)
        }
      } else if (room.type === 'trading') {
        const conditional = evaluateTradeConditionalSkill(skill, {
          config, roomOperators: activeOperators, presentOperators: globalContext.presentOperators,
          eliteFacilities: globalContext.eliteFacilities, woodCatnip: globalContext.woodCatnip,
        })
        if (conditional) {
          applied = conditional.value
        } else if (skill.buffId === 'trade_ord_spd&dorm&lv[010]' || skill.buffId === 'trade_ord_spd&dorm&lv[000]') {
          const multiplier = skill.buffId.endsWith('[010]') ? 2 : 1
          applied = config.facilities.dormitories.reduce<number>((sum, level) => sum + level, 0) * multiplier
        } else if (skill.buffId === 'trade_ord_spd&meet[010]') {
          applied = Math.min(30, 15 + config.facilities.reception * 5)
        } else if (skill.buffId === 'trade_ord_par&per[001]') {
          const workplaceNames = new Set(selectedOperators(config, [
            ...config.controlOperatorIds, ...config.rooms.flatMap(r => r.operatorIds),
            ...config.facilityOperatorIds.reception, ...config.facilityOperatorIds.workshop,
            ...config.facilityOperatorIds.office, ...config.facilityOperatorIds.training,
            ...recyclingOccupants(config),
            ...config.efficiencyResources.extraWorkplaceOperatorIds,
          ]).map(op => op.name))
          applied = 30 + (workplaceNames.has('伊内丝') ? 5 : 0) + (workplaceNames.has('W') ? 5 : 0)
        } else if (skill.buffId === 'trade_ord_spd_ext[001]' || skill.buffId === 'trade_ord_spd_ext[000]') {
          const ulpianus = globalContext.presentOperators.some(op => op.name === '乌尔比安')
          const base = skill.buffId.endsWith('[001]') ? 30 : 25
          const extra = skill.buffId.endsWith('[001]') ? 10 : 5
          applied = base + (ulpianus ? extra : 0)

        } else if (skill.buffId === 'trade_ord_spd&meet[000]') {
          applied = Math.min(40, 25 + config.facilities.reception * 5)
          facilityDetail = `reception level ${config.facilities.reception}`
        } else if (skill.buffId === 'trade_ord_spd_variable3[000]') {
          applied = Math.min(100, Math.floor(roomOrderLimitIncrease / 5) * 25)
          facilityDetail = `order limit +${roomOrderLimitIncrease}`
        } else if (skill.buffId === 'trade_ord_spd_variable[000]') {
          applied = roomOrderLimitIncrease * 4
          facilityDetail = `order limit +${roomOrderLimitIncrease}`
        } else if (skill.buffId === 'trade_ord_spd_par[001]') {
          applied = activeOperators.filter((item) => matchesRiicIdentity(item, 'nationId', 'laterano')).length * 15
        } else if (skill.buffId === 'trade_ord_spd&limit_tag[000]') {
          const tradeIds = new Set(config.rooms.filter(r => r.type === 'trading').flatMap(r => r.operatorIds))
          applied = globalContext.presentOperators.filter(op => tradeIds.has(op.charId) && hasRiicTag(op, 'bubbleHunter')).length * 20
        } else if (skill.buffId === 'trade_ord_spd&tag[020]') {
          const count = Math.min(5, globalContext.suiFacilities)
          applied = count * 4
          facilityDetail = `Sui facilities ${count}`
        } else if (skill.buffId === 'trade_ord_spd&share[000]') {
          applied = Math.max(0, staffCount - 1) * 15
        } else if (skill.buffId === 'trade_ord_spd&share[002]' || skill.buffId === 'trade_ord_spd&share[001]') {
          const rate = skill.buffId.endsWith('[002]') ? 20 : 10
          applied = Math.max(0, staffCount - 1) * rate

        } else if (skill.buffId === 'trade_ord_spd_bd[100]') {
          applied = monsterCuisine
          facilityDetail = `monster cuisine ${monsterCuisine}`
        } else if (skill.buffId === 'trade_ord_spd_bd_n2[000]') {
          applied = worldlyFireworks
          facilityDetail = `worldly fireworks ${worldlyFireworks}`
        } else if (skill.buffId === 'trade_ord_vodfox[000]') {
          applied = Math.max(0, staffCount - 1) * 45
        } else if (skill.buffId === 'trade_ord_spd_variable2[001]' || skill.buffId === 'trade_ord_spd_variable2[000]') {
          applied = 0 // Resolved after all other conditional contributions below.
        } else if (
          skill.buffId === 'trade_ord_limit_diff[000]' ||
          skill.buffId === 'trade_ord_limit_count[000]'
        ) {
          applied = 0
          facilityDetail = '最高阶段双技能在队友效率与容量求值后统一结算'
        } else if (skill.buffId === 'trade_ord_spd_bd_n1[000]') {
          applied = 0
        } else if (skill.buffId === 'trade_ord_spd_bd[010]' || skill.buffId === 'trade_ord_spd_bd[000]') {
          const divisor = skill.buffId.endsWith('[010]') ? 2 : 4
          applied = Math.floor(tradingPerceptionInformation / divisor)
          facilityDetail = `perception information ${tradingPerceptionInformation}`
        } else if (skill.buffId === 'trade_ord_spd&gold[100]') {
          applied = goldProductionLines * 5
          facilityDetail = `gold production lines ${goldProductionLines}`
        } else if (skill.buffId === 'trade_ord_line_durin[010]') {
          applied = 0
        } else if (skill.buffId === 'trade_ord_line_gold[010]') {
          applied = 5
          facilityDetail = `实体 ${globalContext.physicalGoldProductionLines}，绮良虚拟 +${kiraraGoldLines}`
        } else if (skill.buffId === 'trade_ord_spd&gold[010]' || skill.buffId === 'trade_ord_spd&gold[000]') {
          const divisor = skill.buffId.endsWith('[010]') ? 2 : 4
          applied = 5 + Math.floor(goldProductionLines / divisor) * 15
          facilityDetail = `gold production lines ${goldProductionLines}`
        } else {
          applied = directTradingBonus(skill)
        }
        const target = conditional?.includesNamedTarget ? null
          : skill.buffId === 'trade_ord_spd&multiPar[100]'
            ? (activeOperators.some(op => hasRiicTag(op, 'exusiai')) ? 25 : 0)
            : sameRoomTargetBonus(skill, operatorNames, room.type)
        if (target !== null) applied = (applied ?? 0) + target
        const isTradeCapacityOrMoraleOnly = [
          'trade_ord_limit&cost_P[020]',
          'trade_ord_limit&cost_P[001]',
          'trade_ord_limit&cost_P[000]',
          'trade_ord_limit&cost_P[010]',
          'trade_ord_limit&trade&lv[000]',
          'trade_ord_limit&trade&lv[001]',
          'trade_ord_limit&cost[000]',
          'trade_cost[000]',
        ].includes(skill.buffId)
        if (isTradeCapacityOrMoraleOnly) applied = 0 // Capacity/morale are evaluated in their own layers.
        if (['trade_cost&bd2[000]', 'trade_cost&bd2[001]'].includes(skill.buffId)) {
          if (activeOperators.length <= 1) {
            applied = null
          } else {
            applied = 0
            facilityDetail = '心情减免已由心情计算层结算'
          }
        }
        if (/高品质|特别订单|独占订单|违约订单|赤金交付数/.test(skill.description)) {
          applied = applied ?? 0
        }
      } else {
        const powerRoomOperators = config.rooms
          .filter((item) => item.type === 'power')
          .flatMap((item) =>
            selectedOperators(config,
              item.operatorIds.filter((id) => activeInContext(id, config, activeOperatorIds)),
            ),
          )
        const otherPowerOperators = powerRoomOperators.filter(
          (item) => item.charId !== operator.charId,
        )
        const workPlatformIds = new Set([
          'char_285_medic2',
          'char_286_cast3',
          'char_376_therex',
          'char_4000_jnight',
          'char_4093_frston',
          'char_4136_phonor',
          'char_4188_confes',
          'char_4227_gallus',
        ])
        const aigisBonus = evaluateAigisPowerSkill(skill, selectedOperators(config, config.rooms.filter(r => r.type === 'manufacture').flatMap(r => r.operatorIds)))
        if (aigisBonus !== null) {
          applied = aigisBonus
        } else if (skill.buffId === 'power_rec_spd&dorm&lv[000]') {
          applied = config.facilities.dormitories.reduce<number>((sum, level) => sum + level, 0) * 0.5
        } else if (skill.buffId === 'power_rec_rhine[000]') {
          const count = globalContext.presentOperators.filter(op => op.charId !== operator.charId && matchesRiicIdentity(op, 'groupId', 'rhine')).length
          applied = 10 + Math.min(5, count) * 3
        } else if (stablePowerBonus(skill) !== null) {
          applied = temporalSkillBonus(skill.buffId, operator.charId, timeContext) ?? stablePowerBonus(skill)
        } else if (skill.buffId === 'power_count[000]') {
          applied = 0 // Virtual station count is resolved by deriveEffectivePowerStations.
        } else if (skill.buffId === 'power_rec_drone[000]') {
          applied = Math.min(25, Math.floor(globalContext.droneCapacity / 10))
        } else if (skill.buffId === 'power_prod_spd_P[000]') {
          applied = 0
          facilityDetail = 'applied to the Wild Mane factory'
        } else if (skill.buffId === 'power_rec_spd_ext&faction[000]') {
          applied = otherPowerOperators.some((item) => matchesRiicIdentity(item, 'nationId', 'laterano')) ? 5 : 0
        } else if (skill.buffId === 'power_rec_spd_P[000]') {
          applied = selectedOperators(config, config.controlOperatorIds).some((item) => item.name === '凯尔希')
            ? 5
            : 0
        } else if (skill.buffId === 'power_rec_spd_ext&tag[000]') {
          applied = otherPowerOperators.some((item) => workPlatformIds.has(item.charId)) ? 5 : 0
        } else if (['power_rec_spd&cost[010]', 'power_rec_spd&cost[000]'].includes(skill.buffId)) {
          applied = 0 // Mood drain reduction evaluated in morale layer.
        } else if (skill.buffId === 'power_rec_spd_P[001]') {
          const logosPresent = globalContext.trainingOperatorIds.some(
            id => id === 'char_4121_logos' || id === '逻各斯' || OPERATOR_MAP.get(id)?.name === '逻各斯',
          )
          applied = logosPresent ? 5 : 0
          if (logosPresent) {
            facilityDetail = '逻各斯进驻训练室协助位 +5%'
          }
        } else {
          applied = directPowerBonus(skill)
        }
      }

      if (
        room.type === 'manufacture' &&
        automationOperators.size > 0 &&
        !automationOperators.has(operator.charId) &&
        !facilityBased &&
        applied !== null
      ) {
        if (applied !== 0) details.push(`${operator.name}·${skill.name}：被自动化清零`)
        applied = 0
      }
      if (
        room.type === 'trading' &&
        shamareActive &&
        operator.charId !== 'char_254_vodfox' &&
        applied !== null
      ) {
        if (applied !== 0) details.push(`${operator.name}·${skill.name}：被巫恋清零`)
        applied = 0
      }

      if (room.type === 'manufacture' && operator.charId !== 'char_243_waaifu' && !facilityBased && applied !== null) {
        waaiFuCopyableBonus += applied
      }
      if (applied !== null) {
        skillBonus += applied
        opSkillTotal += applied
        if (applied !== 0) {
          details.push(
            `${operator.name}·${skill.name}：${applied > 0 ? '+' : ''}${applied}%${facilityDetail ? `（${facilityDetail}）` : ''}`,
          )
          opItems.push({
            name: `${operator.name}·${skill.name}`,
            value: applied,
            detail: facilityDetail || undefined,
          })
        }
      } else {
        unquantifiedSkills.push(`${operator.name}·${skill.name}`)
      }
    }

    const synergies = global.operatorBonuses.get(operator.charId) ?? []
    for (const syn of synergies) {
      opItems.push(syn)
      opSkillTotal += syn.value
    }
    operatorContributions.push({
      operatorId: operator.charId,
      operatorName: operator.name,
      staffBonus: opStaff,
      skillBonus: opSkillTotal,
      totalBonus: opStaff + opSkillTotal,
      items: opItems,
    })
  }

  if (room.type === 'manufacture' && automationOperators.size === 0) {
    const copyOperator = activeOperators.find(operator => operator.skills.some(skill => skill.buffId === 'manu_prod_spd_variable2[000]'))
    if (copyOperator) {
      // Preserve the separately granted knight support already included by this rule.
      const knightSupport = vivianaActive
        ? activeOperators.filter(operator => operator.charId !== copyOperator.charId && hasRiicTag(operator, 'knight')).length * 7
        : 0
      const copied = Math.min(40, Math.floor((waaiFuCopyableBonus + knightSupport) / 5) * 5)
      const contribution = operatorContributions.find(item => item.operatorId === copyOperator.charId)!
      if (copied !== 0) {
        const name = copyOperator.name + '·配合意识'
        contribution.items.push({ name, value: copied, detail: '复制其他干员已结算的非设施数量生产力' })
        contribution.skillBonus += copied
        contribution.totalBonus += copied
        skillBonus += copied
        details.push(name + '：+' + copied + '%')
      }
    }
  }

  const jaye = room.type === 'trading' ? activeOperators.find(op =>
    op.skills.some(skill => skill.buffId === 'trade_ord_limit_diff[000]')) : undefined
  if (jaye) {
    const hasCountSkill = jaye.skills.some(skill => skill.buffId === 'trade_ord_limit_count[000]')
    const isElite0 = Boolean(config.jayeElite0 || !hasCountSkill)
    const snowsant = activeOperators.find(op => op.skills.some(skill => /^trade_ord_spd_variable2\[(000|001)\]$/.test(skill.buffId)))
    const copySkill = snowsant?.skills.find(skill => /^trade_ord_spd_variable2\[(000|001)\]$/.test(skill.buffId))
    const partners = activeOperators.filter(op => op.charId !== jaye.charId && op.charId !== snowsant?.charId)
    const resolved = evaluateHighestPhaseJaye({
      roomLevel: room.level,
      hasBothJayeSkills: hasCountSkill && !config.jayeElite0,
      isElite0,
      clearedByShamare: shamareActive,
      snowsant: snowsant && copySkill ? { operatorId: snowsant.charId, cap: copySkill.buffId.endsWith('[001]') ? 35 : 25 } : undefined,
      partners: partners.map(op => {
        const contribution = operatorContributions.find(item => item.operatorId === op.charId)!
        const skills = op.skills.filter(skill => skill.roomType === 'TRADING')
        let capacity = skills.reduce((sum, skill) => sum + orderLimitDelta(skill, room, operatorNames), 0)
        if (gnosisInControl && matchesRiicIdentity(op, 'nationId', 'kjerag')) capacity += 6
        if (wisdelInControl && op.name === '赫德雷') capacity += 2
        const orderLimitSkills = skills.filter(skill => ['trade_ord_spd_variable[000]', 'trade_ord_spd_variable3[000]'].includes(skill.buffId))
        const orderLimitDerivedEfficiency = orderLimitSkills.reduce((sum, skill) => {
          const item = contribution.items.find(i => i.name === `${op.name}·${skill.name}`)
          return sum + (item ? item.value : 0)
        }, 0)
        return {
          operatorId: op.charId,
          efficiency: contribution.skillBonus,
          snowsantCopyableEfficiency: contribution.skillBonus,
          orderLimitDelta: capacity,
          dependsOnOrderLimit: orderLimitSkills.length > 0,
          orderLimitDerivedEfficiency,
        }
      }),
    })
    if (resolved.supported) {
      for (const [op, value, label] of [
        [jaye, resolved.jayeEfficiency, isElite0 ? '摊贩经济' : '摊贩经济 / 市井之道'],
        [snowsant, resolved.snowsantEfficiency, copySkill?.name ?? '天道酬勤'],
      ] as const) {
        if (!op || value === 0) continue
        const contribution = operatorContributions.find(item => item.operatorId === op.charId)!
        const name = op.name + '·' + label
        const detail = op === jaye
          ? (isElite0 ? `订单上限 ${resolved.effectiveOrderLimit}，精0跑单全额差额加成` : `订单上限 ${resolved.effectiveOrderLimit}，双技能队列项抵消`)
          : (isElite0 ? '复制其他干员订单效率' : '先复制第三人，再计入孑的容量折减')
        contribution.items.push({ name, value, detail })
        contribution.skillBonus += value
        contribution.totalBonus += value
        skillBonus += value
        details.push(`${name}：+${value}%（${detail}）`)
      }
    } else {
      if (isElite0) {
        unquantifiedSkills.push('孑·摊贩经济')
      } else {
        unquantifiedSkills.push('孑·摊贩经济', '孑·市井之道')
      }
      if (snowsant) unquantifiedSkills.push(snowsant.name + '·' + copySkill!.name)
      details.push(`${resolved.reason}：${resolved.detail}`)
    }
  }

  if (room.type === 'trading' && !shamareActive && !jaye) {
    const copyOperators = activeOperators.filter(op => op.skills.some(skill => /^trade_ord_spd_variable2\[(000|001)\]$/.test(skill.buffId)))
    const copyIds = new Set(copyOperators.map(op => op.charId))
    for (const operator of copyOperators) {
      const copySkill = operator.skills.find(skill => /^trade_ord_spd_variable2\[(000|001)\]$/.test(skill.buffId))!
      const copied = snowsantCopiedTradeBonus(operatorContributions, copyIds, copySkill.buffId.endsWith('[001]') ? 35 : 25)
      const contribution = operatorContributions.find(item => item.operatorId === operator.charId)!
      if (copied !== 0) {
        const name = operator.name + '·' + copySkill.name
        contribution.items.push({ name, value: copied, detail: '复制其他干员已结算订单效率' })
        contribution.skillBonus += copied
        contribution.totalBonus += copied
        skillBonus += copied
        details.push(name + '：+' + copied + '%')
      }
    }
  }

  const exhausted = operators.filter((operator) => !activeOperators.some((a) => a.charId === operator.charId))
  for (const op of exhausted) {
    const synergies = global.operatorBonuses.get(op.charId) ?? []
    const grantedBonus = synergies.reduce((sum, item) => sum + item.value, 0)
    operatorContributions.push({
      operatorId: op.charId,
      operatorName: op.name,
      staffBonus: 0,
      skillBonus: grantedBonus,
      totalBonus: grantedBonus,
      items: [{ name: '0 心情：进驻基础及自身技能失效', value: 0 }, ...synergies],
    })
  }

  skillBonus += global.bonus
  details.push(...global.details)
  if (global.unquantifiedSkills.length) {
    unquantifiedSkills.push(...global.unquantifiedSkills)
  }
  const {quality,qualityWarmup} = room.type === 'trading'
    ? temporalTradeQuality(activeOperators.map(operator=>operator.charId),room.quality,config,timeContext,room.level)
    : {quality:room.quality,qualityWarmup:1}
  const specialOrder =
    room.type === 'trading' ? inferSpecialOrder(activeOperators, room.specialOrder) : room.specialOrder
  if (room.type === 'trading' && quality !== room.quality) {
    details.push(`订单品质：由干员技能自动切换为 ${quality === 'beta' ? 'β' : 'α'} 分布`)
  }
  if (room.type === 'trading' && specialOrder !== room.specialOrder) {
    details.push('特殊订单：已按进驻干员与订单优先级自动应用')
  }
  if (room.type === 'trading' && specialOrder === 'shiftRun') {
    details.push(
      room.level >= 3
        ? '跑单：订单生成前换入但书·β与龙舌兰·β，生成后恢复原班组'
        : '跑单：订单生成前换入但书·β，生成后恢复原班组',
    )
  }

  return {
    efficiencyPercent: 100 + staffBonus + skillBonus,
    staffBonus,
    skillBonus,
    operatorNames: operators.map((operator) => operator.name),
    details,
    unquantifiedSkills,
    quality,
    qualityWarmup,
    specialOrder,
    operatorContributions,
    roomContributions,
  }
}

export function formatStructuredContributions(result: OperatorEfficiencyResult): string {
  const parts: string[] = []
  for (const op of result.operatorContributions) {
    const itemStrs = op.items
      .filter((it) => it.value !== 0)
      .map((it) => `${it.name}${it.value >= 0 ? `+${it.value}%` : `${it.value}%`}`)
    parts.push(
      `[${op.operatorName}] ${op.totalBonus >= 0 ? `+${op.totalBonus}%` : `${op.totalBonus}%`}${itemStrs.length ? ` (${itemStrs.join(', ')})` : ''}`,
    )
  }
  for (const roomItem of result.roomContributions) {
    if (roomItem.value !== 0) {
      parts.push(`[房间/全局] ${roomItem.value >= 0 ? `+${roomItem.value}%` : `${roomItem.value}%`} (${roomItem.source})`)
    }
  }
  return parts.join('; ')
}
