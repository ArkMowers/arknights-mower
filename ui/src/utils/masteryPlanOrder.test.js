import { describe, expect, it } from 'vitest'
import { interleaveMasteryPlans, masteryAssistants } from './masteryPlanOrder'

const plan = (key, assistant, status = 'idle', charId = key) => ({
  key,
  char_id: charId,
  support_plan: { stages: [{ level: 1, operator: assistant }] },
  status
})
const keys = (entries) => entries.map((entry) => entry.key)

describe('interleaveMasteryPlans', () => {
  it('keeps one operator together and separates different operators of the same assistant', () => {
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

  it('ignores professions and includes a shared swap assistant', () => {
    const entries = [plan('a', 'x'), plan('b', 'y'), plan('c', 'z')]
    entries[0].support_plan.stages[0].swap_target = 'y'
    entries[0].profession = 'CASTER'
    entries[1].profession = 'MEDIC'
    entries[2].profession = 'CASTER'
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['a', 'c', 'b'])
  })

  it('unions assistants across one operator and prefers fewer overlaps when unavoidable', () => {
    const entries = [
      plan('active', 'x', 'training', 'a'),
      plan('a2', 'y', 'idle', 'a'),
      plan('b', 'x'),
      plan('c', 'x')
    ]
    entries[2].support_plan.stages[0].swap_target = 'y'
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'a2', 'c', 'b'])
  })

  it('uses the effective runtime and excludes past and out-of-target stages', () => {
    const entry = plan('a', 'past')
    entry.support_plan.stages.push({ level: 2, operator: 'old' }, { level: 3, operator: 'future' })
    entry.support_runtime = { level: 2, operator: 'current', swap_target: 'swap' }
    entry.target_level = 2
    expect([...masteryAssistants(entry)]).toEqual(['current', 'swap'])
  })

  it('does not apply the previous skill carry record to the new skill stages', () => {
    const entry = plan('a', 'planned')
    entry.support_runtime = { level: 3, operator: 'previous', carry_from_skill: 0 }
    expect([...masteryAssistants(entry)]).toEqual(['planned'])
  })

  it('keeps plans without assistant data stable', () => {
    const entries = [
      { key: 'a', char_id: 'a', status: 'idle' },
      { key: 'b', char_id: 'b', status: 'idle' }
    ]
    expect(interleaveMasteryPlans(entries)).toEqual(entries)
  })

  it('uses the active assistant as the first gap and leaves failed plans last', () => {
    const entries = [
      plan('a1', 'WARRIOR', 'idle', 'a'),
      plan('active', 'WARRIOR', 'training', 'a'),
      plan('b1', 'SNIPER'),
      plan('failed', 'MEDIC', 'failed')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'a1', 'b1', 'failed'])
  })

  it('starts with a different assistant after the active operator when available', () => {
    const entries = [
      plan('active', 'WARRIOR', 'training'),
      plan('a1', 'WARRIOR'),
      plan('b1', 'SNIPER')
    ]
    expect(keys(interleaveMasteryPlans(entries))).toEqual(['active', 'b1', 'a1'])
  })

  it('places the unavoidable same-assistant plans together only after alternatives run out', () => {
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
