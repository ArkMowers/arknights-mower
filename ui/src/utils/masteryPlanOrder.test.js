import { describe, expect, it } from 'vitest'
import { interleaveMasteryPlans } from './masteryPlanOrder'

const plan = (key, profession, status = 'idle', charId = key) => ({
  key,
  char_id: charId,
  profession,
  status
})
const keys = (entries) => entries.map((entry) => entry.key)

describe('interleaveMasteryPlans', () => {
  it('keeps one operator together and separates different operators of the same profession', () => {
    const entries = [
      plan('a1', 'WARRIOR', 'idle', 'a'),
      plan('a2', 'WARRIOR', 'idle', 'a'),
      plan('a3', 'WARRIOR'),
      plan('b1', 'SNIPER'),
      plan('b2', 'SNIPER'),
      plan('c1', 'MEDIC')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['a1', 'a2', 'b1', 'a3', 'b2', 'c1'])
    expect(keys(entries)).toEqual(['a1', 'a2', 'a3', 'b1', 'b2', 'c1'])
  })

  it('uses the active profession as the first gap and leaves failed plans last', () => {
    const entries = [
      plan('a1', 'WARRIOR', 'idle', 'a'),
      plan('active', 'WARRIOR', 'training', 'a'),
      plan('b1', 'SNIPER'),
      plan('failed', 'MEDIC', 'failed')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'a1', 'b1', 'failed'])
  })

  it('starts with a different profession after the active operator when available', () => {
    const entries = [
      plan('active', 'WARRIOR', 'training'),
      plan('a1', 'WARRIOR'),
      plan('b1', 'SNIPER')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'b1', 'a1'])
  })

  it('places the unavoidable same-profession plans together only after alternatives run out', () => {
    const entries = [
      plan('a1', 'WARRIOR'),
      plan('a2', 'WARRIOR'),
      plan('a3', 'WARRIOR'),
      plan('a4', 'WARRIOR'),
      plan('b1', 'SNIPER')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['a1', 'b1', 'a2', 'a3', 'a4'])
  })
})
