import { afterEach, describe, expect, it, vi } from 'vitest'
import { defaultIncomeSettings } from './income'
import { calculateIncome } from './incomeWorker'
import { createDefaultWorkspace } from './vendor/workbench/defaults'
import { compileRosterSchedule } from './vendor/scheduler/compileRosterSchedule'
import { simulateSchedule } from './vendor/simulator/scheduleSimulation'
import { createProductionTimeline } from './vendor/simulator/productionTimeline'

vi.mock('./vendor/simulator/productionTimeline', async (importOriginal) => {
  const { createProductionTimeline, assertRunOrderMode } = await importOriginal()
  return { createProductionTimeline: vi.fn(createProductionTimeline), assertRunOrderMode }
})

afterEach(() => vi.restoreAllMocks())

function plan(product, level = 1, unlockLevel = 3) {
  return {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    facility_levels: { room_1_1: unlockLevel, room_3_3: level, room_1_3: 3, room_2_3: 3 },
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_3_3: { name: '制造站', product, plans: [] },
      room_1_3: { name: '发电站', plans: [] },
      room_2_3: { name: '发电站', plans: [] }
    }
  }
}
const settings = {
  ...defaultIncomeSettings(),
  warmupDays: 0,
  sampleDays: 1,
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom'
}

describe('manufacturing formulas unlocked across the base', () => {
  it.each([1, 2, 3])(
    'requires the selling trading post itself to be level three (level %s)',
    (level) => {
      const source = plan('gold', 1)
      source.plan1.room_2_1 = { name: '贸易站', product: 'orundum', plans: [] }
      source.plan1.room_2_2 = { name: '贸易站', product: 'lmd', plans: [] }
      source.facility_levels.room_2_1 = level
      source.facility_levels.room_2_2 = 3
      const result = calculateIncome(source, settings)
      expect(result.success).toBe(level === 3)
      if (level === 3) {
        expect(result.simulationReport.production.sample.inflows.orundum).toBe(240)
      } else {
        expect(result.diagnostics.some((d) => d.code === 'ORDER_DISTRIBUTION_UNSUPPORTED')).toBe(
          true
        )
      }
    }
  )

  it.each(['orirock', 'orirock_device', 'exp'])(
    'produces %s in lower-level factories with an unstaffed level-three factory',
    (product) => {
      for (const level of [1, 2]) {
        const source = plan(product, level)
        const original = structuredClone(source)
        const result = calculateIncome(source, settings)
        expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
        const production = result.simulationReport.production
        expect(production.manufacturing.find((room) => room.roomId === 'room_3_3')).toMatchObject({
          product: product === 'exp' ? 'exp' : 'fragment',
          sampleCompletedItems: product === 'exp' ? 8 : 24
        })
        expect(production.sample.inflows[product === 'exp' ? 'exp' : 'fragment']).toBe(
          product === 'exp' ? 8000 : 24
        )
        expect(source).toEqual(original)
      }
    }
  )

  it.each(['orirock', 'orirock_device', 'exp'])(
    'does not unlock %s through a level-three power plant or trading post',
    (product) => {
      const source = plan(product, 2, 2)
      source.plan1.room_2_1 = { name: '贸易站', product: 'lmd', plans: [] }
      source.facility_levels.room_2_1 = 3
      source.facility_levels.room_1_3 = 3
      const result = calculateIncome(source, settings)
      expect(result.success).toBe(false)
      expect(result.diagnostics.some((d) => d.code === 'MANUFACTURE_FORMULA_LEVEL')).toBe(true)
    }
  )

  it('retains finite material constraints after the recipe is unlocked', () => {
    const result = calculateIncome(plan('orirock', 2), {
      ...settings,
      finiteInventory: true,
      initialInventory: { orirock: 2, lmd: 1600 }
    })
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    expect(result.simulationReport.production.sample.inflows.fragment).toBe(1)
    expect(result.resources.closing.orirock).toBe(0)
    expect(result.resources.closing.lmd).toBe(0)
  })

  it.each([
    [1, 8],
    [2, 12]
  ])('retains level-%s storage capacity of %s shards', (level, expected) => {
    const workspace = createDefaultWorkspace()
    for (const room of Object.values(workspace.mainPlan.facilities)) {
      room.level = 0
      room.slots = []
    }
    Object.assign(workspace.mainPlan.facilities.room_1_1, { level: 3, product: 'gold' })
    Object.assign(workspace.mainPlan.facilities.room_1_2, { level, product: 'fragment' })
    const create = vi.mocked(createProductionTimeline).getMockImplementation()
    vi.mocked(createProductionTimeline).mockImplementationOnce((...args) => {
      const controller = create(...args)
      controller.nativeCollectManufacturingItems = () => {}
      return controller
    })
    const report = simulateSchedule(compileRosterSchedule(workspace, { idleOperators: [] }), {
      sampleHours: 20,
      production: { inventoryMode: 'unlimited', droneTarget: 'none', collectionIntervalHours: 100 }
    })
    expect(report.success, JSON.stringify(report.diagnostics)).toBe(true)
    expect(
      report.production.manufacturing.find((room) => room.roomId === 'room_1_2')
    ).toMatchObject({ completedItems: expected, pendingItems: 0 })
  })

  it.each(['orirock', 'orirock_device', 'exp3'])(
    'switches a low-level factory from gold to %s through a backup plan',
    (product) => {
      const source = plan('gold', 2)
      source.advanced_settings = {
        product_switching: {
          enable: true,
          use_drones_when_leaving_orirock: false,
          waiting_seconds: 0
        }
      }
      source.backup_plans = [
        {
          name: '切换配方',
          trigger: "op_data.facility_product('room_3_3') != None",
          plan: { room_3_3: { product, plans: [] } }
        }
      ]
      const result = calculateIncome(source, settings)
      expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
      expect(result.simulationReport.production.events).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            type: 'product-switched',
            roomId: 'room_3_3',
            fromProduct: 'gold',
            toProduct: product
          })
        ])
      )
      expect(
        result.simulationReport.production.sample.inflows[product === 'exp3' ? 'exp' : 'fragment']
      ).toBeGreaterThan(0)
    }
  )
})
