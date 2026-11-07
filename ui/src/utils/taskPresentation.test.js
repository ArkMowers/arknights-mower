import { describe, expect, it, vi } from 'vitest'
import {
  backupChangeText,
  actionSubjectRuns,
  groupActionMembers,
  queueMasteryDetails,
  queueTaskRoom,
  queueTaskRows,
  queueTaskTarget,
  queueTaskText,
  queueTaskTitle,
  queueTaskTokens,
  taskPresentation
} from './taskPresentation.js'

describe('queue task rows', () => {
  const refresh = (room, time = '2026-11-05T16:05:19.000') => ({
    time,
    type: { value: '强制刷新任务时间', display_value: '强制刷新任务时间' },
    display_name: '刷新跑单时间',
    plan: {},
    meta_data: room
  })
  const plan = { room_1_1: { name: '贸易站' }, room_2_1: { name: '贸易站' } }

  it('combines same-time refresh targets only in the page rows and retains their original order', () => {
    const tasks = Object.freeze([
      Object.freeze(refresh('room_2_1')),
      Object.freeze(refresh('room_1_1'))
    ])
    const rows = queueTaskRows(tasks, [], plan)
    expect(rows).toHaveLength(1)
    expect(rows[0].task).toBe(tasks[0])
    expect(rows[0].tasks).toEqual(tasks)
    expect(rows[0].heading).toEqual([{ type: 'text', text: '刷新跑单时间' }])
    expect(rows[0].refreshTargets).toEqual([
      { id: 'room_2_1', label: '贸易站 B201' },
      { id: 'room_1_1', label: '贸易站 B101' }
    ])
    expect(tasks).toHaveLength(2)
    expect(tasks[0].meta_data).toBe('room_2_1')
  })

  it('keeps a single refresh target below its heading and uses its supplied facility label', () => {
    const task = refresh('room_2_1')
    task.presentation = {
      title: '刷新跑单时间',
      targets: [{ id: 'room_2_1', label: '发电站 B201' }]
    }
    const [row] = queueTaskRows([task], [], plan)
    expect(row.heading).toEqual([{ type: 'text', text: '刷新跑单时间' }])
    expect(row.refreshTargets).toEqual([{ id: 'room_2_1', label: '发电站 B201' }])
  })

  it.each([
    { time: '2026-11-05T16:05:19.000', type: '线索任务', plan: {} },
    refresh('room_3_1', '2026-11-05T16:05:19.001'),
    { ...refresh('room_3_1'), recovery_observation_rooms: ['dormitory_1'] }
  ])('preserves intervening tasks when grouping adjacent refresh targets: %j', (intervening) => {
    const tasks = [
      refresh('room_2_1'),
      refresh('room_1_1'),
      intervening,
      refresh('room_1_2'),
      refresh('room_2_2')
    ]
    const rows = queueTaskRows(tasks, [], plan)
    expect(rows.map((row) => row.tasks)).toEqual([tasks.slice(0, 2), [intervening], tasks.slice(3)])
    expect(rows.flatMap((row) => row.tasks)).toEqual(tasks)
    expect(rows[2].refreshTargets.map((target) => target.id)).toEqual(['room_1_2', 'room_2_2'])
  })

  it('uses the precise instant rather than displayed seconds for refresh grouping', () => {
    expect(
      queueTaskRows(
        [
          refresh('room_1_1', '2026-11-05T16:05:19.001'),
          refresh('room_2_1', '2026-11-05T16:05:19.002')
        ],
        [],
        plan
      )
    ).toHaveLength(2)
    expect(
      queueTaskRows(
        [
          refresh('room_1_1', '2026-11-05T16:05:19'),
          refresh('room_2_1', '2026-11-05T16:05:19.000')
        ],
        [],
        plan
      )
    ).toHaveLength(1)
    expect(
      queueTaskRows(
        [
          refresh('room_1_1', '2026-11-05T16:05:19.123456'),
          refresh('room_2_1', '2026-11-05T16:05:19.123457')
        ],
        [],
        plan
      )
    ).toHaveLength(2)
    expect(
      queueTaskRows(
        [
          refresh('room_1_1', '2026-11-05T16:05:19.1234'),
          refresh('room_2_1', '2026-11-05T16:05:19.123400')
        ],
        [],
        plan
      )
    ).toHaveLength(1)
  })

  it('keeps separate scheduler clock times across the browser daylight-saving transition', () => {
    vi.stubEnv('TZ', 'America/New_York')
    try {
      const tasks = [
        refresh('room_1_1', '2026-03-08T02:30:00'),
        refresh('room_2_1', '2026-03-08T03:30:00')
      ]
      expect(queueTaskRows(tasks, [], plan).map(({ clock }) => clock)).toEqual([
        '02:30:00',
        '03:30:00'
      ])
    } finally {
      vi.unstubAllEnvs()
    }
  })

  it('groups equivalent explicit offsets independently of times without an offset', () => {
    const tasks = [
      refresh('room_1_1', '2026-03-08T02:30:00.123456+08:00'),
      refresh('room_2_1', '2026-03-07T18:30:00.123456Z'),
      refresh('room_2_1', '2026-03-07T18:30:00.123456')
    ]
    expect(
      queueTaskRows(tasks, [], plan).map(({ refreshTargets }) => refreshTargets.length)
    ).toEqual([2, 1])
  })

  it.each([
    { meta_data: 'room_2_1-extra' },
    { meta_data: '' },
    { type: { display_value: '仓库扫描' } },
    { recovery_observation_rooms: ['dormitory_1'] },
    { plan: { room_2_1: ['Current'] } },
    { time: 'unknown' }
  ])('does not combine other task kinds or unconfirmed targets: %j', (changes) => {
    const tasks = [refresh('room_1_1'), { ...refresh('room_2_1'), ...changes }]
    expect(queueTaskRows(tasks, [], plan)).toHaveLength(2)
  })

  it('keeps ordinary task contents, Current and Free slots unchanged', () => {
    const task = {
      time: '2026-11-05T18:11:29',
      type: { display_value: '上班' },
      plan: { room_1_1: ['Current', '阿米娅', 'Free'], dormitory_1: ['芬'] },
      presentation: {
        title: '红松上班；芬休息',
        actions: [{ kind: 'group', subject: '红松', action: '上班' }]
      }
    }
    const [row] = queueTaskRows([task], ['阿米娅', '芬'], plan)
    expect(row.task).toBe(task)
    expect(row.task.plan).toEqual({ room_1_1: ['Current', '阿米娅', 'Free'], dormitory_1: ['芬'] })
    expect(row.actions).toEqual(task.presentation.actions)
    expect(row.refreshTargets).toEqual([])
    expect(row.heading.map((token) => token.text).join('')).toBe('红松上班；芬休息')
  })

  it('keeps each task calendar date and seconds without changing queue order', () => {
    const times = [
      '2026-11-06T17:38:57.960569',
      '2026-11-07T13:26:26.624427',
      '2026-11-07T16:00:00',
      '2026-11-09T09:00:00',
      '2026-11-08T20:00:00'
    ]
    const tasks = times.map((time) => ({ time, type: '跑单' }))
    const rows = queueTaskRows(tasks)
    expect(rows.map((row) => row.task)).toEqual(tasks)
    expect(rows.map((row) => [row.clock, row.day])).toEqual([
      ['17:38:57', '2026-11-06'],
      ['13:26:26', '2026-11-07'],
      ['16:00:00', '2026-11-07'],
      ['09:00:00', '2026-11-09'],
      ['20:00:00', '2026-11-08']
    ])
  })

  it('sorts forecast and queue facilities alike while preserving task and staffing order', () => {
    const rooms = Object.freeze([
      Object.freeze({ id: 'dormitory_4', label: '宿舍4', agents: Object.freeze(['芬']) }),
      Object.freeze({ id: 'meeting', label: '会客室', agents: Object.freeze(['红']) }),
      Object.freeze({ id: 'dormitory_1', label: '宿舍1', agents: Object.freeze(['Free', '陈']) }),
      Object.freeze({
        id: 'central',
        label: '控制中枢',
        agents: Object.freeze(['Current', '红松'])
      })
    ])
    const originalIds = ['dormitory_4', 'meeting', 'dormitory_1', 'central']
    const orderedIds = ['central', 'dormitory_1', 'dormitory_4', 'meeting']
    const task = Object.freeze({
      time: '2026-11-05T18:11:29',
      plan: Object.freeze(Object.fromEntries(rooms.map(({ id, agents }) => [id, agents]))),
      presentation: Object.freeze({ header: '随后执行红松上班', title: '红松上班', rooms })
    })

    const [row] = queueTaskRows([task])
    const forecast = taskPresentation(task.presentation, true)
    expect(row.roomEntries.map(([id]) => id)).toEqual(orderedIds)
    expect(forecast.rooms.map(({ id }) => id)).toEqual(orderedIds)
    for (const [index, [id, agents]] of row.roomEntries.entries()) {
      expect(agents).toBe(task.plan[id])
      expect(forecast.rooms[index].agents).toBe(agents)
    }
    expect(row.task).toBe(task)
    expect(Object.keys(task.plan)).toEqual(originalIds)
    expect(rooms.map(({ id }) => id)).toEqual(originalIds)
  })

  it('keeps content keys stable across equivalent polls and unrelated insertions', () => {
    const task = {
      time: '2026-11-05T18:11:29',
      type: { display_value: '上班' },
      plan: { room_1_1: ['Current', '阿米娅'], dormitory_1: ['芬'] },
      presentation: {
        title: '红松上班',
        actions: [{ kind: 'group', subject: '红松', action: '上班' }]
      }
    }
    const original = queueTaskRows([task], [], plan)[0].key
    const equivalent = {
      ...task,
      presentation: {
        actions: [{ action: '上班', subject: '红松', kind: 'group' }],
        title: '红松上班'
      }
    }
    const rows = queueTaskRows([refresh('room_2_1'), equivalent], [], plan)
    expect(rows[1].key).toBe(original)
    expect(
      queueTaskRows(
        [{ ...task, plan: { ...task.plan, room_1_1: ['Free', '阿米娅'] } }],
        [],
        plan
      )[0].key
    ).not.toBe(original)
    expect(queueTaskRows([{ ...task, time: '2026-11-05T18:11:30' }], [], plan)[0].key).not.toBe(
      original
    )
  })

  it('gives distinct ordinary duplicates separate stable keys', () => {
    const task = { time: '2026-11-05T18:11:29', type: '公招', plan: {} }
    const keys = queueTaskRows([task, { ...task }]).map((row) => row.key)
    expect(new Set(keys).size).toBe(2)
    expect(queueTaskRows(JSON.parse(JSON.stringify([task, task]))).map((row) => row.key)).toEqual(
      keys
    )
  })
})

describe('task presentation', () => {
  it('keeps group snapshots independent of current configured members and handles old multi-bindings', () => {
    const plan = {
      central: {
        plans: [
          { agent: '阿米娅', group: '感知', replacement: ['芬'] },
          {
            agent: '凯尔希',
            group: '其他',
            group_bindings: [{ group: '感知', replacement: ['红'] }]
          },
          { agent: '阿米娅', group: '感知' }
        ]
      }
    }
    expect(groupActionMembers({ subject: '感知' }, plan)).toEqual(['阿米娅', '凯尔希'])
    expect(groupActionMembers({ subject: '感知', members: ['陈', '陈'] }, plan)).toEqual(['陈'])
    expect(groupActionMembers({ subject: '感知', members: [] }, plan)).toEqual([])
    expect(
      taskPresentation({
        title: '感知上班',
        actions: [{ kind: 'group', subject: '感知', action: '上班', members: [1] }]
      })
    ).toBeNull()
  })

  it('budgets one individual preview per action while preserving group and action ordering', () => {
    const source = [
      { kind: 'group', subject: '感知', action: '上班', members: ['阿米娅'] },
      ...['芬', '红', '陈', '凯尔希', '赫默'].map((subject) => ({
        kind: 'operator',
        subject,
        action: '下班'
      })),
      { kind: 'operator', subject: '白面鸮', action: '休息' }
    ]
    const runs = actionSubjectRuns(source)
    expect(runs.map((run) => run.action)).toEqual(['上班', '下班', '休息'])
    expect(runs[1].parts).toEqual([
      {
        kind: 'operators',
        members: ['芬', '红', '陈', '凯尔希', '赫默'],
        preview: ['芬'],
        overflow: 4,
        tail: ['红', '陈']
      }
    ])
    expect(runs.map((run) => run.text).join('；')).toBe(
      '感知上班；芬、红、陈、凯尔希、赫默下班；白面鸮休息'
    )
    expect(source).toHaveLength(7)
  })

  it('keeps the single preview and all overflow attached when groups separate personal subjects', () => {
    const [run] = actionSubjectRuns([
      { kind: 'operator', subject: '芬', action: '下班' },
      { kind: 'group', subject: '感知', action: '下班', members: ['阿米娅'] },
      { kind: 'operator', subject: '红', action: '下班' },
      { kind: 'operator', subject: '陈', action: '下班' }
    ])
    expect(run.parts[0]).toMatchObject({ preview: ['芬'], overflow: 2, tail: ['红', '陈'] })
    expect(run.parts[1]).toMatchObject({ kind: 'group', subject: '感知' })
    expect(run.parts[2]).toMatchObject({ preview: [], overflow: 0, tail: [] })
    expect(run.text).toBe('芬、感知、红、陈下班')
  })

  it('uses supplied semantics and historical facility labels without inferring a shift', () => {
    const task = {
      type: { display_value: '下班' },
      presentation: {
        title: '甲组下班、乙组上班',
        rooms: [{ id: 'room_3_3', label: '发电站 B303', agents: ['Current', '阿米娅'] }]
      }
    }
    expect(queueTaskTitle(task)).toBe('甲组下班、乙组上班')
    expect(queueTaskRoom(task, 'room_3_3', { room_3_3: { name: '制造站' } })).toBe('发电站 B303')
  })

  it('translates an old room target but preserves unrelated task parameters', () => {
    expect(queueTaskTarget({ meta_data: 'room_2_1' }, { room_2_1: { name: '贸易站' } })).toBe(
      '贸易站 B201'
    )
    expect(queueTaskTarget({ meta_data: '1-7' }, {})).toBe('1-7')
    expect(queueTaskTarget({ meta_data: 'room_2_1-extra' }, {})).toBe('room_2_1-extra')
  })

  it('keeps source text as fallback when forecast metadata is incomplete', () => {
    expect(taskPresentation({ title: '公招' }, true)).toBeNull()
    expect(
      taskPresentation(
        {
          title: '公招',
          header: '稍后公招',
          rooms: [{ id: 'room_1_1', label: 'B101', agents: [null] }]
        },
        true
      )
    ).toBeNull()
    expect(taskPresentation({ title: '公招', header: '稍后公招' }, true)).toMatchObject({
      rooms: [],
      backups: [],
      targets: []
    })
  })

  it('keeps activation and deactivation names separate', () => {
    const changes = [
      { name: '夜班', active: true },
      { name: '白班', active: false },
      { name: '活动', active: true }
    ]
    expect(backupChangeText(changes, true)).toBe('夜班、活动')
    expect(backupChangeText(changes, false)).toBe('白班')
  })

  it('accepts optional explicit actions and rejects malformed action metadata', () => {
    expect(taskPresentation({ title: '空任务' }).actions).toEqual([])
    expect(
      taskPresentation({
        title: '红松上班',
        actions: [{ kind: 'group', subject: '红松', action: '上班' }]
      })
    ).toMatchObject({ actions: [{ kind: 'group', subject: '红松', action: '上班' }] })
    expect(
      taskPresentation({
        title: '红松上班',
        actions: [{ kind: 'group', subject: '红松', action: '站岗' }]
      })
    ).toBeNull()
  })
  it('retains an explicit idle transition in task rows and recognizes its adjacent operator name', () => {
    const actions = [
      { kind: 'operator', subject: '桑葚', action: '休息' },
      { kind: 'operator', subject: '陈', action: '转为空闲' }
    ]
    const presentation = { title: '桑葚休息；陈转为空闲', actions }
    expect(taskPresentation(presentation)).toMatchObject(presentation)
    const task = { time: '2026-11-05T14:58:49', plan: {}, presentation }
    const [row] = queueTaskRows([task], ['桑葚', '陈'])
    expect(row.actions).toEqual(actions)
    expect(actionSubjectRuns(row.actions).map((run) => run.text)).toEqual([
      '桑葚休息',
      '陈转为空闲'
    ])
    expect(queueTaskTokens(task, ['桑葚', '陈'])).toEqual([
      { type: 'operator', text: '桑葚', name: '桑葚' },
      { type: 'text', text: '休息；' },
      { type: 'operator', text: '陈', name: '陈' },
      { type: 'text', text: '转为空闲' }
    ])
    expect(
      taskPresentation({ ...presentation, header: '随后执行「桑葚休息；陈转为空闲」' }, true)
        ?.actions
    ).toEqual(actions)
  })

  it('falls back to the real task label for a presentation with an empty title', () => {
    expect(queueTaskTitle({ presentation: { title: '' }, type: { display_value: '空任务' } })).toBe(
      '空任务'
    )
    expect(queueTaskTitle({ presentation: { title: '' } })).toBe('空任务')
  })

  it.each([
    ['28分55秒', '28 分 55 秒'],
    ['28 分 55 秒', '28 分 55 秒'],
    ['1小时2分3秒', '1 小时 2 分 3 秒'],
    ['1 小时 2 分 3 秒', '1 小时 2 分 3 秒']
  ])(
    'keeps a recorded task title in a wait-only forecast header: %s',
    (duration, displayedDuration) => {
      const header = `休息 ${duration}，至 12:31:33`
      const displayed = `休息 ${displayedDuration}，至 12:31:33`
      const recorded = {
        title: '用尽下班',
        header,
        rooms: [],
        targets: [],
        backups: []
      }
      expect(taskPresentation(recorded, true).header).toBe(`${displayed}，随后执行「用尽下班」`)
      expect(recorded.header).toBe(header)
      expect(
        taskPresentation({ ...recorded, header: `${header}，随后执行「用尽下班」` }, true).header
      ).toBe(`${displayed}，随后执行「用尽下班」`)
      expect(taskPresentation({ ...recorded, title: '' }, true).header).toBe(displayed)
    }
  )

  it('does not append metadata that the backend has already used as the complete label', () => {
    expect(
      queueTaskText({ display_name: '替班心情检查：白面鸮', meta_data: '替班心情检查：白面鸮' })
    ).toBe('替班心情检查：白面鸮')
    expect(queueTaskText({ display_name: '替班心情检查：白面鸮', meta_data: '白面鸮' })).toBe(
      '替班心情检查：白面鸮'
    )
    expect(queueTaskText({ display_name: '检查芬', meta_data: '芬' })).toBe('检查芬 芬')
    expect(queueTaskText({ display_name: '扫描仓库', meta_data: '全部物品' })).toBe(
      '扫描仓库 全部物品'
    )
  })

  it('keeps explicit group subjects distinct from operator names', () => {
    const task = {
      plan: { meeting: ['芬'] },
      presentation: {
        title: '红松上班；芬休息',
        actions: [
          { kind: 'group', subject: '红松', action: '上班' },
          { kind: 'operator', subject: '芬', action: '休息' }
        ]
      }
    }
    expect(queueTaskTokens(task, ['红松', '芬'])).toEqual([
      { type: 'group', text: '红松', name: '红松' },
      { type: 'text', text: '上班；' },
      { type: 'operator', text: '芬', name: '芬' },
      { type: 'text', text: '休息' }
    ])
  })

  it('keeps the charging action in the heading and the confirmed target in its details', () => {
    const task = {
      display_name: '肥鸭',
      meta_data: '伊内丝',
      plan: { dormitory_2: ['伊内丝', '菲亚梅塔'] },
      presentation: {
        title: '肥鸭 充 伊内丝',
        rooms: [{ id: 'dormitory_2', label: '宿舍2', agents: ['伊内丝', '菲亚梅塔'] }]
      }
    }

    expect(queueTaskText(task)).toBe('菲亚梅塔充能')
    expect(queueTaskTokens(task, ['菲亚梅塔', '伊内丝'])).toEqual([
      { type: 'text', text: '菲亚梅塔充能' }
    ])
    expect(queueTaskRows([task])[0].chargingTarget).toBe('伊内丝')
    expect(
      queueTaskRows([{ ...task, presentation: { title: '肥鸭' } }])[0].chargingTarget
    ).toBeNull()
  })

  it('uses clear queue names for legacy charging and clue exchange tasks', () => {
    expect(queueTaskTitle({ type: { _value_: '菲亚梅塔', display_value: '肥鸭' } })).toBe(
      '菲亚梅塔充能'
    )
    expect(queueTaskTitle({ type: '趴体' })).toBe('线索交流')
    expect(queueTaskTitle({ type: '线索任务' })).toBe('线索任务')
  })

  it('marks the explicit mastery step, preserves skill names and recognizes the swap target', () => {
    const task = {
      type: { display_value: '换协助位' },
      meta_data: '焰狐龙梓兰 二技能·飞翔瞪射 专二 → 专三 换入逻各斯'
    }
    expect(queueTaskTokens(task)).toEqual([{ type: 'text', text: '自动专精换协助位' }])
    expect(queueTaskTitle({ presentation: { title: '自动专精换协助位' } })).toBe('自动专精换协助位')
    const detail = queueMasteryDetails(task, ['焰狐龙梓兰', '逻各斯', '翔'])
    expect(detail).toMatchObject({ room: 'train', label: '训练室' })
    const { tokens } = detail
    expect(tokens.filter((token) => token.type === 'operator').map((token) => token.name)).toEqual([
      '焰狐龙梓兰',
      '逻各斯'
    ])
    expect(tokens.filter((token) => token.type === 'mastery')).toEqual([
      { type: 'mastery', text: '专二 → 专三', levels: [2, 3] }
    ])
    expect(tokens.map((token) => token.text).join('')).toBe(
      '焰狐龙梓兰 二技能·飞翔瞪射 专二 → 专三 换入逻各斯'
    )
    expect(
      queueMasteryDetails({ display_name: '技能专精', meta_data: '芬 专三' }, ['芬'])
        .tokens.filter((token) => token.type === 'mastery')
        .map((token) => token.levels)
    ).toEqual([[3]])
    expect(
      queueMasteryDetails({ type: '技能专精', meta_data: '芬 未专精 → 专一' }, ['芬'])
        .tokens.filter((token) => token.type === 'mastery')
        .map((token) => token.levels)
    ).toEqual([[0, 1]])
    expect(
      queueMasteryDetails({ type: '技能专精', meta_data: '焰狐龙梓兰 专精等级未知' }, [
        '焰狐龙梓兰'
      ]).tokens.filter((token) => token.type === 'mastery')
    ).toEqual([])
  })

  it('preserves a generic mastery recheck description without inventing a facility target or skill', () => {
    const task = {
      presentation: { title: '自动专精' },
      meta_data: '等待加工完成后重检'
    }
    expect(queueTaskTokens(task)).toEqual([{ type: 'text', text: '自动专精' }])
    expect(queueMasteryDetails(task)).toEqual({
      room: null,
      label: null,
      tokens: [{ type: 'text', text: '等待加工完成后重检' }]
    })
    expect(queueMasteryDetails({ display_name: '跑单' })).toBeNull()
  })
})
