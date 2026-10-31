import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {describe, expect, it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'

const fields = ['rest_in_full', 'exhaust_require', 'workaholic', 'resting_priority', 'resting_priority_replacement', 'free_room_exclusions', 'resting_standby', 'free_blacklist', 'refresh_trading', 'refresh_drained', 'ope_resting_priority'] as const
function setup(conf: Record<string, unknown>, backups: Record<string, unknown>[]) {
  const workspace = createDefaultWorkspace()
  Object.assign(workspace.mainPlan.conf, conf)
  workspace.mainPlan.facilities.room_1_1.slots = [{occupant: {kind: 'operator', operatorId: id('芬')}, groupId: null, replacements: [id('香草')]}]
  workspace.compatibility.backupPlans = backups.map(conf => ({trigger: 'False', conf}))
  const base = compileRosterSchedule(workspace)
  const config = compiledScheduleToRuntimeConfig(base)
  config.mowerAlpha = true
  const state = createRosterRuntime(config)
  const controller = createBackupPlanController(base, state)
  return {base, state, controller, activate: (active: boolean[]) => state.mowerShiftModel!.activate(active)}
}

describe('Mower alpha backup config layering', () => {
  it.each(fields)('adds then removes %s entries, permits later re-addition and restores earlier layers', field => {
    const {base, state, controller, activate} = setup({[field]: ['芬']}, [
      {[field]: '香草,芬', removed_operators: {[field]: '芬,香草'}},
      {[field]: ['芬']},
    ])
    const before = structuredClone(base)
    const morale = {...state.morale}, occupants = {...state.occupants}
    activate([true, false])
    expect(controller.schedule.policies[field]).toEqual([])
    activate([true, true])
    expect(controller.schedule.policies[field]).toEqual([id('芬')])
    activate([true, false])
    expect(controller.schedule.policies[field]).toEqual([])
    activate([false, false])
    expect(controller.schedule.policies[field]).toEqual([id('芬')])
    expect(base).toEqual(before)
    expect(state.morale).toEqual(morale)
    expect(state.occupants).toEqual(occupants)
  })

  it('removes replacement and idle-exclusion policies from runtime rules and restores them on exit', () => {
    const {state, activate} = setup({resting_priority_replacement: ['香草'], free_room_exclusions: ['芬'], resting_standby: ['香草']}, [
      {removed_operators: {resting_priority_replacement: '香草', free_room_exclusions: '芬', resting_standby: '香草'}},
    ])
    activate([true])
    expect(state.config.mowerSourceRules).toMatchObject({priorityReplacement: [], freeRoomExclusions: [], standby: []})
    activate([false])
    expect(state.config.mowerSourceRules).toMatchObject({priorityReplacement: [id('香草')], freeRoomExclusions: [id('芬')], standby: [id('香草')]})
  })

  it('inherits an implicit legacy default bed order but accepts an explicit default reset', () => {
    const {state, activate} = setup({dorm_order: 'dormitory_2,dormitory_1'}, [
      {dorm_order: 'dormitory_1_2,dormitory_2_2,dormitory_3_2,dormitory_4_2', dorm_order_override: null},
      {dorm_order: '', dorm_order_override: true},
    ])
    activate([true, false])
    expect(state.config.mowerDormOrder?.slice(0, 2)).toEqual(['dormitory_2', 'dormitory_1'])
    activate([true, true])
    expect(state.config.mowerDormOrder?.slice(0, 2)).toEqual(['dormitory_1', 'dormitory_2'])
    activate([true, false])
    expect(state.config.mowerDormOrder?.slice(0, 2)).toEqual(['dormitory_2', 'dormitory_1'])
  })

  it('infers a nondefault order when override is null', () => {
    const {state, activate} = setup({}, [{dorm_order: 'dormitory_2,dormitory_1', dorm_order_override: null}])
    activate([true])
    expect(state.config.mowerDormOrder?.slice(0, 2)).toEqual(['dormitory_2', 'dormitory_1'])
  })

  it('merges named mood limits by operator identity and restores global and named settings on exit', () => {
    const {controller, state, activate} = setup({mood_limits: {lower: 1, upper: 22}, operator_mood_limits: {[id('芬')]: {lower: 2, upper: 18}}}, [
      {mood_limits: {lower: 3, upper: 21}, operator_mood_limits: {'芬': {lower: 4, upper: 16}}},
      {mood_limits: null, operator_mood_limits: {'香草': {lower: 5, upper: 17}}},
    ])
    activate([true, true])
    expect(controller.schedule.rawConf.mood_limits).toEqual({lower: 3, upper: 21})
    expect(controller.schedule.rawConf.operator_mood_limits).toEqual({[id('芬')]: {lower: 4, upper: 16}, [id('香草')]: {lower: 5, upper: 17}})
    expect(state.config.mowerMoodLimits).toEqual({all: {lower: 3, upper: 21}, operators: {[id('芬')]: {lower: 4, upper: 16}, [id('香草')]: {lower: 5, upper: 17}}})
    activate([false, true])
    expect(controller.schedule.rawConf.mood_limits).toEqual({lower: 1, upper: 22})
    expect(controller.schedule.rawConf.operator_mood_limits).toEqual({[id('芬')]: {lower: 2, upper: 18}, [id('香草')]: {lower: 5, upper: 17}})
    expect(state.config.mowerMoodLimits?.all).toEqual({lower: 1, upper: 22})
  })

  it('removes a room-qualified refresh target by operator name', () => {
    const {controller, activate} = setup({refresh_trading: ['芬(room_1_1)', '香草']}, [
      {refresh_trading: ['芬(room_1_2)'], removed_operators: {refresh_trading: '芬'}},
    ])
    activate([true])
    expect(controller.schedule.policies.refresh_trading).toEqual([id('香草')])
  })

  it('overlays a product-only Current plan and additional bindings, restoring both on exit', () => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.dormitory_1.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    const facility = workspace.mainPlan.facilities.room_1_1
    facility.product = 'gold'
    facility.slots = [{occupant: {kind: 'operator', operatorId: '芬'}, groupId: 'main', replacements: ['香草']}]
    workspace.mainPlan.facilities.room_1_2.slots = [{occupant: {kind: 'operator', operatorId: id('砾')}, groupId: 'first', replacements: [id('克洛丝')]}]
    workspace.mainPlan.facilities.room_2_1.slots = [{occupant: {kind: 'operator', operatorId: id('玫兰莎')}, groupId: 'second', replacements: [id('安德切尔')]}]
    workspace.compatibility.backupPlans = [
      {trigger: 'False', plan: {room_1_1: {product: 'exp3', plans: [{agent: 'Current'}]}}},
      {trigger: 'False', plan: {room_1_1: {product: 'orirock', plans: [{agent: '芬', group: 'first', replacement: ['香草'], group_bindings: [{group: 'second', replacement: ['翎羽']}]}]}}},
    ]
    const base = compileRosterSchedule(workspace), config = compiledScheduleToRuntimeConfig(base)
    config.mowerAlpha = true
    const state = createRosterRuntime(config), controller = createBackupPlanController(base, state)
    const current = () => controller.schedule.rooms.find(room => room.roomId === 'room_1_1')!
    state.mowerShiftModel!.activate([true, false])
    expect(current().product).toBe('exp')
    expect(current().slots[0]!.groupId).toBe('main')
    state.mowerShiftModel!.activate([true, true])
    expect(current().product).toBe('fragment')
    expect(current().slots[0]!.groupBindings).toEqual([{group: 'first', replacement: [id('香草')]}, {group: 'second', replacement: [id('翎羽')]}])
    state.mowerShiftModel!.activate([true, false])
    expect(current().product).toBe('exp')
    expect(current().slots[0]!.groupBindings).toBeUndefined()
    state.mowerShiftModel!.activate([false, false])
    expect(current().product).toBe('gold')
  })

  it('preserves the raw recipe across fragment overlays and restoration', () => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.room_1_1.product = 'fragment'
    workspace.compatibility.facilityMetadata = {room_1_1: {rawProduct: 'orirock_device', custom: true}}
    workspace.compatibility.backupPlans = [
      {trigger: 'False', plan: {room_1_1: {product: 'orirock', plans: []}}},
      {trigger: 'False', plan: {room_1_1: {product: 'orirock_device', plans: []}}},
    ]
    const base = compileRosterSchedule(workspace), config = compiledScheduleToRuntimeConfig(base)
    config.mowerAlpha = true
    const state = createRosterRuntime(config), controller = createBackupPlanController(base, state)
    const metadata = () => controller.schedule.sourceWorkspace.compatibility.facilityMetadata?.room_1_1
    state.mowerShiftModel!.activate([true, false])
    expect(metadata()).toEqual({rawProduct: 'orirock', custom: true})
    state.mowerShiftModel!.activate([true, true])
    expect(metadata()?.rawProduct).toBe('orirock_device')
    state.mowerShiftModel!.activate([false, false])
    expect(metadata()?.rawProduct).toBe('orirock_device')
  })

  it('moves a working primary when a backup relocates it within the same room', () => {
    const workspace = createDefaultWorkspace()
    const slot = (name: string, replacement: string) => ({occupant: {kind: 'operator' as const, operatorId: id(name)}, groupId: null, replacements: [id(replacement)]})
    workspace.mainPlan.facilities.room_1_1.slots = [slot('芬', '香草'), slot('砾', '翎羽')]
    workspace.compatibility.backupPlans = [{trigger: 'False', plan: {room_1_1: {plans: [
      {agent: '砾', group: '', replacement: ['翎羽']}, {agent: '芬', group: '', replacement: ['香草']},
    ]}}}]
    const base = compileRosterSchedule(workspace), config = compiledScheduleToRuntimeConfig(base)
    config.mowerAlpha = true
    const state = createRosterRuntime(config)
    createBackupPlanController(base, state)
    const previous = getMowerSourceRuntime(state).data
    Object.assign(previous.operators[id('芬')]!, {currentRoom: 'room_1_1', currentIndex: 0, timeStampMicros: 0})
    Object.assign(previous.operators[id('砾')]!, {currentRoom: 'room_1_1', currentIndex: 1, timeStampMicros: 0})
    const next = state.mowerShiftModel!.swap(previous, [true])
    expect(state.mowerShiftModel!.transition(previous, next, [false], [true]).room_1_1).toEqual([id('砾'), id('芬')])
  })

  it('keeps a resting primary in its bed when a backup changes the allowed replacement', () => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.room_1_1.slots = [{occupant: {kind: 'operator', operatorId: id('芬')}, groupId: null, replacements: [id('香草')]}]
    workspace.mainPlan.facilities.dormitory_1.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    workspace.compatibility.backupPlans = [{trigger: 'False', plan: {room_1_1: {plans: [{agent: '芬', group: '', replacement: ['翎羽']}]}}}]
    const base = compileRosterSchedule(workspace), config = compiledScheduleToRuntimeConfig(base)
    config.mowerAlpha = true
    const state = createRosterRuntime(config)
    createBackupPlanController(base, state)
    const previous = getMowerSourceRuntime(state).data
    Object.assign(previous.operators[id('芬')]!, {currentRoom: 'dormitory_1', currentIndex: 2, mood: 10, timeStampMicros: 0})
    Object.assign(previous.operators[id('香草')]!, {currentRoom: 'room_1_1', currentIndex: 0, mood: 24, timeStampMicros: 0})
    previous.dorms[0]!.name = id('芬')
    previous.dorms[0]!.timeMicros = 3600000000
    const next = state.mowerShiftModel!.swap(previous, [true])
    const transition = state.mowerShiftModel!.transition(previous, next, [false], [true])
    expect(transition.room_1_1).toEqual([id('翎羽')])
    expect(Object.values(transition).flat()).not.toContain(id('芬'))
    expect(previous.operators[id('芬')]!.currentRoom).toBe('dormitory_1')
    Object.assign(next.operators[id('香草')]!, {currentRoom: '', currentIndex: -1})
    Object.assign(next.operators[id('翎羽')]!, {currentRoom: 'room_1_1', currentIndex: 0})
    const restored = state.mowerShiftModel!.swap(next, [false])
    const exit = state.mowerShiftModel!.transition(next, restored, [true], [false])
    expect(exit.room_1_1).toEqual([id('香草')])
    expect(Object.values(exit).flat()).not.toContain(id('芬'))
  })

  it('validates the actual active combination of cooperating backups', () => {
    const workspace = createDefaultWorkspace()
    workspace.mainPlan.facilities.dormitory_1.slots = Array.from({length: 5}, () => ({occupant: {kind: 'free' as const}, groupId: null, replacements: []}))
    workspace.mainPlan.facilities.room_1_1.slots = [{occupant: {kind: 'operator', operatorId: id('芬')}, groupId: null, replacements: [id('香草')]}]
    workspace.mainPlan.facilities.room_1_2.slots = [{occupant: {kind: 'operator', operatorId: id('砾')}, groupId: null, replacements: [id('翎羽')]}]
    workspace.compatibility.backupPlans = [
      {trigger: 'True', plan: {room_1_1: {plans: [{agent: '芬', group: 'paired', replacement: ['砾']}]}}},
      {trigger: 'True', plan: {room_1_2: {plans: [{agent: '砾', group: 'paired', replacement: ['翎羽']}]}}},
    ]
    const base = compileRosterSchedule(workspace), config = compiledScheduleToRuntimeConfig(base)
    config.mowerAlpha = true
    const state = createRosterRuntime(config), controller = createBackupPlanController(base, state)
    expect(() => state.mowerShiftModel!.activate([true, false])).toThrow(/同一非空组/)
    state.mowerShiftModel!.activate([true, true])
    expect(controller.active).toEqual([true, true])
  })

  it('rejects unsupported removal fields and malformed removal lists before activation', () => {
    for (const removed of [{ling_xi: '芬'}, {workaholic: 1}, ['芬']]) {
      expect(() => setup({}, [{removed_operators: removed}])).toThrow(/removed_operators/)
    }
  })
})
