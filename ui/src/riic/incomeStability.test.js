import { expect, it } from 'vitest'
import { incomeStability } from './incomeStability'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'

it('splits crossing intervals by duration and excludes dormitory occupancy from work fractions', () => {
  const report = {
    assumptions: { warmupHours: 2 },
    elapsedHours: 10,
    segments: [
      {
        start: 2,
        end: 5,
        occupants: { room_1_1_0: 'A', dormitory_1_0: 'B' },
        efficiencyPercent: { room_1_1: 100 }
      },
      {
        start: 5,
        end: 8,
        occupants: { room_1_1_0: 'B', dormitory_1_0: 'A' },
        efficiencyPercent: { room_1_1: 200 }
      },
      { start: 8, end: 10, occupants: { room_1_1_0: 'B' }, efficiencyPercent: { room_1_1: 50 } }
    ]
  }
  const original = structuredClone(report)
  expect(incomeStability(report)).toEqual({
    halfHours: 4,
    roomComparisons: [{ roomId: 'room_1_1', firstEfficiency: 125, secondEfficiency: 125 }],
    maxWorkFractionDifference: 0.75
  })
  expect(report).toEqual(original)
})

const plan = {
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '制造站', product: 'gold', plans: [] },
    room_1_3: { name: '发电站', plans: [] }
  }
}
const settings = () => ({
  ...defaultIncomeSettings(),
  expectationMode: false,
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  sampleDays: 1
})

it('reports only sampling drone generation and overflow without emptying the closing stock', () => {
  const result = calculateIncome(plan, { ...settings(), warmupDays: 1 })
  expect(result.success).toBe(true)
  const drones = result.stability.drones
  expect(drones.opening).toBeCloseTo(240, 6)
  expect(drones.closing).toBeCloseTo(250, 6)
  expect(drones.generated).toBeCloseTo(240, 6)
  expect(drones.consumed).toBe(0)
  expect(drones.overflow).toBeCloseTo(230, 6)
  expect(drones.change).toBeCloseTo(10, 6)
  const room = result.stability.roomComparisons.find((room) => room.roomId === 'room_1_1')
  expect(room.firstEfficiency).toBeCloseTo(100, 8)
  expect(room.secondEfficiency).toBeCloseTo(100, 8)
})

it.each([0, 1])(
  'keeps drone conservation and ledger agreement with %s warmup days and manufacturing acceleration',
  (warmupDays) => {
    const staffed = structuredClone(plan)
    staffed.conf.workaholic = '芬'
    staffed.plan1.room_1_1.plans = [{ agent: '芬', replacement: [] }]
    staffed.advanced_settings = { drone_room: 'room_1_1' }
    const result = calculateIncome(staffed, { ...settings(), warmupDays })
    expect(result.success).toBe(true)
    const drones = result.stability.drones
    expect(drones.consumed).toBeGreaterThan(0)
    expect(drones.closing).toBeCloseTo(
      drones.opening + drones.generated - drones.overflow - drones.consumed,
      6
    )
    expect(drones.consumed).toBeCloseTo(result.resources.outflows.drone, 6)
    expect(drones.opening).toBeCloseTo(result.resources.opening.drone ?? 0, 6)
    expect(drones.closing).toBeCloseTo(result.resources.closing.drone, 6)
  }
)
