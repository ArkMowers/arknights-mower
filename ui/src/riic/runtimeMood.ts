import { createDefaultConfig, createRoom } from './vendor/domain/defaults'
import { OPERATORS } from './vendor/domain/operators'
import { selectUnlockedSkills } from './vendor/domain/operatorInventory'
import { currentMoraleRates } from './vendor/engine/morale'
import { evaluateDormitoryRecovery } from './vendor/engine/dormitoryRecovery'
import { eligibleSingleRecoveryTargets, hasSingleRecoverySkill } from './vendor/engine/singleRecoveryEligibility'
import { MORALE_SKILL_THRESHOLDS, MORALE_RATE_EPSILON, retainedRecoveryTarget } from './vendor/engine/moraleThresholds'

const byName = new Map(OPERATORS.map(operator => [operator.name, operator]))

/** The backend supplies observed positions; the income engine owns all skill rules. */
export function rates(input: any) {
  const config = createDefaultConfig()
  config.rooms = []
  config.controlOperatorIds = []
  config.facilityOperatorIds.dormitories = [[], [], [], []]
  config.facilities.dormitories = [0, 0, 0, 0]
  Object.assign(config.facilities, { central: 0, office: 0, reception: 0, workshop: 0, training: 0, recycle: 0 })
  config.operatorRecords = {}
  for (const operator of OPERATORS) {
    const stage = input.stages?.[operator.name]
    config.operatorRecords[operator.charId] = { ...operator, skills: stage ? selectUnlockedSkills(operator, stage[0], stage[1]) : operator.skills }
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
  for (const [id, mood] of Object.entries(config.operatorMorale)) {
    if (MORALE_SKILL_THRESHOLDS.some(threshold => Math.abs(mood - threshold) < MORALE_RATE_EPSILON)) {
      config.operatorMorale[id] = mood + (resting.has(id) ? 1 : -Math.sign(result.rates[id] ?? 0)) * MORALE_RATE_EPSILON * 2
    }
  }
  result = currentMoraleRates(config)
  const values = new Map(Object.entries(config.operatorMorale))
  const targets = new Map<string, string>()
  for (const [provider, target] of Object.entries(input.singleTargets ?? {})) {
    const p = byName.get(provider), t = byName.get(target as string)
    if (p && t) targets.set(p.charId, t.charId)
  }
  const automaticTargets: Record<string, any> = {}
  for (let index = 0; index < 4; index++) {
    if (!config.facilities.dormitories[index]) continue
    const room = `dormitory_${index + 1}`
    const occupants = config.facilityOperatorIds.dormitories[index].map(id => config.operatorRecords![id]!)
    const position = (id: string) => `${room}:${occupants.findIndex(operator => operator.charId === id)}:${input.versions?.[names.get(id) ?? ''] ?? 0}`
    for (const provider of occupants) {
      if (!hasSingleRecoverySkill(provider)) continue
      const candidates = eligibleSingleRecoveryTargets(occupants, provider.charId, id => values.get(id) ?? Number.NaN).map(operator => operator.charId)
      if (!candidates.includes(targets.get(provider.charId)!)) {
        const target = retainedRecoveryTarget(candidates, input.automaticTargets?.[provider.charId], room, provider.charId, position, id => values.get(id) ?? Number.NaN)
        if (target) {
          targets.set(provider.charId, target)
          automaticTargets[provider.charId] = { room, target, providerPosition: position(provider.charId), targetPosition: position(target) }
        }
      }
    }
    const recovery = evaluateDormitoryRecovery(config, index, values, config.facilities.dormitories[index] * 1000, targets)
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
