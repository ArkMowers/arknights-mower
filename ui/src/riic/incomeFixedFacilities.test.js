import { describe, expect, it } from 'vitest'
import { defaultIncomeSettings, incomeRequest } from './income'
import { calculateIncome } from './incomeWorker'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'

const fixedFacilities = [
  ['central', '中枢', 'central'],
  ['meeting', '会客室', 'meeting'],
  ['factory', '加工站', 'factory'],
  ['contact', '人力办公室', 'contact'],
  ['train', '训练室', 'train'],
  ...[1, 2, 3, 4].map((index) => [`dormitory_${index}`, '宿舍', 'dormitory'])
]
const settings = () => ({
  ...defaultIncomeSettings(),
  warmupDays: 0,
  sampleDays: 1,
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom'
})
function plan() {
  return {
    default: 'plan1',
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '杜林' }] },
      room_1_3: { name: '发电站', plans: [] },
      room_2_3: { name: '发电站', plans: [] },
      room_3_3: { name: '发电站', plans: [] },
      ...Object.fromEntries(
        fixedFacilities.map(([room, name]) => [
          room,
          { name, plans: room.startsWith('dormitory_') ? Array(5).fill({ agent: 'Free' }) : [] }
        ])
      )
    },
    conf: { workaholic: '杜林' },
    facility_levels: Object.fromEntries(
      fixedFacilities.map(([room]) => [room, room.startsWith('dormitory_') ? 1 : 3])
    ),
    backup_plans: []
  }
}
function withoutFixedNames(source) {
  const blank = structuredClone(source)
  for (const [room] of fixedFacilities) blank[blank.default.trim()][room].name = ''
  return blank
}

describe('income fixed facility names', () => {
  it('imports canonical Chinese names with the same schedule as empty names', () => {
    const source = plan()
    source.plan1.central.future_field = { value: 'preserved' }
    source.future_field = { value: 'root' }
    source.plan1.future_room = { name: '未知设施', plans: [] }
    const original = structuredClone(source)
    const named = incomeRequest(source, settings())
    const blank = incomeRequest(withoutFixedNames(source), settings())
    for (const [room, , type] of fixedFacilities)
      expect(named.workspace.mainPlan.facilities[room].type).toBe(type)
    expect(named).toEqual(blank)
    expect(compileRosterSchedule(named.workspace, named.options.simulationAssumptions)).toEqual(
      compileRosterSchedule(blank.workspace, blank.options.simulationAssumptions)
    )
    expect(named.workspace.compatibility.facilityMetadata.central.future_field).toEqual({
      value: 'preserved'
    })
    expect(named.workspace.compatibility.unrecognizedFields.future_field).toEqual({ value: 'root' })
    expect(named.workspace.compatibility.unrecognizedRooms.future_room).toEqual(
      source.plan1.future_room
    )
    expect(source).toEqual(original)
  })

  it('runs actual income calculation identically for named and unnamed fixed rooms', () => {
    const source = plan()
    const original = structuredClone(source)
    const named = calculateIncome(source, settings())
    const blank = calculateIncome(withoutFixedNames(source), settings())
    expect(named.success, JSON.stringify(named)).toBe(true)
    expect(blank.success, JSON.stringify(blank)).toBe(true)
    expect(named.summary).toEqual(blank.summary)
    expect(named.rooms).toEqual(blank.rooms)
    expect(named.simulationReport.events).toEqual(blank.simulationReport.events)
    expect(source).toEqual(original)
  })

  it('uses the selected main-plan key without changing other plans or backup definitions', () => {
    const source = plan()
    source.plan2 = source.plan1
    source.plan1 = { central: { name: '中枢', plans: [] } }
    source.default = ' plan2 '
    source.backup_plans = [{ name: '保留', trigger: { left: 'False' }, plan: source.plan1 }]
    const original = structuredClone(source)
    const request = incomeRequest(source, settings())
    expect(request.workspace.mainPlan.facilities.central.type).toBe('central')
    expect(request.workspace.compatibility.otherPlans.plan1).toEqual(source.plan1)
    expect(request.workspace.compatibility.backupPlans).toEqual(source.backup_plans)
    expect(source).toEqual(original)
  })

  it('keeps the already supported recycle name and its metadata', () => {
    const source = plan()
    source.plan1.recycle = { name: '回收站', plans: [], future_field: 'preserved' }
    source.facility_levels.recycle = 1
    const original = structuredClone(source)
    const named = incomeRequest(source, settings())
    const blankSource = structuredClone(source)
    blankSource.plan1.recycle.name = ''
    const blank = incomeRequest(blankSource, settings())
    expect(named.workspace.mainPlan.facilities.recycle).toEqual(
      blank.workspace.mainPlan.facilities.recycle
    )
    expect(named.workspace.mainPlan.facilities.recycle.type).toBe('recycle')
    expect(named.workspace.compatibility.facilityMetadata.recycle).toEqual({
      rawName: '回收站',
      future_field: 'preserved'
    })
    expect(source).toEqual(original)
  })

  it('keeps backup names intact while active backups retain fixed room semantics', () => {
    const source = plan()
    source.backup_plans = [
      {
        name: '固定设施',
        trigger: { left: 'True' },
        plan: Object.fromEntries(
          fixedFacilities.map(([room, name]) => [
            room,
            {
              name,
              plans: room.startsWith('dormitory_') ? Array(5).fill({ agent: 'Current' }) : [],
              future_field: 'preserved'
            }
          ])
        )
      }
    ]
    const original = structuredClone(source)
    const blankSource = withoutFixedNames(source)
    for (const facility of Object.values(blankSource.backup_plans[0].plan)) facility.name = ''
    const request = incomeRequest(source, settings())
    expect(request.workspace.compatibility.backupPlans).toEqual(source.backup_plans)
    const named = calculateIncome(source, settings())
    const blank = calculateIncome(blankSource, settings())
    expect(named.success, JSON.stringify(named)).toBe(true)
    expect(blank.success, JSON.stringify(blank)).toBe(true)
    expect(named.summary).toEqual(blank.summary)
    expect(named.simulationReport.events).toEqual(blank.simulationReport.events)
    expect(named.simulationReport.events.some((event) => event.type === 'backup-plan')).toBe(true)
    expect(source).toEqual(original)
  })

  it.each([
    ['central', '未知设施', ''],
    ['dormitory_1', '制造站', 'manufacture'],
    ['meeting', '中枢', '']
  ])('preserves a mismatched name for %s', (room, name, type) => {
    const source = plan()
    source.plan1[room].name = name
    const original = structuredClone(source)
    const request = incomeRequest(source, settings())
    expect(request.workspace.mainPlan.facilities[room].type).toBe(type)
    if (!type) expect(request.workspace.compatibility.facilityMetadata[room].rawName).toBe(name)
    expect(source).toEqual(original)
  })
})
