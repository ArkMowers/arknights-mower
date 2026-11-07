import { afterEach, describe, expect, it, vi } from 'vitest'
import * as morale from './vendor/engine/morale'
import * as globalContext from './vendor/engine/globalContext'
import { rates } from './runtimeMood'

afterEach(() => vi.restoreAllMocks())

function working(mood: number) {
  return {
    moods: { 阿米娅: mood, 桃金娘: 24 },
    rooms: {
      central: { roster: ['阿米娅'], level: 5 },
      room_1_1: { roster: ['桃金娘'], facility: 'trade', level: 3 },
    },
  }
}

describe('runtime mood preparation', () => {
  it('evaluates work rates once when no threshold adjustment changes mood', () => {
    const calculate = vi.spyOn(morale, 'currentMoraleRates')
    const prepare = vi.spyOn(globalContext, 'buildRiicGlobalContext')
    const input = working(13)
    const before = JSON.stringify(input)
    const result = rates(input)
    expect(result.rates['桃金娘']).toBeCloseTo(0.7)
    expect(calculate).toHaveBeenCalledTimes(1)
    expect(prepare).not.toHaveBeenCalled()
    expect(JSON.stringify(input)).toBe(before)
  })

  it('recalculates after a directional adjustment at a skill threshold', () => {
    const calculate = vi.spyOn(morale, 'currentMoraleRates')
    const input = working(12)
    const before = JSON.stringify(input)
    expect(rates(input).rates['桃金娘']).toBeCloseTo(0.7)
    expect(calculate).toHaveBeenCalledTimes(2)
    expect(JSON.stringify(input)).toBe(before)
  })

  it('keeps one evaluation for an unassigned operator with zero rate at a threshold', () => {
    const calculate = vi.spyOn(morale, 'currentMoraleRates')
    expect(rates({ moods: { 芬: 12 }, rooms: {} }).rates['芬']).toBe(0)
    expect(calculate).toHaveBeenCalledTimes(1)
  })

  it('shares one immutable global context across dormitories within each call', () => {
    const originalPrepare = globalContext.buildRiicGlobalContext
    const prepare = vi.spyOn(globalContext, 'buildRiicGlobalContext').mockImplementation((...args) => {
      const context = originalPrepare(...args)
      Object.freeze(context)
      Object.freeze(context.presentOperators)
      Object.freeze(context.effectivePowerStations)
      Object.freeze(context.silentResonance)
      return context
    })
    const input = {
      moods: Object.fromEntries(['流明', '芬', '纯烬艾雅法拉', '香草', '蜜莓', '桑葚', '承曦格雷伊'].map(name => [name, 10])),
      rooms: {
        dormitory_1: { roster: ['流明', '芬'], level: 5 },
        dormitory_2: { roster: ['纯烬艾雅法拉', '香草'], level: 5 },
        meeting: { roster: ['蜜莓', '桑葚'], level: 3 },
        room_1_1: { roster: ['承曦格雷伊'], facility: 'power', level: 3 },
      },
    }
    const before = JSON.stringify(input)
    const result = rates(input)
    expect(result.rates['芬']).toBeCloseTo(-4.25)
    expect(result.rates['香草']).toBeCloseTo(-4.18)
    expect(prepare).toHaveBeenCalledTimes(1)
    expect(JSON.stringify(input)).toBe(before)
    input.rooms.room_1_1.roster = []
    expect(rates(input).rates['芬']).toBeCloseTo(-4.2)
    expect(prepare).toHaveBeenCalledTimes(2)
  })
})
