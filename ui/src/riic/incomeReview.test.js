import { describe, expect, it } from 'vitest'
import { createIncomeReview } from './incomeReview'

function fixture() {
  return {
    savedAt: 1234,
    snapshot: { label: '原排班' },
    input: {
      plan: {
        default: 'plan1',
        conf: { exhaust_require: ['芬'] },
        advanced_settings: { drone_room: 'room_1_1' },
        backup_plans: [{ name: '原副表', trigger: 'gold < 10' }],
        plan1: { room_1_1: { plans: [{ agent: '芬', group: 'A', replacement: ['香草'] }] } }
      },
      settings: {
        warmupDays: 3,
        sampleDays: 28,
        operatorMode: 'cache',
        inventorySource: 'manual',
        initialInventory: { gold: 17 },
        seed: null,
        cachedOperators: [{ name: '芬', phase: null, level: null }]
      }
    },
    result: {
      success: true,
      modelProvenance: { calculatorBaseRevision: 'recorded-source' },
      simulationReport: {
        engine: 'mower-morale-v1',
        schemaVersion: 1,
        observedHours: 672,
        elapsedHours: 744,
        assumptions: { warmupHours: 72 },
        operators: [
          {
            operatorId: 'fang',
            operatorName: '芬',
            workHours: 10,
            mainWorkHours: 8,
            substituteWorkHours: 2,
            restHours: 0,
            idleHours: 660,
            exhaustedHours: 2,
            workRestRatio: null,
            workFraction: 10 / 672,
            finalMorale: 0
          }
        ],
        shiftDeferrals: [{ key: 'A', operatorIds: ['fang'], blockedAt: 73.25 }],
        events: [
          { type: 'shift-on', time: 73, operators: ['fang'] },
          { type: 'shift-off', time: 75, operators: ['unrelated'] }
        ]
      }
    }
  }
}
function rows(file) {
  return file.text
    .split('\n')
    .slice(3)
    .map((line) => JSON.parse(line))
}
function allText(draft) {
  return draft.files.map((file) => file.text).join('\n')
}

describe('income review materials', () => {
  it('preserves the successful source, original plan, raw hours, null ratio and unknown growth', () => {
    const record = fixture()
    const draft = createIncomeReview(record)
    expect(draft.files).toHaveLength(4)
    expect(rows(draft.files[1])).toEqual([{ path: '/input/plan', value: record.input.plan }])
    expect(
      rows(draft.files[2]).find((row) => row.path === '/simulationReport/operators').value
    ).toEqual(record.result.simulationReport.operators[0])
    const text = allText(draft)
    expect(text).toContain('recorded-source')
    expect(text).toContain('"blockedAt":73.25')
    expect(text).toContain('"time":73')
    expect(text).not.toContain('unrelated')
    expect(text).toContain('"phase":null')
    expect(text).toContain('"workRestRatio":null')
    expect(text).toContain('不能据此认定期末死锁')
    expect(text).toContain('不含 exhaustedHours')
    expect(draft.text).toContain('不要从零生成排班')
    expect(draft.text).toContain('已拥有')
    record.input.plan.conf.exhaust_require.push('当前编辑')
    expect(allText(draft)).not.toContain('当前编辑')
  })
  it('keeps old provenance and missing reports unknown', () => {
    const record = fixture()
    delete record.result.modelProvenance
    delete record.result.simulationReport
    const text = allText(createIncomeReview(record))
    expect(text).toContain('"modelProvenance":null')
    expect(text).toContain('"reportAvailable":false')
    expect(text).toContain('"engine":null')
  })
  it('caps large reports with whole JSON records and explicit omission counts', () => {
    const record = fixture()
    record.input.plan.backup_plans = Array.from({ length: 100 }, (_, i) => ({
      name: `副表${i}`,
      text: '长'.repeat(1000)
    }))
    record.result.simulationReport.operators = Array.from({ length: 500 }, (_, i) => ({
      operatorId: String(i),
      exhaustedHours: i,
      workRestRatio: null,
      workHours: 0,
      restHours: 0
    }))
    record.result.simulationReport.events = Array.from({ length: 100 }, (_, i) => ({
      type: 'shift-off',
      time: i,
      operators: ['1']
    }))
    const draft = createIncomeReview(record)
    for (const file of draft.files) {
      expect(file.text.length).toBeLessThanOrEqual(6000)
      expect(() => rows(file)).not.toThrow()
    }
    expect(draft.files[1].coverage.plan.omittedRecords).toBeGreaterThan(0)
    expect(draft.files[2].coverage.operators.omittedRecords).toBeGreaterThan(0)
    expect(
      rows(draft.files[2]).find((row) => row.path === '/simulationReport/operators').value
        .operatorId
    ).toBe('499')
    expect(allText(draft)).toContain('"omittedBeforePacking":76')
  })
  it('requires successful input and result together', () => {
    expect(() => createIncomeReview({ result: { success: false } })).toThrow('成功演算')
  })
})

it('retains income, resource flows and coverage with a typical large roster', () => {
  const record = fixture()
  const base = record.result.simulationReport.operators[0]
  record.result.simulationReport.operators = Array.from({ length: 80 }, (_, i) => ({
    ...base,
    operatorId: String(i),
    operatorName: `干员${i}`
  }))
  record.result.summary = { totalScore82: 12345, netLmd: 5000 }
  record.result.resources = {
    opening: { gold: 5 },
    inflows: { gold: 20 },
    outflows: { gold: 10 },
    closing: { gold: 15 }
  }
  record.result.diagnostics = Array.from({ length: 100 }, (_, i) => ({
    code: `D${i}`,
    message: '观察'.repeat(100)
  }))
  record.result.simulationReport.events = Array.from({ length: 100 }, (_, i) => ({
    time: i,
    operators: ['0'],
    type: 'shift-off'
  }))
  record.result.simulationReport.segments = [
    { start: 75, end: 76, occupants: { room_1_1_0: '0' }, bedOccupants: {}, morale: { 0: 0 } }
  ]
  const draft = createIncomeReview(record)
  const text = allText(draft)
  expect(text).toContain('"netLmd":5000')
  expect(text).toContain('"closing":{"gold":15}')
  expect(draft.files[2].coverage.operators.omittedRecords).toBeGreaterThan(0)
  const header = JSON.parse(draft.files[3].text.split('\n')[2])
  expect(header.selection.events.relatedEvents).toBe(100)
  expect(header.selection.events.omittedBeforePacking).toBe(76)
  expect(header.selection.segments.candidateSegments).toBe(1)
  expect(header.coverage.relatedEvents.includedRecords).toBeGreaterThan(0)
  expect(text).toContain('"morale":{"0":0}')
  for (const file of draft.files) expect(file.text.length).toBeLessThanOrEqual(6000)
})

it('prioritizes sampled events nearest deferrals and keeps only observed segment facts', () => {
  const record = fixture()
  record.result.simulationReport.events = Array.from({ length: 100 }, (_, time) => ({
    time,
    operators: ['fang'],
    type: 'shift-off'
  }))
  record.result.simulationReport.segments = [
    {
      start: 70,
      end: 71,
      occupants: { room_1_1_0: 'fang' },
      bedOccupants: {},
      morale: { fang: 0 }
    },
    {
      start: 74,
      end: 75,
      occupants: { room_1_1_0: 'fang', room_1_1_1: 'other' },
      bedOccupants: { dorm_0: 'other' },
      morale: { fang: 0, other: 20 }
    },
    { start: 75, end: 76, occupants: { room_1_1_0: 'fang' }, bedOccupants: {}, morale: { fang: 1 } }
  ]
  const observations = createIncomeReview(record).files[3]
  const selected = rows(observations)
  const events = selected
    .filter((row) => row.path === '/simulationReport/events')
    .map((row) => row.value)
  expect(events[0].time).toBe(73)
  expect(events.every((event) => event.time >= 72)).toBe(true)
  const segment = selected.find((row) => row.path === '/simulationReport/segments/selected').value
  expect(segment).toEqual({
    start: 74,
    end: 75,
    occupants: { room_1_1_0: 'fang' },
    bedOccupants: {},
    morale: { fang: 0 }
  })
  expect(observations.text).toContain('morale is at segment start')
})
