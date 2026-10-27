import { afterEach, expect, it } from 'vitest'
import { computed } from 'vue'
import { i18n } from './index'
import { incomeDisplayMessage, incomeRoomName } from './income'
import {
  defaultIncomeSettings,
  incomeFacilities,
  incomeMetrics,
  incomeWorkspace
} from '@/riic/income'
import {
  incomeImageAlgorithmLines,
  incomeImageFilename,
  incomeReportLines
} from '@/riic/incomeImage'
import { validateRosterWorkspace } from '@/riic/vendor/workbench/validate'
import { calculateIncome } from '@/riic/incomeWorker'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

it.each([false, true])(
  'localizes model diagnostics with finite inventory %s while retaining the completed records',
  (finiteInventory) => {
    const plan = {
      default: 'plan1',
      conf: {},
      backup_plans: [],
      plan1: {
        room_1_1: { name: '制造站', product: 'gold', plans: [] },
        room_1_3: { name: '发电站', plans: [] }
      }
    }
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      warmupDays: 0,
      sampleDays: 1,
      finiteInventory,
      inventorySource: 'manual',
      operatorMode: 'maximum',
      weightMode: 'custom'
    })
    expect(result.success, result.error).toBe(true)
    const original = JSON.stringify(result)
    i18n.global.locale.value = 'en-US'
    expect(
      result.diagnostics
        .map((diagnostic) => ({
          code: diagnostic.code,
          message: incomeDisplayMessage(diagnostic.message)
        }))
        .filter(({ message }) => /[\u4e00-\u9fff]/.test(message))
    ).toEqual([])
    expect(JSON.stringify(result)).toBe(original)
  }
)

it('translates real validation messages and nested backup warnings while retaining source diagnostics and custom labels', () => {
  const plan = {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    plan1: {
      room_1_1: { name: '制造站', product: 'gold', plans: [{ agent: '阿米娅' }] },
      room_1_2: { name: '贸易站', product: 'lmd', plans: [{ agent: '阿米娅' }] }
    }
  }
  const diagnostics = validateRosterWorkspace(incomeWorkspace(plan)).issues
  const duplicate = diagnostics.find((issue) => issue.code === 'DUPLICATE_OPERATOR').message
  const raw = JSON.stringify(diagnostics)
  const display = computed(() => incomeDisplayMessage(duplicate))
  i18n.global.locale.value = 'en-US'
  expect(display.value).toContain('Amiya is assigned to both B101 and B102')
  const backup =
    '副表 鸿雪下班 单独生效时：替补干员 斯卡蒂 必须为同一非空组内的其他主力或未在岗的替补。 实际组合将在切表前校验。'
  expect(incomeDisplayMessage(backup)).toContain(
    'When backup 鸿雪下班 is applied alone: Replacement Skadi'
  )
  expect(
    incomeDisplayMessage(
      '无人机由 Mower 的任务阶段使用：每 1.5 小时待办检查、120 架判断门槛；按所选设施加速，不额外消耗跑单无人机。'
    )
  ).toContain('every 1.5 hours and a 120-drone')
  i18n.global.locale.value = 'ja-JP'
  expect(display.value).toContain('アーミヤ')
  i18n.global.locale.value = 'zh-TW'
  expect(display.value).toContain('阿米婭')
  expect(JSON.stringify(diagnostics)).toBe(raw)
})

it('translates report assumptions and export annotations while preserving the completed result and names', () => {
  const plan = { default: 'plan1', conf: {}, backup_plans: [], plan1: {} }
  const settings = {
    ...defaultIncomeSettings(),
    finiteInventory: false,
    weightMode: 'custom',
    operatorMode: 'maximum'
  }
  const result = {
    observedHours: 48,
    summary: { totalScore82: 100 },
    initialConditions: { fiammettaMorale: 16 }
  }
  const original = JSON.stringify({ plan, settings, result })
  const lines = computed(() => incomeReportLines(result, settings, plan, '我的中文排班').join('\n'))
  i18n.global.locale.value = 'en-US'
  expect(lines.value).toContain('Fiammetta starts at 16 Morale')
  expect(lines.value).toContain('manufactured Pure Gold × 500')
  expect(lines.value).toContain('Source image: 我的中文排班')
  expect(incomeImageFilename('我的中文排班', result)).toBe('我的中文排班_daily-income100_2days.jpg')
  expect(incomeImageAlgorithmLines(settings)).toEqual([
    'Custom',
    'EXP 1 · Pure Gold 0.8 · Orders 0.2',
    'Originium Shards 0 · Orundum 0'
  ])
  i18n.global.locale.value = 'ja-JP'
  expect(lines.value).toContain('フィアメッタの初期体力は 16')
  i18n.global.locale.value = 'zh-TW'
  expect(lines.value).toContain('菲亞梅塔初始心情 16')
  expect(JSON.stringify({ plan, settings, result })).toBe(original)
})

it('translates facility choices and metric units while preserving the plan, identifiers and amounts', () => {
  const plan = {
    default: 'plan1',
    conf: {},
    backup_plans: [],
    plan1: { room_1_1: { name: '制造站', product: 'gold', plans: [] } }
  }
  const original = structuredClone(plan)
  const options = computed(() => incomeFacilities(plan))
  const metrics = computed(() => incomeMetrics({ exp: 100, netLmd: 200, orderLmd: 300 }, 2))
  expect(options.value[0].label).toContain('制造站')
  const amounts = metrics.value.map(({ daily, total }) => ({ daily, total }))
  i18n.global.locale.value = 'en-US'
  expect(options.value[0]).toMatchObject({
    roomId: 'room_1_1',
    target: 'gold',
    label: 'B101 Factory · Pure Gold'
  })
  expect(metrics.value[0]).toMatchObject({ label: 'EXP', unit: 'EXP', daily: 100, total: 200 })
  expect(metrics.value.map(({ daily, total }) => ({ daily, total }))).toEqual(amounts)
  expect(incomeRoomName('dormitory_1')).toBe('Dormitory 1')
  expect(incomeRoomName('central')).toBe('Control Center')
  expect(incomeRoomName('room_1_1', 'B101 (制造站)')).toBe('B101 (Factory)')
  expect(incomeRoomName('dormitory_1', '宿舍1')).toBe('Dormitory 1')
  expect(incomeRoomName('gaming_1', '活动室1')).toBe('Activity Room 1')
  expect(incomeRoomName('gaming_1', '我的活动室')).toBe('我的活动室')
  expect(incomeRoomName('room_1_1', '我的制造站')).toBe('我的制造站')
  expect(incomeRoomName('自定义房间', '控制中枢')).toBe('控制中枢')
  expect(plan).toEqual(original)
})
