import { expect, it } from 'vitest'
import { defaultIncomeSettings } from './income'
import { incomeReportLines } from './incomeImage'

const plan = {
  default: 'plan1',
  conf: {},
  backup_plans: [],
  plan1: {
    room_1_1: { name: '制造站', product: 'exp3', plans: [] }
  }
}
const settings = {
  ...defaultIncomeSettings(),
  operatorMode: 'maximum',
  inventorySource: 'manual',
  finiteInventory: false,
  weightMode: 'custom',
  warmupDays: 0,
  sampleDays: 1
}
function report(droneAllocationModel) {
  return {
    observedHours: 24,
    summary: {},
    modelProvenance: { timingModel: 'theoretical-events-v1' },
    simulationReport: {
      production: {
        assumptions: { expectationMode: true, droneAllocationModel },
        expected: {
          droneGenerated: 10,
          droneAllocated: 8,
          droneLost: 1,
          droneUnallocated: 1,
          droneSwitchAllocated: 2,
          pendingSwitchDrones: 3
        }
      }
    },
    stability: {
      drones: { opening: 150, closing: 151, change: 1, generated: 10, consumed: 9, overflow: 0 }
    }
  }
}
const lines = (result) => incomeReportLines(result, settings, plan, '排班').join('\n')

it('describes generated capacity and switch reservations without presenting physical stock', () => {
  const text = lines(report('generated-capacity-v1'))
  expect(text).toContain('不模拟无人机库存、容量、阈值和检查间隔')
  expect(text).toContain('生成 10，有效分配 8，其中切产物 2；损耗 1，未利用 1')
  expect(text).toContain('期末待结算切产物份额 3 架')
  expect(text).toContain('按能力生成时刻归属预热或统计阶段')
  expect(text).toContain('未结算的切产物份额不计收入')
  expect(text).not.toContain('统计期无人机：期初')
  expect(text).not.toContain('先消耗期初库存且不计其收益')
})

it('retains the saved threshold model explanation for historical results', () => {
  const text = lines(report('threshold-v1'))
  expect(text).toContain('无人机沿用配置的检查间隔、制造保留阈值和贸易加速规则')
  expect(text).toContain('统计期无人机：期初 150，期末 151')
  expect(text).toContain('先消耗期初库存且不计其收益')
  expect(text).not.toContain('统计期无人机能力：')
})

it('retains the unmarked continuous-generation explanation for earlier saved results', () => {
  const text = lines(report(undefined))
  expect(text).toContain('无人机按新生成能力连续加速目标设施')
  expect(text).toContain('收益另按生成的加速能力计算，本次可折算 8 架')
  expect(text).not.toContain('期末待结算切产物份额')
})
