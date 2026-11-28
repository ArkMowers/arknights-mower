import { describe, expect, it } from 'vitest'
import catalog from '../../../arknights_mower/data/riic/operators.json'
import { OPERATORS, OPERATOR_MAP, GAME_DATA_VERSION } from './vendor/domain/operators'
import { selectUnlockedSkills } from './vendor/domain/operatorInventory'

describe('shared operator catalog', () => {
  it('exposes operator identity and keeps only complete skill slots in the shared file', () => {
    expect(GAME_DATA_VERSION).toBe(catalog.sourceVersion)
    expect(OPERATOR_MAP.get('char_002_amiya')).toMatchObject({
      name: '阿米娅',
      rarity: 5,
      profession: 'CASTER',
      isAlter: false
    })
    expect(catalog.operators.every((operator) => !Object.hasOwn(operator, 'skills'))).toBe(true)
  })

  it('derives maximum skills without sharing their mutable objects with stage history', () => {
    const operator = OPERATORS.find((operator) => operator.name === '阿米娅')
    expect(selectUnlockedSkills(operator, 0, 1).map((skill) => skill.unlockPhase)).toEqual([0])
    expect(selectUnlockedSkills(operator, 2, 80)).toEqual(operator.skills)
    operator.skills.forEach((skill, index) => {
      const slot = operator.skillSlots[index]
      expect(skill).toEqual(slot[slot.length - 1])
      expect(skill).not.toBe(slot[slot.length - 1])
    })
  })
})
