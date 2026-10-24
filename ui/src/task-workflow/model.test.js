import { computed, reactive } from 'vue'
import { describe, expect, it } from 'vitest'
import { createTaskWorkflow, setAllTasksEnabled, setTaskEnabled } from './model'

const switches = [
  ['clue', 'enable_party'],
  ['training', 'enable_mastery'],
  ['trust', 'trust_rotation_enable'],
  ['skland', 'skland_enable'],
  ['mail', 'check_mail_enable'],
  ['report', 'report_enable'],
  ['recruit', 'recruit_enable'],
  ['depot', 'maa_depot_enable'],
  ['visit', 'visit_friend_enable'],
  ['credit-fight', 'maa_credit_fight'],
  ['shop', 'maa_mall_enable'],
  ['stage-plan', 'stage_plan_enable'],
  ['long', 'maa_rg_enable']
]

function freeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze)
    Object.freeze(value)
  }
  return value
}

describe('task configuration checklist', () => {
  it('keeps every task and configuration destination available while disabled', () => {
    const workflow = createTaskWorkflow({})
    expect(workflow.groups.map(({ id, label }) => [id, label])).toEqual([
      ['base', '基建任务'],
      ['daily', '日常任务'],
      ['combat', '作战与空闲'],
      ['support', '运行配置']
    ])
    const expectedGroups = {
      base: ['base', 'runorder', 'drone', 'clue', 'workshop', 'training'],
      daily: [
        'trust',
        'skland',
        'mail',
        'report',
        'recruit',
        'depot',
        'visit',
        'credit-fight',
        'shop',
        'rewards'
      ],
      combat: ['stage-plan', 'long'],
      support: ['intervals', 'runtime', 'accounts', 'maa']
    }
    const editors = new Set(workflow.editors.map(({ id }) => id))
    for (const group of workflow.groups) {
      expect(workflow.tasks.filter((task) => task.group === group.id).map(({ id }) => id)).toEqual(
        expectedGroups[group.id]
      )
      expect(editors.has(`category:${group.id}`)).toBe(false)
    }
    for (const task of workflow.tasks) expect(editors.has(task.editor), task.id).toBe(true)
    for (const id of ['device', 'credit', 'idle']) expect(editors.has(id)).toBe(true)
    expect(workflow.tasks.some(({ id }) => id === 'device')).toBe(false)
    expect(workflow.editors.find(({ id }) => id === 'device').title).toBe('连接与启动')
    expect(workflow.tasks.find(({ id }) => id === 'base').title).toBe('基建排班')
    expect(workflow.tasks.find(({ id }) => id === 'intervals')).toMatchObject({
      title: '执行间隔',
      group: 'support',
      mode: 'automatic'
    })
    expect(new Set(workflow.tasks.map(({ id }) => id)).size).toBe(workflow.tasks.length)
    expect(new Set(workflow.editors.map(({ id }) => id)).size).toBe(workflow.editors.length)
  })

  it.each(switches)('binds %s only to its real configuration field %s', (id, key) => {
    const config = {
      ...Object.fromEntries(switches.map(([, field]) => [field, false])),
      maa_rg_enable: 0,
      stage_plan_runner: 'mower',
      visit_friend_mode: 'maa',
      maa_mall_mode: 'mower',
      mail_enable: true,
      maa_gap: 3,
      skland_info: [{ account: 'private-account', password: 'private-secret' }]
    }
    const before = structuredClone(config)
    expect(createTaskWorkflow(config).statuses[id]).toBe(false)
    expect(setTaskEnabled(config, id, true)).toBe(true)
    expect(config).toEqual({ ...before, [key]: id === 'long' ? 1 : true })
    expect(createTaskWorkflow(config).statuses[id]).toBe(true)
    expect(setTaskEnabled(config, id, false)).toBe(true)
    expect(config).toEqual(before)
  })

  it.each([false, 0, true, 1])(
    'reads the saved long-task switch %s without changing its mode',
    (value) => {
      const config = freeze({ maa_rg_enable: value, maa_long_task_type: 'sf' })
      expect(createTaskWorkflow(config).statuses.long).toBe(value === true || value === 1)
    }
  )

  it.each([
    'base',
    'runorder',
    'drone',
    'workshop',
    'rewards',
    'intervals',
    'runtime',
    'accounts',
    'maa',
    'device',
    'idle',
    'category:daily',
    'unknown',
    'constructor'
  ])('does not invent an independent switch for %s', (id) => {
    const config = freeze({
      drone_room: '',
      workshop_manual_settings: [{ enabled: true }],
      maa_recruit: true,
      automatic_rescue_enable: false
    })
    expect(setTaskEnabled(config, id, false)).toBe(false)
    const task = createTaskWorkflow(config).tasks.find((entry) => entry.id === id)
    if (task) expect(task.mode).toBe('automatic')
    expect(config.maa_recruit).toBe(true)
    expect(config.workshop_manual_settings[0].enabled).toBe(true)
  })

  it('changes independent switches without clearing plans, reward choices or parameters', () => {
    const config = {
      ...Object.fromEntries(switches.map(([, field]) => [field, true])),
      maa_rg_enable: 1,
      drone_room: 'room_1_1',
      drone_interval: 4,
      recruit_gap: 9,
      maa_gap: 3,
      automatic_rescue_enable: true,
      workshop_manual_settings: [{ enabled: true, operator: '九色鹿' }],
      maa_recruit: true,
      stage_plan_runner: 'maa',
      visit_friend_mode: 'mower',
      maa_mall_mode: 'maa',
      maa_long_task_type: 'rogue'
    }
    const before = structuredClone(config)
    setAllTasksEnabled(config, false)
    expect(config).toEqual({
      ...before,
      ...Object.fromEntries(switches.map(([, key]) => [key, key === 'maa_rg_enable' ? 0 : false]))
    })
    setAllTasksEnabled(config, true)
    expect(config).toEqual(before)
  })

  it('keeps visits, shopping, credit fights and operations independent of their runners', () => {
    const workflow = createTaskWorkflow({
      visit_friend_enable: true,
      visit_friend_mode: 'mower',
      maa_mall_enable: false,
      maa_mall_mode: 'maa',
      maa_credit_fight: true,
      stage_plan_enable: false,
      stage_plan_runner: 'maa'
    })
    expect(workflow.statuses.visit).toBe(true)
    expect(workflow.statuses.shop).toBe(false)
    expect(workflow.statuses['credit-fight']).toBe(true)
    expect(workflow.statuses['stage-plan']).toBe(false)
    expect(
      workflow.tasks
        .filter(({ id }) => ['visit', 'shop', 'credit-fight'].includes(id))
        .map(({ editor }) => editor)
    ).toEqual(['visit', 'credit-fight', 'shop'])
  })

  it('keeps automatic trade acceleration available without a selected drone room', () => {
    const workflow = createTaskWorkflow({ drone_room: '' })
    expect(workflow.statuses.drone).toBe(true)
    expect(workflow.tasks.find(({ id }) => id === 'drone').mode).toBe('automatic')
  })

  it.each([
    [[{ enabled: true }], [], true],
    [[{ enabled: false }], [{ enabled: true }], false],
    [[], [{ enabled: true }], false],
    [undefined, [{ enabled: true }], true],
    [undefined, [], false]
  ])('reads manual workshop choices before generated settings', (manual, generated, enabled) => {
    expect(
      createTaskWorkflow({ workshop_manual_settings: manual, workshop_settings: generated })
        .statuses.workshop
    ).toBe(enabled)
  })

  it.each([
    [{ stage_plan_enable: true, stage_plan_runner: 'maa' }, true],
    [{ stage_plan_enable: true, stage_plan_runner: 'mower' }, false],
    [{ visit_friend_enable: true, visit_friend_mode: 'maa' }, true],
    [{ visit_friend_enable: true, visit_friend_mode: 'mower' }, false],
    [{ maa_mall_enable: true, maa_mall_mode: 'maa' }, true],
    [{ maa_mall_enable: true, maa_mall_mode: 'mower' }, false],
    [{ maa_credit_fight: true }, true],
    [{ maa_rg_enable: 1, maa_long_task_type: 'rogue' }, false],
    [{ maa_enable: true }, false]
  ])('derives MAA reward activity from actual daily work', (config, enabled) => {
    expect(createTaskWorkflow(config).statuses.rewards).toBe(enabled)
  })

  it.each(['maa_mail', 'maa_recruit', 'maa_orundum', 'maa_mining', 'maa_specialaccess'])(
    'recognizes %s as an additional MAA reward without enabling public recruitment',
    (key) => {
      const workflow = createTaskWorkflow({ [key]: true, recruit_enable: false })
      expect(workflow.statuses.rewards).toBe(true)
      expect(workflow.statuses.recruit).toBe(false)
      expect(workflow.tasks.find(({ id }) => id === 'rewards').mode).toBe('automatic')
    }
  )

  it('reads configuration without mutations, credentials or invented runtime state', () => {
    const config = freeze({
      maa_rg_enable: 1,
      maa_long_task_type: 'sf',
      skland_info: [{ account: 'private-account', password: 'private-secret' }],
      device_profile: { last_serial: 'private-device' },
      running: true,
      next_task_time: 'fictional-next-task'
    })
    const workflow = createTaskWorkflow(config)
    expect(Object.keys(workflow).sort()).toEqual(['editors', 'groups', 'statuses', 'tasks'])
    for (const status of Object.values(workflow.statuses)) expect(typeof status).toBe('boolean')
    for (const value of [
      'private-account',
      'private-secret',
      'private-device',
      'fictional-next-task'
    ]) {
      expect(JSON.stringify(workflow)).not.toContain(value)
    }
    expect(createTaskWorkflow(config)).toEqual(workflow)
  })

  it('updates checkbox states when their real configuration fields change', () => {
    const config = reactive({ recruit_enable: false, maa_rg_enable: 0, stage_plan_runner: 'maa' })
    const workflow = computed(() => createTaskWorkflow(config))
    expect(workflow.value.statuses.recruit).toBe(false)
    config.recruit_enable = true
    setTaskEnabled(config, 'long', true)
    expect(workflow.value.statuses.recruit).toBe(true)
    expect(workflow.value.statuses.long).toBe(true)
    expect(config.stage_plan_runner).toBe('maa')
  })
})
