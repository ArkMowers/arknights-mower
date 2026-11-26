import { createDefaultConfig, createRoom } from './vendor/domain/defaults'
import { OPERATORS, type OperatorRecord } from './vendor/domain/operators'
import type { AppConfig } from './vendor/domain/types'
import { selectUnlockedSkills } from './vendor/domain/operatorInventory'
import { currentMoraleRates } from './vendor/engine/morale'
import { evaluateDormitoryRecovery } from './vendor/engine/dormitoryRecovery'
import { buildRiicGlobalContext, type RiicGlobalContext } from './vendor/engine/globalContext'
import { eligibleSingleRecoveryTargets, hasSingleRecoverySkill } from './vendor/engine/singleRecoveryEligibility'
import { MORALE_SKILL_THRESHOLDS, MORALE_RATE_EPSILON } from './vendor/engine/moraleThresholds'
import { importMowerJson } from './vendor/workbench/compat/mowerJson'

const byName = new Map(OPERATORS.map(operator => [operator.name, operator]))

type AutomaticTarget = { room: string; target: string; providerPosition: string; targetPosition: string }
type DormitoryInput = {
  rooms: Record<string, { singleRecipient?: string }>
  singleTargets?: Record<string, string>
  automaticTargets?: Record<string, AutomaticTarget>
  versions?: Record<string, number>
}

// The shared evaluator also reads self and room-wide effects from these skills.
// Omit only their ordinary single-target clause when evaluating an inactive source.
function withoutOrdinaryBonus(operator: OperatorRecord): OperatorRecord {
  return {
    ...operator,
    skills: operator.skills.map(skill => {
      if (skill.roomType !== 'DORMITORY') return skill
      const description = skill.description.replace(/某个干员(?:的心情)?每小时恢复\+[\d.]+.*?(?=[；，]同时|$)/, '')
      return description === skill.description ? skill : { ...skill, description }
    }),
  }
}

function automaticRoomRecipient(
  occupants: OperatorRecord[], providers: OperatorRecord[], room: string,
  previous: Record<string, AutomaticTarget>, position: (id: string) => string, mood: (id: string) => number,
) {
  const eligible = new Set<string>()
  const retained = new Set<string>()
  for (const provider of providers) {
    const cached = previous[provider.charId]
    const sameBeds = cached?.room === room && cached.providerPosition === position(provider.charId)
      && cached.targetPosition === position(cached.target)
    const candidates = eligibleSingleRecoveryTargets(occupants, provider.charId, id => {
      const value = mood(id)
      // A missing baseline alone cannot release a previously occupied single-target slot.
      return sameBeds && id === cached.target && Number.isNaN(value) ? 0 : value
    })
    for (const { charId } of candidates) {
      if (sameBeds && cached.target === charId) retained.add(charId)
      if (Number.isFinite(mood(charId))) eligible.add(charId)
    }
  }
  if (retained.size === 1) return [...retained][0]
  const ids = occupants.map(op => op.charId).filter(id => eligible.has(id))
  return ids.sort((a, b) => mood(a) - mood(b))[0]
}

function dormitoryRates(
  config: AppConfig, index: number, values: Map<string, number>, context: RiicGlobalContext,
  input: DormitoryInput, automaticTargets: Record<string, AutomaticTarget>, unknown: Set<string>,
) {
  const room = `dormitory_${index + 1}`
  const records = config.operatorRecords!
  const occupants = config.facilityOperatorIds.dormitories[index].map(id => records[id])
  const providers = occupants.filter(hasSingleRecoverySkill)
  const mood = (id: string) => values.get(id) ?? Number.NaN
  const position = (id: string) => {
    const slot = occupants.findIndex(operator => operator.charId === id)
    return `${room}:${slot}:${input.versions?.[occupants[slot]?.name] ?? 0}`
  }
  const candidates = occupants.filter(operator => {
    const value = mood(operator.charId)
    return (Number.isNaN(value) || value < 24 - MORALE_RATE_EPSILON)
      && !operator.skills.some(skill => skill.buffId === 'dorm_recExcludeOther[000]')
      && providers.some(provider => provider !== operator)
  })
  const observed = candidates.find(operator => operator.name === input.rooms[room].singleRecipient)
  const observedTargets = new Set(providers.map(provider =>
    candidates.find(operator => operator !== provider && operator.name === input.singleTargets?.[provider.name])?.charId,
  ).filter((id): id is string => id !== undefined))
  const target = observed?.charId ?? (observedTargets.size === 1 ? [...observedTargets][0] : undefined)

  const evaluate = (scenario: AppConfig, targets?: ReadonlyMap<string, string>, moods = values) =>
    evaluateDormitoryRecovery(scenario, index, moods, config.facilities.dormitories[index] * 1000, targets, false, context)
  if (!providers.length || !candidates.length) return evaluate(config)

  const recipient = target ?? automaticRoomRecipient(occupants, providers, room, input.automaticTargets ?? {}, position, mood)
  if (!recipient) return evaluate(config)
  const possibleSources = providers.filter(provider => provider.charId !== recipient)
  const knownSources = target ? possibleSources.filter(provider => input.singleTargets?.[provider.name] === records[target].name) : []
  const sources = knownSources.length ? knownSources : possibleSources
  if (!target) {
    for (const provider of sources) {
      automaticTargets[provider.charId] = {
        room, target: recipient, providerPosition: position(provider.charId), targetPosition: position(recipient),
      }
    }
  }
  const targets = new Map(sources.map(source => [source.charId, recipient]))
  if (providers.length === 1 && Number.isFinite(mood(recipient))) return evaluate(config, targets)
  const inactive = { ...records }
  for (const provider of providers) inactive[provider.charId] = withoutOrdinaryBonus(provider)
  if (!Number.isFinite(mood(recipient))) {
    // Count the unfinished recipient for shared effects. Only residents with a baseline publish a rate.
    return evaluate({ ...config, operatorRecords: inactive }, undefined, new Map(values).set(recipient, 0))
  }

  // Compare the full room rate with each possible source supplying its ordinary bonus alone.
  const scenarios = sources.map(provider => evaluate(
    { ...config, operatorRecords: { ...inactive, [provider.charId]: provider } }, targets,
  ))
  const warnings = new Set(scenarios.flatMap(result => result.unquantified))
  if (scenarios.some(result => result.rates.get(recipient) !== scenarios[0].rates.get(recipient))) {
    unknown.add(recipient)
    warnings.add(`${records[recipient].name}的单回来源尚未确定，可能的恢复速率不同`)
  }
  return { ...scenarios[0], unquantified: [...warnings] }
}

// 共享运行时仅接收 JSON；嵌入式引擎没有浏览器的克隆 API。
if (typeof globalThis.structuredClone !== 'function') {
  globalThis.structuredClone = value => JSON.parse(JSON.stringify(value))
}

/** The backend supplies observed positions; the income engine owns all skill rules. */
export function rates(input: any) {
  const config = createDefaultConfig()
  config.rooms = []
  config.controlOperatorIds = []
  config.facilityOperatorIds.dormitories = [[], [], [], []]
  config.facilities.dormitories = [0, 0, 0, 0]
  Object.assign(config.facilities, { central: 0, office: 0, reception: 0, workshop: 0, training: 0, recycle: 0 })
  config.operatorRecords = {}
  const participants = new Set<string>(Object.keys(input.moods))
  for (const room of Object.values(input.rooms) as any[]) {
    room.roster.forEach((name: string) => participants.add(name))
  }
  for (const name of participants) {
    const operator = byName.get(name)
    if (!operator) continue
    const stage = input.stages?.[name]
    config.operatorRecords[operator.charId] = stage
      ? { ...operator, skills: selectUnlockedSkills(operator, stage[0], stage[1]) }
      : operator
    config.operatorMorale[operator.charId] = Number.NaN
  }
  const names = new Map<string, string>()
  for (const [name, mood] of Object.entries(input.moods)) {
    const operator = byName.get(name)
    if (!operator || typeof mood !== 'number') continue
    names.set(operator.charId, name)
    config.operatorMorale[operator.charId] = mood
  }
  const ids = (roster: string[]) => roster.map(name => byName.get(name)?.charId).filter(Boolean) as string[]
  const unknown = new Set<string>()
  for (const [key, room] of Object.entries(input.rooms) as [string, any][]) {
    const roster = ids(room.roster)
    if (key === 'central') {
      config.controlOperatorIds = roster
      config.facilities.central = room.level ?? 5
    }
    else if (key.startsWith('dormitory_')) {
      const index = Number(key.split('_')[1]) - 1
      config.facilityOperatorIds.dormitories[index] = roster
      config.facilities.dormitories[index] = room.level ?? 5
    } else if (['meeting', 'contact', 'recycle', 'train', 'factory'].includes(key)) {
      const mapped = { meeting: 'reception', contact: 'office', recycle: 'recycle', train: 'training', factory: 'workshop' }[key]!
      ;(config.facilityOperatorIds as any)[mapped] = roster
      ;(config.facilities as any)[mapped] = room.level ?? 3
    } else {
      const type = ({ '制造站': 'manufacture', '贸易站': 'trading', '发电站': 'power', trade: 'trading' } as Record<string, string>)[room.facility] ?? room.facility
      if (!['manufacture', 'trading', 'power'].includes(type)) {
        roster.forEach(id => unknown.add(id))
        continue
      }
      const output = createRoom(key, type)
      Object.assign(output, { operatorIds: roster, operatorCount: roster.length, level: room.level ?? 3, product: room.product ?? 'gold' })
      config.rooms.push(output)
    }
  }
  config.dormitoryOccupantCount = config.facilityOperatorIds.dormitories.flat().length
  config.efficiencyResources.trainingOperatorIds = [...config.facilityOperatorIds.training]
  const resting = new Set(config.facilityOperatorIds.dormitories.flat())
  config.zeroMoraleOperatorIds = Object.entries(config.operatorMorale).filter(([id, mood]) => !resting.has(id) && mood <= 0).map(([id]) => id)
  let result = currentMoraleRates(config)
  let adjusted = false
  for (const [id, mood] of Object.entries(config.operatorMorale)) {
    if (MORALE_SKILL_THRESHOLDS.some(threshold => Math.abs(mood - threshold) < MORALE_RATE_EPSILON)) {
      const updated = mood + (resting.has(id) ? 1 : -Math.sign(result.rates[id] ?? 0)) * MORALE_RATE_EPSILON * 2
      config.operatorMorale[id] = updated
      adjusted ||= updated !== mood
    }
  }
  if (adjusted) result = currentMoraleRates(config)
  const values = new Map(Object.entries(config.operatorMorale))
  const automaticTargets: Record<string, AutomaticTarget> = {}
  let recoveryContext: RiicGlobalContext | undefined
  for (let index = 0; index < 4; index++) {
    if (!config.facilities.dormitories[index]) continue
    recoveryContext ??= buildRiicGlobalContext(config, undefined, values)
    const recovery = dormitoryRates(config, index, values, recoveryContext, input, automaticTargets, unknown)
    for (const [id, rate] of recovery.rates) result.rates[id] = -rate
    result.unquantified.push(...recovery.unquantified)
  }
  return {
    rates: Object.fromEntries([...names].map(([id, name]) => [name, unknown.has(id) ? null : result.rates[id] ?? 0])),
    unquantified: result.unquantified,
    thresholds: [0, ...MORALE_SKILL_THRESHOLDS, 24],
    automaticTargets,
  }
}

;(globalThis as any).mowerMoodRates = (payload: string) => JSON.stringify(rates(JSON.parse(payload)))
;(globalThis as any).mowerFacilityLevels = (payload: string) => JSON.stringify(Object.fromEntries(
  Object.entries(importMowerJson(payload).mainPlan.facilities).map(([room, facility]) => [room, facility.level]),
))
