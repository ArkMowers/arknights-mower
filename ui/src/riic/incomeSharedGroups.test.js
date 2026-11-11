import { afterEach, expect, it, vi } from 'vitest'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings } from './income'
import * as shiftCycle from './vendor/scheduler/mowerShiftCycle'
import {
  MowerResourceWaitError,
  MowerShiftPreviewError
} from './vendor/scheduler/mowerNativeErrors'
import { incomeDiagnosticGroups } from './incomeDiagnostics'
import * as rosterRuntime from './vendor/scheduler/rosterRuntime'
import { getMowerSourceRuntime } from './vendor/scheduler/mowerSourceRuntime'
import { mowerRecoveryManagers } from './vendor/scheduler/mowerDormRecovery'

afterEach(() => vi.restoreAllMocks())

it.each([2, 3, 4])(
  'calculates interleaved Free beds with a single-target manager in slot %s',
  (managerIndex) => {
    const room = 'dormitory_1'
    const plan = {
      default: 'plan1',
      conf: { ling_xi: 0 },
      facility_levels: { room_1_3: 3, room_2_3: 3 },
      backup_plans: [],
      plan1: {
        room_1_3: { name: '发电站', plans: [] },
        room_2_3: { name: '发电站', plans: [] },
        room_1_1: {
          name: '制造站',
          product: 'gold',
          plans: [{ agent: '芬', group: '', replacement: ['香草'] }]
        },
        [room]: {
          plans: Array.from({ length: 5 }, (_, index) => ({
            agent: index === managerIndex ? '闪灵' : 'Free',
            group: '',
            replacement: []
          }))
        }
      }
    }
    const before = structuredClone(plan)
    const create = rosterRuntime.createRosterRuntime
    let state
    vi.spyOn(rosterRuntime, 'createRosterRuntime').mockImplementation((config) => {
      const next = create(config)
      state ??= next
      return next
    })
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: 0,
      sampleDays: 1
    })
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    expect(result.observedHours).toBe(24)
    expect(result.summary.goldCount).toBeGreaterThan(0)
    expect(state.config.beds.filter((bed) => bed.roomId === room).map((bed) => bed.id)).toEqual(
      [0, 1, 2, 3, 4].filter((index) => index !== managerIndex).map((index) => `${room}_${index}`)
    )
    const data = getMowerSourceRuntime(state).data
    expect(data.currentOperator(room, managerIndex)?.nativeName).toBe('闪灵')
    expect(mowerRecoveryManagers(data, room, data.currentRoom(room, true))[0]?.[1]).toBe(
      managerIndex
    )
    expect(state.events.some((event) => event.type === 'shift-off')).toBe(true)
    expect(plan).toEqual(before)
  }
)

it.each([false, true])(
  'calculates a unique normal resting group through the income worker (backup=%s)',
  (backup) => {
    const plan = {
      default: 'plan1',
      facility_levels: { room_1_3: 3, room_2_3: 3 },
      conf: { ling_xi: 0 },
      backup_plans: [],
      plan1: {
        room_1_3: { name: '发电站', plans: [] },
        room_2_3: { name: '发电站', plans: [] },
        room_1_1: {
          name: '制造站',
          product: 'gold',
          plans: [
            {
              agent: '芬',
              group: '红松',
              replacement: ['翎羽'],
              group_bindings: [{ group: '工作换位', replacement: ['翎羽'] }]
            }
          ]
        },
        room_1_2: {
          name: '制造站',
          product: 'gold',
          plans: [{ agent: '香草', group: '工作换位', replacement: ['芬'] }]
        },
        dormitory_1: {
          plans: Array.from({ length: 5 }, () => ({ agent: 'Free', group: '', replacement: [] }))
        }
      }
    }
    if (backup)
      plan.backup_plans.push({
        name: '正常下班组',
        trigger: 'True',
        plan: { room_1_1: structuredClone(plan.plan1.room_1_1) }
      })
    const before = structuredClone(plan)
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: 0,
      sampleDays: 1
    })
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    expect(result.simulationReport.observedHours).toBe(24)
    expect(result.simulationReport.success).toBe(true)
    expect(result.summary.goldCount).toBeGreaterThan(0)
    expect(plan).toEqual(before)
  }
)

it.each(
  [
    [
      '绑组共享替班冲突，保留原任务并等待岗位释放',
      MowerResourceWaitError,
      'MOWER_PENDING_RESOURCE_WAIT'
    ],
    ['副表要求整组强制下班，等待副表退出', MowerShiftPreviewError, 'MOWER_PENDING_TASK_FAILURE'],
    ['换班预演失败，保留原任务等待相关观测', MowerShiftPreviewError, 'MOWER_PENDING_TASK_FAILURE']
  ].flatMap(([reason, Failure, code]) =>
    [false, true].map((expectationMode) => ({ reason, Failure, code, expectationMode }))
  )
)(
  'settles retained tasks: $reason (expectation=$expectationMode)',
  ({ Failure, reason, code, expectationMode }) => {
    const plan = {
      default: 'plan1',
      conf: { workaholic: '芬,香草', ling_xi: 0 },
      facility_levels: { room_1_3: 3, room_2_3: 3 },
      plan1: {
        room_1_3: { name: '发电站', plans: [] },
        room_2_3: { name: '发电站', plans: [] },
        room_1_1: {
          name: '制造站',
          product: 'gold',
          plans: [{ agent: '芬', group: '', replacement: ['香草'] }]
        }
      },
      backup_plans: [
        {
          name: '换班',
          trigger: 'True',
          plan: { room_1_1: { plans: [{ agent: '香草', group: '', replacement: ['芬'] }] } }
        }
      ]
    }
    const create = rosterRuntime.createRosterRuntime
    let state
    vi.spyOn(rosterRuntime, 'createRosterRuntime').mockImplementation((config) => {
      const next = create(config)
      state ??= next
      return next
    })
    vi.spyOn(shiftCycle, 'prepareMowerShiftCycle').mockImplementation(() => {
      throw new Failure(reason)
    })
    const result = calculateIncome(plan, {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      inventorySource: 'manual',
      finiteInventory: false,
      weightMode: 'custom',
      warmupDays: 0,
      sampleDays: 1,
      expectationMode,
      seed: 42
    })
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    expect(result.observedHours).toBe(24)
    expect(result.summary.goldCount).toBeGreaterThan(0)
    expect(result.simulationReport.production.success).toBe(true)
    expect(result.timelineData).toBeDefined()
    const pending = getMowerSourceRuntime(state).queue.tasks.filter((task) => task.executionFailure)
    expect(pending.length).toBeGreaterThan(0)
    expect(pending.every((task) => task.executionFailure.reason === reason)).toBe(true)
    expect(pending.some((task) => Object.keys(task.plan).length > 0)).toBe(true)
    expect(incomeDiagnosticGroups(result.diagnostics).failures).toEqual([])
    expect(result.diagnostics).toContainEqual(
      expect.objectContaining({ code, message: expect.stringContaining(reason) })
    )
  }
)
