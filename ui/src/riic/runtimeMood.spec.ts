import { afterEach, describe, expect, it, vi } from 'vitest'
import * as morale from './vendor/engine/morale'
import * as globalContext from './vendor/engine/globalContext'
import { OPERATORS } from './vendor/domain/operators'
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

function singleRoom(moods: Record<string, number>, recipient?: string) {
  return { moods, rooms: { dormitory_1: { roster: Object.keys(moods), level: 5, singleRecipient: recipient } } }
}

describe('one ordinary single-target bonus per dormitory', () => {
  const moods = { 安赛尔: 24, 琴柳: 24, 芬: 12, 香草: 4, 黑角: 24 }

  it('uses a confirmed provider without assigning a second bonus to the lowest-mood roommate', () => {
    const result = rates({ ...singleRoom(moods), singleTargets: { 安赛尔: '芬' } })
    expect(result.rates).toEqual({ 安赛尔: -4, 琴柳: -4, 芬: -4.55, 香草: -4, 黑角: -4 })
    expect(result.automaticTargets).toEqual({})
  })

  it('keeps a measured recipient independent of both an old target and source strength', () => {
    const room = singleRoom(moods, '芬')
    const predicted = rates(singleRoom(moods)).automaticTargets
    const input = { ...room, singleTargets: { 琴柳: '香草' }, automaticTargets: predicted }
    const result = rates(input)
    expect(result.rates).toEqual({ 安赛尔: -4, 琴柳: -4, 芬: null, 香草: -4, 黑角: -4 })
    expect(result.automaticTargets).toEqual({})
    expect(rates({ ...input, moods: { 安赛尔: 24, 琴柳: 24, 香草: 4 } }).rates['香草']).toBe(-4)
  })

  it('keeps one automatic recipient without choosing a provider by position or strength', () => {
    const input = singleRoom(moods)
    const correct = { 安赛尔: -4, 琴柳: -4, 芬: -4, 香草: null, 黑角: -4 }
    const first = rates(input)
    expect(first.rates).toEqual(correct)
    input.rooms.dormitory_1.roster.reverse()
    expect(rates(input).rates).toEqual(correct)
    const cached = { ...singleRoom(moods), automaticTargets: first.automaticTargets }
    expect(rates({ ...cached, moods: { 安赛尔: 24, 琴柳: 24, 芬: 12 } }).rates['芬']).toBe(-4)
    expect(rates({ ...cached, moods: { ...moods, 香草: 24 } }).rates['芬']).toBeNull()
  })

  it('evaluates each room independently at the same instant', () => {
    const first = singleRoom(moods, '芬')
    const result = rates({
      moods: { ...moods, 芙蓉: 24, 翎羽: 7 },
      rooms: { ...first.rooms, dormitory_2: { roster: ['芙蓉', '翎羽'], level: 5 } },
    })
    expect(result.rates['芬']).toBeNull()
    expect(result.rates['香草']).toBe(-4)
    expect(result.rates['翎羽']).toBeCloseTo(-4.55)
  })

  it.each([
    ['蓝毒', '芬', null], ['芬', '蓝毒', -4.55],
  ])('compares the actual directed bonus for %s', (recipient, other, expected) => {
    const input = singleRoom({ 深靛: 24, 安赛尔: 24, 蓝毒: 16, 芬: 12 }, String(recipient))
    const result = rates(input)
    expect(result.rates[String(recipient)]).toBe(expected)
    expect(result.rates[String(other)]).toBe(-4)
    expect(result.automaticTargets).toEqual({})
  })

  it('uses unlocked stages and keeps the group bonus from the same provider', () => {
    const input = singleRoom({ 波登可: 24, 安赛尔: 24, 芬: 12, 香草: 4 }, '芬')
    const base = rates({ ...input, stages: { 波登可: [0, 1] } })
    expect(base.rates['芬']).toBeCloseTo(-4.55)
    expect(base.rates['香草']).toBe(-4)
    const promoted = rates({ ...input, stages: { 波登可: [1, 1] } })
    expect(promoted.rates['芬']).toBeNull()
    expect(promoted.rates['香草']).toBeCloseTo(-4.15)
    expect(rates({ ...input, stages: { 波登可: [1, 1] }, singleTargets: { 安赛尔: '芬' } }).rates['芬']).toBeCloseTo(-4.7)
  })

  it('preserves self recovery and the fixed charger rate when the other source is confirmed', () => {
    const input = singleRoom({ 古米: 11, 安赛尔: 24, 芬: 12, 香草: 4, 菲亚梅塔: 1 }, '芬')
    const result = rates({ ...input, singleTargets: { 安赛尔: '芬' } })
    expect(result.rates).toEqual({ 古米: -4.35, 安赛尔: -4, 芬: -4.55, 香草: -4, 菲亚梅塔: -2 })
  })

  it('allows an observed skill-bearing recipient with other unfinished residents', () => {
    const input = singleRoom({ 断罪者: 15, 安赛尔: 12, 芬: 7, 菲亚梅塔: 1 }, '断罪者')
    expect(rates(input).rates).toEqual({ 断罪者: -4.55, 安赛尔: -4, 芬: -4, 菲亚梅塔: -2 })
  })

  it('keeps the equal share and compares effective rates for a sole unfinished resident', () => {
    const input = singleRoom({ 冰酿: 24, 安赛尔: 24, 琴柳: 24, 芬: 10, 香草: 24 }, '芬')
    expect(rates(input).rates['芬']).toBeCloseTo(-4.8)
    input.moods['香草'] = 10
    expect(rates(input).rates['芬']).toBeNull()
    expect(rates(input).rates['香草']).toBeCloseTo(-4.4)
    expect(rates({ ...input, moods: { 冰酿: 24, 安赛尔: 24, 琴柳: 24, 香草: 10 } }).rates['香草']).toBeCloseTo(-4.4)
  })

  it('merges conflicting cached predictions and retains the result only while positions are valid', () => {
    const input = singleRoom({ 安赛尔: 24, 芙蓉: 24, 芬: 12, 香草: 5 })
    const id = (name: string) => OPERATORS.find(operator => operator.name === name)!.charId
    const room = 'dormitory_1'
    const previous = {
      [id('安赛尔')]: { room, target: id('芬'), providerPosition: `${room}:0:0`, targetPosition: `${room}:2:0` },
      [id('芙蓉')]: { room, target: id('香草'), providerPosition: `${room}:1:0`, targetPosition: `${room}:3:0` },
    }
    const result = rates({ ...input, automaticTargets: previous })
    expect(result.rates['芬']).toBe(-4)
    expect(result.rates['香草']).toBeCloseTo(-4.55)
    expect(Object.values(result.automaticTargets).map(entry => entry.target)).toEqual([id('香草'), id('香草')])
    const crossed = { ...input, moods: { ...input.moods, 芬: 3 }, automaticTargets: result.automaticTargets }
    expect(rates(crossed).rates['香草']).toBeCloseTo(-4.55)
    expect(rates({ ...crossed, versions: { 香草: 1 } }).rates['芬']).toBeCloseTo(-4.55)
    expect(rates({ ...crossed, moods: { ...crossed.moods, 香草: 24 } }).rates['芬']).toBeCloseTo(-4.55)
  })
})
