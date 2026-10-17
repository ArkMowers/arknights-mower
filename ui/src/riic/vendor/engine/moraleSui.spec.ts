import { describe, expect, it } from 'vitest'
import { createDefaultConfig } from '../domain/defaults'
import { OPERATOR_MAP, OPERATORS } from '../domain/operators'
import { selectUnlockedSkills } from '../domain/operatorInventory'
import { currentMoraleRates, simulateMorale } from './morale'

const ling = 'char_2023_ling'
const dusk = 'char_2015_dusk'
const chongyue = 'char_2024_chyue'
const chen = 'char_010_chen'
const hoshiguma = 'char_136_hsguma'
const yato = 'char_502_nblade'
const aak = 'char_225_haak'
const suiNames = ['年', '夕', '令', '重岳', '黍', '余', '望']

function controlConfig(ids: string[]) {
  const config = createDefaultConfig()
  config.controlOperatorIds = ids
  return config
}

describe('Ling control-center Sui consumption', () => {
  it.each(suiNames)('keeps %s at 0.75 with Ling despite control skills', name => {
    const member = OPERATORS.find(op => op.name === name)!.charId
    const config = controlConfig([ling, member === ling ? yato : member, chen, hoshiguma, aak])
    const rates = currentMoraleRates(config).rates
    expect(rates[ling]).toBeCloseTo(0.75)
    expect(rates[member]).toBeCloseTo(0.75)
    expect(rates[chen]).toBeCloseTo(member === dusk ? 2.1 : 2.15)
    expect(rates[aak]).toBeCloseTo(member === dusk ? 2.1 : 2.15)
  })

  it('retains only staffing reduction in an incomplete control center', () => {
    const config = controlConfig([ling, chongyue, chen])
    expect(currentMoraleRates(config).rates[ling]).toBeCloseTo(0.85)
    expect(currentMoraleRates(config).rates[chongyue]).toBeCloseTo(0.85)
    expect(currentMoraleRates(config).rates[chen]).toBeCloseTo(0.8)
    config.facilities.dormitories = [1, 1, 1, 1]
    config.rooms.forEach(room => { room.level = 1 })
    expect(currentMoraleRates(config).rates[ling]).toBeCloseTo(0.85)
  })

  it('applies Cup Never Empty at elite zero level one', () => {
    const config = controlConfig([ling, dusk, chen, hoshiguma, yato])
    const original = OPERATOR_MAP.get(ling)!
    config.operatorRecords = { [ling]: { ...original, skills: selectUnlockedSkills(original, 0, 1) } }
    expect(config.operatorRecords[ling]!.skills.map(skill => skill.buffId)).toEqual(['control_facCostReset[000]'])
    expect(currentMoraleRates(config).rates[dusk]).toBeCloseTo(0.75)
    config.operatorRecords[ling]!.skills = []
    expect(currentMoraleRates(config).rates[dusk]).toBeCloseTo(1.1)
  })

  it('restores personal and room modifiers when Ling leaves control', () => {
    const config = controlConfig([ling, chongyue, chen, hoshiguma, yato])
    expect(currentMoraleRates(config).rates[chongyue]).toBeCloseTo(0.75)
    config.controlOperatorIds[0] = aak
    config.facilityOperatorIds.dormitories[0] = [ling]
    expect(currentMoraleRates(config).rates[chongyue]).toBeCloseTo(2.65)
    config.facilityOperatorIds.dormitories[0] = []
    config.rooms[0]!.operatorIds = [ling]
    expect(currentMoraleRates(config).rates[chongyue]).toBeCloseTo(2.65)
  })

  it('does not protect Sui working outside control', () => {
    const config = controlConfig([ling, chen, hoshiguma, yato, aak])
    const shu = 'char_2025_shu'
    config.rooms[0]!.operatorIds = [shu]
    expect(currentMoraleRates(config).rates[shu]).toBeCloseTo(0.65)
    config.controlOperatorIds[0] = dusk
    expect(currentMoraleRates(config).rates[shu]).toBeCloseTo(0.65)
  })

  it('keeps consumption constant across Ling and Dusk morale thresholds', () => {
    const config = controlConfig([ling, dusk, chen, hoshiguma, yato])
    config.hours = 24
    const result = simulateMorale(config)
    for (const id of [ling, dusk]) {
      const op = result.operators.find(op => op.operatorId === id)!
      expect(op.initialConsumptionPerHour).toBeCloseTo(0.75)
      expect(op.ending).toBeCloseTo(6)
      expect(op.exhaustedAt).toBeNull()
    }
  })
})
