import { expect, it } from 'vitest'
import { createDefaultConfig } from './vendor/domain/defaults'
import { mowerDormFillerId, isMowerDormFiller } from './vendor/scheduler/mowerDormFiller'
import { createDormRecoveryObservation } from './incomeDormRecovery'
import { calculateIncome } from './incomeWorker'
import { defaultIncomeSettings, incomeRequest } from './income'
import { runCalculationBridge } from './vendor/workbench/calculationBridge'
import { incomeReportLines } from './incomeImage'

// Contract: docs/subsystems/plan-editor.md#dorm-filler-recovery
function dorm(count = 5, level = 1) {
  const config = createDefaultConfig()
  const ids = Array.from({ length: count }, (_, i) => mowerDormFillerId('dormitory_1', i))
  config.facilities.dormitories = [level]
  config.facilityOperatorIds.dormitories = [ids]
  config.operatorMorale = Object.fromEntries(ids.map((id) => [id, 24]))
  config.dormitoryOccupantCount = count
  return config
}
function provider(config, id, buffs, mood = 24, control = false) {
  config.operatorRecords ??= {}
  config.operatorRecords[id] = {
    charId: id,
    name: id,
    appellation: '',
    rarity: 0,
    profession: '',
    isAlter: false,
    nationId: null,
    groupId: null,
    teamId: null,
    skills: buffs.map(([buffId, description]) => ({
      buffId,
      description,
      name: buffId,
      roomType: control ? 'CONTROL' : 'DORMITORY',
      skillIcon: '',
      unlockPhase: 0,
      unlockLevel: 1
    }))
  }
  config.operatorMorale[id] = mood
  if (control) config.controlOperatorIds.push(id)
  else config.facilityOperatorIds.dormitories[0].unshift(id)
}
function observe(config, hours = 24) {
  const observation = createDormRecoveryObservation(0)
  observation.observe(config, 0, hours)
  return observation.result(hours)
}
it('counts uncapped theoretical filler recovery and leaves real state unchanged', () => {
  const config = dorm()
  const saved = structuredClone(config)
  const result = observe(config)
  expect(result.total).toBe(240)
  expect(result.daily).toBe(240)
  expect(result.rooms).toEqual([{ roomId: 'dormitory_1', total: 240, daily: 240, bedHours: 120 }])
  expect(result.partial).toBe(false)
  expect(config).toEqual(saved)
})
it('clips warmup and normalizes changed occupancy over the whole sample', () => {
  const observer = createDormRecoveryObservation(12)
  observer.observe(dorm(), 0, 6)
  observer.observe(dorm(2), 6, 18)
  observer.observe(dorm(1, 5), 18, 24)
  observer.observe(dorm(0), 24, 36)
  expect(observer.result(24).daily).toBe(48)
  expect(observer.result(24).rooms[0].bedHours).toBe(18)
  expect(() => observer.result(0)).toThrow('统计时长无效')
})
it('counts group and control bonuses per filler but a single-target bonus only once', () => {
  const config = dorm(2)
  provider(config, 'group', [['dorm_rec_all[000]', '该宿舍内所有干员的心情每小时恢复+0.2']])
  provider(config, 'single', [['dorm_rec_single[000]', '某个干员的心情每小时恢复+0.75']])
  provider(config, 'resting', [], 12)
  provider(
    config,
    'control',
    [['control_dorm_rec[000]', '所有宿舍内干员的心情每小时恢复+0.05']],
    24,
    true
  )
  const saved = structuredClone(config)
  expect(observe(config).daily).toBeCloseTo((2 * 2.25 + 0.75) * 24)
  expect(config).toEqual(saved)
  config.operatorRecords.single.skills = []
  expect(observe(config).daily).toBeCloseTo(2 * 2.25 * 24)
})
it('keeps the strongest group and single-target bonuses without double counting', () => {
  const config = dorm(1)
  provider(config, 'a', [['dorm_rec_all[000]', '该宿舍内所有干员的心情每小时恢复+0.2']])
  provider(config, 'b', [['dorm_rec_all[001]', '该宿舍内所有干员的心情每小时恢复+0.3']])
  provider(config, 'c', [['dorm_rec_single[000]', '某个干员的心情每小时恢复+0.5']])
  provider(config, 'd', [['dorm_rec_single[001]', '某个干员的心情每小时恢复+0.75']])
  expect(observe(config).daily).toBeCloseTo(3.05 * 24)
})
it('shares recovery with unfinished real residents but excludes their own gains', () => {
  const config = dorm(2)
  provider(config, 'shared', [['dorm_rec_all&single[000]', '心情恢复']], 24)
  provider(config, 'resting', [], 12)
  expect(observe(config).daily).toBeCloseTo((4 + (0.8 * 2) / 3) * 24)
  config.operatorRecords.shared.skills[0].buffId = 'dorm_rec_all&tired[000]'
  expect(observe(config).daily).toBeCloseTo(2 * 2.25 * 24)
})
it('marks unsupported effects as partial and reports zero when no filler is present', () => {
  const config = dorm(1)
  provider(config, 'unknown', [['unsupported', '心情每小时恢复+1']])
  const result = observe(config)
  expect(result.daily).toBe(48)
  expect(result.partial).toBe(true)
  expect(result.warnings.join()).toContain('尚未量化')
  expect(observe(dorm(0))).toMatchObject({ total: 0, daily: 0, rooms: [], partial: false })
})
it.each([true, false])(
  'reports filler recovery through the Worker with free_room=%s',
  (freeRoom) => {
    const plan = {
      default: 'plan1',
      conf: { free_room: freeRoom },
      backup_plans: [],
      facility_levels: { dormitory_1: 5 },
      plan1: {
        room_1_2: { name: '发电站', plans: [] },
        room_1_3: { name: '发电站', plans: [] },
        room_1_1: {
          name: '贸易站',
          product: 'money',
          plans: [{ agent: '芬', replacement: ['雷蛇'] }]
        },
        dormitory_1: { plans: Array.from({ length: 5 }, () => ({ agent: 'Free' })) }
      }
    }
    const settings = {
      ...defaultIncomeSettings(),
      operatorMode: 'maximum',
      weightMode: 'custom',
      expectationMode: true,
      finiteInventory: false,
      warmupDays: 1,
      sampleDays: 2
    }
    const result = calculateIncome(plan, settings)
    expect(result.success, JSON.stringify(result.diagnostics)).toBe(true)
    const request = incomeRequest(plan, settings)
    const baseline = runCalculationBridge(request.workspace, request.options)
    expect(result.summary.totalScore82).toBe(baseline.report.summary.totalScore82)
    expect(result.resources).toEqual(baseline.simulationReport.production.sample)
    expect(result.simulationReport.segments).toEqual(baseline.simulationReport.segments)
    const fillerHours = result.simulationReport.operators
      .filter((op) => isMowerDormFiller(op.operatorId))
      .reduce((sum, op) => sum + op.restHours, 0)
    expect(fillerHours).toBeGreaterThan(0)
    expect(result.dormRecovery.total).toBeCloseTo(fillerHours * 4, 6)
    expect(result.dormRecovery.daily).toBeCloseTo(result.dormRecovery.total / 2, 6)
    expect(result.dormRecovery.partial).toBe(false)
    const archived = structuredClone(result)
    expect(incomeReportLines(archived, settings, plan, '测试').join('\n')).toContain(
      '宿舍填充干员理论恢复量'
    )
    delete archived.dormRecovery
    expect(incomeReportLines(archived, settings, plan, '测试').join('\n')).not.toContain(
      '宿舍填充干员理论恢复量'
    )
  }
)

it('keeps per-dormitory results in facility order across occupancy changes', () => {
  const config = dorm(1)
  config.facilities.dormitories = [1, 5]
  const filler = mowerDormFillerId('dormitory_2', 0)
  config.facilityOperatorIds.dormitories.push([filler])
  const observer = createDormRecoveryObservation(0)
  config.facilityOperatorIds.dormitories[0] = []
  observer.observe(config, 0, 12)
  config.facilityOperatorIds.dormitories[0] = [mowerDormFillerId('dormitory_1', 0)]
  observer.observe(config, 12, 24)
  expect(observer.result(24).rooms.map(({ roomId, daily }) => [roomId, daily])).toEqual([
    ['dormitory_1', 24],
    ['dormitory_2', 96]
  ])
})
