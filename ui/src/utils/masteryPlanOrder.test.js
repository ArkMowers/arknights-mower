import { describe, expect, it } from 'vitest'
import { interleaveMasteryPlans } from './masteryPlanOrder'

const plan = (key, profession, status = 'idle') => ({ key, char_id: key, profession, status })
const keys = (entries) => entries.map((entry) => entry.key)

describe('interleaveMasteryPlans', () => {
  it('separates skills of the same profession while preserving their relative order', () => {
    const entries = [
      plan('a1', 'WARRIOR'),
      plan('a2', 'WARRIOR'),
      plan('a3', 'WARRIOR'),
      plan('b1', 'SNIPER'),
      plan('b2', 'SNIPER'),
      plan('c1', 'MEDIC')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['a1', 'b1', 'a2', 'b2', 'a3', 'c1'])
    expect(keys(entries)).toEqual(['a1', 'a2', 'a3', 'b1', 'b2', 'c1'])
  })

  it('uses the active profession as the first gap and leaves failed plans last', () => {
    const entries = [
      plan('a1', 'WARRIOR'),
      plan('active', 'WARRIOR', 'training'),
      plan('b1', 'SNIPER'),
      plan('failed', 'MEDIC', 'failed')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'b1', 'a1', 'failed'])
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
