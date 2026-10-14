import { describe, expect, it } from 'vitest'
import { incomeWorkspace, defaultIncomeSettings, incomeRequest } from './income'
import { calculateIncome } from './incomeWorker'
import { incomeReportLines } from './incomeImage'
import { validateRosterWorkspace } from './vendor/workbench/validate'
import { prepareMowerBackupRoom } from './vendor/domain/mowerBackupFacilities'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'

const fixture = () => ({
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '芬', replacement: ['香草'] }] },
    room_1_3: { name: '发电站', plans: [] },
    dormitory_1: { name: '', plans: Array.from({ length: 5 }, () => ({ agent: 'Free' })) }
  }
})
const settings = () => ({
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  finiteInventory: false,
  weightMode: 'custom',
  warmupDays: 0,
  sampleDays: 2
})

describe('saved facility levels', () => {
  it('keeps explicit levels, empty built support rooms and original plan intact', () => {
    const plan = fixture()
    plan.facility_levels = {
      room_1_1: 1,
      room_1_3: 2,
      dormitory_1: 2,
      contact: 1,
      meeting: 0,
      train: 0,
      factory: 3,
      recycle: 3
    }
    const original = structuredClone(plan)
    const request = incomeRequest(plan, settings())
    const facilities = request.workspace.mainPlan.facilities
    expect(facilities.dormitory_1.level).toBe(2)
    expect(facilities.contact).toMatchObject({ level: 1, slots: [] })
    expect(validateRosterWorkspace(request.workspace).power).toEqual({
      generation: 130,
      consumption: 50,
      margin: 80,
      sufficient: true
    })
    expect(
      compileRosterSchedule(request.workspace).rooms.find((r) => r.roomId === 'dormitory_1').level
    ).toBe(2)
    expect(plan).toEqual(original)
    expect(incomeReportLines({}, settings(), original, '').join('\n')).toContain('dormitory_1=2')
  })

  it('defaults all unstaffed right-side buildings to level three and counts their power', () => {
    const plan = fixture()
    delete plan.plan1.dormitory_1
    const workspace = incomeWorkspace(plan)
    for (const room of ['meeting', 'factory', 'contact', 'train', 'recycle']) {
      expect(workspace.mainPlan.facilities[room]).toMatchObject({ level: 3, slots: [] })
    }
    expect(validateRosterWorkspace(workspace).power).toEqual({
      generation: 270,
      consumption: 250,
      margin: 20,
      sufficient: true
    })
    plan.facility_levels = { train: 1, contact: 0 }
    const changed = incomeWorkspace(plan)
    expect(changed.mainPlan.facilities.train.level).toBe(1)
    expect(changed.mainPlan.facilities.contact.level).toBe(0)
    expect(validateRosterWorkspace(changed).power.consumption).toBe(140)
  })

  it('uses explicit construction state when inferring remaining levels', () => {
    const plan = fixture()
    plan.plan1.room_2_3 = { name: '发电站', plans: [] }
    plan.plan1.room_3_3 = { name: '发电站', plans: [] }
    expect(incomeWorkspace(plan).mainPlan.facilities.dormitory_1.level).toBe(5)
    plan.facility_levels = { room_3_3: 0, room_1_1: 2 }
    const workspace = incomeWorkspace(plan)
    expect(workspace.mainPlan.facilities.dormitory_1.level).toBe(1)
    expect(workspace.mainPlan.facilities.room_1_1.level).toBe(2)
    expect(() => prepareMowerBackupRoom(workspace, 'room_1_1', 2)).toThrow()
  })

  it.each([
    ['dormitory_1', 6],
    ['contact', 4],
    ['room_1_1', 1.5],
    ['central', -1],
    ['contact', '2'],
    ['unknown', 1]
  ])('rejects invalid level %s=%s', (room, level) => {
    const plan = fixture()
    plan.facility_levels = { [room]: level }
    expect(() => incomeWorkspace(plan)).toThrow()
  })

  it('accepts equal power and reports deficits without erasing staffed rooms', () => {
    const plan = fixture()
    plan.facility_levels = {
      room_1_3: 1,
      room_1_1: 2,
      dormitory_1: 3,
      meeting: 0,
      contact: 0,
      train: 0,
      factory: 0
    }
    expect(validateRosterWorkspace(incomeWorkspace(plan)).power).toEqual({
      generation: 60,
      consumption: 60,
      margin: 0,
      sufficient: true
    })
    plan.facility_levels.dormitory_1 = 4
    const result = calculateIncome(plan, settings())
    expect(result.success).toBe(false)
    expect(JSON.stringify(result)).toContain('电力赤字')
    plan.facility_levels.room_1_1 = 0
    expect(incomeWorkspace(plan).mainPlan.facilities.room_1_1.slots).toHaveLength(1)
    expect(
      validateRosterWorkspace(incomeWorkspace(plan)).criticalErrors.some(
        (i) => i.code === 'INVALID_CONFIG'
      )
    ).toBe(true)
  })

  it('does not increase explicit backup levels or permit excess staffing', () => {
    const plan = fixture()
    plan.facility_levels = { contact: 1, recycle: 0, central: 1 }
    const workspace = incomeWorkspace(plan)
    expect(prepareMowerBackupRoom(workspace, 'contact', 1).level).toBe(1)
    expect(() => prepareMowerBackupRoom(workspace, 'recycle', 1)).toThrow()
    plan.plan1.central = { name: '', plans: [{ agent: '阿米娅' }, { agent: '杜宾' }] }
    expect(
      validateRosterWorkspace(incomeWorkspace(plan)).criticalErrors.some(
        (i) => i.code === 'SLOT_OVERFLOW'
      )
    ).toBe(true)
  })

  it.each([
    [1, 2],
    [5, 4]
  ])('uses level %s full ambience for actual recovery curve', (level, recovery) => {
    const plan = fixture()
    plan.plan1.room_2_3 = { name: '发电站', plans: [] }
    plan.facility_levels = { dormitory_1: level }
    const result = calculateIncome(plan, settings())
    expect(result.success, JSON.stringify(result)).toBe(true)
    const points = result.morale.find((r) => r.name === '芬').points
    const slopes = points.slice(1).flatMap(([x, y], i) => {
      const [previousX, previousY] = points[i]
      return x - previousX > 0.001 ? [(y - previousY) / (x - previousX)] : []
    })
    expect(slopes.some((rate) => Math.abs(rate - recovery) < 0.001)).toBe(true)
    expect(slopes.some((rate) => Math.abs(rate + 1) < 0.001)).toBe(true)
    expect(Math.max(...slopes)).toBeLessThanOrEqual(recovery + 0.001)
  })
})
