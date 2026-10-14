import { operatorFor, hasOperatorSkill } from '../domain/operatorContext'
import { matchesRiicFaction as isFaction, isRiicAlter as isAlter } from '../domain/riicIdentity'
import { OPERATOR_MAP, type OperatorRecord, type OperatorSkill } from '../domain/operators'
import type { AppConfig, OperatorMoraleResult, OutputRoom, RoomType } from '../domain/types'
import { evaluateOperators } from './operatorRules'
import { createOperatorGroupSchedule } from './operatorGroups'
import { createShiftRoster } from './shiftRoster'
import { buildRiicGlobalContext, deriveWorldlyFireworks } from './globalContext'
import { isSupportOperatorWorking, recyclingOccupants, supportSkillConditionMatches, SUPPORT_OPERATOR_IDS } from './supportFacilities/conditions'

interface Assignment {
  operator: OperatorRecord
  roomId: string
  roomType: RoomType | 'control' | 'office' | 'reception' | 'recycle'
  room?: OutputRoom
  peers: OperatorRecord[]
}

interface ResourceValues {
  enthusiasm: number
  fireworks: number
}

interface RateSnapshot {
  rates: Map<string, number>
  details: Map<string, string[]>
  resources: ResourceValues
}

export interface CurrentMoraleRates {
  /** Explicit gaps in legacy numeric rate rules; callers must surface these. */
  unquantified: string[]
  rates: Record<string, number>
  details: Record<string, string[]>
}

export interface MoraleSimulation {
  averageEfficiencyPercent: Record<string, number>
  averagePowerBonusPercent: number
  operators: OperatorMoraleResult[]
  roomShiftDetails: Record<string, string[]>
}

function dormitoryRecoveryPerHour(config: AppConfig) {
  const builtDorms = config.facilities.dormitories.filter(level => level > 0)
  if (!builtDorms.length) return 0
  return builtDorms
    .reduce<number>((sum, level) => sum + 1.5 + level * 0.5, 0) /
    builtDorms.length
}

function leavesAtZeroMorale(operatorId: string, config: AppConfig) {
  return operatorId !== 'char_285_medic2' && !(config.workaholicOperatorIds ?? []).includes(operatorId)
}

const MLYNAR_EXTENDED_SKILLS = new Set([
  '左膀右臂', 'S.W.E.E.P.', '零食网络', '清理协议', '替身', '必要责任', '护卫',
  '小小的领袖', '独善其身', '笑靥如春', '金盏花诗会', '捍卫之道', '博识生手',
  '点滴关照', '总工程师',
])

const CUSTOM_MOOD_SKILLS = new Set([
  '德才兼备', '异格者', '彩虹小队', '幕后指挥', '学生会会长', '坚毅随和',
  '潮汐守望', '公事公办', '巴别塔之帜', '孤光共照', '知我为我',
  '演技的怪物', '互为半身', '生活的重压', '万里传书', '跋山涉水', '春雷响，万物长', '团队精神', '杯莫停',
  '“未完的故事”', '羁绊相生', '成效优先', '英雄的骄傲·β',
])

function selected(config: AppConfig, ids: string[]) {
  return ids.map((id) => operatorFor(config, id)).filter((item): item is OperatorRecord => Boolean(item))
}

function assignments(config: AppConfig): Assignment[] {
  const result: Assignment[] = []
  const controlPeers = selected(config, config.controlOperatorIds)
  for (const operator of controlPeers) {
    result.push({ operator, roomId: '控制中枢', roomType: 'control', peers: controlPeers })
  }
  for (const room of config.rooms) {
    const peers = selected(config, room.operatorIds)
    for (const operator of peers) {
      result.push({ operator, roomId: room.id, roomType: room.type, room, peers })
    }
  }
  for (const roomType of ['office', 'reception', 'recycle'] as const) {
    if (roomType === 'recycle' && !config.facilities.recycle) continue
    const peers = selected(config, config.facilityOperatorIds[roomType] ?? [])
    for (const operator of peers) result.push({ operator, roomId: roomType, roomType, peers })
  }
  return result
}

function relevantRoomType(roomType: Assignment['roomType']) {
  return roomType === 'office' ? 'HIRE' : roomType === 'reception' ? 'MEETING' : roomType === 'control' ? 'CONTROL' : roomType.toUpperCase()
}

function activeAssignments(all: Assignment[], activeIds: Set<string>) {
  return all.filter((assignment) => activeIds.has(assignment.operator.charId))
}

function conditionMatches(skill: OperatorSkill, assignment: Assignment, activeIds: Set<string>, config: AppConfig) {
  const description = skill.description
  const peers = assignment.peers.filter(peer => activeIds.has(peer.charId) &&
    (skill.buffId !== 'meet_spd&cost_char[000]' || isSupportOperatorWorking(config, peer.charId, activeIds)))
  if (!supportSkillConditionMatches(skill, assignment.operator.charId, peers.map(peer => peer.charId))) return false
  if (description.includes('生产作战记录类配方时') && assignment.room?.product !== 'exp') return false
  const sameRoom = description.match(/当与(.+?)在同一个(?:制造站|贸易站)时/)
  if (sameRoom) {
    return assignment.peers.some((peer) => peer.name === sameRoom[1] && activeIds.has(peer.charId))
  }
  const controlTogether = description.match(/当与(.+?)进驻控制中枢一起工作时/)
  if (controlTogether) {
    return assignment.peers.some((peer) => peer.name === controlTogether[1] && activeIds.has(peer.charId))
  }
  return true
}

function consumptionDelta(description: string): number | null {
  const consume = description.match(/心情每小时消耗([+-])([\d.]+)/)
  if (consume) return (consume[1] === '+' ? 1 : -1) * Number(consume[2])
  const recover = description.match(/心情每小时恢复\+([\d.]+)/)
  return recover ? -Number(recover[1]) : null
}

function moodScope(description: string): 'room' | 'others' | 'self' {
  if (/除自身以外|其余干员/.test(description)) return 'others'
  if (/当前制造站内所有干员|贸易站内(?:全体)?干员|全体心情|控制中枢内所有干员/.test(description)) {
    return 'room'
  }
  return 'self'
}

function resources(
  config: AppConfig,
  all: Assignment[],
  activeIds: Set<string>,
  morale: Map<string, number>,
): ResourceValues {
  const activeControlIds = new Set(
    activeAssignments(all, activeIds)
      .filter((item) => item.roomType === 'control')
      .map((item) => item.operator.charId),
  )
  let enthusiasm = 0
  if (activeControlIds.has('char_4186_tmoris')) enthusiasm += 10
  if (activeControlIds.has('char_4183_mortis')) enthusiasm += 20
  if (activeControlIds.has('char_4185_amoris')) enthusiasm += 10
  if (activeControlIds.has('char_4184_dolris')) {
    enthusiasm += Math.max(
      0,
      Math.min(config.facilities.dormitories.filter(level => level > 0).length * 5, config.dormitoryOccupantCount),
    )
  }

  const fireworks = deriveWorldlyFireworks(config, activeIds, morale)

  return { enthusiasm, fireworks }
}

function targetsForScope(
  source: Assignment,
  all: Assignment[],
  activeIds: Set<string>,
  scope: ReturnType<typeof moodScope>,
) {
  if (scope === 'self') return [source]
  return source.peers
    .filter((peer) => activeIds.has(peer.charId))
    .filter((peer) => scope !== 'others' || peer.charId !== source.operator.charId)
    .map((peer) => all.find((item) => item.operator.charId === peer.charId))
    .filter((item): item is Assignment => Boolean(item))
}

function computeRates(
  config: AppConfig,
  all: Assignment[],
  activeIds: Set<string>,
  morale: Map<string, number>,
): RateSnapshot {
  const rates = new Map<string, number>()
  const details = new Map<string, string[]>()
  const active = activeAssignments(all, activeIds)
  const activeControl = active.filter((item) => item.roomType === 'control')
  const activeControlCount = activeControl.length
  const resourceValues = resources(config, all, activeIds, morale)

  const add = (target: Assignment, delta: number, detail: string) => {
    rates.set(target.operator.charId, (rates.get(target.operator.charId) ?? 0) + delta)
    const targetDetails = details.get(target.operator.charId) ?? []
    if (!targetDetails.includes(detail)) targetDetails.push(detail)
    details.set(target.operator.charId, targetDetails)
  }
  const addAll = (targets: Assignment[], delta: number, detail: string) => {
    for (const target of targets) add(target, delta, detail)
  }

  for (const assignment of active) {
    let rate = 1 - activeControlCount * 0.05
    const baseDetails = [
      '基础消耗 1/h',
      `控制中枢 ${activeControlCount} 人：-${(activeControlCount * 0.05).toFixed(2)}/h`,
    ]
    if (assignment.roomType === 'manufacture' || assignment.roomType === 'trading') {
      const count = assignment.room?.operatorIds.length ?? 0
      const reduction = count >= 3 ? 0.1 : count >= 2 ? 0.05 : 0
      rate -= reduction
      if (reduction) baseDetails.push(`${count} 人进驻减免：-${reduction.toFixed(2)}/h`)
    }
    rates.set(assignment.operator.charId, rate)
    details.set(assignment.operator.charId, baseDetails)
  }

  const waaiFuRooms = new Set(
    active
      .filter((item) => item.operator.charId === 'char_243_waaifu' && item.roomType === 'manufacture')
      .map((item) => item.roomId),
  )
  const shouldCancelPositiveSelf = (
    source: Assignment,
    delta: number,
    scope: ReturnType<typeof moodScope>,
  ) => delta > 0 && scope === 'self' && (
    waaiFuRooms.has(source.roomId) ||
    (source.roomType === 'control' && activeControl.some((item) => item.operator.charId === 'char_2023_ling') && isFaction(source.operator, 'sui'))
  )

  for (const source of active) {
    for (const skill of source.operator.skills.filter((item) => item.roomType === relevantRoomType(source.roomType))) {
      if (CUSTOM_MOOD_SKILLS.has(skill.name) || !conditionMatches(skill, source, activeIds, config)) continue
      if (skill.description.includes('宿舍')) continue
      const delta = consumptionDelta(skill.description)
      if (delta === null) continue
      const scope = moodScope(skill.description)
      if (shouldCancelPositiveSelf(source, delta, scope)) {
        add(source, 0, `${waaiFuRooms.has(source.roomId) ? '槐琥·团队精神' : '令·杯莫停'}：消除 ${source.operator.name}·${skill.name} 的自身消耗`)
        continue
      }
      addAll(
        targetsForScope(source, all, activeIds, scope),
        delta,
        `${source.operator.name}·${skill.name}：${delta > 0 ? '+' : ''}${delta}/h`,
      )
    }
  }

  const applyCountRecovery = (
    sourceId: string,
    predicate: (operator: OperatorRecord) => boolean,
    amount: number,
    label: string,
  ) => {
    if (!activeIds.has(sourceId)) return
    const count = activeControl.filter((item) => predicate(item.operator)).length
    if (count) addAll(activeControl, -count * amount, `${label}：${count} 人，-${(count * amount).toFixed(2)}/h`)
  }

  applyCountRecovery('char_010_chen', (operator) => isFaction(operator, 'lgd'), 0.05, '陈·德才兼备')
  for (const id of ['char_1021_kroos2', 'char_1011_lava2', 'char_1024_hbisc2']) {
    applyCountRecovery(id, isAlter, 0.05, `${OPERATOR_MAP.get(id)?.name ?? id}·异格者`)
  }
  for (const id of ['char_456_ash', 'char_457_blitz', 'char_458_rfrost', 'char_459_tachak']) {
    applyCountRecovery(id, (operator) => isFaction(operator, 'rainbow'), 0.05, `${OPERATOR_MAP.get(id)?.name ?? id}·彩虹小队`)
  }
  applyCountRecovery('char_206_gnosis', (operator) => isFaction(operator, 'kjerag', 'karlan'), 0.05, '灵知·幕后指挥')
  applyCountRecovery('char_197_poca', (operator) => isFaction(operator, 'student'), 0.05, '早露·学生会会长')

  if (activeIds.has('char_226_hmau') && hasOperatorSkill(config,'char_226_hmau','control_mp_cost&faction2[000]')) {
    const leeOperators = activeControl.filter((item) => isFaction(item.operator, 'lee'))
    if (leeOperators.length) {
      addAll(activeControl, -leeOperators.length * 0.05, `吽·坚毅随和：全员 -${(leeOperators.length * 0.05).toFixed(2)}/h`)
      for (const lee of leeOperators) {
        add(lee, -leeOperators.length * 0.2, `吽·坚毅随和：鲤氏派系额外 -${(leeOperators.length * 0.2).toFixed(2)}/h`)
      }
    }
  }

  const varkis = activeControl.find((item) => item.operator.charId === 'char_4166_varkis')
  if (varkis && activeControl.some((item) =>
    item.operator.charId !== varkis.operator.charId && isFaction(item.operator, 'sargon'),
  )) {
    add(varkis, 0.02, '摆渡人·英雄的骄傲·β：与萨尔贡干员同驻，+0.02/h')
  }

  const theresa = activeControl.find((item) => item.operator.charId === 'char_4134_cetsyr')
  const amiya = activeControl.find((item) => item.operator.name === '阿米娅')
  if (theresa && amiya && hasOperatorSkill(config,theresa.operator.charId,'control_mp_cost_double[001]')) {
    add(theresa, -0.1, '魔王·“未完的故事”：与阿米娅同驻，-0.1/h')
    add(amiya, -0.1, '魔王·“未完的故事”：与魔王同驻，-0.1/h')
  }

  const chongyue = activeControl.find((item) => item.operator.charId === 'char_2024_chyue')
  if (chongyue) {
    if (activeControl.some((item) => item.operator.charId === 'char_2023_ling')) {
      add(chongyue, 0, '令·杯莫停：消除重岳·知我为我的自身消耗')
    } else {
      add(chongyue, 0.5, '重岳·知我为我：+0.5/h')
    }
  }

  const sakiko = activeControl.find((item) => item.operator.charId === 'char_4182_oblvns')
  if (sakiko && resourceValues.enthusiasm >= 40) {
    add(sakiko, 0.05, `丰川祥子·生活的重压：热情值 ${resourceValues.enthusiasm}，+0.05/h`)
  }
  const mutsumi = activeControl.find((item) => item.operator.charId === 'char_4183_mortis')
  if (mutsumi) {
    if (sakiko && hasOperatorSkill(config,mutsumi.operator.charId,'control_mp_cost_reset[000]')) {
      add(mutsumi, 0, '若叶睦·互为半身：与丰川祥子同驻，消除自身技能消耗')
    } else {
      const delta = Math.floor(resourceValues.enthusiasm / 8) * 0.01
      if (delta) add(mutsumi, delta, `若叶睦·演技的怪物：热情值 ${resourceValues.enthusiasm}，+${delta.toFixed(2)}/h`)
    }
  }
  if (sakiko && activeControl.some((item) => item.operator.charId === 'char_4184_dolris' && hasOperatorSkill(config,item.operator.charId,'control_dorm_rec2[000]'))) {
    add(sakiko, -0.1, '三角初华·羁绊相生：丰川祥子 -0.1/h')
  }
  if (sakiko && activeControl.some((item) => item.operator.charId === 'char_4185_amoris' && hasOperatorSkill(config,item.operator.charId,'control_mp&meet_spd[000]'))) {
    add(sakiko, 0.05, '祐天寺若麦·成效优先：丰川祥子 +0.05/h')
  }

  const gladiia = activeControl.find((item) => item.operator.charId === 'char_474_glady')
  if (gladiia) {
    // cc.g.abyssal: physical presence, not productive/positive-morale workers.
    const dormIds = new Set(config.facilityOperatorIds.dormitories.flat())
    const hunters = buildRiicGlobalContext(config, activeIds, morale).presentOperators.filter(op => isFaction(op, 'abyssal'))
    const outside = hunters.filter(op => !dormIds.has(op.charId)).length
    const resting = hunters.filter(op => dormIds.has(op.charId))
    const full = resting.filter(op => (morale.get(op.charId) ?? (config.zeroMoraleOperatorIds.includes(op.charId) ? 0 : config.operatorMorale[op.charId] ?? 24)) >= 24 - 1e-8).length
    const delta = .5 * (outside - resting.length - full)
    add(gladiia, delta, `歌蕾蒂娅·潮汐守望：宿舍外 ${outside}，宿舍内 ${resting.length}（满心情 ${full}），${delta >= 0 ? '+' : ''}${delta}/h`)

  }

  const chimes = active.find((item) => item.operator.charId === 'char_4083_chimes' && item.roomType === 'trading')
  if (chimes) {
    const isE2 = hasOperatorSkill(config, chimes.operator.charId, 'trade_cost&bd2[001]')
    const rate = isE2 ? 0.02 : 0.01
    const skillName = isE2 ? '万里传书' : '跋山涉水'
    const delta = -0.1 - Math.floor(resourceValues.fireworks / 10) * rate
    addAll(
      active.filter((item) => item.roomId === chimes.roomId),
      delta,
      `铎铃·${skillName}：人间烟火 ${resourceValues.fireworks}，${delta.toFixed(2)}/h`,
    )
  }

  const shu = active.find((item) => item.operator.charId === 'char_2025_shu' && item.roomType === 'manufacture')
  if (shu) {
    const delta = -0.1
    addAll(
      active.filter((item) => item.roomId === shu.roomId),
      delta,
      `黍·春雷响，万物长：${delta.toFixed(2)}/h`,
    )
  }

  const mlynarActive = activeControl.some(item => item.operator.charId === 'char_4064_mlynar' && hasOperatorSkill(config,item.operator.charId,'control_mp_lonely[000]'))
  const mlynarExpansion = mlynarActive ? activeControl.reduce((count, item) => count + item.operator.skills.filter(
    skill => skill.roomType === 'CONTROL' && MLYNAR_EXTENDED_SKILLS.has(skill.name),
  ).length, 0) * .05 : 0

  let otherFacilityRecovery = 0
  let otherFacilityLabel = ''
  if (activeControl.some((item) => item.operator.charId === 'char_1035_wisdel' && hasOperatorSkill(config,item.operator.charId,'control_mp_expand_double[000]'))) {
    const value = activeControl.some((item) => item.operator.charId === 'char_4134_cetsyr') ? 0.2 : 0.1
    if (value > otherFacilityRecovery) {
      otherFacilityRecovery = value
      otherFacilityLabel = `维什戴尔·巴别塔之帜${value === 0.2 ? '（魔王联动）' : ''}`
    }
  }
  if (activeControl.some((item) => item.operator.charId === 'char_2024_chyue' && hasOperatorSkill(config,item.operator.charId,'control_mp_bd_cost_expand[000]'))) {
    const value = 0.05 + Math.floor(resourceValues.fireworks / 20) * 0.05
    if (value > otherFacilityRecovery) {
      otherFacilityRecovery = value
      otherFacilityLabel = `重岳·孤光共照（人间烟火 ${resourceValues.fireworks}）`
    }
  }
  for (const target of active.filter(item => item.roomType !== 'control')) {
    const mlynarRecovery = mlynarActive ? mlynarExpansion + (['power','office','reception'].includes(target.roomType) ? .1 : 0) : 0
    const recovery = Math.max(mlynarRecovery, otherFacilityRecovery)
    if (mlynarActive && target.roomType === 'power') add(target, 0, '玛恩纳候选效果：发电站 -0.1/h，与扩展合计后参与同类最高')
    if (recovery) add(target, -recovery, `公事公办/孤光共照/巴别塔之帜：同类最高 -${recovery.toFixed(2)}/h（${mlynarRecovery >= otherFacilityRecovery ? '玛恩纳' : otherFacilityLabel}）`)
  }

  return { rates, details, resources: resourceValues }
}

/** Evaluate the currently occupied roster only. Dynamic schedulers use this
 * adapter after each atomic roster change instead of invoking legacy rotation. */
export function currentMoraleRates(config: AppConfig): CurrentMoraleRates {
  const all = assignments(config)
  const morale = new Map(all.map(({ operator, roomType }) => {
    // Preserve the frozen legacy adapter; new support providers also accept its explicit zero flag.
    const newSupport = roomType === 'recycle' || Object.values(SUPPORT_OPERATOR_IDS).some(id => id === operator.charId)
    const initial = newSupport && config.zeroMoraleOperatorIds.includes(operator.charId)
      ? 0 : config.operatorMorale[operator.charId] ?? 24
    return [operator.charId, Math.max(0, Math.min(24, initial))] as const
  }))
  const activeIds = new Set(all
    .map(({ operator }) => operator.charId)
    .filter((id) => (morale.get(id) ?? 0) > 0))
  const snapshot = computeRates(config, all, activeIds, morale)
  const unquantified: string[] = []
  return {
    unquantified,
    rates: Object.fromEntries(snapshot.rates),
    details: Object.fromEntries(snapshot.details),
  }
}

function boundaryValues(assignment: Assignment) {
  if (assignment.operator.charId === 'char_4062_totter') return [20, 16, 12, 8, 4]
  if (assignment.operator.charId === 'char_2023_ling' || assignment.operator.charId === 'char_2015_dusk') return [12]
  return []
}

function nextBoundaryDuration(
  all: Assignment[],
  activeIds: Set<string>,
  morale: Map<string, number>,
  rates: Map<string, number>,
) {
  let duration = Number.POSITIVE_INFINITY
  for (const assignment of all) {
    const id = assignment.operator.charId
    if (!activeIds.has(id)) continue
    const value = morale.get(id) ?? 0
    const rate = rates.get(id) ?? 1
    for (const boundary of boundaryValues(assignment)) {
      if (rate > 0 && value > boundary + 1e-7) duration = Math.min(duration, (value - boundary) / rate)
      if (rate < 0 && value < boundary - 1e-7) duration = Math.min(duration, (boundary - value) / -rate)
    }
  }
  return duration
}

function nudgeBoundaryCrossings(
  all: Assignment[],
  activeIds: Set<string>,
  morale: Map<string, number>,
  rates: Map<string, number>,
) {
  let changed = false
  for (const assignment of all) {
    const id = assignment.operator.charId
    if (!activeIds.has(id)) continue
    const value = morale.get(id) ?? 0
    const rate = rates.get(id) ?? 1
    for (const boundary of boundaryValues(assignment)) {
      if (Math.abs(value - boundary) <= 1e-8 && rate !== 0) {
        morale.set(id, boundary + (rate > 0 ? -1e-7 : 1e-7))
        changed = true
      }
    }
  }
  return changed
}

export function simulateMorale(
  config: AppConfig,
  options: { warmupHours?: number; sampleHours?: number } = {},
): MoraleSimulation {
  const warmupHours = Math.max(0, options.warmupHours ?? 0)
  const sampleHours = Math.max(1, options.sampleHours ?? config.hours)
  const totalHours = warmupHours + sampleHours
  const roster = createShiftRoster(config)
  const morale = new Map(roster.participants.map((participant) => {
    const configured = config.operatorMorale[participant.operatorId]
    const initial = config.zeroMoraleOperatorIds.includes(participant.operatorId)
      ? 0
      : Math.max(0, Math.min(24,
          typeof configured === 'number' && Number.isFinite(configured) ? configured : 24,
        ))
    return [participant.operatorId, initial] as const
  }))
  const initialMorale = new Map(morale)
  const groupSchedule = createOperatorGroupSchedule(config.operatorGroups, roster.primaryOperatorIds)
  const exhaustedAt = new Map<string, number>()
  const leftAt = new Map<string, number>()
  const leaveReason = new Map<string, OperatorMoraleResult['leaveReason']>()
  const startedAt = new Map<string, number>(roster.participants
    .filter((participant) => participant.role === 'primary')
    .map((participant) => [participant.operatorId, 0] as const))
  const firstRates = new Map<string, number>()
  const firstDetails = new Map<string, string[]>()
  const roomShiftDetails: Record<string, string[]> = Object.fromEntries(
    config.rooms.map((room) => [room.id, []]),
  )
  const efficiencyTotals: Record<string, number> = Object.fromEntries(config.rooms.map((room) => [room.id, 0]))
  let powerBonusTotal = 0
  let elapsed = 0
  const recoveryPerHour = dormitoryRecoveryPerHour(config)
  const alwaysPresentIds = new Set([
    ...config.facilityOperatorIds.dormitories.flat(),
    ...config.facilityOperatorIds.reception,
    ...config.facilityOperatorIds.workshop,
    ...config.facilityOperatorIds.office,
    ...config.facilityOperatorIds.training,
    ...recyclingOccupants(config),
    ...config.efficiencyResources.extraWorkplaceOperatorIds,
  ].filter((id) => !config.zeroMoraleOperatorIds.includes(id)))

  const activeIds = () => new Set(
    [
      ...[...roster.activeOperatorIds()].filter((id) => (morale.get(id) ?? 0) > 0),
      ...alwaysPresentIds,
    ],
  )
  const recordSnapshot = (snapshot: RateSnapshot, ids: Set<string>) => {
    for (const id of ids) {
      if (firstRates.has(id)) continue
      firstRates.set(id, snapshot.rates.get(id) ?? 0)
      firstDetails.set(id, [...(snapshot.details.get(id) ?? [])])
    }
  }
  const applyDepartures = (triggerIds: Set<string>, time: number) => {
    const departures = new Set(
      [...groupSchedule.expandDepartures(triggerIds)]
        .filter((id) => leavesAtZeroMorale(id, config)),
    )
    for (const transition of roster.depart(
      departures,
      (id) => (morale.get(id) ?? 0) >= 24 - 1e-8,
    )) {
      if (triggerIds.has(transition.operatorId)) exhaustedAt.set(transition.operatorId, time)
      leftAt.set(transition.operatorId, time)
      leaveReason.set(
        transition.operatorId,
        triggerIds.has(transition.operatorId) ? 'morale-exhausted' : 'group-sync',
      )
      if (transition.replacementOperatorId) {
        const replacementName = OPERATOR_MAP.get(transition.replacementOperatorId)?.name ?? transition.replacementOperatorId
        const operatorName = OPERATOR_MAP.get(transition.operatorId)?.name ?? transition.operatorId
        if (
          time >= warmupHours &&
          (roomShiftDetails[transition.roomId]?.length ?? 0) < 12
        ) {
          roomShiftDetails[transition.roomId]?.push(
            `${operatorName} → ${replacementName}：统计期第 ${(time - warmupHours).toFixed(1)} 小时交接`,
          )
        }
        if ((morale.get(transition.replacementOperatorId) ?? 0) > 0) {
          startedAt.set(transition.replacementOperatorId, time)
        }
      }
    }
  }

  while (true) {
    const zeroIds = new Set(
      [...roster.activeOperatorIds()].filter(
        (id) => leavesAtZeroMorale(id, config) && (morale.get(id) ?? 0) <= 1e-9,
      ),
    )
    if (!zeroIds.size) break
    applyDepartures(zeroIds, 0)
  }

  while (elapsed < totalHours - 1e-9) {
    roster.fillVacancies((id) => (morale.get(id) ?? 0) >= 24 - 1e-8)
    const runtimeConfig = roster.currentConfig()
    const all = assignments(runtimeConfig)
    const currentActiveIds = activeIds()
    let snapshot = computeRates(runtimeConfig, all, currentActiveIds, morale)
    recordSnapshot(snapshot, currentActiveIds)
    if (nudgeBoundaryCrossings(all, currentActiveIds, morale, snapshot.rates)) {
      snapshot = computeRates(runtimeConfig, all, currentActiveIds, morale)
      recordSnapshot(snapshot, currentActiveIds)
    }
    const rates = snapshot.rates
    let duration = Math.min(totalHours - elapsed, nextBoundaryDuration(all, currentActiveIds, morale, rates))
    for (const id of currentActiveIds) {
      if (!morale.has(id)) continue
      const rate = rates.get(id) ?? 1
      if (rate > 0) duration = Math.min(duration, (morale.get(id) ?? 0) / rate)
    }
    if (roster.hasVacancies() && recoveryPerHour > 0) {
      for (const id of roster.inactiveOperatorIds()) {
        const remaining = 24 - (morale.get(id) ?? 0)
        if (remaining > 1e-8) duration = Math.min(duration, remaining / recoveryPerHour)
      }
    }
    if (!Number.isFinite(duration)) duration = totalHours - elapsed
    if (duration <= 1e-9) {
      const zeroIds = new Set(
        [...roster.activeOperatorIds()].filter(
          (id) => leavesAtZeroMorale(id, config) && (morale.get(id) ?? 0) <= 1e-9,
        ),
      )
      if (zeroIds.size) applyDepartures(zeroIds, elapsed)
      else break
      continue
    }

    const globalContext = buildRiicGlobalContext(runtimeConfig, currentActiveIds, morale)
    const measuredDuration = Math.max(
      0,
      Math.min(elapsed + duration, totalHours) - Math.max(elapsed, warmupHours),
    )
    for (const room of runtimeConfig.rooms) {
      efficiencyTotals[room.id] = (efficiencyTotals[room.id] ?? 0) +
        evaluateOperators(room, runtimeConfig, currentActiveIds, morale, globalContext).efficiencyPercent * measuredDuration
    }
    powerBonusTotal += runtimeConfig.rooms
      .filter((room) => room.type === 'power')
      .reduce((sum, room) =>
        sum + evaluateOperators(room, runtimeConfig, currentActiveIds, morale, globalContext).efficiencyPercent - 100,
      0) * measuredDuration

    for (const id of currentActiveIds) {
      if (!morale.has(id)) continue
      const rate = rates.get(id) ?? 1
      morale.set(id, Math.max(0, Math.min(24, (morale.get(id) ?? 0) - rate * duration)))
    }
    for (const id of roster.inactiveOperatorIds()) {
      morale.set(id, Math.min(24, (morale.get(id) ?? 0) + recoveryPerHour * duration))
    }
    elapsed += duration
    const zeroIds = new Set(
      [...roster.activeOperatorIds()].filter(
        (id) => leavesAtZeroMorale(id, config) && (morale.get(id) ?? 0) <= 1e-8,
      ),
    )
    if (zeroIds.size) applyDepartures(zeroIds, elapsed)
  }

  return {
    averageEfficiencyPercent: Object.fromEntries(
      Object.entries(efficiencyTotals).map(([roomId, total]) => [roomId, total / sampleHours]),
    ),
    averagePowerBonusPercent: powerBonusTotal / sampleHours,
    roomShiftDetails,
    operators: roster.participants.map((participant) => {
      const id = participant.operatorId
      const group = participant.role === 'primary' ? groupSchedule.groupByOperator.get(id) : undefined
      const details = [...(firstDetails.get(id) ?? [])]
      if (participant.role === 'backup' && participant.replacesOperatorId) {
        const primaryName = OPERATOR_MAP.get(participant.replacesOperatorId)?.name ?? participant.replacesOperatorId
        details.unshift(`替补关系：接替 ${primaryName} 离开后的 ${participant.roomId} 工位`)
      }
      if (group) details.unshift(`组合「${group.name}」：预测起点同步进驻，任一成员耗尽时全组离开`)
      return {
        operatorId: id,
        operatorName: OPERATOR_MAP.get(id)?.name ?? id,
        roomId: participant.roomId,
        role: participant.role,
        replacesOperatorId: participant.replacesOperatorId,
        startedAt: startedAt.get(id) ?? null,
        initial: initialMorale.get(id) ?? 24,
        ending: morale.get(id) ?? 0,
        initialConsumptionPerHour: firstRates.get(id) ?? 0,
        exhaustedAt: exhaustedAt.get(id) ?? null,
        leftAt: leftAt.get(id) ?? null,
        leaveReason: leaveReason.get(id) ?? null,
        groupName: group?.name ?? null,
        details,
      }
    }),
  }
}
