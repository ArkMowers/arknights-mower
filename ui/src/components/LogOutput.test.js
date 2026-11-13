import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, reactive, ssrContextKey } from 'vue'
import { NButton, NIcon, NPopover, NScrollbar } from 'naive-ui'
import DetailChevron from '@vicons/ionicons5/es/ChevronDownOutline'
import JumpToLatestButton from './JumpToLatestButton.vue'
import LogOperator from './LogOperator.vue'
import LogInventory from './LogInventory.vue'
import LogItemToken from './LogItemToken.vue'
import LogStage from './LogStage.vue'
import LogOutput from './LogOutput.vue'
import TaskActionSubjects from './TaskActionSubjects.vue'

const instances = vi.hoisted(() => ({ operator: 0 }))
vi.mock('naive-ui', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    NButton: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('button', [slots.icon?.(), slots.default?.()])
    }),
    NIcon: defineComponent({
      props: ['component'],
      setup: (props) => () => h(props.component)
    }),
    NPopover: defineComponent({
      props: { show: Boolean },
      setup:
        (props, { slots }) =>
        () =>
          h('span', [
            slots.trigger?.(),
            props.show ? h('aside', { 'data-action-popover': true }, slots.default?.()) : null
          ])
    }),
    NScrollbar: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          h('div', slots.default?.())
    })
  }
})
vi.mock('@/components/LogOperator.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    default: defineComponent({
      props: { name: String, showName: Boolean, size: Number },
      setup(props) {
        const instance = ++instances.operator
        return () =>
          h(
            'span',
            {
              'data-operator-name': props.name,
              'data-operator-instance': instance,
              'data-operator-size': props.size
            },
            [
              h('img', { alt: '', src: `/avatar/${encodeURIComponent(props.name)}.webp` }),
              props.showName ? h('span', props.name) : null
            ]
          )
      }
    })
  }
})

const { descriptor } = parse(readFileSync(new URL('./LogOutput.vue', import.meta.url), 'utf8'))
const subjectDescriptor = parse(
  readFileSync(new URL('./TaskActionSubjects.vue', import.meta.url), 'utf8')
).descriptor
const clientSubjects = {
  ...TaskActionSubjects,
  components: { NPopover, LogOperator },
  ssrRender: undefined,
  render: compile(subjectDescriptor.template.content),
  setup: (props, context) => ({ ...TaskActionSubjects.setup(props, context) })
}
const clientOutput = {
  ...LogOutput,
  components: {
    NScrollbar,
    JumpToLatestButton: {
      ...JumpToLatestButton,
      components: { NButton, NIcon },
      ssrRender: undefined,
      render: compile(
        parse(readFileSync(new URL('./JumpToLatestButton.vue', import.meta.url), 'utf8')).descriptor
          .template.content
      ),
      setup: (props, context) => ({ ...JumpToLatestButton.setup(props, context) })
    },
    DetailChevron,
    LogOperator,
    TaskActionSubjects: clientSubjects,
    LogItemToken: {
      ...LogItemToken,
      components: { LogOperator },
      ssrRender: undefined,
      render: compile(
        parse(readFileSync(new URL('./LogItemToken.vue', import.meta.url), 'utf8')).descriptor
          .template.content
      ),
      setup: (props, context) => ({ ...LogItemToken.setup(props, context) })
    },
    LogStage: {
      ...LogStage,
      components: { NPopover },
      ssrRender: undefined,
      render: compile(
        parse(readFileSync(new URL('./LogStage.vue', import.meta.url), 'utf8')).descriptor.template
          .content
      ),
      setup: (props, context) => ({ ...LogStage.setup(props, context) })
    },
    LogInventory: {
      ...LogInventory,
      ssrRender: undefined,
      render: compile(
        parse(readFileSync(new URL('./LogInventory.vue', import.meta.url), 'utf8')).descriptor
          .template.content
      ),
      setup: (props, context) => ({ ...LogInventory.setup(props, context) })
    }
  },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...LogOutput.setup(props, context) })
}
const mounted = []

describe('explicit grouped observations', () => {
  it('updates the depot heading independently of the timestamped latest log and folds it on completion', async () => {
    const parent = { type: 'depot-scan', id: 'warehouse-visit' }
    const record = (id, time, msg, fields = {}) => ({
      id,
      group: 'depot-recognition',
      parent,
      text: `2026-11-06 ${time} INFO ${msg}`,
      ...fields
    })
    const progress = (id, time, phase, summary) =>
      record(id, time, summary, {
        event: { ...parent, phase, summary, anchor: phase === 'started' }
      })
    const start = progress(1, '20:55:58', 'started', '仓库扫描，正在同步森空岛库存')
    const first = record(2, '20:56:02', 'Scene 1: 首页', { group: 'recognition' })
    const update = progress(3, '20:56:03', 'updated', '仓库扫描，正在识别消耗物品')
    const unrelated = record(4, '20:56:04', '读取其他设施', {
      parent: { ...parent, id: 'other-visit' }
    })
    const warning = {
      ...record(5, '20:56:05', '个别物品数量未读出'),
      text: '2026-11-06 20:56:05 WARNING 个别物品数量未读出'
    }
    const latest = record(6, '20:56:06', 'Scene 1301: 仓库', { group: 'recognition' })
    const result = record(7, '20:56:13', '仓库扫描：已识别1种物品\n龙门币：200', {
      inventory: { items: [{ name: '龙门币', count: 200 }] }
    })
    const complete = progress(8, '20:56:14', 'completed', '仓库扫描完成，已识别 1 种物品')
    const page = mount({ lines: [start, first], concise: true, running: true })
    const heading = () => page.all().find((entry) => hasClass(entry, 'log-depot-scan'))
    const preview = () => page.all().find((entry) => hasClass(entry, 'log-live-detail'))
    const source = (id) => page.rows().find((entry) => entry.props['data-log-key'] === `id:${id}`)
    const anchor = heading()
    expect(hasClass(anchor, 'log-lifecycle-active')).toBe(true)
    expect(visibleText(preview())).toBe('20:56:02Scene 1: 首页')

    page.props.lines.push(update, unrelated, warning)
    await nextTick()
    expect(heading()).toBe(anchor)
    expect(visibleText(heading())).toBe(update.event.summary)
    expect(visibleText(heading().parent)).toContain('20:55:58')
    expect(visibleText(preview())).toBe('20:56:02Scene 1: 首页')
    expect(visibleText(source(4))).toContain('读取其他设施')
    expect(visibleText(source(5))).toContain('个别物品数量未读出')

    page.props.lines.push(latest)
    await nextTick()
    expect(visibleText(preview())).toBe('20:56:06Scene 1301: 仓库')
    expect(preview().props['data-log-detail-source']).toBe(latest.text)
    expect(visibleText(source(2))).toBe('')
    expect(visibleText(source(6))).toBe('')

    page.props.lines.push(result)
    await nextTick()
    expect(visibleText(preview())).toBe('20:56:13仓库扫描：已识别1种物品')
    page.props.lines.push(complete)
    await nextTick()
    expect(heading()).toBe(anchor)
    expect(visibleText(heading())).toBe(complete.event.summary)
    expect(hasClass(heading(), 'log-lifecycle-active')).toBe(false)
    expect(preview()).toBeUndefined()
    expect(visibleText(source(6))).toBe('')

    const toggle = page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
    await toggle.props.onClick()
    expect(visibleText(source(2))).toContain('20:56:02Scene 1: 首页')
    expect(visibleText(source(6))).toContain('20:56:06Scene 1301: 仓库')
    expect(visibleText(source(7))).toContain('龙门币')
    expect(preview()).toBeUndefined()
  })

  it('updates one mood calculation heading without moving its time or losing its source lines', async () => {
    const label = '基建调度'
    const source = (id, second, phase, summary) => ({
      id,
      text: `2026-11-06 20:35:${second} INFO ${summary}`,
      group: 'base-scheduler',
      event: {
        type: 'mood-calculation',
        id: 'calculation',
        label,
        phase,
        anchor: phase === 'started',
        summary
      }
    })
    const start = source(
      1,
      '05',
      'started',
      '基建调度：正在根据已有的心情读数、设施内的干员和基建技能，推算干员工作或休息时的心情变化（先更新设施和基建技能资料）'
    )
    const update = source(2, '06', 'updated', '基建调度：已开始推算心情和变化速度')
    const terminal = source(
      3,
      '07',
      'completed',
      '基建调度：心情推算用时 0.500 秒（更新设施和基建技能资料 0.002 秒、推算心情和变化速度 0.498 秒）'
    )
    const page = mount({ lines: [start], running: true })
    const summaries = () => page.all().filter((entry) => hasClass(entry, 'log-mood-calculation'))
    const heading = summaries()[0]
    expect(visibleText(heading)).toBe(start.event.summary)
    expect(hasClass(heading, 'log-lifecycle-active')).toBe(true)

    page.props.lines.push(update)
    await nextTick()
    expect(summaries()).toEqual([heading])
    expect(visibleText(heading)).toBe(update.event.summary)
    expect(visibleText(heading.parent)).toContain('20:35:05')
    expect(visibleText(page.rows().at(-1))).toBe('')

    page.props.running = false
    await nextTick()
    expect(visibleText(heading)).toBe('基建调度：心情推算尚未完成')
    expect(hasClass(heading, 'log-lifecycle-active')).toBe(false)
    page.props.running = true
    await nextTick()
    expect(hasClass(heading, 'log-lifecycle-active')).toBe(false)

    page.props.lines.push(terminal)
    await nextTick()
    expect(summaries()).toEqual([heading])
    expect(visibleText(heading)).toBe(terminal.event.summary)
    expect(hasClass(heading, 'log-lifecycle-active')).toBe(false)
    expect(visibleText(page.rows().at(-1))).toBe('')
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual([
      start.text,
      update.text,
      terminal.text
    ])

    page.props.lines = [terminal]
    await nextTick()
    expect(summaries()).toHaveLength(0)
    expect(visibleText(page.rows()[0])).toContain(terminal.event.summary)
  })

  it('previews only the latest owned mood detail and opens the original chronological records', async () => {
    const parent = { type: 'mood-calculation', id: 'planning-batch' }
    const label = '基建调度'
    const line = (id, second, message, scope = parent, level = 'INFO') => ({
      id,
      text: `2026-11-06 20:35:${second} ${level} ${message}`,
      group: 'base-scheduler',
      parent: scope
    })
    const lifecycle = (id, second, phase, summary) => ({
      ...line(id, second, summary),
      event: { ...parent, label, phase, anchor: phase === 'started', summary }
    })
    const before = line(1, '04', '推算前检查')
    const start = lifecycle(2, '05', 'started', '基建调度：正在推算干员工作或休息时的心情变化')
    const first = line(3, '06', '更新设施和基建技能资料（推算从已有心情读数开始）')
    const latest = line(4, '08', '推算达到目标心情的时间')
    const unrelated = line(5, '09', '另一批心情推算', { ...parent, id: 'other-batch' })
    const differentType = line(6, '10', '另一业务的进度', { ...parent, type: 'depot-scan' })
    const warning = line(7, '11', '缺少一处设施的心情读数', parent, 'WARNING')
    const timing = line(
      8,
      '12',
      '分项耗时：更新设施和基建技能资料 0.002 秒、推算达到目标心情的时间 0.498 秒'
    )
    const terminal = lifecycle(9, '13', 'completed', '基建调度：心情推算完成，耗时 0.500 秒')
    const page = mount({ lines: [before, start, first], running: true, concise: true })
    const heading = () => page.all().find((entry) => hasClass(entry, 'log-mood-calculation'))
    const preview = () => page.all().find((entry) => hasClass(entry, 'log-live-detail'))
    const row = (record) =>
      page.rows().find((entry) => entry.props['data-log-source'] === record.text)
    const toggle = () => page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))

    expect(visibleText(heading())).toBe(start.event.summary)
    expect(hasClass(heading(), 'log-lifecycle-active')).toBe(true)
    expect(visibleText(preview())).toContain('更新设施和基建技能资料（推算从已有心情读数开始）')
    expect(visibleText(row(first))).toBe('')
    expect(visibleText(row(before))).toContain('推算前检查')

    page.props.lines.push(latest, unrelated, differentType, warning)
    await nextTick()
    expect(visibleText(preview())).toBe('20:35:08推算达到目标心情的时间')
    expect(hasClass(preview(), 'log-lifecycle-active')).toBe(false)
    expect(visibleText(row(latest))).toBe('')
    expect(visibleText(row(unrelated))).toContain('另一批心情推算')
    expect(visibleText(row(differentType))).toContain('另一业务的进度')
    expect(visibleText(row(warning))).toContain('缺少一处设施的心情读数')
    expect(row(warning).props['data-log-level']).toBe('WARNING')

    await toggle().props.onClick()
    expect(preview()).toBeUndefined()
    expect(visibleText(row(first))).toContain('20:35:06')
    expect(visibleText(row(latest))).toContain('20:35:08')
    expect(page.rows().indexOf(row(first))).toBeLessThan(page.rows().indexOf(row(latest)))
    await toggle().props.onClick()

    page.props.lines.push(timing, terminal)
    await nextTick()
    expect(preview()).toBeUndefined()
    expect(hasClass(heading(), 'log-lifecycle-active')).toBe(false)
    expect(visibleText(heading())).toBe(terminal.event.summary)
    expect(visibleText(heading().parent)).toContain('20:35:05')
    expect(visibleText(row(latest))).toBe('')
    expect(visibleText(row(timing))).toBe('')
    await toggle().props.onClick()
    expect(visibleText(row(timing))).toContain('分项耗时：')
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      page.props.lines.map((record) => record.text)
    )
  })

  it.each([
    ['制造站 B102', '产物为中级作战记录', '贸易站'],
    ['贸易站 B102', '订单类型为龙门商法', '制造站']
  ])('updates the %s observation in place', async (label, state, configuredName) => {
    const room = 'room_1_2'
    const event = { type: 'facility-observation', id: 'facility-scan', room, label }
    const started = `${label}：${state}，正在读取干员心情`
    const completed = `${label}：${state}，[[operator:阿罗玛]]（心情6.348）、空位、[[operator:乌尔比安]]（心情未确认）`
    const source = (id, second, summary, phase, agents = []) => ({
      id,
      text: `2026-11-06 20:34:${second} INFO ${summary}`,
      group: 'base-scheduler',
      room,
      agents,
      event: { ...event, phase, anchor: phase === 'started', summary, agents }
    })
    const anchor = source(1, '10', started, 'started')
    const scene = logLine(2, '2026-11-06 20:34:11 INFO Scene 205: 基建放大查看', 'recognition')
    const terminal = source(3, '14', completed, 'completed', ['阿罗玛', '乌尔比安'])
    const page = mount({
      lines: [anchor, scene],
      running: true,
      facilityPlan: { [room]: { name: configuredName } }
    })
    const summaries = () =>
      page.all().filter((entry) => hasClass(entry, 'log-facility-observation'))
    const summary = summaries()[0]
    expect(visibleText(summary)).toBe(started)
    expect(hasClass(summary, 'log-lifecycle-active')).toBe(true)
    expect(all(summary).find((entry) => entry.props['data-room-id'] === room).text).toBe(label)

    page.props.lines.push(terminal)
    await nextTick()

    expect(summaries()).toEqual([summary])
    expect(visibleText(summary.parent)).toContain('20:34:10')
    expect(visibleText(summary)).toBe(completed.replace(/\[\[operator:([^\]]+)\]\]/gu, '$1'))
    expect(hasClass(summary, 'log-lifecycle-active')).toBe(false)
    expect(portraits(summary).map((entry) => entry.props['data-operator-name'])).toEqual([
      '阿罗玛',
      '乌尔比安'
    ])
    expect(all(summary).some((entry) => hasClass(entry, 'log-token--item'))).toBe(true)
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual([
      anchor.text,
      scene.text,
      terminal.text
    ])
    expect(hasClass(page.rows().at(-1), 'log-line--source-only')).toBe(true)

    page.props.lines = [scene, terminal]
    await nextTick()
    expect(summaries()).toHaveLength(0)
    expect(visibleText(page.rows().at(-1))).toContain(state)
  })

  it('updates one rescue parent and keeps complete slots plus explicitly scoped facility details below it', async () => {
    const rooms = [
      {
        room: 'dormitory_2',
        label: '宿舍2',
        agents: ['Current', 'Current', 'Current', '桑葚', 'Current'],
        status: 'pending'
      }
    ]
    const event = { type: 'rescue-staffing', id: 'rescue-A', phase: 'queued', anchor: true, rooms }
    const parent = {
      type: 'rescue-staffing',
      id: event.id,
      room: rooms[0].room,
      attempt: 'attempt-A'
    }
    const facility = {
      type: 'facility-arrangement',
      id: parent.attempt,
      phase: 'started',
      anchor: true,
      room: parent.room,
      label: '宿舍2',
      agents: ['桑葚']
    }
    const lines = [
      { id: 3000, event, text: '2026-11-05 18:00:00 INFO 已生成救急换班任务，等待执行' },
      {
        id: 3001,
        event: {
          ...event,
          phase: 'started',
          anchor: false,
          rooms: [{ ...rooms[0], status: 'active' }]
        },
        text: '2026-11-05 18:00:01 INFO 正在执行救急换班任务'
      },
      {
        id: 3002,
        parent,
        event: facility,
        room: parent.room,
        text: '2026-11-05 18:00:02 INFO 宿舍2'
      },
      {
        id: 3003,
        parent,
        room: parent.room,
        agents: ['桑葚'],
        text: '2026-11-05 18:00:03 INFO 选择 [[operator:桑葚]]'
      },
      { id: 3004, text: '2026-11-05 18:00:04 INFO 与救急任务无关的记录' },
      {
        id: 3005,
        parent,
        event: { ...facility, phase: 'completed', anchor: false, agents: ['桑葚', '阿米娅'] },
        text: '2026-11-05 18:00:05 INFO 已安排桑葚、阿米娅进驻宿舍2'
      },
      {
        id: 3006,
        event: {
          ...event,
          phase: 'completed',
          anchor: false,
          rooms: [{ ...rooms[0], status: 'completed' }]
        },
        text: '2026-11-05 18:00:06 INFO 救急换班任务已完成'
      }
    ]
    const page = mount({ running: true, lines: lines.slice(0, 4) })
    const block = page.all().find((entry) => hasClass(entry, 'log-rescue-block'))
    expect(block).toBeDefined()
    const preview = () => all(block).find((entry) => hasClass(entry, 'log-live-detail'))
    expect(visibleText(preview())).toContain('18:00:03选择 桑葚')
    page.props.lines.push(...lines.slice(4))
    await nextTick()
    expect(visibleText(block)).toContain('救急换班任务已完成')
    expect(preview()).toBeUndefined()
    expect(visibleText(block)).not.toContain('选择 桑葚')
    await all(block)
      .find((entry) => hasClass(entry, 'log-detail-toggle'))
      .props.onClick()
    expect(visibleText(block)).toContain('选择 桑葚')
    expect(visibleText(block)).not.toContain('与救急任务无关')
    const slots = all(block).find((entry) => hasClass(entry, 'log-rescue-room'))
    expect(portraits(slots).map((entry) => entry.props['data-operator-name'])).toEqual(
      rooms[0].agents
    )
    expect(portraits(slots).every((entry) => entry.props['data-operator-size'] === 24)).toBe(true)
    expect(all(block).filter((entry) => hasClass(entry, 'log-arrangement'))).toHaveLength(1)
    expect(
      page
        .rows()
        .filter((entry) => !entry.props['data-log-rescue-mirror'])
        .map((entry) => entry.props['data-log-source'])
    ).toEqual(lines.map((line) => line.text))
  })
  it('does not move a foreign or unscoped record into an interleaved rescue task for the same room', async () => {
    const rooms = [{ room: 'meeting', label: '会客室', agents: ['阿米娅'], status: 'pending' }]
    const queued = (id) => ({ type: 'rescue-staffing', id, phase: 'queued', anchor: true, rooms })
    const scoped = (id, attempt) => ({ type: 'rescue-staffing', id, room: 'meeting', attempt })
    const facility = (id) => ({
      type: 'facility-arrangement',
      id,
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    })
    const page = mount({
      running: true,
      lines: [
        { id: 3010, event: queued('A'), text: 'INFO 已生成救急换班任务A' },
        { id: 3011, event: queued('B'), text: 'INFO 已生成救急换班任务B' },
        { id: 3012, parent: scoped('A', 'a'), event: facility('a'), text: 'INFO 会客室' },
        { id: 3013, parent: scoped('B', 'b'), event: facility('b'), text: 'INFO 会客室' },
        { id: 3014, parent: scoped('A', 'a'), text: '2026-11-05 18:00:05 ERROR A选人未确认' },
        { id: 3015, parent: scoped('B', 'b'), text: 'INFO B读取名单' },
        {
          id: 3016,
          parent: scoped('missing', 'orphan'),
          event: facility('orphan'),
          text: 'INFO 会客室'
        },
        { id: 3017, text: 'INFO 无归属记录' }
      ]
    })
    const blocks = page.all().filter((entry) => hasClass(entry, 'log-rescue-block'))
    expect(blocks).toHaveLength(2)
    for (const block of blocks)
      await all(block)
        .find((entry) => hasClass(entry, 'log-detail-toggle'))
        .props.onClick()
    expect(visibleText(blocks[0])).toContain('A选人未确认')
    expect(visibleText(blocks[0])).not.toContain('B读取名单')
    expect(visibleText(blocks[1])).toContain('B读取名单')
    expect(visibleText(blocks[1])).not.toContain('A选人未确认')
    expect(all(blocks[0]).some((entry) => hasClass(entry, 'log-level--error'))).toBe(true)
  })
  it('keeps failed room states and explicit pre-entry causes, then resumes only after a new real start', async () => {
    const rooms = [
      { room: 'meeting', label: '会客室', agents: ['阿米娅'], status: 'pending' },
      { room: 'dormitory_2', label: '宿舍2', agents: ['Current', '', '桑葚'], status: 'pending' },
      { room: 'room_1_1', label: '制造站 B101', agents: ['陈'], status: 'pending' }
    ]
    const base = {
      type: 'rescue-staffing',
      id: 'retry-parent',
      phase: 'queued',
      anchor: true,
      rooms
    }
    const record = (id, event, extra = {}) => ({
      id,
      event,
      text: `2026-11-05 18:00:00 INFO source-${id}`,
      ...extra
    })
    const update = (phase, states) => ({
      ...base,
      phase,
      anchor: false,
      rooms: rooms.map((room, i) => ({ ...room, status: states[i] }))
    })
    const scope = { type: base.type, id: base.id, room: 'dormitory_2', attempt: 'before-entry' }
    const page = mount({ running: true, lines: [record(3020, base)] })
    const parent = () => page.all().find((node) => hasClass(node, 'log-rescue-summary'))
    expect(visibleText(parent())).toBe('已生成救急换班任务，等待执行')
    expect(hasClass(parent(), 'log-lifecycle-active')).toBe(false)
    const started = update('started', ['completed', 'active', 'pending'])
    page.props.lines.push(record(3021, started))
    await nextTick()
    expect(hasClass(parent(), 'log-lifecycle-active')).toBe(true)
    page.props.running = false
    await nextTick()
    expect(visibleText(parent())).toBe('救急换班任务尚未完成')
    page.props.running = true
    await nextTick()
    expect(hasClass(parent(), 'log-lifecycle-active')).toBe(false)
    page.props.lines.push(
      record(3022, {
        ...update('failed', ['completed', 'unconfirmed', 'pending']),
        detail: '选择尚未确认'
      }),
      record(3023, undefined, {
        parent: scope,
        text: '2026-11-05 18:00:00 ERROR 进房前保护拒绝本次安排'
      })
    )
    await nextTick()
    const block = page.all().find((node) => hasClass(node, 'log-rescue-block'))
    await all(block)
      .find((entry) => hasClass(entry, 'log-detail-toggle'))
      .props.onClick()
    expect(
      all(block)
        .filter((node) => hasClass(node, 'log-rescue-room'))
        .map((node) => node.props['data-rescue-status'])
    ).toEqual(['completed', 'unconfirmed', 'pending'])
    expect(visibleText(block)).toContain('进房前保护拒绝本次安排')
    expect(all(block).filter((node) => hasClass(node, 'log-arrangement'))).toHaveLength(0)
    page.props.lines.push(record(3024, started))
    await nextTick()
    expect(hasClass(parent(), 'log-lifecycle-active')).toBe(true)
    expect(visibleText(block)).toContain('选择尚未确认')
    page.props.lines.push(
      record(3025, update('completed', ['completed', 'completed', 'completed']))
    )
    await nextTick()
    expect(visibleText(parent())).toBe('救急换班任务已完成')
    expect(hasClass(parent(), 'log-lifecycle-active')).toBe(false)
  })
  it('shows the latest facility attempt as the room summary and retains the older failure as history', async () => {
    const rooms = [
      { room: 'meeting', label: '会客室', agents: ['Current', '阿米娅'], status: 'active' }
    ]
    const event = {
      type: 'rescue-staffing',
      id: 'attempt-parent',
      phase: 'queued',
      anchor: true,
      rooms
    }
    const scope = (attempt) => ({ type: event.type, id: event.id, room: 'meeting', attempt })
    const facility = (id, phase, agents = ['阿米娅']) => ({
      type: 'facility-arrangement',
      id,
      phase,
      anchor: phase === 'started',
      room: 'meeting',
      label: '会客室',
      agents
    })
    const page = mount({
      running: true,
      lines: [
        { id: 3030, event, text: 'INFO 已生成救急换班任务，等待执行' },
        {
          id: 3031,
          event: { ...event, phase: 'started', anchor: false },
          text: 'INFO 正在执行救急换班任务'
        },
        { id: 3032, event: facility('old', 'started'), parent: scope('old'), text: 'INFO 会客室' },
        {
          id: 3033,
          event: facility('old', 'failed'),
          parent: scope('old'),
          text: '2026-11-05 18:00:00 WARNING 首次选人未确认'
        },
        { id: 3034, event: facility('new', 'started'), parent: scope('new'), text: 'INFO 会客室' },
        {
          id: 3035,
          event: facility('new', 'completed', ['阿米娅', '陈']),
          parent: scope('new'),
          text: 'INFO 已安排阿米娅、陈进驻会客室'
        }
      ]
    })
    const block = page.all().find((node) => hasClass(node, 'log-rescue-block'))
    await all(block)
      .find((entry) => hasClass(entry, 'log-detail-toggle'))
      .props.onClick()
    const summaries = all(block).filter((node) => hasClass(node, 'log-arrangement'))
    expect(summaries.map(visibleText)).toEqual([
      '已安排阿米娅、陈进驻会客室',
      '尚未确认阿米娅进驻会客室'
    ])
    expect(
      all(block).filter(
        (node) => hasClass(node, 'log-facility-heading') && hasClass(node, 'log-rescue-history')
      )
    ).toHaveLength(1)
    expect(visibleText(block)).toContain('首次选人未确认')
    expect(
      portraits(all(block).find((node) => hasClass(node, 'log-rescue-room'))).map(
        (node) => node.props['data-operator-name']
      )
    ).toEqual(['Current', '阿米娅'])
  })
  it('updates the actual facility anchor in place without creating a separate arrangement line', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'actual-room-entry',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['克莱门莎', '跃跃']
    }
    const first = {
      id: 930,
      group: 'base-scheduler',
      room: 'meeting',
      event,
      text: '2026-11-05 17:47:22 INFO 会客室'
    }
    const detail = {
      id: 931,
      group: 'base-scheduler',
      room: 'meeting',
      agents: event.agents,
      text: '2026-11-05 17:47:22 INFO 安排干员：[[operator:克莱门莎]]、[[operator:跃跃]] → 会客室'
    }
    const page = mount({ running: true, lines: [first, detail] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(hasClass(summary().parent, 'log-facility-heading')).toBe(true)
    expect(visibleText(summary().parent)).toContain('17:47:22')
    page.props.lines = [
      first,
      detail,
      {
        id: 932,
        group: 'base-scheduler',
        room: 'meeting',
        event: { ...event, anchor: false, phase: 'completed' },
        text: '2026-11-05 17:48:07 INFO 已安排 克莱门莎、跃跃 进驻 会客室'
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('已安排克莱门莎、跃跃进驻会客室')
    expect(page.all().filter((entry) => hasClass(entry, 'log-arrangement'))).toHaveLength(1)
    expect(page.all().filter((entry) => hasClass(entry, 'log-facility-heading'))).toHaveLength(1)
    expect(visibleText(page.root ?? summary().parent.parent)).not.toContain(
      '已安排 克莱门莎、跃跃 进驻 会客室'
    )
  })

  it('keeps unanchored legacy calls literal instead of moving a later result before room entry', () => {
    const legacy = {
      type: 'facility-arrangement',
      id: 'outer-call',
      phase: 'started',
      room: 'meeting',
      label: '会客室',
      agents: ['克莱门莎']
    }
    const anchor = { ...legacy, id: 'actual-call', anchor: true }
    const page = mount({
      running: true,
      lines: [
        { id: 933, event: legacy, text: '2026-11-05 17:47:15 INFO 正在安排 克莱门莎 进驻 会客室' },
        { id: 934, room: 'meeting', event: anchor, text: '2026-11-05 17:47:22 INFO 会客室' },
        {
          id: 935,
          event: { ...legacy, phase: 'completed' },
          text: '2026-11-05 17:48:07 INFO 已安排 克莱门莎 进驻 会客室'
        }
      ]
    })
    expect(page.all().filter((entry) => hasClass(entry, 'log-arrangement'))).toHaveLength(1)
    expect(visibleText(page.rows()[0])).toContain('17:47:15正在安排')
    expect(visibleText(page.all().find((entry) => hasClass(entry, 'log-arrangement')))).toBe(
      '正在安排克莱门莎进驻会客室'
    )
  })

  it('keeps the completed dormitory roster at room entry through temporary staffing and detail folding', async () => {
    const room = 'dormitory_1'
    const parent = { type: 'facility-arrangement', id: 'dorm-recovery-order', room }
    const event = { ...parent, label: '宿舍1' }
    const roster = ['冰酿', '闪灵', '菲亚梅塔', '撷英调香师', '苍苔']
    const temporary = `宿舍1：准备将[[operator:苍苔]]调整到第5位，先安排临时阵容`
    const finalSource = `已安排 ${roster.map((name) => `[[operator:${name}]]`).join('、')} 进驻 宿舍1`
    const row = (id, time, message, fields = {}) => ({
      id,
      text: `2026-11-06 ${time} INFO ${message}`,
      group: 'base-scheduler',
      parent,
      ...fields
    })
    const start = row(1, '19:46:54,676', '宿舍1', {
      room,
      event: { ...event, agents: ['苍苔'], phase: 'started', anchor: true }
    })
    const details = [
      row(2, '19:46:59,046', temporary, {
        room,
        agents: ['苍苔'],
        task: {
          title: '临时驻员安排',
          header: temporary,
          rooms: [{ id: room, label: '宿舍1', agents: roster }]
        }
      }),
      row(3, '19:47:00,174', '安排干员：撷英调香师、苍苔 → 1层宿舍', { room }),
      row(4, '19:47:19,268', '宿舍1：已确认苍苔位于第5位，继续按最终名单补齐其余位置', { room }),
      row(5, '19:47:24,573', '任务与当前房间相同，跳过安排dormitory_1人员'),
      row(6, '19:47:25,333', 'Scene 201: 基建全局视角', { group: 'recognition' })
    ]
    const completed = row(7, '19:47:25,333', finalSource, {
      room,
      agents: roster,
      event: { ...event, agents: roster, phase: 'completed', anchor: false }
    })
    const page = mount({ lines: [start, ...details], running: true })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    const detailRow = () => page.rows().find((entry) => entry.props['data-log-key'] === 'id:2')
    expect(portraits(summary()).map((portrait) => portrait.props['data-operator-name'])).toEqual([
      '苍苔'
    ])

    page.props.lines.push(completed)
    await nextTick()
    expect(visibleText(summary())).toBe(`已安排${roster.join('、')}进驻宿舍1`)
    expect(visibleText(summary().parent)).toContain('19:46:54')
    const toggle = page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
    await toggle.props.onClick()
    expect(visibleText(detailRow())).toContain('先安排临时阵容')
    expect(hasClass(page.rows().at(-1), 'log-line--source-only')).toBe(true)

    await toggle.props.onClick()
    page.props.concise = true
    await nextTick()
    expect(hasClass(detailRow(), 'log-line--source-only')).toBe(true)
    expect(visibleText(summary())).toBe(`已安排${roster.join('、')}进驻宿舍1`)

    page.props.lines = [...details, completed]
    await nextTick()
    expect(summary()).toBeUndefined()
    expect(visibleText(detailRow())).toContain('先安排临时阵容')
    expect(page.rows().at(-1).props['data-log-source']).toBe(completed.text)
    expect(visibleText(page.rows().at(-1))).toContain('已安排')
  })

  it('shows retained facility details immediately without replaying the live-line fade', async () => {
    const room = 'dormitory_1'
    const parent = { type: 'facility-arrangement', id: 'detail-reveal', room }
    const start = {
      id: 1,
      text: 'INFO 宿舍1',
      room,
      event: { ...parent, label: '宿舍1', agents: ['苍苔'], phase: 'started', anchor: true }
    }
    const detail = { id: 2, text: 'INFO 核对驻员位置', room, parent }
    const page = mount({ lines: [start], concise: true, running: true })
    const output = page.all().find((entry) => hasClass(entry, 'log-output'))
    const animate = vi.fn(() => ({ finished: Promise.resolve(), cancel: vi.fn() }))
    output.animate = vi.fn()
    output.querySelectorAll = (selector) =>
      selector === '[data-log-detail-owner]'
        ? page
            .rows()
            .filter((row) => row.props['data-log-detail-owner'])
            .map((row) =>
              Object.assign(row, {
                animate,
                dataset: { logDetailOwner: row.props['data-log-detail-owner'] },
                getBoundingClientRect: () => ({ height: 20 })
              })
            )
        : []
    vi.stubGlobal('getComputedStyle', () => ({ opacity: '1' }))
    page.props.lines.push(detail)
    await nextTick()
    expect(visibleText(page.rows().at(-1))).toBe('')
    expect(visibleText(page.all().find((entry) => hasClass(entry, 'log-live-detail')))).toContain(
      '核对驻员位置'
    )

    const toggle = page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
    await toggle.props.onClick()
    expect(visibleText(page.rows().at(-1))).toContain('核对驻员位置')
    expect(page.all().some((entry) => hasClass(entry, 'log-live-detail'))).toBe(false)
    expect(animate).not.toHaveBeenCalled()
    expect(hasClass(page.rows().at(-1), 'log-line--enter')).toBe(false)
  })

  it.each(['completed', 'stopped'])(
    'keeps one current associated detail until the facility %s',
    async (finish) => {
      const room = 'dormitory_1'
      const parent = { type: 'facility-arrangement', id: 'fiammetta-entry', room }
      const event = { ...parent, label: '宿舍1', agents: ['菲亚梅塔', '苍苔'] }
      const line = (id, time, level, msg, scope = parent) => ({
        id,
        group: 'base-scheduler',
        text: `2026-11-06 ${time} ${level} ${msg}`,
        parent: scope
      })
      const earlyWarning = line(1, '20:37:33', 'WARNING', '未确认进入宿舍1，返回首页后重新定位')
      const earlyNavigation = line(2, '20:37:35', 'INFO', '场景图导航：back_to_infrastructure')
      const start = {
        ...line(3, '20:38:15', 'INFO', '宿舍1'),
        room,
        event: { ...event, phase: 'started', anchor: true }
      }
      const first = line(4, '20:38:16', 'INFO', '读取当前驻员')
      const latest = line(5, '20:38:17', 'INFO', '核对充能位置')
      const warning = line(6, '20:38:18', 'WARNING', '有一项数据需要复核')
      const unrelated = line(7, '20:38:19', 'INFO', '读取其他设施', { ...parent, id: 'other' })
      const page = mount({
        lines: [earlyWarning, earlyNavigation, start, first],
        running: true,
        concise: true
      })
      const preview = () => page.all().find((entry) => hasClass(entry, 'log-live-detail'))
      const heading = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
      const ordinary = (id) =>
        page.rows().find((entry) => entry.props['data-log-key'] === `id:${id}`)
      expect(visibleText(ordinary(2))).toContain('场景图导航')
      expect(visibleText(preview())).toBe('20:38:16读取当前驻员')
      expect(hasClass(heading(), 'log-lifecycle-active')).toBe(true)
      expect(hasClass(preview(), 'log-lifecycle-active')).toBe(false)

      page.props.lines.push(latest, warning, unrelated)
      await nextTick()
      expect(visibleText(preview())).toBe('20:38:17核对充能位置')
      expect(visibleText(ordinary(5))).toBe('')
      expect(ordinary(6).props['data-log-level']).toBe('WARNING')
      expect(visibleText(ordinary(6))).toContain('需要复核')
      expect(visibleText(ordinary(7))).toContain('读取其他设施')

      const toggle = page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
      await toggle.props.onClick()
      expect(preview()).toBeUndefined()
      expect(visibleText(ordinary(4))).toContain('读取当前驻员')
      expect(visibleText(ordinary(5))).toContain('核对充能位置')
      await toggle.props.onClick()
      expect(visibleText(preview())).toBe('20:38:17核对充能位置')

      if (finish === 'stopped') page.props.running = false
      else
        page.props.lines.push({
          ...line(8, '20:38:22', 'INFO', '已安排菲亚梅塔与苍苔进驻宿舍1'),
          room,
          event: { ...event, phase: 'completed', anchor: false }
        })
      await nextTick()
      expect(preview()).toBeUndefined()
      expect(hasClass(heading(), 'log-lifecycle-active')).toBe(false)
      expect(visibleText(ordinary(2))).toContain('场景图导航')
      expect(visibleText(ordinary(1))).toContain('未确认进入宿舍1')
    }
  )

  it('retains the first explicit anchor when the same operation reenters a facility', () => {
    const event = {
      type: 'facility-arrangement',
      id: 'retry-room',
      phase: 'started',
      anchor: true,
      room: 'dormitory_1',
      label: '宿舍1',
      agents: ['冰酿']
    }
    const page = mount({
      running: true,
      lines: [
        { id: 936, room: event.room, event, text: '2026-11-05 17:48:15 INFO 宿舍1' },
        { id: 937, room: event.room, event, text: '2026-11-05 17:48:31 INFO 宿舍1' },
        {
          id: 938,
          room: event.room,
          event: { ...event, anchor: false, phase: 'completed' },
          text: '2026-11-05 17:49:07 INFO 已安排 冰酿 进驻 宿舍1'
        }
      ]
    })
    const summaries = page.all().filter((entry) => hasClass(entry, 'log-arrangement'))
    expect(summaries).toHaveLength(1)
    expect(visibleText(summaries[0].parent)).toContain('17:48:15')
    expect(visibleText(summaries[0])).toBe('已安排冰酿进驻宿舍1')
  })
  it('returns the waiting animation to a still-pending parent without mixing nested results', () => {
    const parent = {
      type: 'facility-arrangement',
      id: 'nested-parent',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const child = {
      ...parent,
      id: 'nested-child',
      room: 'dormitory_1',
      label: '宿舍1',
      agents: ['陈']
    }
    const lines = [
      { id: 940, event: parent, text: '2026-11-05 17:47:22 INFO 会客室' },
      { id: 941, event: child, text: '2026-11-05 17:47:23 INFO 宿舍1' },
      {
        id: 942,
        event: { ...child, phase: 'completed', anchor: false },
        text: '2026-11-05 17:48:07 INFO 已安排 陈 进驻 宿舍1'
      }
    ]
    const page = mount({ running: true, lines })
    const summaries = page.all().filter((entry) => hasClass(entry, 'log-arrangement'))
    expect(summaries.map(visibleText)).toEqual(['正在安排阿米娅进驻会客室', '已安排陈进驻宿舍1'])
    expect(summaries.map((entry) => hasClass(entry, 'log-lifecycle-active'))).toEqual([true, false])
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      lines.map((entry) => entry.text)
    )
  })
  it('copies lifecycle sources once in order and preserves partial rows around their summary', () => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    const event = {
      type: 'facility-arrangement',
      id: 'copy-anchor',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['克莱门莎']
    }
    const lines = [
      { id: 949, text: '2026-11-05 17:47:20,123 INFO 选中的开头' },
      { id: 950, event, text: '2026-11-05 17:47:22 INFO 会客室' },
      { id: 951, text: '2026-11-05 17:47:23 INFO 确认选择名单' },
      {
        id: 952,
        event: { ...event, phase: 'completed', anchor: false },
        text: '2026-11-05 17:48:07 INFO 已安排 克莱门莎 进驻 会客室'
      },
      { id: 953, text: '2026-11-05 17:48:08,456 INFO 最后一行正文' }
    ]
    const page = mount({ running: true, concise: true, lines })
    const root = page.all().find((entry) => hasClass(entry, 'log-output'))
    const container = page.all().find((entry) => entry.props['aria-label'] === '实时日志')
    root.contains = (entry) => entry === container
    root.querySelectorAll = (selector) =>
      selector === '[data-log-key][data-log-source]'
        ? page
            .all()
            .filter((entry) => entry.props['data-log-key'] && entry.props['data-log-source'])
            .map((entry) => ({
              textContent: text(entry),
              getAttribute: (name) => entry.props[name] ?? null
            }))
        : []
    Object.assign(container, { nodeType: 1, closest: () => null })
    const dom = (entry) => ({
      nodeType: entry.tag === '#text' ? 3 : 1,
      textContent: text(entry),
      classList: { contains: (name) => hasClass(entry, name) },
      getAttribute: (name) => entry.props[name] ?? null,
      childNodes: [
        ...(entry.text ? [{ nodeType: 3, textContent: entry.text }] : []),
        ...entry.children.map(dom)
      ]
    })
    let selected = container.children.map(dom)
    const hasFacilityCopy = (node) =>
      node.getAttribute?.('data-facility-copy') != null || node.childNodes?.some(hasFacilityCopy)
    vi.stubGlobal('getSelection', () => ({
      rangeCount: 1,
      isCollapsed: false,
      toString: () => '',
      getRangeAt: () => ({
        commonAncestorContainer: container,
        cloneContents: () => ({
          nodeType: 11,
          childNodes: selected,
          querySelector: (selector) =>
            selector.includes('[data-facility-copy]') ? selected.find(hasFacilityCopy) : null,
          querySelectorAll: () => []
        })
      })
    }))
    const copy = () => {
      const result = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
      document.addEventListener.mock.calls[0][1](result)
      return result.clipboardData.setData.mock.calls[0][1]
    }
    expect(copy()).toBe(lines.map((entry) => entry.text).join('\n'))
    const copyRow = (id) => dom(page.rows().find((row) => row.props['data-log-key'] === `id:${id}`))
    const partial = copyRow(950)
    partial.textContent = '安排克莱门莎'
    partial.childNodes = [{ nodeType: 3, textContent: partial.textContent }]
    selected = [partial, copyRow(951)]
    expect(copy()).toBe('安排克莱门莎\n' + lines[2].text)

    const first = copyRow(949)
    const stamp = first.childNodes.find((node) => node.classList?.contains('log-stamp'))
    const time = stamp.childNodes.find((node) => node.classList?.contains('log-stamp__time'))
    time.textContent = '47:20'
    time.childNodes = [{ nodeType: 3, textContent: time.textContent }]
    stamp.childNodes = stamp.childNodes.slice(stamp.childNodes.indexOf(time))
    stamp.textContent = stamp.childNodes.map((node) => node.textContent).join('')
    first.textContent = first.childNodes.map((node) => node.textContent).join('')
    const last = copyRow(953)
    const message = last.childNodes.find((node) => node.classList?.contains('log-message'))
    message.textContent = '最后一'
    message.childNodes = [{ nodeType: 3, textContent: message.textContent }]
    last.textContent = last.childNodes.map((node) => node.textContent).join('')
    selected = [first, copyRow(950), copyRow(951), copyRow(952), last]
    expect(copy()).toBe(
      [
        '47:20 选中的开头',
        ...lines.slice(1, -1).map((entry) => entry.text),
        '17:48:08 最后一'
      ].join('\n')
    )
  })
  it('updates a typed production switch at the original parent and nests its latest wait detail immediately below', async () => {
    const event = {
      type: 'production-switch',
      id: 'production-1',
      phase: 'started',
      anchor: true,
      room: 'room_1_2',
      label: '制造站 B102',
      facility: 'manufacture',
      product: '赤金',
      previous: '中级作战记录'
    }
    const first = {
      id: 960,
      event,
      room: event.room,
      text: '2026-11-05 17:50:00 INFO 正在切换制造站 B102 的产物 中级作战记录 → 赤金'
    }
    const technical = { id: 961, text: '2026-11-05 17:50:01 INFO 读取当前生产效率' }
    const detail = '无人机数量不足，当前生产效率为 200%，预计 26 秒后可满足加速计划'
    const wait = {
      id: 962,
      event: { ...event, phase: 'waiting', anchor: false, detail },
      room: event.room,
      text: '2026-11-05 17:50:02 INFO ' + detail
    }
    const page = mount({ running: true, lines: [first, technical, wait] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-production-switch'))
    expect(visibleText(summary())).toBe('正在切换制造站 B102 的产物 中级作战记录 → 赤金')
    const child = page.all().find((entry) => hasClass(entry, 'log-lifecycle-detail'))
    expect(visibleText(child)).toBe(detail)
    expect(summary().parent.parent.children.indexOf(child)).toBe(
      summary().parent.parent.children.indexOf(summary().parent) + 1
    )
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(true)
    page.props.lines.push({
      id: 963,
      event: { ...event, phase: 'completed', anchor: false },
      text: '2026-11-05 17:50:30 INFO 已将制造站 B102 的产物切换为赤金'
    })
    await nextTick()
    expect(visibleText(summary())).toBe('已将制造站 B102 的产物切换为赤金')
    expect(page.all().filter((entry) => hasClass(entry, 'log-production-switch'))).toHaveLength(1)
    expect(page.all().filter((entry) => hasClass(entry, 'log-lifecycle-detail'))).toHaveLength(0)
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      page.props.lines.map((entry) => entry.text)
    )
  })
  it('shows the switch waiting state in the heading and previews the real reason at its own time', async () => {
    const parent = { type: 'production-switch', id: 'switch-attempt' }
    const event = {
      ...parent,
      room: 'room_1_2',
      label: '制造站 B102',
      facility: 'manufacture',
      product: '赤金'
    }
    const reason = '无人机数量不足'
    const page = mount({
      running: true,
      lines: [
        {
          text: '17:50:00 INFO 正在切换产物',
          parent,
          event: { ...event, phase: 'started', anchor: true }
        },
        { text: `17:50:01 INFO ${reason}`, parent },
        {
          text: '17:50:02 INFO 等待切换产物',
          parent,
          event: { ...event, phase: 'waiting', anchor: false, detail: reason }
        }
      ]
    })
    const heading = page.all().find((entry) => hasClass(entry, 'log-production-switch'))
    expect(visibleText(heading)).toBe('等待将制造站 B102 的产物切换为赤金')
    const preview = () => page.all().find((entry) => hasClass(entry, 'log-live-detail'))
    expect(visibleText(preview())).toBe(`17:50:01${reason}`)
    page.props.lines.push({
      text: '17:50:03 INFO 正在切换产物',
      parent,
      event: { ...event, phase: 'started', anchor: true }
    })
    await nextTick()
    expect(visibleText(heading)).toBe('正在将制造站 B102 的产物切换为赤金')
    expect(visibleText(preview())).toBe(`17:50:01${reason}`)
  })
  it('copies a mirrored production wait once in source order while preserving partial child selections', () => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    const event = {
      type: 'production-switch',
      id: 'production-copy',
      phase: 'started',
      anchor: true,
      room: 'room_1_2',
      label: '制造站 B102',
      facility: 'manufacture',
      product: '赤金',
      previous: '中级作战记录'
    }
    const detail = '无人机数量不足，当前生产效率为 200%，预计 26 秒后可满足加速计划'
    const lines = [
      {
        id: 970,
        event,
        text: '2026-11-05 17:50:00 INFO 正在切换制造站 B102 的产物 中级作战记录 → 赤金'
      },
      { id: 971, text: '2026-11-05 17:50:01 INFO 读取当前生产效率' },
      {
        id: 972,
        event: { ...event, phase: 'waiting', anchor: false, detail },
        text: '2026-11-05 17:50:02 INFO ' + detail
      }
    ]
    const page = mount({ running: true, lines })
    const root = page.all().find((entry) => hasClass(entry, 'log-output'))
    const container = page.all().find((entry) => entry.props['aria-label'] === '实时日志')
    const dom = (entry) => ({
      nodeType: entry.tag === '#text' ? 3 : 1,
      textContent: text(entry),
      classList: { contains: (name) => hasClass(entry, name) },
      getAttribute: (name) => entry.props[name] ?? null,
      childNodes: [
        ...(entry.text ? [{ nodeType: 3, textContent: entry.text }] : []),
        ...entry.children.map(dom)
      ]
    })
    const flatten = (entry) => [entry, ...(entry.childNodes ?? []).flatMap(flatten)]
    const matches = (entry, selector) =>
      selector === '[data-log-detail-key]'
        ? Boolean(entry.getAttribute?.('data-log-detail-key'))
        : Boolean(
            entry.classList?.contains('log-line--source-only') && entry.getAttribute('data-log-key')
          )
    root.contains = (entry) => entry === container
    root.querySelectorAll = (selector) =>
      selector === '[data-log-detail-key]'
        ? page
            .all()
            .filter((entry) => entry.props['data-log-detail-key'])
            .map(dom)
        : page
            .all()
            .filter((entry) => entry.props['data-log-source'])
            .map(dom)
    Object.assign(container, { nodeType: 1, closest: () => null })
    let selected = container.children.map(dom)
    vi.stubGlobal('getSelection', () => ({
      rangeCount: 1,
      isCollapsed: false,
      toString: () => '',
      getRangeAt: () => ({
        commonAncestorContainer: container,
        cloneContents: () => ({
          nodeType: 11,
          childNodes: selected,
          querySelector: () => ({}),
          querySelectorAll: (selector) =>
            selected.flatMap(flatten).filter((entry) => matches(entry, selector))
        })
      })
    }))
    const copy = () => {
      const result = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
      document.addEventListener.mock.calls[0][1](result)
      return result.clipboardData.setData.mock.calls[0][1]
    }
    expect(copy()).toBe(lines.map((entry) => entry.text).join('\n'))
    const heading = dom(page.rows()[0])
    const child = dom(page.all().find((entry) => hasClass(entry, 'log-lifecycle-detail')))
    selected = [heading, child]
    expect(copy()).toBe(lines[0].text + '\n' + detail)
    heading.textContent = '切换制造站 B102'
    heading.childNodes = [{ nodeType: 3, textContent: heading.textContent }]
    selected = [heading, child, dom(page.rows()[2])]
    expect(copy()).toBe('切换制造站 B102\n' + detail + '\n' + lines[1].text)
    child.textContent = '预计 26 秒后可满足加速计划'
    child.childNodes = [{ nodeType: 3, textContent: child.textContent }]
    selected = [child]
    expect(copy()).toBe(child.textContent)
    selected = [child, dom(page.rows()[3])]
    expect(copy()).toBe(child.textContent)
  })
  it('announces an unknown starting product without inventing an unknown value or a completion', async () => {
    const event = {
      type: 'production-switch',
      id: 'unknown-product',
      phase: 'started',
      anchor: true,
      room: 'room_1_2',
      label: '制造站 B102',
      facility: 'manufacture',
      product: '赤金'
    }
    const page = mount({
      running: true,
      lines: [
        { id: 964, event, text: '2026-11-05 17:50:00 INFO 正在将制造站 B102 的产物切换为赤金' }
      ]
    })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-production-switch'))
    expect(visibleText(summary())).toBe('正在将制造站 B102 的产物切换为赤金')
    page.props.running = false
    await nextTick()
    expect(visibleText(summary())).toBe('尚未完成将制造站 B102 的产物切换为赤金')
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(false)
    page.props.running = true
    await nextTick()
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(false)
  })
  it('keeps a multi-room order read pending until the whole explicit cohort is confirmed', async () => {
    const event = {
      type: 'order-read',
      id: 'orders-batch',
      phase: 'started',
      anchor: true,
      after_switch: true,
      rooms: [
        { room: 'room_1_1', label: '贸易站 B101', status: 'pending' },
        { room: 'room_2_1', label: '贸易站 B201', status: 'pending' }
      ]
    }
    const source =
      '2026-11-05 18:00:00 INFO 产物切换和驻员安排已完成，正在读取贸易站 B101、贸易站 B201 的订单倒计时'
    const page = mount({ running: true, lines: [{ id: 980, event, text: source }] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-order-read'))
    expect(summary()).toBeDefined()
    expect(visibleText(summary())).toBe(
      '产物切换和驻员安排已完成，正在读取贸易站 B101、贸易站 B201 的订单倒计时'
    )
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
    page.props.lines.push({
      id: 981,
      event: {
        ...event,
        phase: 'updated',
        anchor: false,
        rooms: [{ ...event.rooms[0], status: 'read' }, event.rooms[1]]
      },
      text: '2026-11-05 18:00:01 INFO 已读取贸易站 B101 的订单倒计时'
    })
    await nextTick()
    expect(visibleText(summary())).toContain(
      '已读取贸易站 B101 的订单倒计时；正在读取贸易站 B201 的订单倒计时'
    )
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(true)
    page.props.lines.push({
      id: 982,
      event: {
        ...event,
        phase: 'completed',
        anchor: false,
        rooms: event.rooms.map((room) => ({ ...room, status: 'read' }))
      },
      text: '2026-11-05 18:00:02 INFO 已读取贸易站 B101、贸易站 B201 的订单倒计时'
    })
    await nextTick()
    expect(visibleText(summary())).toBe(
      '产物切换和驻员安排已完成，已读取贸易站 B101、贸易站 B201 的订单倒计时'
    )
    expect(page.all().filter((entry) => hasClass(entry, 'log-order-read'))).toHaveLength(1)
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(false)
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(true)
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      page.props.lines.map((entry) => entry.text)
    )
  })
  it('keeps ordinary order reads free of switch claims and reports paused order acquisition precisely', async () => {
    const event = {
      type: 'order-read',
      id: 'ordinary-orders',
      phase: 'started',
      anchor: true,
      after_switch: false,
      rooms: [
        { room: 'room_1_1', label: '贸易站 B101', status: 'pending' },
        { room: 'room_2_1', label: '贸易站 B201', status: 'pending' }
      ]
    }
    const page = mount({
      running: true,
      lines: [
        {
          id: 983,
          event,
          text: '2026-11-05 18:00:00 INFO 正在读取贸易站 B101、贸易站 B201 的订单倒计时'
        }
      ]
    })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-order-read'))
    expect(summary()).toBeDefined()
    expect(visibleText(summary())).toBe('正在读取贸易站 B101、贸易站 B201 的订单倒计时')
    page.props.lines.push({
      id: 984,
      event: {
        ...event,
        phase: 'completed',
        anchor: false,
        rooms: [
          { ...event.rooms[0], status: 'read' },
          { ...event.rooms[1], status: 'paused' }
        ]
      },
      text: '2026-11-05 18:00:02 INFO 已读取贸易站 B101 的订单倒计时；贸易站 B201 的订单暂停获取'
    })
    await nextTick()
    expect(visibleText(summary())).toBe(
      '已读取贸易站 B101 的订单倒计时；贸易站 B201 的订单暂停获取'
    )
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
    expect(visibleText(summary())).not.toContain('生产')
  })
  it('stops an interrupted order read without inventing success and keeps a failed read reason below its anchor', async () => {
    const event = {
      type: 'order-read',
      id: 'failed-read',
      phase: 'started',
      anchor: true,
      after_switch: false,
      rooms: [{ room: 'room_1_1', label: '贸易站 B101', status: 'pending' }]
    }
    const first = {
      id: 985,
      event,
      text: '2026-11-05 18:00:00 INFO 正在读取贸易站 B101 的订单倒计时'
    }
    const page = mount({ running: true, lines: [first] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-order-read'))
    page.props.running = false
    await nextTick()
    expect(visibleText(summary())).toBe('尚未完成读取贸易站 B101 的订单倒计时')
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(false)
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
    page.props.running = true
    await nextTick()
    expect(hasClass(summary(), 'log-lifecycle-active')).toBe(false)
    page.props.lines.push({
      id: 986,
      event: {
        ...event,
        phase: 'failed',
        anchor: false,
        detail: '订单倒计时未读出，保留原任务和执行时间'
      },
      text: '2026-11-05 18:00:02 WARNING 订单倒计时未读出，保留原任务和执行时间'
    })
    await nextTick()
    expect(visibleText(summary())).not.toContain('已读取')
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
    expect(visibleText(page.all().find((entry) => hasClass(entry, 'log-lifecycle-detail')))).toBe(
      '订单倒计时未读出，保留原任务和执行时间'
    )
    const paused = { ...event, id: 'paused-read' }
    page.props.lines = [
      { id: 987, event: paused, text: first.text },
      {
        id: 988,
        event: {
          ...paused,
          phase: 'completed',
          anchor: false,
          rooms: [{ ...paused.rooms[0], status: 'paused' }]
        },
        text: '2026-11-05 18:00:03 INFO 贸易站 B101 的订单暂停获取'
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('贸易站 B101 的订单暂停获取')
    expect(hasClass(summary(), 'log-order-read--routine')).toBe(false)
  })
  it('retains confirmed room outcomes when another room in the order cohort fails', () => {
    const rooms = [
      { room: 'room_1_1', label: '贸易站 B101', status: 'pending' },
      { room: 'room_2_1', label: '贸易站 B201', status: 'pending' },
      { room: 'room_3_1', label: '贸易站 B301', status: 'pending' }
    ]
    const event = {
      type: 'order-read',
      id: 'partial-failed-order',
      phase: 'started',
      anchor: true,
      after_switch: false,
      rooms
    }
    const page = mount({
      running: true,
      lines: [
        {
          id: 989,
          event,
          text: '2026-11-05 18:00:00 INFO 正在读取贸易站 B101、贸易站 B201、贸易站 B301 的订单倒计时'
        },
        {
          id: 990,
          event: {
            ...event,
            phase: 'failed',
            anchor: false,
            rooms: rooms.map((room, index) => ({
              ...room,
              status: ['read', 'paused', 'pending'][index]
            })),
            detail: '贸易站 B301 的订单倒计时未读出，保留原任务'
          },
          text: '2026-11-05 18:00:02 WARNING 贸易站 B301 的订单倒计时未读出，保留原任务'
        }
      ]
    })
    const summary = page.all().find((entry) => hasClass(entry, 'log-order-read'))
    expect(visibleText(summary)).toBe(
      '已读取贸易站 B101 的订单倒计时；贸易站 B201 的订单暂停获取；尚未完成读取贸易站 B301 的订单倒计时'
    )
    expect(hasClass(summary, 'log-lifecycle-active')).toBe(false)
  })
  it('renders an inventory-limited stage as an interactive main-drop trigger without adding drop text', () => {
    const source = '2026-11-05 16:00:00 INFO 固源岩库存已达到设定上限，本轮跳过1-7'
    const page = mount({
      lines: [
        {
          text: source,
          event: { type: 'stage-inventory-limit', stage: { code: '1-7', drops: ['固源岩'] } }
        }
      ]
    })
    const trigger = page.all().find((entry) => hasClass(entry, 'log-stage__trigger'))
    expect(trigger).toBeDefined()
    expect(text(trigger)).toBe('1-7')
    expect(trigger.props['aria-haspopup']).toBe('dialog')
    expect(visibleText(page.rows()[0])).toContain('固源岩库存已达到设定上限，本轮跳过1-7')
    expect(visibleText(page.rows()[0])).not.toContain('主要掉落')
    expect(page.rows()[0].props['data-log-source']).toBe(source)
  })

  it.each(['current', 'legacy'])(
    'renders the %s base report without folding or changing its copied source',
    (format) => {
      const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
      vi.stubGlobal('document', document)
      const items = [
        { name: '作战录像', value: 42, unit: '经验', item: '中级作战记录' },
        { name: '赤金制造价值', value: 0, unit: '龙门币', item: '赤金' },
        { name: '龙门币订单金额', value: 1000, unit: '龙门币', item: '龙门币' },
        { name: '龙门币订单数', value: null, unit: '笔', item: '龙门币' },
        { name: '合成玉', value: null, unit: '个', item: '合成玉' },
        {
          name: format === 'legacy' ? '合成玉订单数量' : '合成玉订单数',
          value: null,
          unit: '笔',
          item: '合成玉'
        }
      ]
      const report =
        format === 'legacy'
          ? '已保存2026-11-05基报：\n作战录像：42经验\n赤金制造价值：0龙门币\n龙门币订单金额：1000龙门币\n龙门币订单数：未读出\n合成玉：未读出\n合成玉订单数量：未读出'
          : '已保存 2026-11-05 的基报：\n作战录像：42 经验\n赤金制造价值：0 龙门币\n龙门币订单金额：1000 龙门币\n龙门币订单数：未读出\n合成玉：未读出\n合成玉订单数：未读出'
      const drops = '本次Mower刷理智掉落结果已计入库存：采购凭证×3、固源岩×2'
      const page = mount({
        lines: [
          {
            id: 922,
            text: '2026-11-05 16:00:00 INFO ' + report,
            event: { type: 'base-report', date: '2026-11-05', items }
          },
          {
            id: 923,
            text: '2026-11-05 16:01:00 INFO ' + drops,
            event: {
              type: 'operation-drops',
              items: [
                { name: '采购凭证', count: 3 },
                { name: '固源岩', count: 2 }
              ]
            }
          }
        ]
      })
      expect(page.all().filter((entry) => entry.tag === 'img')).toHaveLength(8)
      expect(page.all().some((entry) => hasClass(entry, 'log-inventory__toggle'))).toBe(false)
      expect(visibleText(page.rows()[0])).toContain(report)
      expect(visibleText(page.rows()[1])).toContain(drops)
      expect(
        all(page.rows()[0])
          .filter((entry) => hasClass(entry, 'log-token--item'))
          .map(text)
      ).toEqual(report.split('\n').slice(1))
      const row = page.rows()[0]
      const root = page.all().find((entry) => hasClass(entry, 'log-output'))
      const selected = {
        nodeType: 1,
        textContent: text(row),
        getAttribute: (name) => row.props[name] ?? null,
        classList: { contains: (name) => hasClass(row, name) },
        childNodes: []
      }
      root.contains = (entry) => entry === row
      root.querySelectorAll = () => [selected]
      Object.assign(row, { nodeType: 1, closest: () => null })
      vi.stubGlobal('getSelection', () => ({
        rangeCount: 1,
        isCollapsed: false,
        toString: () => visibleText(row),
        getRangeAt: () => ({
          commonAncestorContainer: row,
          cloneContents: () => ({ nodeType: 11, querySelector: () => ({}), childNodes: [selected] })
        })
      }))
      const copied = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
      document.addEventListener.mock.calls[0][1](copied)
      expect(copied.clipboardData.setData).toHaveBeenCalledExactlyOnceWith(
        'text/plain',
        '2026-11-05 16:00:00 INFO ' + report
      )
      expect(copied.preventDefault).toHaveBeenCalledOnce()
    }
  )

  it('indents training selection details and names each explicitly recorded training position', () => {
    const positions = [
      { agent: '夜莺', index: 0 },
      { agent: '艾雅法拉', index: 1 }
    ]
    const event = {
      type: 'facility-arrangement',
      id: 'training-1',
      phase: 'started',
      anchor: true,
      room: 'train',
      label: '训练室',
      agents: ['夜莺', '艾雅法拉'],
      positions
    }
    const page = mount({
      running: true,
      lines: [
        { id: 920, event, room: 'train', text: '2026-11-05 16:00:00 INFO 正在安排训练室驻员' },
        {
          id: 921,
          room: 'train',
          agents: event.agents,
          event: { type: 'training-selection', positions },
          text: '2026-11-05 16:00:01 INFO 正在安排 [[operator:夜莺]] 进驻训练室协助位、[[operator:艾雅法拉]] 进驻训练室训练位'
        }
      ]
    })
    const summary = page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(visibleText(summary)).toBe('正在安排夜莺进驻训练室协助位、艾雅法拉进驻训练室训练位')
    expect(hasClass(page.rows()[0], 'log-facility-heading')).toBe(true)
    expect(hasClass(page.rows()[1], 'log-line--nested')).toBe(true)
    expect(page.all().some((entry) => hasClass(entry, 'log-facility-heading'))).toBe(true)
  })
  it('opens a configured group roster from an ordinary confirmation log', async () => {
    const source = '2026-11-05 14:24:22 INFO 绑组换班确认完成：红松上班；深海下班'
    const page = mount({
      lines: [{ text: source }],
      facilityPlan: {
        meeting: {
          plans: [
            { agent: '阿米娅', group: '红松' },
            { agent: '斯卡蒂', group: '深海' }
          ]
        }
      }
    })
    const groups = page.all().filter((entry) => hasClass(entry, 'task-action-subjects__group'))
    expect(groups.map(text)).toEqual(['红松', '深海'])
    expect(visibleText(page.rows()[0])).toContain('绑组换班确认完成：红松上班；深海下班')
    groups[0].props.onMouseenter({
      currentTarget: { getBoundingClientRect: () => ({ left: 10, top: 50 }) }
    })
    await nextTick()
    expect(text(page.all().find((entry) => hasClass(entry, 'task-action-roster')))).toContain(
      '阿米娅'
    )
    expect(page.rows()[0].props['data-log-source']).toBe(source)
  })

  it('shows the recorded facility arrangement progress and updates only its matching summary', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'a'.repeat(32),
      phase: 'started',
      anchor: true,
      room: 'dormitory_4',
      label: '宿舍4',
      agents: ['斯卡蒂', '跃跃']
    }
    const first = {
      id: 901,
      room: event.room,
      agents: event.agents,
      event,
      text: '2026-11-05 14:25:46 INFO 正在安排斯卡蒂、跃跃进驻宿舍4'
    }
    const page = mount({ running: true, lines: [first] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(visibleText(summary())).toBe('正在安排斯卡蒂、跃跃进驻宿舍4')
    expect(hasClass(summary(), 'log-arrangement--active')).toBe(true)
    page.props.lines = [
      first,
      {
        id: 905,
        text: '2026-11-05 14:26:00 INFO 另一轮安排已确认',
        event: { ...event, id: 'c'.repeat(32), phase: 'completed', anchor: false }
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('正在安排斯卡蒂、跃跃进驻宿舍4')
    page.props.lines = [
      first,
      {
        id: 902,
        text: '2026-11-05 14:26:27 INFO 已安排斯卡蒂、跃跃进驻宿舍4',
        event: { ...event, phase: 'completed', anchor: false, agents: ['跃跃', '斯卡蒂', '杜林'] }
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('已安排跃跃、斯卡蒂、杜林进驻宿舍4')
    expect(hasClass(summary(), 'log-arrangement--active')).toBe(false)
    expect(page.rows()[0].props['data-log-source']).toBe(first.text)
  })

  it('updates the current recycling roster in its original summary before confirmation', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'recycling-current',
      phase: 'started',
      anchor: true,
      room: 'recycle',
      label: '回收站',
      agents: ['行铃']
    }
    const first = {
      id: 930,
      event,
      text: '2026-11-06 17:43:00 INFO 正在安排行铃进驻回收站'
    }
    const page = mount({ running: true, concise: true, lines: [first] })
    const summaries = () => page.all().filter((entry) => hasClass(entry, 'log-arrangement'))
    const original = summaries()[0]
    expect(visibleText(original)).toBe('正在安排行铃进驻回收站')
    const progress = {
      id: 931,
      parent: { type: event.type, id: event.id, room: event.room },
      event: {
        ...event,
        phase: 'updated',
        anchor: false,
        agents: ['行铃', '旅骨'],
        summary: '正在安排行铃、旅骨进驻回收站'
      },
      text: '2026-11-06 17:43:02 INFO 正在安排行铃、旅骨进驻回收站'
    }
    page.props.lines.push(progress)
    await nextTick()
    expect(summaries()).toHaveLength(1)
    expect(summaries()[0]).toBe(original)
    expect(visibleText(original)).toBe('正在安排行铃、旅骨进驻回收站')
    expect(hasClass(original, 'log-arrangement--active')).toBe(true)
    expect(original.props['data-log-source']).toBe(first.text)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual([
      first.text,
      progress.text
    ])
    expect(hasClass(page.rows()[1], 'log-line--source-only')).toBe(true)

    page.props.running = false
    await nextTick()
    expect(visibleText(original)).toBe('尚未确认行铃、旅骨进驻回收站')
    expect(hasClass(original, 'log-arrangement--active')).toBe(false)
  })

  it('keeps unconfirmed arrangements unfinished when stopped and shows failures explicitly', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'b'.repeat(32),
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const first = { id: 903, event, text: '2026-11-05 14:25:46 INFO 正在安排阿米娅进驻会客室' }
    const page = mount({ running: false, lines: [first] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(visibleText(summary())).toBe('尚未确认阿米娅进驻会客室')
    expect(hasClass(summary(), 'log-arrangement--active')).toBe(false)
    page.props.lines = [
      first,
      {
        id: 904,
        event: { ...event, phase: 'failed', anchor: false },
        text: '2026-11-05 14:26:00 WARNING 安排阿米娅进驻会客室失败'
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('尚未确认阿米娅进驻会客室')
  })

  it('does not infer an emptied facility from an arrangement without explicit operator names', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'd'.repeat(32),
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: []
    }
    const first = { id: 906, event, text: '2026-11-05 14:25:46 INFO 正在调整会客室驻员安排' }
    const page = mount({ running: true, lines: [first] })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(visibleText(summary())).toBe('正在调整会客室驻员安排')
    page.props.lines = [
      first,
      {
        id: 907,
        event: { ...event, phase: 'completed', anchor: false },
        text: '2026-11-05 14:26:00 INFO 已确认会客室驻员安排'
      }
    ]
    await nextTick()
    expect(visibleText(summary())).toBe('已确认会客室驻员安排')
  })

  it('animates only the latest arrangement when earlier history has no terminal event', () => {
    const first = {
      type: 'facility-arrangement',
      id: 'e'.repeat(32),
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const second = { ...first, id: 'f'.repeat(32), room: 'dormitory_1', label: '宿舍1' }
    const page = mount({
      running: true,
      lines: [
        { id: 908, event: first, text: '2026-11-05 14:00:00 INFO 正在安排阿米娅进驻会客室' },
        { id: 909, event: second, text: '2026-11-05 14:01:00 INFO 正在安排阿米娅进驻宿舍1' }
      ]
    })
    const summaries = page.all().filter((entry) => hasClass(entry, 'log-arrangement'))
    expect(summaries.map(visibleText)).toEqual([
      '尚未确认阿米娅进驻会客室',
      '正在安排阿米娅进驻宿舍1'
    ])
    expect(summaries.filter((entry) => hasClass(entry, 'log-arrangement--active'))).toHaveLength(1)
  })

  it('keeps a stopped arrangement inactive after restarting until a new arrangement starts', async () => {
    const event = {
      type: 'facility-arrangement',
      id: 'stopped-arrangement',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const first = { id: 910, event, text: '2026-11-05 14:00:00 INFO 正在安排阿米娅进驻会客室' }
    const page = mount({ running: true, lines: [first] })
    const summaries = () => page.all().filter((entry) => hasClass(entry, 'log-arrangement'))
    expect(hasClass(summaries()[0], 'log-arrangement--active')).toBe(true)
    page.props.running = false
    await nextTick()
    page.props.running = true
    await nextTick()
    expect(visibleText(summaries()[0])).toBe('尚未确认阿米娅进驻会客室')
    expect(hasClass(summaries()[0], 'log-arrangement--active')).toBe(false)
    page.props.lines = [
      first,
      {
        id: 911,
        event: { ...event, id: 'new-arrangement' },
        text: '2026-11-05 14:01:00 INFO 正在安排阿米娅进驻会客室'
      }
    ]
    await nextTick()
    expect(summaries().map((entry) => hasClass(entry, 'log-arrangement--active'))).toEqual([
      false,
      true
    ])
  })

  it('uses item icons and explicit increase or decrease styling for confirmed crafting changes', () => {
    const changes = [
      { name: '化合切削液', delta: -3 },
      { name: 'RMA70-12', delta: -3 },
      { name: '切削原液', delta: 3 },
      { name: '龙门币', delta: -900 }
    ]
    const source =
      '2026-11-05 14:00:00 INFO [[operator:蜜莓]]加工切削原液完成3次，库存变化：化合切削液-3、RMA70-12-3、切削原液+3、龙门币-900'
    const page = mount({
      lines: [{ text: source, agents: ['蜜莓'], event: { type: 'workshop-result', changes } }]
    })
    const entries = page.all().filter((entry) => hasClass(entry, 'log-token--inventory-change'))
    expect(entries.map(text)).toEqual(['化合切削液-3', 'RMA70-12-3', '切削原液+3', '龙门币-900'])
    expect(entries.map((entry) => entry.props['data-change-direction'])).toEqual([
      'decrease',
      'decrease',
      'increase',
      'decrease'
    ])
    expect(entries.every((entry) => all(entry).some((child) => child.tag === 'img'))).toBe(true)
    expect(page.rows()[0].props['data-log-source']).toBe(source)
  })

  it.each([
    ['：库存12，上限20，本批最多3次', { type: 'workshop-material' }],
    ['完成3次，库存变化：碳-3、家具零件+12、龙门币-600', { type: 'workshop-result' }]
  ])(
    'renders the workshop recipe from ingredient to product with both icons for %s',
    (detail, event) => {
      const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
      vi.stubGlobal('document', document)
      const operator = '凯尔希·思衡托'
      const product = { name: '家具零件_碳', item: '家具零件' }
      const source = `2026-11-05 14:00:00 INFO [[operator:${operator}]]加工${product.name}${detail}`
      const nextSource = '2026-11-05 14:00:01 INFO 确认库存'
      const metadata =
        event.type === 'workshop-material'
          ? { ...event, ...product }
          : {
              ...event,
              product,
              changes: [
                { name: '碳', delta: -3 },
                { name: '家具零件', delta: 12 },
                { name: '龙门币', delta: -600 }
              ]
            }
      const page = mount({
        lines: [{ text: source, room: 'factory', agents: [operator], event: metadata }, nextSource]
      })
      const [row, nextRow] = page.rows()
      const recipeItems = all(row).filter(
        (entry) =>
          hasClass(entry, 'log-token--item') && !hasClass(entry, 'log-token--inventory-change')
      )

      expect(portraits(row).map((entry) => entry.props['data-operator-name'])).toEqual([operator])
      expect(recipeItems.map(text)).toEqual(['碳', product.item])
      expect(
        recipeItems.map((entry) => all(entry).find((child) => child.tag === 'img')?.props.src)
      ).toEqual(['碳', product.item].map((name) => `/depot/${encodeURIComponent(name)}.webp`))
      expect(visibleText(row)).toContain(`加工碳 → 家具零件${detail}`)
      expect(visibleText(row)).not.toContain(product.name)
      expect(row.props['data-log-source']).toBe(source)

      const stamp = all(row).find((entry) => hasClass(entry, 'log-stamp__time'))
      const domRow = {
        nodeType: 1,
        textContent: text(row),
        getAttribute: (name) => row.props[name] ?? null,
        querySelector: (selector) => (selector === '.log-stamp__time' ? stamp : null),
        closest: (selector) =>
          selector.split(', ').some((part) => {
            const attributes = [...part.matchAll(/\[([^\]]+)\]/gu)]
            return (
              part.startsWith('.log-line[') &&
              attributes.every(([, name]) => row.props[name] != null)
            )
          })
            ? domRow
            : null
      }
      const textFromStamp = domRow.textContent.slice(domRow.textContent.indexOf(text(stamp)))
      const bounds = {
        selectNodeContents: vi.fn(),
        setStart: vi.fn(),
        toString: () => textFromStamp
      }
      document.createRange = () => bounds
      const root = page.all().find((entry) => hasClass(entry, 'log-output'))
      root.contains = (candidate) => candidate === domRow
      let selectedText = domRow.textContent
      vi.stubGlobal('getSelection', () => ({
        rangeCount: 1,
        isCollapsed: false,
        toString: () => selectedText,
        getRangeAt: () => ({
          commonAncestorContainer: domRow,
          compareBoundaryPoints: () => -1,
          cloneContents: () => ({
            nodeType: 11,
            childNodes: [{ nodeType: 3, textContent: selectedText }],
            querySelector: () => (selectedText === domRow.textContent ? {} : null)
          })
        })
      }))
      const copy = document.addEventListener.mock.calls.find(([name]) => name === 'copy')[1]
      const eventCopy = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
      copy(eventCopy)
      expect(eventCopy.clipboardData.setData).toHaveBeenCalledExactlyOnceWith('text/plain', source)
      expect(eventCopy.preventDefault).toHaveBeenCalledOnce()

      selectedText = textFromStamp
      eventCopy.clipboardData.setData.mockClear()
      eventCopy.preventDefault.mockClear()
      copy(eventCopy)
      expect(bounds.setStart).toHaveBeenCalledExactlyOnceWith(stamp, 0)
      expect(eventCopy.clipboardData.setData).toHaveBeenCalledExactlyOnceWith('text/plain', source)
      expect(eventCopy.preventDefault).toHaveBeenCalledOnce()

      selectedText = '碳 → 家具零件'
      eventCopy.clipboardData.setData.mockClear()
      eventCopy.preventDefault.mockClear()
      copy(eventCopy)
      expect(eventCopy.clipboardData.setData).not.toHaveBeenCalled()
      expect(eventCopy.preventDefault).not.toHaveBeenCalled()

      const container = { nodeType: 1, closest: () => null }
      const nextDomRow = {
        nodeType: 1,
        textContent: text(nextRow),
        getAttribute: (name) => nextRow.props[name] ?? null
      }
      root.contains = (candidate) => candidate === container
      root.querySelectorAll = () => [domRow, nextDomRow]
      vi.stubGlobal('getSelection', () => ({
        rangeCount: 1,
        isCollapsed: false,
        toString: () => `${selectedText}\n${nextDomRow.textContent}`,
        getRangeAt: () => ({
          commonAncestorContainer: container,
          cloneContents: () => ({
            nodeType: 11,
            querySelector: () => ({}),
            childNodes: [
              {
                ...domRow,
                textContent: selectedText,
                childNodes: [{ nodeType: 3, textContent: selectedText }],
                classList: { contains: (name) => name === 'log-line' }
              },
              nextDomRow
            ]
          })
        })
      }))
      copy(eventCopy)
      expect(eventCopy.clipboardData.setData).toHaveBeenCalledExactlyOnceWith(
        'text/plain',
        `碳 → 家具零件\n${nextSource}`
      )

      selectedText = textFromStamp
      eventCopy.clipboardData.setData.mockClear()
      copy(eventCopy)
      expect(eventCopy.clipboardData.setData).toHaveBeenCalledExactlyOnceWith(
        'text/plain',
        `${source}\n${nextSource}`
      )
    }
  )

  it('keeps dotted operator names whole when the operator catalog changes', async () => {
    const name = '凯尔希·思衡托'
    const source = `2026-11-05 14:00:00 INFO ${name}上班`
    const page = mount({ lines: [source], operatorNames: ['凯尔希'] })

    expect(portraits(page.rows()[0]).map((entry) => entry.props['data-operator-name'])).toEqual([])
    expect(visibleText(page.rows()[0])).toContain(name)

    page.props.operatorNames = ['凯尔希', name]
    await nextTick()
    const rendered = portraits(page.rows()[0])
    expect(rendered.map((entry) => entry.props['data-operator-name'])).toEqual([name])
    const [portrait] = rendered
    expect(all(portrait).find((entry) => entry.tag === 'img').props.src).toBe(
      `/avatar/${encodeURIComponent(name)}.webp`
    )
    expect(page.rows()[0].props['data-log-source']).toBe(source)
  })

  it('renders the explicit operator target of an unplanned exhaustion forecast in place', () => {
    const header = '休息 28分55秒，至 12:31:33，随后执行「用尽下班」，目标干员：[[operator:陈]]'
    const page = mount({
      lines: [
        {
          id: 802,
          text: `2026-11-05 12:02:38 INFO ${header}`,
          agents: ['陈'],
          task: {
            title: '用尽下班',
            header,
            wait_seconds: 1735,
            rooms: [],
            targets: [],
            backups: []
          }
        }
      ]
    })
    expect(portraits(page.rows()[0]).map((item) => item.props['data-operator-name'])).toEqual([
      '陈'
    ])
    expect(visibleText(page.rows()[0])).not.toContain('[[operator:')
  })
  it.each([
    ['28分55秒', '28 分 55 秒'],
    ['28 分 55 秒', '28 分 55 秒'],
    ['1小时2分3秒', '1 小时 2 分 3 秒'],
    ['1 小时 2 分 3 秒', '1 小时 2 分 3 秒']
  ])(
    'renders a recorded next task after a wait-only header while retaining every room: %s',
    (duration, displayedDuration) => {
      const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
      vi.stubGlobal('document', document)
      const header = `休息 ${duration}，至 12:31:33`
      const source = `2026-11-05 12:02:38 INFO ${header}`
      const page = mount({
        lines: [
          {
            id: 801,
            text: source,
            task: {
              header,
              title: '用尽下班',
              wait_seconds: 1735,
              rooms: [{ id: 'dormitory_1', label: '宿舍1', agents: ['陈', 'Current', 'Free'] }],
              targets: [],
              backups: []
            }
          }
        ]
      })
      const visible = visibleText(page.rows()[0])
      expect(visible).toContain(`休息 ${displayedDuration}，至 12:31:33，随后执行「用尽下班」`)
      expect(page.all().some((entry) => hasClass(entry, 'log-forecast__header'))).toBe(true)
      expect(visible.match(/随后执行/gu)).toHaveLength(1)
      expect(visible).toContain('宿舍1')
      expect(portraits(page.rows()[0]).map((item) => item.props['data-operator-name'])).toEqual([
        '陈',
        'Current',
        'Free'
      ])
      expect(page.rows()[0].props['data-log-source']).toBe(source)
      const root = page.all().find((entry) => hasClass(entry, 'log-output'))
      const row = page.rows()[0]
      const copiedRow = {
        nodeType: 1,
        textContent: text(row),
        classList: { contains: (name) => hasClass(row, name) },
        getAttribute: (name) => row.props[name] ?? null
      }
      Object.assign(root, { nodeType: 1, closest: () => null })
      root.contains = (candidate) => candidate === root
      root.querySelectorAll = () => [copiedRow]
      vi.stubGlobal('getSelection', () => ({
        rangeCount: 1,
        isCollapsed: false,
        getRangeAt: () => ({
          commonAncestorContainer: root,
          cloneContents: () => ({
            nodeType: 11,
            childNodes: [copiedRow],
            querySelector: () => copiedRow
          })
        })
      }))
      const copy = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
      document.addEventListener.mock.calls[0][1](copy)
      expect(copy.clipboardData.setData).toHaveBeenCalledExactlyOnceWith('text/plain', source)
      expect(copy.preventDefault).toHaveBeenCalledOnce()
    }
  )
  it('does not merge a missing original group into a borrowed effective business group', () => {
    const page = mount({
      lines: ['陈', '砾'].map((name, index) => ({
        id: index,
        text: `2026-11-05 12:00:0${index} INFO 重设 [[operator:${name}]] 至空闲`,
        event: { type: 'operator-reset-idle' },
        agents: [name],
        group: index ? null : 'base-scheduler'
      }))
    })
    expect(page.all().filter((element) => hasClass(element, 'log-reset-group'))).toHaveLength(0)
    expect(page.rows()).toHaveLength(2)
  })
  it('keeps the first real reset timestamp visible in compact mode', () => {
    const page = mount({
      compact: true,
      lines: ['陈', '砾'].map((name, index) => ({
        id: index,
        text: `2026-11-05 12:00:0${index} INFO 重设 [[operator:${name}]] 至空闲`,
        event: { type: 'operator-reset-idle' },
        agents: [name]
      }))
    })
    const group = page.all().find((element) => hasClass(element, 'log-reset-group'))
    expect(visibleText(group)).toContain('12:00:00')
    expect(visibleText(group)).not.toContain('12:00:01')
  })
  it('keeps the loader on the waiting scene line while reset details arrive', async () => {
    const now = Date.now()
    const page = mount({
      running: true,
      lines: [
        {
          id: 1,
          at: now - 5000,
          text: '2026-11-05 12:00:00 INFO Scene 9998: 场景跳转时的等待界面'
        },
        ...['陈', '砾'].map((name, index) => ({
          id: index + 2,
          text: `2026-11-05 12:00:0${index + 1} INFO 重设 [[operator:${name}]] 至空闲`,
          event: { type: 'operator-reset-idle' },
          agents: [name]
        }))
      ]
    })
    const group = page.all().find((element) => hasClass(element, 'log-reset-group'))
    expect(all(group).filter((element) => hasClass(element, 'log-wait-loader'))).toHaveLength(0)
    const loader = page.all().find((element) => hasClass(element, 'log-wait-loader'))
    expect(visibleText(loader.parent)).toContain('Scene 9998: 场景跳转时的等待界面')
    page.props.lines.push({
      id: 4,
      at: now,
      text: '2026-11-05 12:00:03 INFO Scene 201: 基建全局视角'
    })
    await nextTick()
    expect(page.all().filter((element) => hasClass(element, 'log-wait-loader'))).toHaveLength(0)
  })
  it('retains both date headings when only reset records span two game calendar dates', () => {
    const lines = ['2026-11-05', '2026-11-06'].flatMap((date, day) =>
      ['陈', '砾'].map((name, index) => ({
        id: day * 2 + index,
        text: `${date} 12:00:0${index} INFO 重设 [[operator:${name}]] 至空闲`,
        event: { type: 'operator-reset-idle' },
        agents: [name],
        group: 'base-scheduler'
      }))
    )
    const page = mount({ lines })
    expect(
      page
        .all()
        .filter((element) => hasClass(element, 'log-date'))
        .map(text)
    ).toEqual(['2026-11-05', '2026-11-06'])
    expect(page.all().filter((element) => hasClass(element, 'log-reset-group'))).toHaveLength(2)
  })

  it('expands only a depot inventory and keeps its state across an equivalent poll', async () => {
    const items = Array.from({ length: 39 }, (_, index) => ({ name: `材料${index}`, count: index }))
    const source = `2026-11-05 12:00:00 INFO 仓库扫描：已识别39种物品\n${items.map((item) => `${item.name}：${item.count}`).join('\n')}`
    const record = { id: 12, text: source, group: 'depot-recognition', inventory: { items } }
    const page = mount({ lines: [record] })
    const inventoryRows = () =>
      page.all().filter((element) => hasClass(element, 'log-inventory__item'))
    const button = () => page.all().find((element) => hasClass(element, 'log-inventory__toggle'))
    expect(inventoryRows()).toHaveLength(3)
    expect(text(button())).toBe('还有36项，展开')
    expect(button().props['aria-expanded']).toBe(false)
    button().props.onClick()
    await nextTick()
    expect(inventoryRows()).toHaveLength(39)
    page.props.lines = [JSON.parse(JSON.stringify(record))]
    await nextTick()
    expect(inventoryRows()).toHaveLength(39)
    button().props.onClick()
    await nextTick()
    expect(inventoryRows()).toHaveLength(3)
    expect(page.rows()[0].props['data-log-source']).toBe(source)
    expect(page.warnings).toEqual([])
  })
  it('joins consecutive reset records with one visible prefix while keeping all sources', () => {
    const lines = ['陈', '阿米娅', '砾'].map((name, index) => ({
      id: index + 1,
      text: `2026-11-05 12:00:0${index} INFO 重设 [[operator:${name}]] 至空闲`,
      room: 'dormitory_1',
      group: 'base-scheduler',
      agents: [name],
      event: { type: 'operator-reset-idle' }
    }))
    const page = mount({ lines })
    const group = page.all().find((element) => hasClass(element, 'log-reset-group'))
    expect(group).toBeDefined()
    expect(visibleText(group).match(/重设/gu)).toHaveLength(1)
    expect(visibleText(group).match(/至空闲/gu)).toHaveLength(1)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
    expect(group.props['data-log-source']).toBe(lines.map((line) => line.text).join('\n'))
    expect(portraits(group).map((item) => item.props['data-operator-name'])).toEqual([
      '陈',
      '阿米娅',
      '砾'
    ])
  })

  it('starts linked facility details folded in both modes and keeps unrelated records visible', async () => {
    const room = 'dormitory_2'
    const id = 'dorm-change'
    const parent = { type: 'facility-arrangement', id, room }
    const arrangement = {
      type: 'facility-arrangement',
      id,
      room,
      label: '宿舍2',
      agents: ['槐琥']
    }
    const lines = [
      { text: 'INFO 正在进入宿舍2', parent },
      { text: 'INFO 宿舍2', parent, event: { ...arrangement, phase: 'started', anchor: true } },
      { text: 'INFO 选人页当前选中槐琥', parent },
      { text: 'INFO 宿舍2其他任务', room },
      { text: 'INFO 其他尝试记录', parent: { ...parent, id: 'other' } },
      { text: 'WARNING 宿舍2读取异常', parent },
      {
        text: 'INFO 已安排槐琥进驻宿舍2',
        parent,
        event: { ...arrangement, phase: 'completed', anchor: false }
      },
      {
        text: 'INFO 已确认絮雨转为空闲',
        parent,
        event: { type: 'facility-idle', id, room, agents: ['絮雨'] }
      }
    ]
    const page = mount({ lines })
    const heading = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    const toggle = () => page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(visibleText(page.root)).not.toContain('选人页当前选中槐琥')
    await toggle().props.onClick()
    expect(visibleText(page.root)).toContain('选人页当前选中槐琥')
    expect(visibleText(heading())).toBe('已安排槐琥进驻宿舍2')
    expect(toggle().props['aria-expanded']).toBe(true)
    toggle().props.onClick()
    await nextTick()
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(visibleText(page.root)).toContain('正在进入宿舍2')
    expect(visibleText(page.root)).not.toContain('选人页当前选中槐琥')
    expect(visibleText(page.root)).toContain('宿舍2读取异常')
    expect(heading().props['data-facility-copy']).toBe(1)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )

    page.props.concise = true
    await nextTick()
    expect(visibleText(heading())).toBe('已安排槐琥进驻宿舍2，絮雨转为空闲')
    expect(visibleText(page.root)).toContain('正在进入宿舍2')
    expect(visibleText(page.root)).not.toContain('选人页当前选中槐琥')
    expect(visibleText(page.root)).toContain('宿舍2其他任务')
    expect(visibleText(page.root)).toContain('其他尝试记录')
    expect(visibleText(page.root)).toContain('宿舍2读取异常')
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
    expect(toggle().props['aria-expanded']).toBe(false)
    toggle().props.onClick()
    await nextTick()
    expect(toggle().props['aria-expanded']).toBe(true)
    expect(visibleText(page.root)).toContain('正在进入宿舍2')
    expect(visibleText(page.root)).toContain('选人页当前选中槐琥')
    expect(visibleText(heading())).toBe('已安排槐琥进驻宿舍2，絮雨转为空闲')

    page.props.concise = false
    await nextTick()
    expect(toggle().props['aria-expanded']).toBe(true)
    expect(visibleText(heading())).toBe('已安排槐琥进驻宿舍2')
    expect(visibleText(page.root)).toContain('选人页当前选中槐琥')
    toggle().props.onClick()
    await nextTick()
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(visibleText(page.root)).not.toContain('选人页当前选中槐琥')
  })

  it('shows one run order staffing summary and keeps order collection separate', async () => {
    const room = 'room_1_1'
    const parent = { type: 'facility-arrangement', id: 'run-order', room }
    const event = { ...parent, label: '贸易站 B101', agents: ['但书'] }
    const started = '正在 贸易站 B101 安排 [[operator:但书]] 跑单'
    const completed = '已在 贸易站 B101 安排 [[operator:但书]] 跑单'
    const lines = [
      { id: 1, text: 'INFO 但书 房间变动', parent },
      {
        id: 2,
        text: `INFO ${started}`,
        parent,
        event: { ...event, phase: 'started', anchor: true, summary: started }
      },
      { id: 3, text: 'INFO Scene 205: 基建放大查看', parent }
    ]
    const page = mount({
      running: true,
      concise: true,
      lines: lines.slice(),
      facilityPlan: { [room]: { name: '制造站' } }
    })
    const heading = () => page.all().find((entry) => hasClass(entry, 'log-arrangement'))
    expect(visibleText(heading())).toBe('正在 贸易站 B101 安排 但书 跑单')
    expect(portraits(heading()).map((entry) => entry.props['data-operator-name'])).toEqual(['但书'])
    expect(visibleText(page.rows()[0])).toContain('房间变动')
    expect(visibleText(page.rows()[2])).toBe('')
    expect(visibleText(page.all().find((entry) => hasClass(entry, 'log-live-detail')))).toContain(
      '基建放大查看'
    )

    const rest = [
      {
        id: 4,
        text: `INFO ${completed}`,
        parent,
        event: { ...event, phase: 'completed', anchor: false, summary: completed }
      },
      { id: 5, text: 'INFO 已收取订单', room }
    ]
    page.props.lines = [...lines, ...rest]
    await nextTick()
    expect(visibleText(heading())).toBe('已在 贸易站 B101 安排 但书 跑单')
    expect(visibleText(page.root)).toContain('已收取订单')
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      [...lines, ...rest].map((line) => line.text)
    )

    page
      .all()
      .find((entry) => hasClass(entry, 'log-detail-toggle'))
      .props.onClick()
    await nextTick()
    expect(visibleText(page.root)).toContain('房间变动')
    expect(visibleText(page.root)).toContain('基建放大查看')
  })

  it('folds a completed collection start in concise logs while keeping its source', async () => {
    const room = 'room_1_1'
    const order = {
      id: 1,
      text: '2026-11-06 16:26:38,523 INFO 当前为 但书 订单, 订单价值为: 2000'
    }
    const start = {
      id: 2,
      room,
      group: 'base-scheduler',
      text: '2026-11-06 16:26:38,541 INFO 贸易站 B101：正在收取订单'
    }
    const collected = {
      ...start,
      id: 3,
      text: '2026-11-06 16:26:39,846 INFO 贸易站 B101：已收取订单'
    }
    const page = mount({ concise: true, lines: [order, start] })
    expect(visibleText(page.root)).toContain('正在收取订单')

    page.props.lines = [order, start, collected]
    await nextTick()
    expect(visibleText(page.root)).toContain('当前为 但书 订单')
    expect(visibleText(page.root)).not.toContain('正在收取订单')
    expect(visibleText(page.root)).toContain('16:26:39贸易站 B101：已收取订单')
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      [order, start, collected].map((line) => line.text)
    )

    page.props.concise = false
    await nextTick()
    expect(visibleText(page.root)).toContain('正在收取订单')
    expect(visibleText(page.root)).toContain('已收取订单')

    page.props.concise = true
    for (const following of [
      { ...collected, room: 'room_2_1' },
      { ...collected, text: collected.text.replace('2026-11-06', '2026-11-07') },
      { ...collected, text: collected.text.replace('已收取订单', '未识别到可收取订单') },
      { ...collected, text: collected.text.replace('INFO', 'WARNING') }
    ]) {
      page.props.lines = [order, start, following]
      await nextTick()
      expect(visibleText(page.root)).toContain('正在收取订单')
    }
  })

  it('keeps scoped dormitory and manufacturing details with their original summaries', async () => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    let nextId = 0
    const attempt = (room, label, agent, time) => {
      const parent = { type: 'facility-arrangement', id: `arrange-${room}`, room }
      const event = { ...parent, label, agents: [agent] }
      const line = (body, fields = {}, level = 'INFO') => ({
        id: ++nextId,
        group: 'base-scheduler',
        text: `2026-11-06 ${time} ${level} ${body}`,
        ...fields
      })
      const start = line(`正在安排${agent}进驻${label}`, {
        room,
        event: { ...event, phase: 'started', anchor: true }
      })
      const details = [
        line('Scene 205: 进入设施', { parent, group: 'recognition' }),
        line('Scene 207: 打开选人界面', { parent, group: 'recognition' })
      ]
      const unrelated = line(`${label}：其他任务查询`, { room, group: 'credit-shop' })
      details.push(
        line(`${label}：选人页当前选中${agent}`, { room, parent }),
        line(`${label}：核对驻员位置`, { room, parent })
      )
      const warning = line(`${label}读取异常`, { room, parent }, 'WARNING')
      const completed = line(`已安排${agent}进驻${label}`, {
        room,
        parent,
        event: { ...event, phase: 'completed', anchor: false }
      })
      return {
        details,
        unrelated,
        warning,
        lines: [start, ...details.slice(0, 2), unrelated, ...details.slice(2), warning, completed]
      }
    }
    const dorm = attempt('dormitory_1', '宿舍1', '菲亚梅塔', '10:27:55')
    const manufacture = attempt('room_2_2', '制造站 B202', '槐琥', '10:28:30')
    const lines = [...dorm.lines, ...manufacture.lines]
    const page = mount({ lines, facilityPlan: { room_2_2: { name: '制造站' } } })
    const headings = () => page.all().filter((entry) => hasClass(entry, 'log-facility-heading'))
    const findRow = (source) =>
      page.rows().find((row) => row.props['data-log-key'] === `id:${source.id}`)
    const summary = (heading) => all(heading).find((entry) => hasClass(entry, 'log-arrangement'))
    const checkStructure = () => {
      expect(headings().map((heading) => visibleText(summary(heading)))).toEqual([
        '已安排菲亚梅塔进驻宿舍1',
        '已安排槐琥进驻制造站 B202'
      ])
      expect(page.all().some((entry) => entry.props['data-group'] === 'recognition')).toBe(false)
      expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
    }
    const checkDetails = (group, open) => {
      for (const detail of group.details) {
        const row = findRow(detail)
        expect(hasClass(row, 'log-line--source-only')).toBe(!open)
        if (open) expect(hasClass(row, 'log-line--nested')).toBe(true)
      }
      expect(visibleText(findRow(group.unrelated))).toContain('其他任务查询')
      expect(hasClass(findRow(group.unrelated), 'log-line--nested')).toBe(false)
      expect(visibleText(findRow(group.warning))).toContain('读取异常')
    }
    const output = page.all().find((entry) => hasClass(entry, 'log-output'))
    const copyListener = document.addEventListener.mock.calls[0][1]
    output.contains = (entry) => all(output).includes(entry)
    const checkCopy = (index, group) => {
      const heading = summary(headings()[index])
      Object.assign(heading, {
        nodeType: 1,
        textContent: text(heading),
        getAttribute: (name) => heading.props[name] ?? null,
        closest: (selector) => (selector.includes('.log-arrangement') ? heading : null)
      })
      vi.stubGlobal('getSelection', () => ({
        rangeCount: 1,
        isCollapsed: false,
        toString: () => heading.textContent,
        getRangeAt: () => ({ commonAncestorContainer: heading })
      }))
      const clipboardData = { setData: vi.fn() }
      copyListener({ clipboardData, preventDefault: vi.fn() })
      expect(clipboardData.setData).toHaveBeenCalledExactlyOnceWith(
        'text/plain',
        group.lines
          .filter((line) => line !== group.unrelated)
          .map((line) => line.text)
          .join('\n')
      )
    }
    const toggle = (index) =>
      all(headings()[index]).find((entry) => hasClass(entry, 'log-detail-toggle'))
    checkStructure()
    checkDetails(dorm, false)
    checkDetails(manufacture, false)
    await toggle(0).props.onClick()
    await toggle(1).props.onClick()
    checkDetails(dorm, true)
    checkDetails(manufacture, true)
    checkCopy(0, dorm)
    await toggle(0).props.onClick()
    await toggle(1).props.onClick()

    page.props.concise = true
    await nextTick()
    checkDetails(dorm, false)
    checkDetails(manufacture, false)
    toggle(0).props.onClick()
    await nextTick()
    checkDetails(dorm, true)
    checkDetails(manufacture, false)
    toggle(1).props.onClick()
    await nextTick()
    checkStructure()
    checkDetails(manufacture, true)
    toggle(0).props.onClick()
    await nextTick()
    checkDetails(dorm, false)
    checkDetails(manufacture, true)
    checkCopy(0, dorm)
    checkCopy(1, manufacture)
  })
})
const node = (tag, value = '') => ({ tag, text: value, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const hasClass = (element, name) => element.props.class?.split(/\s+/).includes(name)
const headingText = (element) =>
  text(all(element).find((entry) => hasClass(entry, 'log-heading__title'))).trim()
const portraits = (element) => all(element).filter((item) => item.props['data-operator-name'])
const visibleText = (element) =>
  hasClass(element, 'log-hidden') || hasClass(element, 'log-line--source-only')
    ? ''
    : element.text + element.children.map(visibleText).join('')

function wheelLogUp(page) {
  const scroll = page.all().find((element) => hasClass(element, 'log-output__scroll'))
  scroll.props.onWheelPassive({ type: 'wheel', deltaY: -100 })
}

function mount(overrides = {}, slots) {
  const props = reactive({ lines: [], operatorNames: [], ...overrides })
  const warnings = []
  const renderer = createRenderer({
    createElement: node,
    createText: (value) => node('#text', value),
    createComment: () => node('#comment'),
    setText: (element, value) => (element.text = value),
    setElementText(element, value) {
      element.text = value
      element.children = []
    },
    patchProp: (element, key, _previous, value) => (element.props[key] = value),
    parentNode: (element) => element.parent,
    nextSibling: (element) =>
      element.parent?.children[element.parent.children.indexOf(element) + 1],
    insert(element, parent, anchor = null) {
      if (element.parent) {
        const previous = element.parent.children
        previous.splice(previous.indexOf(element), 1)
      }
      element.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
    },
    remove(element) {
      const siblings = element.parent?.children
      if (siblings) siblings.splice(siblings.indexOf(element), 1)
      element.parent = null
    }
  })
  const app = renderer.createApp({ render: () => h(clientOutput, props, slots) })
  app.config.warnHandler = (message) => warnings.push(message)
  app.provide(ssrContextKey, { modules: new Set() })
  const host = node('root')
  app.mount(host)
  mounted.push(app)
  return {
    props,
    warnings,
    all: () => all(host),
    root: host,
    rows: () =>
      all(host).filter(
        (element) =>
          hasClass(element, 'log-line') ||
          (hasClass(element, 'log-facility-heading') && element.props['data-log-source'])
      ),
    unmount() {
      app.unmount()
      mounted.splice(mounted.indexOf(app), 1)
    }
  }
}

function mountRoomCopy({ ancestorType = 'text', selectedText, rangeCount = 1 } = {}) {
  const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
  vi.stubGlobal('document', document)
  const page = mount({
    lines: ['INFO room_1_1'],
    facilityPlan: { room_1_1: { name: '贸易站' } }
  })
  const root = page.all().find((element) => hasClass(element, 'log-output'))
  const room = page.all().find((element) => element.props['data-room-id'] === 'room_1_1')
  Object.assign(room, {
    nodeType: 1,
    textContent: text(room),
    getAttribute: (name) => room.props[name],
    closest: (selector) => (selector === '[data-room-id]' ? room : null)
  })
  const ancestor = ancestorType === 'element' ? room : { nodeType: 3, parentElement: room }
  root.contains = (candidate) =>
    all(root).includes(candidate.nodeType === 3 ? candidate.parentElement : candidate)
  const range = {
    commonAncestorContainer: ancestor,
    cloneContents: vi.fn(() => ({ querySelector: () => null }))
  }
  const selection = {
    rangeCount,
    isCollapsed: false,
    getRangeAt: vi.fn(() => range),
    toString: () => selectedText ?? room.textContent
  }
  vi.stubGlobal('getSelection', () => selection)
  const event = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
  const listener = document.addEventListener.mock.calls[0][1]
  return { room, range, selection, event, copy: () => listener(event) }
}

afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('running log output', () => {
  it('renders multiple rare choices in one tag band with individual colors and complete source text', () => {
    const source =
      '2026-11-05 00:30:00 INFO 2号招募位：发现稀有标签：治疗＋费用回复；资深干员；高级资深干员'
    const page = mount({
      lines: [
        {
          text: source,
          recruitment: {
            event: 'rare',
            rarity: 6,
            combinations: [
              { tags: ['治疗', '费用回复'], rarity: 4 },
              { tags: ['资深干员'], rarity: 5 },
              { tags: ['高级资深干员'], rarity: 6 }
            ]
          }
        }
      ]
    })
    const bands = page.all().filter((entry) => hasClass(entry, 'log-recruit-tags'))
    const choices = page.all().filter((entry) => hasClass(entry, 'log-recruit-combinations__group'))
    expect(bands).toHaveLength(1)
    expect(text(bands[0])).toBe('治疗＋费用回复；资深干员；高级资深干员')
    expect(bands[0].props['data-recruit-rarity']).toBeUndefined()
    expect(choices.map(text)).toEqual(['治疗＋费用回复', '资深干员', '高级资深干员'])
    expect(choices.map((entry) => entry.props['data-recruit-rarity'])).toEqual([4, 5, 6])
    expect(choices.map((entry) => entry.props.title)).toEqual([
      '4星标签组合',
      '5星标签组合',
      '6星标签组合'
    ])
    expect(choices.every((entry) => !hasClass(entry, 'log-recruit-tags'))).toBe(true)
    expect(
      page.all().find((entry) => hasClass(entry, 'log-token--recruit-notice')).props[
        'data-recruit-rarity'
      ]
    ).toBe(6)
    expect(text(page.rows()[0])).toBe(source)
    expect(portraits(page.rows()[0])).toEqual([])
    expect(page.warnings).toEqual([])
  })

  it('keeps all 25 choices and their separators in the compact layout', () => {
    const combinations = Array.from({ length: 25 }, (_, index) => ({
      tags: [`标签${index}`],
      rarity: 5
    }))
    const body =
      '2号招募位：发现稀有标签：' + combinations.map((choice) => choice.tags[0]).join('；')
    const source = '2026-11-05 00:30:00 INFO ' + body
    const page = mount({
      compact: true,
      lines: [{ text: source, recruitment: { event: 'rare', rarity: 5, combinations } }]
    })
    expect(page.all().filter((entry) => hasClass(entry, 'log-recruit-tags'))).toHaveLength(1)
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-recruit-combinations__group'))
        .map(text)
    ).toEqual(combinations.map((choice) => choice.tags[0]))
    expect(visibleText(page.rows()[0])).toBe('00:30:00' + body)
  })

  it('shows the full original rare log when the combination metadata omits an earlier choice', () => {
    const source = '2026-11-05 00:30:00 INFO 2号招募位：发现稀有标签：先锋干员＋支援；近战位＋控场'
    const page = mount({
      lines: [
        {
          text: source,
          recruitment: {
            event: 'rare',
            rarity: 5,
            combinations: [{ tags: ['近战位', '控场'], rarity: 5 }]
          }
        }
      ]
    })
    expect(page.all().some((entry) => hasClass(entry, 'log-recruit-tags'))).toBe(false)
    expect(text(page.rows()[0])).toBe(source)
  })

  it('retains plain text for a payload mixing legacy tags with combinations', () => {
    const source = '2026-11-05 00:30:00 INFO 2号招募位：发现稀有标签：先锋干员＋支援'
    const page = mount({
      lines: [
        {
          text: source,
          recruitment: {
            event: 'rare',
            rarity: 5,
            tags: ['先锋干员', '支援'],
            combinations: [{ tags: ['先锋干员', '支援'], rarity: 5 }]
          }
        }
      ]
    })
    expect(page.all().some((entry) => hasClass(entry, 'log-recruit-tags'))).toBe(false)
    expect(text(page.rows()[0])).toBe(source)
  })

  it.each(['9小时', '3小时50分'])('renders one unbroken duration field: %s', (duration) => {
    const source = `2026-11-04 18:00:00 INFO 1号招募位：开始招募，标签：支援机械，时长：${duration}`
    const page = mount({
      lines: [
        {
          text: source,
          recruitment: { event: 'start', tags: ['支援机械'], rarity: 1 }
        }
      ]
    })
    const fields = page.all().filter((entry) => hasClass(entry, 'log-token--recruit-duration'))
    expect(fields).toHaveLength(1)
    expect(text(fields[0])).toBe(`时长：${duration}`)
    expect(fields[0].props['data-recruit-rarity']).toBeUndefined()
    expect(text(page.rows()[0])).toBe(source)
  })

  it('preserves the recorded robot rarity on every rare combination and its notice', () => {
    const combinations = [
      ['元素'],
      ['支援机械'],
      ['元素', '支援机械'],
      ['支援机械', '治疗'],
      ['支援机械', '爆发']
    ].map((tags) => ({ tags, rarity: 1 }))
    const source =
      '2026-11-05 20:27:37 INFO 4号招募位：发现稀有标签：' +
      combinations.map((choice) => choice.tags.join('＋')).join('；')
    const page = mount({
      lines: [
        {
          text: source,
          group: 'recruitment',
          recruitment: { event: 'rare', rarity: 1, combinations }
        }
      ]
    })
    const groups = page.all().filter((entry) => hasClass(entry, 'log-recruit-combinations__group'))
    const notice = page.all().find((entry) => hasClass(entry, 'log-token--recruit-notice'))
    expect(groups.map((entry) => entry.props['data-recruit-rarity'])).toEqual([1, 1, 1, 1, 1])
    expect(groups.map(text)).toEqual(combinations.map((choice) => choice.tags.join('＋')))
    expect(notice.props['data-recruit-rarity']).toBe(1)
    expect(page.rows()[0].props['data-log-source']).toBe(source)
  })
  it.each([1, 4, 5, 6])('renders the %i-star selection as one compact group in place', (rarity) => {
    const source = '2026-11-04 18:00:00 INFO 1号招募位：开始招募，标签：治疗、费用回复，时长：9小时'
    const page = mount({
      lines: [
        {
          text: source,
          group: 'recruitment',
          recruitment: { event: 'start', tags: ['治疗', '费用回复'], rarity }
        }
      ]
    })
    const groups = page.all().filter((entry) => hasClass(entry, 'log-recruit-tags'))
    expect(groups).toHaveLength(1)
    expect(groups[0].props['data-recruit-rarity']).toBe(rarity)
    expect(groups[0].props.title).toBe(`${rarity}星标签组合`)
    expect(text(groups[0])).toBe('治疗、费用回复')
    expect(text(page.rows()[0])).toBe(source)
    expect(portraits(page.rows()[0])).toEqual([])
    expect(page.warnings).toEqual([])
  })

  it('renders rare notice color without tinting the timestamp or the entire log line', () => {
    const source = '2026-11-04 18:00:00 INFO 1号招募位：发现稀有标签：高级资深干员'
    const page = mount({
      lines: [
        {
          text: source,
          recruitment: { event: 'rare', tags: ['高级资深干员'], rarity: 6 }
        }
      ]
    })
    const colored = page.all().filter((entry) => entry.props['data-recruit-rarity'] === 6)
    expect(colored.map(text)).toEqual(['发现稀有标签', '高级资深干员'])
    expect(page.rows()[0].props['data-recruit-rarity']).toBeUndefined()
    expect(text(page.rows()[0])).toBe(source)
  })

  it('keeps recognition tags together and neutral in the compact layout', () => {
    const tags = ['重装干员', '辅助干员', '治疗', '费用回复', '输出']
    const source = `2026-11-04 18:00:00 INFO 4号招募位：识别标签：${tags.join('、')}`
    const page = mount({
      compact: true,
      lines: [
        {
          text: source,
          recruitment: { event: 'tags', tags, rarity: null }
        }
      ]
    })
    const groups = page.all().filter((entry) => hasClass(entry, 'log-recruit-tags'))
    expect(groups).toHaveLength(1)
    expect(groups[0].props['data-recruit-rarity']).toBeUndefined()
    expect(text(groups[0])).toBe(tags.join('、'))
    expect(page.all().filter((entry) => hasClass(entry, 'log-recruit-tags__name'))).toHaveLength(5)
    expect(visibleText(page.rows()[0])).toBe(`18:00:004号招募位：识别标签：${tags.join('、')}`)
  })

  it('invalidates cached presentation when metadata arrives and retains legacy fallback', async () => {
    const source = '2026-11-04 18:00:00 INFO 1号招募位：开始招募，标签：治疗，时长：9小时'
    const page = mount({ lines: [{ text: source }] })
    expect(page.all().some((entry) => hasClass(entry, 'log-recruit-tags'))).toBe(false)
    page.props.lines = [
      { text: source, recruitment: { event: 'start', tags: ['治疗'], rarity: 4 } }
    ]
    await nextTick()
    expect(page.all().filter((entry) => hasClass(entry, 'log-recruit-tags'))).toHaveLength(1)
    page.props.lines = [
      { text: source, recruitment: { event: 'start', tags: ['费用回复'], rarity: 4 } }
    ]
    await nextTick()
    expect(page.all().some((entry) => hasClass(entry, 'log-recruit-tags'))).toBe(false)
    expect(text(page.rows()[0])).toBe(source)
  })

  it('highlights snapshot group names while retaining person portraits when a group has the same name', () => {
    const header = '休息 72分0秒，至 19:42:00，随后执行「红松、企鹅物流上班；巫恋休息」'
    const task = {
      header,
      title: '红松、企鹅物流上班；巫恋休息',
      actions: [
        { kind: 'group', subject: '红松', action: '上班', members: ['阿米娅', '凯尔希'] },
        { kind: 'group', subject: '企鹅物流', action: '上班' },
        { kind: 'operator', subject: '巫恋', action: '休息' }
      ],
      rooms: [],
      targets: [],
      backups: []
    }
    const page = mount({
      lines: [{ text: `2026-11-04 18:00:00 INFO ${header}`, task }],
      facilityPlan: { meeting: { plans: [{ group: '巫恋' }] } }
    })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'task-action-subjects__group'))
        .map(text)
    ).toEqual(['红松', '企鹅物流'])
    expect(
      page.all().find((entry) => hasClass(entry, 'task-action-subjects__group')).props['aria-label']
    ).toBe('红松：阿米娅、凯尔希，共2人')
    expect(portraits(page.rows()[0]).map((entry) => entry.props['data-operator-name'])).toEqual([
      '巫恋'
    ])
    expect(visibleText(page.rows()[0])).toContain('红松、企鹅物流上班')
    expect(visibleText(page.rows()[0])).toContain('休息 72 分 0 秒，至 19:42:00')
    expect(visibleText(page.rows()[0])).not.toContain('红松组上班')
    expect(page.warnings).toEqual([])
  })

  it('opens a configured group roster from a backup adjustment forecast', async () => {
    const title = '调整干员（副表：远牙动态低优、感知下班）'
    const header = `已生成任务「${title}」，执行时间 2026-11-06 20:34:58`
    const page = mount({
      lines: [{ text: `2026-11-06 20:34:58 INFO ${header}`, task: { title, header } }],
      facilityPlan: { meeting: { plans: [{ agent: '阿米娅', group: '感知' }] } }
    })
    const group = page.all().find((entry) => hasClass(entry, 'task-action-subjects__group'))
    expect(text(group)).toBe('感知')
    group.props.onMouseenter({
      currentTarget: { getBoundingClientRect: () => ({ left: 10, top: 50 }) }
    })
    await nextTick()
    expect(text(page.all().find((entry) => hasClass(entry, 'task-action-roster')))).toContain(
      '阿米娅'
    )
  })

  it('renders one forecast with ordered facilities, operators and activation changes', async () => {
    const raw = '2026-11-04 18:30:02 INFO 纯文本回退；发电站 B303：Current、阿米娅；宿舍2：芬、Free'
    const task = {
      header: '休息至 19:42:00，随后执行甲组下班、乙组上班',
      title: '甲组下班、乙组上班',
      wait_seconds: 4320,
      rooms: [
        { id: 'room_3_3', label: '发电站 B303', agents: ['Current', '阿米娅'] },
        { id: 'dormitory_2', label: '宿舍2', agents: ['芬', 'Free'] }
      ],
      backups: [
        { name: '夜班', active: true },
        { name: '白班', active: false }
      ],
      targets: []
    }
    const page = mount({
      lines: [{ id: 1, text: raw, task }],
      facilityPlan: { room_3_3: { name: '制造站' } }
    })
    expect(page.rows()).toHaveLength(1)
    expect(page.all().some((entry) => hasClass(entry, 'log-forecast__details'))).toBe(true)
    expect(page.all().some((entry) => hasClass(entry, 'log-forecast__toggle'))).toBe(false)
    const header = page.all().find((entry) => hasClass(entry, 'log-forecast__header'))
    const details = page.all().find((entry) => hasClass(entry, 'log-forecast__details'))
    expect(header.parent).toBe(details.parent)
    expect(header.parent.props['data-log-source']).toBe(raw)
    expect(header.parent.children.indexOf(header)).toBeLessThan(
      header.parent.children.indexOf(details)
    )
    expect(all(header).some((entry) => hasClass(entry, 'log-forecast__room'))).toBe(false)
    expect(
      all(details)
        .filter((entry) => entry.props['data-operator-name'])
        .map((entry) => entry.props['data-operator-size'])
    ).toEqual([24, 24, 24, 24])
    expect(page.all().find((entry) => hasClass(entry, 'log-forecast__header')).props.title).toBe(
      '预计休息 72分0秒（记录时）'
    )
    expect(visibleText(page.rows()[0])).not.toContain('纯文本回退')
    expect(visibleText(page.rows()[0])).toContain('预计激活的副表：夜班')
    expect(visibleText(page.rows()[0])).toContain('预计停用的副表：白班')
    expect(visibleText(page.rows()[0]).split('19:42:00')).toHaveLength(2)
    expect(portraits(page.rows()[0]).map((entry) => entry.props['data-operator-name'])).toEqual([
      '芬',
      'Free',
      'Current',
      '阿米娅'
    ])
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-forecast__room-label'))
        .map(text)
    ).toEqual(['宿舍2', '发电站 B303'])
    page.props.facilityPlan.room_3_3.name = '贸易站'
    await nextTick()
    expect(visibleText(page.rows()[0])).toContain('发电站 B303')
    page.props.lines[0].task.header = '休息至 20:00:00，随后执行甲组上班'
    await nextTick()
    expect(visibleText(page.rows()[0])).toContain('20:00:00')
    expect(visibleText(page.rows()[0])).not.toContain('19:42:00')
    const toggle = () => page.all().find((entry) => hasClass(entry, 'log-detail-toggle'))
    const hasDetails = () => page.all().some((entry) => hasClass(entry, 'log-forecast__details'))
    expect(toggle().props['aria-expanded']).toBe(true)
    toggle().props.onClick()
    await nextTick()
    expect(hasDetails()).toBe(false)
    expect(page.rows()[0].props['data-log-source']).toBe(raw)
    page.props.concise = true
    await nextTick()
    expect(hasDetails()).toBe(false)
    toggle().props.onClick()
    await nextTick()
    expect(hasDetails()).toBe(true)
    page.props.concise = false
    await nextTick()
    expect(hasDetails()).toBe(false)
    toggle().props.onClick()
    await nextTick()
    expect(hasDetails()).toBe(true)
  })

  it.each([
    [1, false],
    [2, true],
    [3, true]
  ])('uses shared operator columns for %i forecast rooms when needed', (count, aligned) => {
    const header = '休息至 19:42:00，随后执行「换班」'
    const task = {
      header,
      title: '换班',
      rooms: [
        { id: 'room_1_1', label: '贸易站 B101', agents: ['但书', 'Current'] },
        { id: 'room_2_1', label: '贸易站 B201', agents: ['龙舌兰', 'Current'] },
        { id: 'dormitory_2', label: '宿舍2', agents: ['芬', 'Current'] }
      ].slice(0, count),
      targets: [],
      backups: []
    }
    const page = mount({ lines: [{ id: 1, text: `2026-11-04 18:30:02 INFO ${header}`, task }] })
    const roster = page.all().find((entry) => hasClass(entry, 'log-forecast__rooms'))
    expect(hasClass(roster, 'log-forecast__rooms--aligned')).toBe(aligned)
    expect(all(roster).filter((entry) => hasClass(entry, 'log-forecast__room'))).toHaveLength(count)
  })

  it('falls back to the original message for invalid task metadata', () => {
    const raw = '2026-11-04 18:30:02 INFO 原始预告完整保留'
    const page = mount({ lines: [{ text: raw, task: { title: '公招' } }] })
    expect(text(page.rows()[0])).toBe(raw)
  })

  it('shows full task details directly with plain summary text, Current and stable source identity', async () => {
    const task = {
      header: '随后执行红松上班',
      title: '红松上班',
      actions: [{ kind: 'operator', subject: '红松', action: '上班' }],
      rooms: [{ id: 'room_3_3', label: '发电站 B303', agents: ['Current', '红松'] }],
      backups: [{ name: '深海下班', active: true }],
      targets: []
    }
    const raw = '2026-11-05 01:00:00 INFO 随后执行红松上班；发电站 B303：Current、红松'
    const page = mount({ lines: [{ id: 42, text: raw, task }] })
    expect(page.all().some((entry) => hasClass(entry, 'log-forecast__details'))).toBe(true)
    const header = page.all().find((entry) => hasClass(entry, 'log-forecast__header'))
    expect(header.props.onClick).toBeUndefined()
    expect(page.all().some((entry) => hasClass(entry, 'log-forecast__toggle'))).toBe(false)
    expect(portraits(page.rows()[0]).map((entry) => entry.props['data-operator-name'])).toContain(
      'Current'
    )
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-token--backup'))
        .map(text)
    ).toContain('深海下班')

    page.props.lines = [{ id: 42, text: raw, task: JSON.parse(JSON.stringify(task)) }]
    await nextTick()
    expect(page.all().some((entry) => hasClass(entry, 'log-forecast__details'))).toBe(true)
    expect(page.rows()[0].props['data-log-key']).toBe('id:42')
    expect(visibleText(page.rows()[0])).toContain('发电站 B303')
    expect(page.rows()[0].props['data-log-source']).toBe(raw)
  })

  it('shows one slot title per consecutive recruitment run and preserves every source row', () => {
    const messages = [
      ['recruitment', '1号招募位：识别标签：治疗'],
      ['recruitment', '1号招募位：开始招募，选择标签：治疗，时长：9小时'],
      ['recruitment', '2号招募位：招募获得：芬'],
      ['recruitment', '1号招募位：保留标签，等待手动选择'],
      ['base-scheduler', '基建：排班'],
      ['recruitment', '1号招募位：招募获得：炎熔']
    ]
    const lines = messages.map(([group, message], index) => ({
      id: index + 1,
      group,
      text: `2026-11-05 01:00:0${index} INFO ${message}`
    }))
    const page = mount({ lines })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-recruit-slot'))
        .map(headingText)
    ).toEqual(['1号公招位', '2号公招位', '1号公招位', '1号公招位'])
    expect(page.rows().map(text)).toEqual(lines.map((line) => line.text))
    expect(
      page
        .rows()
        .map(visibleText)
        .every((line) => !line.includes('号招募位'))
    ).toBe(true)
    expect(page.rows().map((row) => row.props['data-log-key'])).toEqual(
      lines.map((line) => `id:${line.id}`)
    )
    expect(page.rows()[3].props['data-log-source']).toBe(lines[3].text)
  })

  it('summarizes explicit recruitment slots and folds only their routine observations', async () => {
    const parent = { type: 'recruitment-slot', id: 'slot-1', slot: 1 }
    const lines = [
      { text: '15:21:40 INFO Scene 801: 公招主界面', group: 'recognition' },
      { text: '15:21:41 INFO 1号招募位：准备领取干员', event: parent, parent },
      { text: '15:21:42 INFO Scene 7: 跳过', group: 'recognition', parent },
      { text: '15:21:43 INFO 1号招募位：招募获得：克洛丝', agents: ['克洛丝'], parent },
      { text: '15:21:44 INFO 1号招募位：识别标签：治疗', parent },
      { text: '15:21:45 INFO 1号招募位：发现稀有标签：高级资深干员', parent },
      { text: '15:21:46 WARNING 1号招募位：招募画面读取失败', parent },
      { text: '15:21:47 INFO 1号招募位：招募券30张，低于三星招募阈值40张，本次跳过', parent },
      { text: '15:21:48 INFO 2号招募位：招募获得：芬', parent }
    ].map((entry, index) => ({ id: index + 1, group: 'recruitment', ...entry }))
    const page = mount({ lines, concise: true })
    const summary = () => page.all().find((entry) => hasClass(entry, 'log-recruit-slot'))
    const toggle = () => all(summary()).find((entry) => hasClass(entry, 'log-detail-toggle'))
    const folded = () => page.rows().map((row) => Boolean(hasClass(row, 'log-line--source-only')))

    expect(visibleText(summary())).toContain('1号公招位 · 获得 克洛丝')
    expect(visibleText(summary())).toContain(' · 招募券不足，跳过')
    expect(visibleText(summary())).not.toContain('芬')
    expect(folded()).toEqual([false, true, true, true, true, false, false, true, false])
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
    expect(toggle().props['aria-expanded']).toBe(false)
    toggle().props.onClick()
    await nextTick()
    expect(folded().every((isFolded) => !isFolded)).toBe(true)
    expect(page.rows().map(text)).toEqual(lines.map((line) => line.text))
    expect(toggle().props['aria-expanded']).toBe(true)
  })

  it('bridges only bracketed legacy observations within the same slot and stops at a decision', () => {
    const messages = [
      '1号招募位：招募获得：克洛丝',
      'Scene 801: 公招主界面',
      '1号招募位：识别标签：治疗',
      '1号招募位：招募券30张，低于三星招募阈值40张，本次跳过',
      'Scene 7: 跳过',
      '1号招募位：招募获得：米格鲁',
      '1号招募位：开始招募，不选标签，时长：9小时',
      'Scene 803: 开包干员展示',
      '2号招募位：招募获得：芬',
      '2号招募位：识别标签：治疗'
    ]
    const lines = messages.map((message, index) => ({
      id: index + 1,
      text: `2026-11-06 15:21:${String(index).padStart(2, '0')} INFO ${message}`
    }))
    const page = mount({ lines, concise: true })
    const summaries = page.all().filter((entry) => hasClass(entry, 'log-recruit-slot'))
    expect(summaries.map(headingText)).toEqual(['1号公招位', '1号公招位', '2号公招位'])
    expect(summaries.map(visibleText)).toEqual([
      expect.stringContaining('获得 克洛丝 · 招募券不足，跳过'),
      expect.stringContaining('获得 米格鲁 · 已开始招募'),
      expect.stringContaining('获得 芬')
    ])
    expect(
      page
        .rows()
        .filter((row) => !hasClass(row, 'log-line--source-only'))
        .map((row) => row.props['data-log-source'])
    ).toEqual([lines[4].text, lines[7].text])
  })

  it('includes the acquired operator in the active recruitment summary and stops the whole highlight', async () => {
    const parent = { type: 'recruitment-slot', id: 'recruit-with-portrait', slot: 1 }
    const page = mount({
      running: true,
      lines: [
        {
          id: 'recruit-start',
          group: 'recruitment',
          text: '15:22:00 INFO 1号招募位：准备领取干员',
          parent,
          event: { ...parent, phase: 'started' }
        },
        {
          id: 'recruit-observation',
          group: 'recruitment',
          text: '15:22:01 INFO 1号招募位：招募获得：芬',
          parent
        }
      ]
    })
    const active = () => page.all().find((entry) => hasClass(entry, 'log-lifecycle-active'))
    expect(portraits(active()).map((entry) => entry.props['data-operator-name'])).toEqual(['芬'])
    expect(all(active()).some((entry) => hasClass(entry, 'log-stamp'))).toBe(false)
    page.props.running = false
    await nextTick()
    expect(active()).toBeUndefined()
    expect(page.all().some((entry) => entry.props['data-operator-name'] === '芬')).toBe(true)
  })

  it('updates the latest phased recruitment summary in place and keeps interrupted history static', async () => {
    const slot = (id, slot, phase, message) => {
      const parent = { type: 'recruitment-slot', id, slot }
      return {
        id: `${id}-${phase}`,
        group: 'recruitment',
        text: `15:22:00 INFO ${slot}号招募位：${message}`,
        parent,
        event: phase ? { ...parent, phase } : parent
      }
    }
    const first = slot('first', 1, 'started', '准备领取干员')
    const second = slot('second', 2, 'started', '检查招募标签')
    const legacy = slot('legacy', 3, null, '检查招募标签')
    const page = mount({ lines: [first, legacy] })
    const summaries = () => page.all().filter((entry) => hasClass(entry, 'log-recruit-slot'))
    const active = () =>
      summaries()
        .filter((entry) => all(entry).some((child) => hasClass(child, 'log-lifecycle-active')))
        .map(headingText)
    expect(active()).toEqual([])
    expect(visibleText(summaries()[0])).toContain('检查结果未确认')
    expect(summaries()[1].props['data-recruit-phase']).toBeNull()

    page.props.running = true
    await nextTick()
    expect(active()).toEqual(['1号公招位'])
    page.props.lines.push(second)
    await nextTick()
    expect(active()).toEqual(['2号公招位'])
    const secondSummary = summaries().at(-1)

    page.props.lines.push(slot('second', 4, 'completed', '检查完成'))
    await nextTick()
    expect(active()).toEqual(['2号公招位'])
    const terminal = slot('second', 2, 'completed', '检查完成')
    page.props.lines.push(terminal)
    await nextTick()
    expect(summaries().at(-1)).toBe(secondSummary)
    expect(secondSummary.props['data-recruit-phase']).toBe('completed')
    expect(visibleText(secondSummary)).toContain('检查完成')
    expect(active()).toEqual([])
    expect(hasClass(page.rows().at(-1), 'log-line--source-only')).toBe(true)
    expect(page.rows().at(-1).props['data-log-source']).toBe(terminal.text)

    page.props.lines.push(slot('third', 3, 'started', '检查招募标签'))
    await nextTick()
    expect(active()).toEqual(['3号公招位'])
    page.props.running = false
    await nextTick()
    expect(active()).toEqual([])
    page.props.running = true
    await nextTick()
    expect(active()).toEqual([])

    page.props.running = false
    page.props.lines.push(slot('fourth', 4, 'started', '检查招募标签'))
    page.props.running = true
    await nextTick()
    expect(active()).toEqual(['4号公招位'])
  })

  it.each([
    ['failed', '检查未完成'],
    ['stopped', '已停止检查']
  ])('shows recruitment %s without inventing an outcome', (phase, status) => {
    const parent = { type: 'recruitment-slot', id: phase, slot: 1 }
    const lines = [
      { text: 'INFO 1号招募位：检查招募标签', event: { ...parent, phase: 'started' }, parent },
      { text: `INFO 1号招募位：${status}`, event: { ...parent, phase }, parent }
    ]
    const page = mount({ lines, running: true })
    const summary = page.all().find((entry) => hasClass(entry, 'log-recruit-slot'))
    expect(summary.props['data-recruit-phase']).toBe(phase)
    expect(visibleText(summary)).toContain(status)
    expect(visibleText(summary)).not.toContain('获得')
    expect(all(summary).some((entry) => hasClass(entry, 'log-lifecycle-active'))).toBe(false)
  })

  it('follows appended records at the tail and keeps equivalent refreshes in place', async () => {
    const lines = Array.from({ length: 10 }, (_, index) => ({
      id: index + 1,
      text: `INFO 记录${index + 1}`
    }))
    const page = mount({ lines, autoScroll: false })
    let position = 40
    let viewportHeight = 40
    let scrolled
    const writes = []
    const container = {
      get clientHeight() {
        return viewportHeight
      },
      get scrollHeight() {
        return page.rows().length * 20
      },
      get scrollTop() {
        return position
      },
      set scrollTop(value) {
        position = value
        writes.push(value)
      },
      getBoundingClientRect: () => ({ top: 0 }),
      addEventListener(type, listener) {
        if (type === 'scroll') scrolled = listener
      },
      removeEventListener() {},
      querySelectorAll: (selector) =>
        selector === '[data-log-anchor]'
          ? page
              .rows()
              .filter((row) => row.props['data-log-anchor'])
              .map((row, index) => ({
                getAttribute: (key) => row.props[key],
                getBoundingClientRect: () => ({
                  top: index * 20 - position,
                  bottom: (index + 1) * 20 - position
                })
              }))
          : []
    }
    page.all().find((entry) => hasClass(entry, 'log-output')).querySelector = () => container
    await nextTick()
    page.props.lines = lines.map((line) => ({ ...line }))
    page.props.facilityPlan = { central: { name: '控制中枢' } }
    await nextTick()
    expect(position).toBe(40)
    expect(writes).toEqual([])

    position = 160
    page.props.lines = [...page.props.lines, { id: 11, text: 'INFO 记录11' }]
    await nextTick()
    expect(position).toBe(160)
    page.props.autoScroll = true
    await nextTick()
    await nextTick()
    expect(position).toBe(180)

    wheelLogUp(page)
    position = 40
    scrolled()
    page.props.lines = [...page.props.lines, { id: 12, text: 'INFO 记录12' }]
    await nextTick()
    expect(position).toBe(40)
    position = 200
    scrolled()
    page.props.lines = [...page.props.lines, { id: 13, text: 'INFO 记录13' }]
    await nextTick()
    expect(position).toBe(220)

    viewportHeight = 20
    page.props.lines = [...page.props.lines, { id: 14, text: 'INFO 记录14' }]
    await nextTick()
    expect(position).toBe(260)

    const clock = vi.spyOn(performance, 'now').mockReturnValue(1000)
    wheelLogUp(page)
    position = 40
    scrolled()
    page.props.lines = [...page.props.lines, { id: 15, text: 'INFO 记录15' }]
    await nextTick()
    expect(position).toBe(40)

    clock.mockReturnValue(1200)
    page.props.lines = [...page.props.lines, { id: 16, text: 'INFO 记录16' }]
    await nextTick()
    expect(position).toBe(300)
    clock.mockRestore()
  })

  it.each([false, true])(
    'removes a completed preview without shifting the reading anchor (at tail %s)',
    async (atTail) => {
      const parent = { type: 'depot-scan', id: 'finished-preview' }
      const page = mount({
        autoScroll: false,
        running: true,
        lines: [
          {
            id: 1,
            text: '20:55:58 INFO 正在扫描仓库',
            event: { ...parent, phase: 'started', anchor: true, summary: '正在扫描仓库' }
          },
          { id: 2, text: '20:56:04 INFO 已进入仓库', parent },
          ...Array.from({ length: 8 }, (_, index) => ({
            id: index + 3,
            text: `INFO 其他记录 ${index}`
          }))
        ]
      })
      const layoutRows = () =>
        page.all().filter((row) => row.props['data-log-anchor'] || hasClass(row, 'log-live-detail'))
      let position = 65
      const container = {
        clientHeight: 40,
        get scrollHeight() {
          return layoutRows().length * 20
        },
        get scrollTop() {
          return position
        },
        set scrollTop(value) {
          position = value
        },
        getBoundingClientRect: () => ({ top: 0 }),
        addEventListener() {},
        removeEventListener() {},
        querySelectorAll: (selector) =>
          selector === '[data-log-anchor]'
            ? layoutRows().flatMap((row, index) =>
                !row.props['data-log-anchor']
                  ? []
                  : [
                      {
                        getAttribute: (key) => row.props[key],
                        getBoundingClientRect: () => ({
                          top: index * 20 - position,
                          bottom: (index + 1) * 20 - position
                        })
                      }
                    ]
              )
            : []
      }
      page.all().find((entry) => hasClass(entry, 'log-output')).querySelector = () => container
      await nextTick()
      page.props.autoScroll = true
      await nextTick()
      await nextTick()
      if (!atTail) wheelLogUp(page)
      position = atTail ? 160 : 65
      expect(container.scrollHeight).toBe(200)
      page.props.lines = [
        ...page.props.lines,
        {
          id: 11,
          text: '20:56:14 INFO 仓库扫描完成',
          event: { ...parent, phase: 'completed', anchor: false, summary: '仓库扫描完成' }
        }
      ]
      await nextTick()
      expect(container.scrollHeight).toBe(180)
      expect(position).toBe(atTail ? 140 : 45)
      expect(page.all().some((entry) => hasClass(entry, 'log-live-detail'))).toBe(false)
    }
  )

  it('keeps one recruitment slot heading through incidental technical observations', () => {
    const messages = [
      ['recruitment', '1号招募位：识别标签：治疗'],
      ['recognition', 'Scene 801: 公招主界面'],
      ['recruitment', '1号招募位：开始招募，选择标签：治疗，时长：9小时'],
      ['recruitment', '结束公招'],
      ['recruitment', '1号招募位：招募获得：炎熔']
    ]
    const lines = messages.map(([group, body], index) => ({
      id: index + 1,
      group,
      text: `2026-11-05 01:00:0${index} INFO ${body}`
    }))
    const page = mount({ lines })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-recruit-slot'))
        .map(headingText)
    ).toEqual(['1号公招位', '1号公招位'])
    expect(page.rows().map(text)).toEqual(lines.map((line) => line.text))
  })

  it.each([false, true])(
    'preserves the scroll position across resizes with follow %s',
    async (autoScroll) => {
      let resized
      let scrolled
      const disconnect = vi.fn()
      vi.stubGlobal(
        'ResizeObserver',
        class {
          constructor(callback) {
            resized = callback
          }
          observe() {}
          disconnect = disconnect
        }
      )
      const page = mount({
        autoScroll,
        lines: Array.from({ length: 10 }, (_, index) => ({
          id: index + 1,
          text: `INFO 日志${index}`
        }))
      })
      let position = autoScroll ? 160 : 107
      let lineHeight = 20
      const container = {
        clientHeight: 40,
        get scrollHeight() {
          return page.rows().length * lineHeight
        },
        get scrollTop() {
          return position
        },
        set scrollTop(value) {
          position = value
        },
        getBoundingClientRect: () => ({ top: 0 }),
        addEventListener(type, listener) {
          if (type === 'scroll') scrolled = listener
        },
        removeEventListener() {},
        querySelectorAll: (selector) =>
          selector === '[data-log-anchor]'
            ? page
                .rows()
                .filter((row) => row.props['data-log-anchor'])
                .map((row, index) => ({
                  getAttribute: (key) => row.props[key],
                  getBoundingClientRect: () => ({
                    top: index * lineHeight - position,
                    bottom: (index + 1) * lineHeight - position
                  })
                }))
            : []
      }
      const root = page.all().find((entry) => hasClass(entry, 'log-output'))
      root.querySelector = (selector) =>
        selector === '.n-scrollbar-container'
          ? container
          : page.all().find((entry) => hasClass(entry, 'log-output__lines'))
      await nextTick()

      if (autoScroll) {
        container.clientHeight = 30
        resized()
        expect(position).toBe(170)

        container.clientHeight = 20
        position = 175
        scrolled()
        resized()
        expect(position).toBe(180)

        container.clientHeight = 10
        wheelLogUp(page)
        position = 150
        scrolled()
        resized()
        expect(position).toBe(150)

        await nextTick()
        const jump = page.all().find((entry) => hasClass(entry, 'log-jump-latest'))
        jump.props.onClick({ currentTarget: jump })
        expect(position).toBe(190)

        container.clientHeight = 70
        position = 130
        container.clientHeight = 10
        scrolled()
        expect(position).toBe(190)

        container.clientHeight = 70
        position = 130
        container.clientHeight = 10
        page.props.lines = [...page.props.lines, { id: 11, text: 'INFO 新日志' }]
        await nextTick()
        expect(position).toBe(210)
      } else {
        lineHeight = 30
        resized()
        expect(position).toBe(157)
      }
      page.unmount()
      expect(disconnect).toHaveBeenCalledOnce()
    }
  )

  it('renders fixed-size product, order and purple drone icons in place with unchanged text', () => {
    const source =
      '2026-11-05 01:00:00 INFO 识别到当前制造产物：中级作战记录；使用3架无人机；当前为 但书 订单, 订单价值为: 2500'
    const page = mount({ lines: [{ id: 1, text: source }], operatorNames: ['但书'] })
    const items = page.all().filter((entry) => hasClass(entry, 'log-token--item'))
    expect(items.map(text)).toEqual(['中级作战记录', '无人机', '但书'])
    for (const item of items.filter((entry) => !hasClass(entry, 'log-token--order-operator'))) {
      const icon = all(item).find((entry) => entry.tag === 'img')
      expect(icon.props.width).toBe('16')
      expect(icon.props.height).toBe('16')
      expect(icon.props.alt).toBe('')
      expect(item.props.style['--log-item-light']).toMatch(/^#[0-9a-f]{6}$/i)
      expect(item.props.style['--log-item-dark']).toMatch(/^#[0-9a-f]{6}$/i)
    }
    expect(hasClass(items[0], 'log-token--item-experience')).toBe(true)
    expect(items[1].props.style['--log-item-light']).toBe('#8b63de')
    expect(portraits(page.rows()[0]).map((entry) => entry.props['data-operator-name'])).toEqual([
      '但书'
    ])
    expect(portraits(items[2])[0].props['data-operator-size']).toBe(16)
    expect(items[2].props.style['--log-item-light']).toBe('#a3c1da')
    expect(text(page.rows()[0])).toBe(source)
  })

  it('groups repeated explicit facilities in order and indents operations without dropping destination semantics', () => {
    const room = 'room_2_1'
    const lines = [
      {
        id: 1,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:00 INFO 贸易站 B201：读取订单'
      },
      { id: 2, group: 'recognition', text: '2026-11-05 01:00:01 INFO Scene 221: 贸易站订单列表' },
      {
        id: 3,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:02 INFO 贸易站 B201：当前无人机数量3'
      },
      {
        id: 4,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:03 INFO 安排干员：但书 → 贸易站 B201'
      }
    ]
    const page = mount({
      lines,
      operatorNames: ['但书'],
      facilityPlan: { [room]: { name: '贸易站' } }
    })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-facility-heading'))
        .map(headingText)
    ).toEqual(['贸易站 B201'])
    expect(page.rows().every((entry) => hasClass(entry, 'log-line--nested'))).toBe(true)
    expect(page.rows().map(text)).toEqual(lines.map((line) => line.text))
    expect(visibleText(page.rows()[0])).toBe('01:00:00读取订单')
    expect(visibleText(page.rows()[2])).toBe('01:00:02当前无人机数量3')
    expect(visibleText(page.rows()[3])).toContain('安排干员：但书 → 贸易站 B201')
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('leaves single facilities inline and does not merge across a different room or substantive unscoped work', () => {
    const room = 'room_2_1'
    const lines = [
      {
        id: 1,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:00 INFO 贸易站 B201：读取订单'
      },
      {
        id: 2,
        group: 'base-scheduler',
        room: 'room_1_1',
        text: '2026-11-05 01:00:01 INFO 贸易站 B101：读取订单'
      },
      {
        id: 3,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:02 INFO 贸易站 B201：使用无人机'
      },
      { id: 4, group: 'base-scheduler', text: '2026-11-05 01:00:03 INFO 执行其他基建任务' },
      {
        id: 5,
        group: 'base-scheduler',
        room,
        text: '2026-11-05 01:00:04 INFO 贸易站 B201：重新读取订单'
      }
    ]
    const page = mount({
      lines,
      facilityPlan: { [room]: { name: '贸易站' }, room_1_1: { name: '贸易站' } }
    })
    expect(page.all().some((entry) => hasClass(entry, 'log-facility-heading'))).toBe(false)
    expect(page.rows().some((entry) => hasClass(entry, 'log-line--nested'))).toBe(false)
    expect(
      page
        .rows()
        .map(visibleText)
        .filter((line) => line.includes('贸易站 B201'))
    ).toHaveLength(3)
    expect(page.rows().map(text)).toEqual(lines.map((line) => line.text))
  })

  it('does not invent full facility headings for unknown metadata or production rooms without a facility type', () => {
    const page = mount({
      lines: [
        { id: 1, group: 'base-scheduler', room: 'unknown-room', text: 'INFO 未知设施：读取状态' },
        { id: 2, group: 'base-scheduler', room: 'unknown-room', text: 'INFO 未知设施：完成' },
        { id: 3, group: 'base-scheduler', room: 'room_2_1', text: 'INFO room_2_1：读取状态' },
        { id: 4, group: 'base-scheduler', room: 'room_2_1', text: 'INFO room_2_1：完成' }
      ]
    })
    expect(page.all().some((entry) => hasClass(entry, 'log-facility-heading'))).toBe(false)
  })

  it.each([
    [
      '宿舍2：准备将[[operator:阿米娅]]调整到第1位，先安排临时阵容',
      '准备将阿米娅调整到第1位，先安排临时阵容'
    ],
    [
      '准备将[[operator:阿米娅]]调整到宿舍2第1位，先安排临时阵容',
      '准备将阿米娅调整到宿舍2第1位，先安排临时阵容'
    ]
  ])(
    'includes a real single-room temporary-arrangement snapshot and trims only its leading facility: %s',
    async (header, displayed) => {
      const room = 'dormitory_2'
      const agents = ['Lancet-2', '阿米娅', 'Current']
      const source = `2026-11-05 01:00:00 INFO ${header}\n宿舍2：${agents.join('、')}`
      const lines = [
        {
          id: 1,
          group: 'base-scheduler',
          room,
          agents: ['阿米娅'],
          text: source,
          task: {
            title: '临时驻员安排',
            header,
            rooms: [{ id: room, label: '宿舍2', agents }],
            backups: [],
            targets: [],
            actions: []
          }
        },
        {
          id: 2,
          group: 'base-scheduler',
          room,
          text: '2026-11-05 01:00:01 INFO 宿舍2：已选择临时驻员'
        },
        { id: 3, group: 'base-scheduler', room, text: '2026-11-05 01:00:02 INFO 宿舍2：确认驻员' }
      ]
      const page = mount({ lines, operatorNames: ['Lancet-2', '阿米娅'] })
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-facility-heading'))
          .map(headingText)
      ).toEqual(['宿舍2'])
      expect(page.rows().every((entry) => hasClass(entry, 'log-line--nested'))).toBe(true)
      expect(visibleText(page.all().find((entry) => hasClass(entry, 'log-forecast__header')))).toBe(
        displayed
      )
      expect(
        portraits(page.all().find((entry) => hasClass(entry, 'log-forecast__header'))).map(
          (entry) => entry.props['data-operator-name']
        )
      ).toEqual(['阿米娅'])
      expect(
        portraits(page.all().find((entry) => hasClass(entry, 'log-forecast__header'))).map(
          (entry) => entry.props['data-operator-size']
        )
      ).toEqual([16])
      expect(page.rows()[0].props['data-log-source']).toBe(source)
      expect(page.rows()[0].props['data-log-source']).toContain('[[operator:阿米娅]]')

      const details = page.all().find((entry) => hasClass(entry, 'log-forecast__details'))
      expect(portraits(details).map((entry) => entry.props['data-operator-name'])).toEqual(agents)
      expect(portraits(details).map((entry) => entry.props['data-operator-size'])).toEqual([
        24, 24, 24
      ])
      expect(text(details)).toContain('宿舍2')
      expect(page.rows()[0].props['data-log-source']).toBe(source)
    }
  )

  it.each(['multiple rooms', 'another target'])(
    'keeps a forecast with %s outside a facility-only run',
    (kind) => {
      const room = 'dormitory_2'
      const primary = { id: room, label: '宿舍2', agents: ['Current'] }
      const other = { id: 'dormitory_3', label: '宿舍3', agents: ['阿米娅'] }
      const page = mount({
        lines: [
          {
            id: 1,
            group: 'base-scheduler',
            room,
            text: '2026-11-05 01:00:00 INFO 宿舍2：准备安排',
            task: {
              header: '宿舍2：准备安排',
              title: '驻员安排',
              backups: [],
              actions: [],
              rooms: kind === 'multiple rooms' ? [primary, other] : [primary],
              targets: kind === 'another target' ? [{ id: other.id, label: other.label }] : []
            }
          },
          { id: 2, group: 'base-scheduler', room, text: '2026-11-05 01:00:01 INFO 宿舍2：读取驻员' }
        ]
      })
      expect(page.all().some((entry) => hasClass(entry, 'log-facility-heading'))).toBe(false)
      expect(page.rows().some((entry) => hasClass(entry, 'log-line--nested'))).toBe(false)
      expect(visibleText(page.rows()[0])).toContain('宿舍2：准备安排')
    }
  )

  it.each([false, true])(
    'starts facility and recruitment sequences again on their recorded date, compact=%s',
    (compact) => {
      const room = 'room_2_1'
      const lines = [
        {
          id: 1,
          group: 'base-scheduler',
          room,
          text: '2026-11-04 23:59:59 INFO 贸易站 B201：读取订单'
        },
        {
          id: 2,
          group: 'base-scheduler',
          room,
          text: '2026-11-05 00:00:00 INFO 贸易站 B201：读取订单'
        },
        { id: 3, group: 'recruitment', text: '2026-11-05 23:59:59 INFO 1号招募位：识别标签：治疗' },
        { id: 4, group: 'recruitment', text: '2026-11-06 00:00:00 INFO 1号招募位：招募获得：炎熔' }
      ]
      const page = mount({ compact, lines, facilityPlan: { [room]: { name: '贸易站' } } })
      expect(page.all().some((entry) => hasClass(entry, 'log-facility-heading'))).toBe(false)
      expect(
        page
          .rows()
          .slice(0, 2)
          .map(visibleText)
          .every((value) => value.includes('贸易站 B201：'))
      ).toBe(true)
      expect(
        page
          .rows()
          .slice(0, 2)
          .some((entry) => hasClass(entry, 'log-line--nested'))
      ).toBe(false)
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-recruit-slot'))
          .map(headingText)
      ).toEqual(['1号公招位', '1号公招位'])
      expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
    }
  )

  it.each([false, true])(
    'shows the first source timestamp on facility and recruitment headings, compact=%s',
    (compact) => {
      const room = 'dormitory_2'
      const lines = [
        {
          id: 1,
          room,
          group: 'base-scheduler',
          text: '2026-11-05 03:04:05,120 INFO 宿舍2：读取驻员'
        },
        { id: 2, room, group: 'base-scheduler', text: '2026-11-05 03:04:07 INFO 宿舍2：确认驻员' },
        { id: 3, group: 'recruitment', text: '2026-11-05 07:08:09 INFO 1号招募位：识别标签：治疗' },
        {
          id: 4,
          group: 'recruitment',
          text: '2026-11-05 07:08:11 INFO 1号招募位：开始招募，选择标签：治疗，时长：9小时'
        }
      ]
      const page = mount({ compact, lines })
      const headings = page
        .all()
        .filter(
          (entry) => hasClass(entry, 'log-facility-heading') || hasClass(entry, 'log-recruit-slot')
        )
      expect(headings.map(headingText)).toEqual(['宿舍2', '1号公招位'])
      const stamps = headings.map((heading) =>
        all(heading).find((entry) => hasClass(entry, 'log-stamp'))
      )
      expect(stamps.map(text)).toEqual(['03:04:05', '07:08:09'])
      expect(stamps[0].props.title).toBe('2026-11-05 03:04:05,120')
      expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
      expect(page.rows().map((entry) => entry.props['data-log-key'])).toEqual([
        'id:1',
        'id:2',
        'id:3',
        'id:4'
      ])
    }
  )

  it('does not invent heading timestamps when source messages have no timestamp', () => {
    const room = 'dormitory_2'
    const page = mount({
      compact: true,
      lines: [
        { id: 1, room, group: 'base-scheduler', text: '宿舍2：读取驻员' },
        { id: 2, room, group: 'base-scheduler', text: '宿舍2：确认驻员' },
        { id: 3, group: 'recruitment', text: '1号招募位：识别标签：治疗' }
      ]
    })
    const headings = page
      .all()
      .filter(
        (entry) => hasClass(entry, 'log-facility-heading') || hasClass(entry, 'log-recruit-slot')
      )
    expect(headings.map(headingText)).toEqual(['宿舍2', '1号公招位'])
    expect(
      headings.some((heading) => all(heading).some((entry) => hasClass(entry, 'log-stamp')))
    ).toBe(false)
  })

  it.each(['上班', '转为空闲'])('copies a %s forecast with its original source', (action) => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    const title = (action === '转为空闲' ? '桑葚休息；' : '') + `阿米娅、芬、赫默、白面鸮${action}`
    const header = `休息至 19:42:00，随后执行「${title}」`
    const rooms =
      action === '上班'
        ? [{ id: 'room_3_3', label: '发电站 B303', agents: ['Current', '阿米娅'] }]
        : []
    const raw =
      `2026-11-04 18:30:02 INFO ${header}` + (rooms.length ? '；发电站 B303：Current、阿米娅' : '')
    const page = mount({
      lines: [
        {
          id: 42,
          text: raw,
          task: {
            header,
            title,
            actions: [
              ...(action === '转为空闲'
                ? [{ kind: 'operator', subject: '桑葚', action: '休息' }]
                : []),
              ...['阿米娅', '芬', '赫默', '白面鸮'].map((subject) => ({
                kind: 'operator',
                subject,
                action
              }))
            ],
            rooms,
            backups: [],
            targets: []
          }
        }
      ]
    })
    const subjects = page.all().find((entry) => hasClass(entry, 'task-action-subjects'))
    expect(subjects.props['data-source-text']).toBe(title)
    expect(all(subjects).filter((entry) => entry.tag === 'button')).toHaveLength(1)
    expect(visibleText(subjects)).toBe(
      action === '转为空闲' ? '桑葚休息；阿米娅+3转为空闲' : '阿米娅+3上班'
    )
    const root = page.all().find((entry) => hasClass(entry, 'log-output'))
    const container = page.all().find((entry) => entry.props['aria-label'] === '实时日志')
    root.contains = (candidate) => candidate === container
    root.querySelectorAll = () =>
      page.rows().map((entry) => ({
        textContent: text(entry),
        getAttribute: (name) => entry.props[name] ?? null
      }))
    Object.assign(container, { nodeType: 1, closest: () => null })
    const dom = (entry) => ({
      nodeType: entry.tag === '#text' ? 3 : entry.tag === '#comment' ? 8 : 1,
      textContent: text(entry),
      classList: { contains: (name) => hasClass(entry, name) },
      getAttribute: (name) => entry.props[name] ?? null,
      childNodes: [
        ...(entry.text ? [{ nodeType: 3, textContent: entry.text }] : []),
        ...entry.children.map(dom)
      ]
    })
    const range = {
      commonAncestorContainer: container,
      cloneContents: () => ({
        nodeType: 11,
        childNodes: container.children.map(dom),
        querySelector: () => ({})
      })
    }
    vi.stubGlobal('getSelection', () => ({
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => range,
      toString: () => visibleText(container)
    }))
    const event = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }
    document.addEventListener.mock.calls[0][1](event)
    expect(event.clipboardData.setData).toHaveBeenCalledExactlyOnceWith('text/plain', raw)
    expect(event.preventDefault).toHaveBeenCalledOnce()
  })
  it('preserves copyable source text and one name per portrait while rendering HTML as text', () => {
    const raw =
      '2026-10-31 16:05:10,879 INFO 安排干员：[\'巫恋\'] <img src=x onerror="alert(1)"> <script>alert(2)</script>'
    const page = mount({ lines: [raw], operatorNames: ['巫恋'] })

    expect(page.rows().map(text)).toEqual([raw])
    expect(text(page.rows()[0]).split('巫恋')).toHaveLength(2)
    expect(portraits(page.rows()[0])).toHaveLength(1)
    expect(page.all().filter((element) => element.tag === 'img')).toHaveLength(1)
    expect(page.all().some((element) => element.tag === 'script')).toBe(false)
    expect(page.all().some((element) => 'innerHTML' in element.props)).toBe(false)
  })

  it('keeps the empty log region and its live status without visible placeholder text', async () => {
    const page = mount()
    const region = () => page.all().find((element) => element.props['aria-label'] === '实时日志')
    const original = region()
    const status = all(original).find((element) => element.props.role === 'status')

    expect(original.props.role).toBe('region')
    expect(status.props['aria-live']).toBe('polite')
    expect(visibleText(original)).toBe('')
    page.props.lines = ['2026-10-31 16:05:10,879 INFO 开始运行']
    await nextTick()
    expect(page.rows()).toHaveLength(1)
    page.props.lines = []
    await nextTick()
    expect(region()).toBe(original)
    expect(all(original)).toContain(status)
    expect(visibleText(original)).toBe('')
  })

  it('shows the compact log title only while running', async () => {
    const page = mount({ compact: true, lines: ['INFO 已保留的日志'] })
    const sticky = () => page.all().find((element) => hasClass(element, 'log-sticky'))
    const region = page.all().find((element) => element.props['aria-label'] === '实时日志')

    expect(sticky()).toBeUndefined()
    page.props.running = true
    await nextTick()
    expect(visibleText(sticky())).toBe('运行日志')

    page.props.running = false
    await nextTick()
    expect(sticky()).toBeUndefined()
    expect(page.all()).toContain(region)
    expect(visibleText(region)).toContain('已保留的日志')
  })

  it('hands off the sticky group to an approaching divider without removing the header', async () => {
    vi.useFakeTimers()
    const page = mount({
      autoScroll: false,
      compact: true,
      lines: [
        { text: 'INFO 安排干员', group: 'base-scheduler' },
        { text: 'INFO 进驻完成', group: 'base-scheduler' },
        { text: 'INFO 检查线索', group: 'clue' },
        { text: 'INFO 赠送线索', group: 'clue' }
      ]
    })
    const root = page.all().find((element) => hasClass(element, 'log-output'))
    const sticky = () => page.all().find((element) => hasClass(element, 'log-sticky'))
    const dividers = page.all().filter((element) => hasClass(element, 'log-group'))
    let onScroll
    const container = {
      clientHeight: 40,
      scrollHeight: 160,
      scrollTop: 0,
      getBoundingClientRect: () => ({ top: 0 }),
      addEventListener: (_type, listener) => (onScroll = listener),
      querySelectorAll: (selector) =>
        selector === '.log-group[data-group]'
          ? dividers.map((divider, index) => ({
              getAttribute: (name) => divider.props[name],
              getBoundingClientRect() {
                const top = index * 90 - container.scrollTop
                return { top, bottom: top + 20, height: 20 }
              }
            }))
          : []
    }
    root.querySelector = (selector) => (selector === '.n-scrollbar-container' ? container : null)
    await nextTick()

    expect(dividers).toHaveLength(2)
    const header = sticky()
    for (const [position, label] of [
      [30, '基建排班'],
      [80, ''],
      [100, ''],
      [110, '线索'],
      [70, '基建排班']
    ]) {
      container.scrollTop = position
      onScroll()
      await vi.advanceTimersByTimeAsync(20)
      expect(sticky()).toBe(header)
      expect(visibleText(header)).toBe(label)
    }

    const rules = () =>
      all(header).filter(
        (element) => hasClass(element, 'log-sticky__lead') || hasClass(element, 'log-sticky__rule')
      )
    expect(rules()).toHaveLength(0)
    page.props.compact = false
    await nextTick()
    expect(rules()).toHaveLength(2)
    expect(rules().every((rule) => rule.props['aria-hidden'] === 'true')).toBe(true)
    container.scrollTop = 80
    onScroll()
    await vi.advanceTimersByTimeAsync(20)
    expect(sticky()).toBe(header)
    expect(rules()).toHaveLength(0)
  })

  it('places an optional header above the scrolling log region and outside it', () => {
    const page = mount({}, { header: () => h('div', { 'data-log-header': true }, '今日') })
    const root = page.all().find((element) => hasClass(element, 'log-output'))
    const header = page.all().find((element) => element.props['data-log-header'])
    const region = page.all().find((element) => element.props['aria-label'] === '实时日志')
    const elements = root.children.filter((element) => !element.tag.startsWith('#'))

    expect(elements).toHaveLength(2)
    expect(elements[0]).toBe(header)
    expect(hasClass(elements[1], 'log-output__body')).toBe(true)
    const scroll = all(elements[1]).find((element) => hasClass(element, 'log-output__scroll'))
    expect(scroll).toBeDefined()
    expect(all(scroll)).toContain(region)
    expect(all(region)).not.toContain(header)
    expect(
      mount()
        .all()
        .some((element) => element.props['data-log-header'])
    ).toBe(false)
  })

  it('marks the INFO operation whitelist as detail and preserves warnings, errors and task stages', () => {
    const lines = [
      'INFO 打开 ALL 筛选',
      'INFO 关闭职业筛选',
      'INFO 等待动画',
      'WARNING 等待动画',
      'ERROR tap: (100, 200)',
      'INFO Scene 207: 干员进驻设施排班界面'
    ]
    const page = mount({ lines })

    expect(page.rows().map((row) => Boolean(hasClass(row, 'log-line--detail')))).toEqual([
      true,
      true,
      true,
      false,
      false,
      false
    ])
    expect(page.rows().map((row) => row.props['data-log-level'])).toEqual([
      'INFO',
      'INFO',
      'INFO',
      'WARNING',
      'ERROR',
      'INFO'
    ])
    expect(page.rows().map(text)).toEqual(lines)
  })

  it('shows compact timestamps from complete and legacy prefixes while retaining the full source', () => {
    const lines = [
      '2026-10-31 16:05:10,879 INFO 巫恋',
      '2026-10-31 16:05:11.123 INFO 等待动画',
      '2026-10-31 INFO 没有完整时间头',
      '12345 条任务仍在队列中',
      '16:05:10 INFO 只有时间',
      '16:05:12  没有日志级别'
    ]
    const page = mount({ lines, operatorNames: ['巫恋'], compact: true })

    expect(page.rows().map(visibleText)).toEqual([
      '16:05:10巫恋',
      '16:05:11等待动画',
      lines[2],
      lines[3],
      '16:05:10只有时间',
      '16:05:12没有日志级别'
    ])
    expect(page.rows().map(text)).toEqual(lines)
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-stamp'))
        .map((stamp) => stamp.props.title)
    ).toEqual(['2026-10-31 16:05:10,879', '2026-10-31 16:05:11.123', '16:05:10', '16:05:12'])
  })

  it('reuses existing row nodes and portrait instances after appending and evicting the oldest line', async () => {
    const lines = ['INFO 巫恋 待命', 'INFO 但书 待命', 'INFO 龙舌兰 待命']
    const page = mount({ lines, operatorNames: ['巫恋', '但书', '龙舌兰'] })
    const initialRows = page.rows()
    const initialPortraits = initialRows.map((row) => portraits(row)[0])

    page.props.lines = [...lines, 'INFO 巫恋 开始任务']
    await nextTick()
    for (const [index, row] of initialRows.entries()) {
      expect(page.rows()[index]).toBe(row)
      expect(portraits(page.rows()[index])[0]).toBe(initialPortraits[index])
    }
    const appendedRow = page.rows()[3]
    const appendedPortrait = portraits(appendedRow)[0]
    page.props.lines = page.props.lines.slice(1)
    await nextTick()

    expect(page.rows()).toHaveLength(3)
    expect(page.rows()[0]).toBe(initialRows[1])
    expect(page.rows()[1]).toBe(initialRows[2])
    expect(page.rows()[2]).toBe(appendedRow)
    expect(portraits(page.rows()[0])[0]).toBe(initialPortraits[1])
    expect(portraits(page.rows()[1])[0]).toBe(initialPortraits[2])
    expect(portraits(page.rows()[2])[0]).toBe(appendedPortrait)
    expect(page.all()).not.toContain(initialRows[0])
  })

  it('keeps repeated identical lines as distinct rows and portraits without duplicate-key warnings', async () => {
    const raw = 'INFO 巫恋 待命'
    const other = 'INFO 但书 待命'
    const page = mount({
      lines: [raw, other, raw, 'INFO 龙舌兰 待命'],
      operatorNames: ['巫恋', '但书', '龙舌兰']
    })
    const initialRows = page.rows().filter((row) => text(row) === raw)
    const otherRow = page.rows()[1]
    const initialPortraits = initialRows.map((row) => portraits(row)[0])
    expect(initialRows[0]).not.toBe(initialRows[1])
    expect(initialPortraits[0].props['data-operator-instance']).not.toBe(
      initialPortraits[1].props['data-operator-instance']
    )

    page.props.lines = [raw, raw, raw, other]
    await nextTick()
    expect(page.rows()).toHaveLength(4)
    expect(page.rows().map(text)).toEqual([raw, raw, raw, other])
    expect(page.rows()[0]).toBe(initialRows[0])
    expect(page.rows()[1]).toBe(initialRows[1])
    expect(page.rows()[3]).toBe(otherRow)
    expect(
      new Set(
        page
          .rows()
          .slice(0, 3)
          .map((row) => portraits(row)[0].props['data-operator-instance'])
      ).size
    ).toBe(3)
    expect(page.warnings).toEqual([])
  })

  it('refreshes portrait matching after known names change without mutating either source array', async () => {
    const lines = Object.freeze(['INFO 巫恋、但书 待命'])
    const operatorNames = Object.freeze(['巫恋'])
    const page = mount({ lines, operatorNames })
    expect(portraits(page.rows()[0]).map((item) => item.props['data-operator-name'])).toEqual([
      '巫恋'
    ])

    page.props.operatorNames = ['巫恋', '但书']
    await nextTick()
    expect(portraits(page.rows()[0]).map((item) => item.props['data-operator-name'])).toEqual([
      '巫恋',
      '但书'
    ])
    page.props.operatorNames = []
    await nextTick()
    expect(portraits(page.rows()[0])).toEqual([])
    expect(page.rows().map(text)).toEqual(lines)
    expect(lines).toEqual(['INFO 巫恋、但书 待命'])
    expect(operatorNames).toEqual(['巫恋'])
  })

  it('updates facility labels in place from the current plan while retaining source room identifiers', async () => {
    const lines = Object.freeze([
      'INFO room_1_1 巫恋 待命',
      'INFO central meeting train dormitory_2 dormitory_1_low room_9_9 unknown_room'
    ])
    const page = mount({
      lines,
      operatorNames: ['巫恋'],
      facilityPlan: { room_1_1: { name: '贸易站' } }
    })
    const initialRow = page.rows()[0]
    const room = page.all().find((element) => element.props['data-room-id'] === 'room_1_1')

    expect(page.rows().map(text)).toEqual([
      'INFO 贸易站 B101 巫恋 待命',
      'INFO 控制中枢 会客室 训练室 宿舍2 宿舍1（低优先级） room_9_9 unknown_room'
    ])
    expect(room.props.title).toBe('room_1_1')
    expect(
      page.all().find((element) => element.props['data-room-id'] === 'room_9_9').props.title
    ).toBe('room_9_9')

    page.props.facilityPlan.room_1_1.name = '制造站'
    await nextTick()
    expect(page.rows()[0]).toBe(initialRow)
    expect(page.all().find((element) => element.props['data-room-id'] === 'room_1_1')).toBe(room)
    expect(text(initialRow)).toBe('INFO 制造站 B101 巫恋 待命')
    expect(room.props['data-room-id']).toBe('room_1_1')
    expect(room.props.title).toBe('room_1_1')
    expect(lines).toEqual([
      'INFO room_1_1 巫恋 待命',
      'INFO central meeting train dormitory_2 dormitory_1_low room_9_9 unknown_room'
    ])
  })

  it('shows a time column and one date marker per day while each row keeps its source line', async () => {
    const lines = [
      '2026-10-30 23:59:58,120 INFO 巫恋 待命',
      '2026-10-30 23:59:59,450 WARNING 截图识别结果需要复核',
      '  File "scheduler.py", line 72',
      '2026-10-31 00:00:01,002 INFO 跨日任务'
    ]
    const page = mount({ lines, operatorNames: ['巫恋'] })
    const container = page.all().find((element) => element.props['aria-label'] === '实时日志')
    const sequence = () =>
      all(container)
        .filter((element) => hasClass(element, 'log-date') || hasClass(element, 'log-line'))
        .map((element) => (hasClass(element, 'log-date') ? `date ${text(element)}` : text(element)))
    const initialRows = page.rows()

    expect(page.rows().map(text)).toEqual(lines)
    expect(sequence()).toEqual([
      'date 2026-10-30',
      lines[0],
      lines[1],
      lines[2],
      'date 2026-10-31',
      lines[3]
    ])
    expect(page.rows().map(visibleText)).toEqual([
      '23:59:58巫恋 待命',
      '23:59:59WARNING 截图识别结果需要复核',
      '  File "scheduler.py", line 72',
      '00:00:01跨日任务'
    ])
    expect(page.all().find((element) => hasClass(element, 'log-stamp')).props.title).toBe(
      '2026-10-30 23:59:58,120'
    )
    expect(
      hasClass(
        page.all().find((element) => hasClass(element, 'log-level')),
        'log-level--warning'
      )
    ).toBe(true)
    expect(page.rows().map((row) => hasClass(row, 'log-line--bare'))).toEqual([
      false,
      false,
      true,
      false
    ])

    page.props.compact = true
    await nextTick()
    expect(sequence()).toEqual(lines)
    expect(page.rows().map(visibleText)).toEqual([
      '23:59:58巫恋 待命',
      '23:59:59WARNING 截图识别结果需要复核',
      lines[2],
      '00:00:01跨日任务'
    ])
    page.rows().forEach((row, index) => expect(row).toBe(initialRows[index]))

    page.props.compact = false
    await nextTick()
    expect(sequence()).toHaveLength(6)
    expect(page.rows().map(text)).toEqual(lines)
  })

  const crossDateSelections = [
    'complete rows',
    'partial facility label',
    'visible timestamp',
    'visible timestamp on linked detail',
    'partial final message'
  ]
  it.each(crossDateSelections)('copies %s across a date marker', async (selection) => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    const linked = selection === 'visible timestamp on linked detail'
    const lines = [
      `2026-10-30 23:59:59,450 ${linked ? 'INFO' : 'WARNING'} room_1_1 待命`,
      '2026-10-31 00:00:01,002 INFO 巫恋 开始任务'
    ]
    const parent = { type: 'facility-arrangement', id: 'meeting-copy', room: 'meeting' }
    const page = mount({
      lines: linked
        ? [
            {
              text: '2026-10-30 23:59:58,100 INFO 会客室',
              event: { ...parent, phase: 'started', anchor: true, label: '会客室', agents: [] }
            },
            { text: lines[0], parent },
            lines[1]
          ]
        : lines,
      operatorNames: ['巫恋'],
      facilityPlan: { room_1_1: { name: '贸易站' } }
    })
    if (linked)
      await page
        .all()
        .find((entry) => hasClass(entry, 'log-detail-toggle'))
        .props.onClick()
    const root = page.all().find((element) => hasClass(element, 'log-output'))
    const container = page.all().find((element) => element.props['aria-label'] === '实时日志')
    root.contains = (candidate) => all(root).includes(candidate)
    Object.assign(container, { nodeType: 1, closest: () => null })
    const domNode = (element) =>
      element.tag === '#text'
        ? { nodeType: 3, textContent: element.text }
        : {
            nodeType: element.tag === '#comment' ? 8 : 1,
            textContent: text(element),
            classList: { contains: (name) => hasClass(element, name) },
            getAttribute: (name) => element.props[name] ?? null,
            childNodes: [
              ...(element.text ? [{ nodeType: 3, textContent: element.text }] : []),
              ...element.children.map(domNode)
            ]
          }
    const matches = (element, selector) =>
      selector.split(',').some((part) => {
        const attribute = /^\[(.+)\]$/.exec(part.trim())?.[1]
        if (attribute) return element.props[attribute] !== undefined
        return hasClass(element, part.trim().slice(1))
      })
    const sourceRows = page.rows().filter((row) => lines.includes(row.props['data-log-source']))
    const [first, second] = sourceRows
    const liveRows = sourceRows.map((row) => ({
      ...domNode(row),
      querySelector: (selector) =>
        selector === '.log-stamp__time'
          ? all(row).find((entry) => hasClass(entry, 'log-stamp__time'))
          : null
    }))
    root.querySelectorAll = () => liveRows
    const firstClone = domNode(first)
    const secondClone = domNode(second)
    let expected = lines.join('\n')
    if (selection === 'partial facility label') {
      const label = all(first).find((entry) => entry.props['data-room-id'])
      firstClone.textContent = '01 待命'
      firstClone.childNodes = [
        {
          ...domNode(label),
          textContent: '01',
          childNodes: [{ nodeType: 3, textContent: '01' }]
        },
        { nodeType: 3, textContent: ' 待命' }
      ]
      expected = `01 待命\n${lines[1]}`
    } else if (selection === 'visible timestamp' || linked) {
      const date = '2026-10-30 '
      firstClone.textContent = firstClone.textContent.slice(date.length)
      firstClone.childNodes = [{ nodeType: 3, textContent: firstClone.textContent }]
      document.createRange = () => ({
        selectNodeContents: vi.fn(),
        setStart: vi.fn(),
        toString: () => liveRows[0].textContent.slice(date.length)
      })
    } else if (selection === 'partial final message') {
      const message = secondClone.childNodes.find((node) => node.classList?.contains('log-message'))
      message.textContent = '巫恋 开始'
      message.childNodes = [{ nodeType: 3, textContent: message.textContent }]
      secondClone.textContent = secondClone.childNodes.map((node) => node.textContent).join('')
      expected = `${lines[0]}\n00:00:01 巫恋 开始`
    }
    const dateMarkers = all(container).filter((entry) => hasClass(entry, 'log-date'))
    const range = {
      commonAncestorContainer: container,
      cloneContents: () => ({
        nodeType: 11,
        childNodes: [firstClone, domNode(dateMarkers.at(-1)), secondClone],
        querySelector: (selector) =>
          all(container)
            .slice(1)
            .find((element) => matches(element, selector)) ?? null
      })
    }
    vi.stubGlobal('getSelection', () => ({
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => range,
      toString: () => '23:59:59WARNING 贸易站 B101 待命'
    }))
    const event = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }

    document.addEventListener.mock.calls[0][1](event)

    expect(event.clipboardData.setData).toHaveBeenCalledExactlyOnceWith('text/plain', expected)
    expect(event.preventDefault).toHaveBeenCalledOnce()
  })

  it('leaves unrelated copy selections untouched and removes its document listener on unmount', () => {
    const document = { addEventListener: vi.fn(), removeEventListener: vi.fn() }
    vi.stubGlobal('document', document)
    const page = mount({ lines: ['INFO dormitory_2'] })
    const root = page.all().find((element) => hasClass(element, 'log-output'))
    root.contains = (candidate) => all(root).includes(candidate)
    const range = { commonAncestorContainer: node('outside'), cloneContents: vi.fn() }
    vi.stubGlobal('getSelection', () => ({
      rangeCount: 1,
      isCollapsed: false,
      getRangeAt: () => range
    }))
    const event = { clipboardData: { setData: vi.fn() }, preventDefault: vi.fn() }

    expect(document.addEventListener).toHaveBeenCalledOnce()
    const [type, listener] = document.addEventListener.mock.calls[0]
    expect(type).toBe('copy')
    listener(event)
    expect(range.cloneContents).not.toHaveBeenCalled()
    expect(event.clipboardData.setData).not.toHaveBeenCalled()
    expect(event.preventDefault).not.toHaveBeenCalled()

    page.unmount()
    expect(document.removeEventListener).toHaveBeenCalledOnce()
    expect(document.removeEventListener).toHaveBeenCalledWith('copy', listener)
  })

  it.each(['element', 'text'])(
    'copies the original ID when the entire room label is selected through its %s ancestor',
    (ancestorType) => {
      const page = mountRoomCopy({ ancestorType })
      expect(page.selection.toString()).toBe('贸易站 B101')

      page.copy()

      expect(page.event.clipboardData.setData).toHaveBeenCalledOnce()
      expect(page.event.clipboardData.setData).toHaveBeenCalledWith('text/plain', 'room_1_1')
      expect(page.event.preventDefault).toHaveBeenCalledOnce()
      expect(page.range.cloneContents).not.toHaveBeenCalled()
    }
  )

  it('leaves a partial room label selection to the browser without expanding it to the room ID', () => {
    const page = mountRoomCopy({ selectedText: '贸易站' })

    page.copy()

    expect(page.selection.toString()).toBe('贸易站')
    expect(page.event.clipboardData.setData).not.toHaveBeenCalled()
    expect(page.event.preventDefault).not.toHaveBeenCalled()
  })

  it('does not replace multiple selected ranges with the text of only the first range', () => {
    const page = mountRoomCopy({ rangeCount: 2, selectedText: '贸易站 B101 控制中枢' })

    page.copy()

    expect(page.selection.getRangeAt).not.toHaveBeenCalled()
    expect(page.event.clipboardData.setData).not.toHaveBeenCalled()
    expect(page.event.preventDefault).not.toHaveBeenCalled()
  })
})

const logLine = (id, text, group = null, at = null) => ({
  id,
  at,
  text,
  group,
  room: null,
  agents: null
})

describe('log grouping, folding and scene waits', () => {
  it.each([false, true])(
    'keeps uninterrupted technical sections across an incidental device observation, compact=%s',
    async (compact) => {
      const sources = ['recognition', 'recognition', 'device-control', 'recognition', 'recognition']
      const messages = [
        'Scene -1: 未知',
        'Scene 9998: 场景跳转时的等待界面',
        '游戏不在前台，正在把游戏调到前台...',
        'Scene -1: 未知',
        'Scene 105: 启动'
      ]
      const lines = sources.map((group, index) =>
        logLine(index, `2026-11-08 00:37:3${index} INFO ${messages[index]}`, group)
      )
      const page = mount({ lines: [], compact })
      for (const line of lines) {
        page.props.lines.push(line)
        await nextTick()
      }
      const replay = mount({ lines, compact })
      for (const view of [page, replay]) {
        expect(
          view
            .all()
            .filter((entry) => hasClass(entry, 'log-group'))
            .map(text)
        ).toEqual(['场景识别'])
        expect(view.rows().map((row) => row.props['data-log-source'])).toEqual(
          lines.map((line) => line.text)
        )
        expect(view.props.lines.map((line) => line.group)).toEqual(sources)
      }
    }
  )

  it.each(['WARNING', 'ERROR'])('keeps a one-line technical %s as a visible boundary', (level) => {
    const lines = [
      logLine(1, 'INFO Scene -1: 未知', 'recognition'),
      logLine(2, 'INFO Scene 9998: 等待', 'recognition'),
      logLine(3, `${level} 设备连接已断开`, 'device-control'),
      logLine(4, 'INFO Scene 105: 启动', 'recognition'),
      logLine(5, 'INFO Scene 103: 登录', 'recognition')
    ]
    const page = mount({ lines })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map(text)
    ).toEqual(['场景识别', '设备连接', '场景识别'])
    expect(page.rows()[2].props['data-log-level']).toBe(level)
  })

  it('labels log delivery warnings independently of an earlier web-service section', () => {
    const page = mount({
      lines: [
        logLine(1, 'INFO 服务启动', 'web-access'),
        logLine(2, 'INFO 客户端已连接', 'web-access'),
        logLine(3, 'WARNING 实时日志积压', 'runtime-log')
      ]
    })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map(text)
    ).toEqual(['Web 访问', '日志显示'])
  })

  it.each([false, true])(
    'does not group startup configuration with the preceding OCR observation, concise=%s',
    (concise) => {
      const records = [
        [null, '开始运行Mower'],
        ['recognition', 'OCR 引擎初始化为 local：存活 Mower 实例数 1'],
        [null, '正在使用全局配置空间: None'],
        ['device-control', '使用设备：MuMu 12 多开实例 0'],
        ['device-control', '连接成功：127.0.0.1:16384']
      ]
      const lines = records.map(([group, body], index) =>
        logLine(index, `2026-11-06 17:54:5${index} INFO ${body}`, group)
      )
      const page = mount({ lines, concise })
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-group'))
          .map((entry) => entry.props['data-group'])
      ).toEqual(['device-control'])
      expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
    }
  )

  it.each([false, true])(
    'keeps meeting-room clue details inside one base section, concise=%s',
    (concise) => {
      const parent = { type: 'facility-arrangement', id: 'meeting-173958', room: 'meeting' }
      const event = { ...parent, label: '会客室', agents: ['见行者', '黍'] }
      const records = [
        ['17:39:55', 'base-scheduler', '重设维什戴尔至空闲'],
        [
          '17:39:58',
          'base-scheduler',
          '正在安排见行者、黍进驻会客室',
          { room: 'meeting', event: { ...event, phase: 'started', anchor: true } }
        ],
        ['17:39:59', 'clue', '当前拥有线索数量为6', { parent }],
        ['17:40:01', 'recognition', 'Scene 207: 干员进驻设施排序界面', { parent }],
        [
          '17:40:01',
          'base-scheduler',
          '安排干员：见行者、黍 → 会客室',
          { parent, room: 'meeting' }
        ],
        [
          '17:40:09',
          'base-scheduler',
          '选人页当前选中：见行者、黍，待排序核对',
          { parent, room: 'meeting' }
        ],
        ['17:40:15', 'clue', '当前拥有线索数量为6', { parent }],
        ['17:40:15', 'base-scheduler', '见行者 房间变动', { parent }],
        [
          '17:40:15',
          'base-scheduler',
          '已安排见行者、黍进驻会客室',
          { parent, room: 'meeting', event: { ...event, phase: 'completed', anchor: false } }
        ],
        ['17:40:16', 'recognition', 'Scene 201: 基建全局视角'],
        ['17:40:18', 'base-scheduler', '安排干员：桑葚 → 办公室', { room: 'contact' }]
      ]
      const lines = records.map(([time, group, body, fields], index) => ({
        ...logLine(index, `2026-11-06 ${time} INFO ${body}`, group),
        ...fields
      }))
      const page = mount({ lines, concise })
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-group'))
          .map((entry) => entry.props['data-group'])
      ).toEqual(['base-scheduler'])
      expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
      expect(page.props.lines.map((line) => line.group)).toEqual(records.map(([, group]) => group))
    }
  )

  it.each([
    ['WARNING', '2026-11-06', true],
    ['INFO', '2026-11-07', false],
    ['INFO', '2026-11-07', true]
  ])('retains the linked clue %s boundary on %s', (level, date, concise) => {
    const parent = { type: 'facility-arrangement', id: 'meeting-boundary', room: 'meeting' }
    const lines = [
      logLine(1, '2026-11-06 23:59:55 INFO 开始基建排班', 'base-scheduler'),
      {
        ...logLine(2, '2026-11-06 23:59:58 INFO 会客室', 'base-scheduler'),
        event: { ...parent, label: '会客室', agents: ['黍'], phase: 'started', anchor: true }
      },
      {
        ...logLine(3, `${date} 23:59:59 ${level} 读取线索数量`, 'clue'),
        parent
      },
      logLine(4, `${date} 23:59:59 INFO 独立线索检查`, 'clue'),
      logLine(5, `${date} 23:59:59 INFO 继续基建排班`, 'base-scheduler')
    ]
    const page = mount({ lines, concise })
    const nodes = page.all()
    const groups = nodes.filter((entry) => hasClass(entry, 'log-group'))
    expect(groups.map((entry) => entry.props['data-group'])).toEqual([
      'base-scheduler',
      'clue',
      'base-scheduler'
    ])
    // 关联详情本身开启线索分段，不能推迟到后面的独立线索记录。
    expect(nodes.indexOf(groups[1])).toBeLessThan(nodes.indexOf(page.rows()[2]))
    expect(hasClass(page.rows()[2], 'log-line--source-only')).toBe(false)
    if (date === '2026-11-07') expect(hasClass(page.rows()[2], 'log-line--nested')).toBe(false)
    expect(page.rows()[2].props['data-log-level']).toBe(level)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('keeps recruitment slots through the screenshot sequence of two-scene blocks', async () => {
    const messages = [
      ['recruitment', '00', '开始公开招募'],
      ['recognition', '01', 'Scene 7: 跳过'],
      ['recognition', '02', 'Scene 803: 干员展示'],
      ['recruitment', '03', '3号公招位：招募获得：清流'],
      ['recognition', '06', 'Scene 801: 公招主界面'],
      ['recognition', '07', 'Scene 802: 挑选标签时'],
      ['recruitment', '07', '3号公招位：识别标签：医疗干员、远程位、治疗、新手、群攻'],
      ['recognition', '10', 'Scene 801: 公招主界面'],
      ['recruitment', '10', '3号公招位：开始招募，不选标签，时长：9小时'],
      ['recognition', '11', 'Scene 7: 跳过'],
      ['recognition', '11', 'Scene 803: 干员展示'],
      ['recruitment', '13', '4号公招位：招募获得：炎熔'],
      ['recognition', '16', 'Scene 801: 公招主界面'],
      ['recognition', '17', 'Scene 802: 挑选标签时'],
      ['recruitment', '18', '4号公招位：识别标签：近卫干员、治疗、费用回复、减速、召唤']
    ]
    const lines = messages.map(([group, second, body], index) =>
      logLine(index, `2026-11-05 09:44:${second},123 INFO ${body}`, group)
    )
    const page = mount({ lines: [] })
    for (const line of lines) {
      page.props.lines.push(line)
      await nextTick()
    }
    const bars = page.all().filter((entry) => hasClass(entry, 'log-group'))
    expect(bars.map((entry) => entry.props['data-group'])).toEqual(['recruitment'])
    const slots = page.all().filter((entry) => hasClass(entry, 'log-recruit-slot'))
    expect(slots.map(headingText)).toEqual(['3号公招位', '4号公招位'])
    expect(
      slots.map((slot) => text(all(slot).find((entry) => hasClass(entry, 'log-stamp'))))
    ).toEqual(['09:44:03', '09:44:13'])
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
    expect(page.props.lines.map((line) => line.group)).toEqual(messages.map(([group]) => group))
  })

  it.each(['clue', 'base-scheduler', 'local-operation', 'recruitment'])(
    'bridges variable mixed technical blocks within the same %s business',
    (business) => {
      const sources = [
        business,
        ...Array.from({ length: 7 }, (_, i) =>
          i >= 3 && i < 5 ? 'device-control' : 'recognition'
        ),
        business
      ]
      const page = mount({
        lines: sources.map((group, index) => logLine(index, `INFO 原位记录 ${index}`, group))
      })
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-group'))
          .map((entry) => entry.props['data-group'])
      ).toEqual([business])
      expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
        sources.map((_group, index) => `INFO 原位记录 ${index}`)
      )
      expect(page.props.lines.map((line) => line.group)).toEqual(sources)
    }
  )

  it('keeps long technical blocks independent without matching business on both sides', () => {
    const sources = [
      ...Array(12).fill('recognition'),
      'clue',
      'clue',
      ...Array(12).fill('recognition'),
      'recruitment',
      'recruitment',
      ...Array(12).fill('device-control')
    ]
    const page = mount({
      lines: sources.map((group, index) => logLine(index, `INFO 记录 ${index}`, group))
    })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map((entry) => entry.props['data-group'])
    ).toEqual(['recognition', 'clue', 'recognition', 'recruitment', 'device-control'])
  })

  it('keeps the real card mood scan warnings in the same base scheduling section across scene lines', () => {
    const base = 'base-scheduler'
    const lines = [
      logLine(1, '2026-11-06 20:34:46,843 INFO 制造站 B303：清流（心情14.942）', base),
      logLine(2, '2026-11-06 20:34:47,978 INFO 开始初始化选人页心情扫描', base),
      logLine(3, '2026-11-06 20:34:48,126 INFO Scene 201: 基建全局视角', 'recognition'),
      logLine(
        4,
        '2026-11-06 20:34:54,902 WARNING 卡牌心情预估未完成，继续正常巡检：未进入卡牌观测页，继续正常巡检',
        base
      ),
      logLine(
        5,
        '2026-11-06 20:34:54,903 WARNING 初始化选人页心情扫描未完成：未进入卡牌观测页，继续正常巡检；保留已取得的观测，其余保持未知',
        base
      ),
      logLine(6, '2026-11-06 20:34:57,784 INFO Scene 201: 基建全局视角', 'recognition'),
      logLine(7, '2026-11-06 20:34:58,272 INFO 已激活的副表：远牙动态低优、感知下班', base)
    ]
    const page = mount({ lines, concise: true })

    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map((entry) => entry.props['data-group'])
    ).toEqual([base])
    const warnings = page.rows().filter((row) => row.props['data-log-level'] === 'WARNING')
    expect(warnings.map(visibleText)).toEqual([
      expect.stringContaining('卡牌心情预估未完成'),
      expect.stringContaining('初始化选人页心情扫描未完成')
    ])
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it.each(['clue', 'recognition', 'device-control'])(
    'keeps a first single %s record free of an invented section boundary',
    (group) => {
      const page = mount({ lines: [logLine(1, 'INFO 单条记录', group)] })
      expect(page.all().filter((entry) => hasClass(entry, 'log-group'))).toHaveLength(0)
      expect(page.rows()).toHaveLength(1)
    }
  )

  it.each(['WARNING', 'ERROR', 'CRITICAL'])(
    'keeps a technical %s boundary and all source records intact',
    (level) => {
      const lines = [
        logLine(1, 'INFO 公招开始', 'recruitment'),
        logLine(2, 'INFO 公招读取', 'recruitment'),
        logLine(3, 'INFO Scene 801: 公招主界面', 'recognition'),
        logLine(4, `${level} 图像读取异常`, 'recognition'),
        logLine(5, 'INFO Scene 802: 挑选标签时', 'recognition'),
        logLine(6, 'INFO 公招结果', 'recruitment'),
        logLine(7, 'INFO 公招结束', 'recruitment')
      ]
      const page = mount({ lines })
      expect(
        page
          .all()
          .filter((entry) => hasClass(entry, 'log-group'))
          .map((entry) => entry.props['data-group'])
      ).toEqual(['recruitment', 'recognition', 'recruitment'])
      expect(page.rows()[3].props['data-log-level']).toBe(level)
      expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
        lines.map((line) => line.text)
      )
    }
  )

  it('restarts the business and slot heading across dates despite ordinary technical observations', () => {
    const lines = [
      logLine(1, '2026-11-05 23:59:55,000 INFO 3号公招位：识别标签：治疗', 'recruitment'),
      logLine(2, '2026-11-05 23:59:56,000 INFO 3号公招位：开始招募', 'recruitment'),
      logLine(3, '2026-11-06 00:00:01,000 INFO Scene 801: 公招主界面', 'recognition'),
      logLine(4, '2026-11-06 00:00:02,000 INFO Scene 802: 挑选标签时', 'recognition'),
      logLine(5, '2026-11-06 00:00:03,000 INFO 3号公招位：识别标签：治疗', 'recruitment'),
      logLine(6, '2026-11-06 00:00:04,000 INFO 3号公招位：开始招募', 'recruitment')
    ]
    const page = mount({ lines })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map((entry) => entry.props['data-group'])
    ).toEqual(['recruitment', 'recognition', 'recruitment'])
    const slots = page.all().filter((entry) => hasClass(entry, 'log-recruit-slot'))
    expect(slots.map(headingText)).toEqual(['3号公招位', '3号公招位'])
  })

  it('restarts a same-business section on a new date even without a technical block', () => {
    const page = mount({
      lines: [
        logLine(1, '2026-11-05 23:59:55,000 INFO 线索读取', 'clue'),
        logLine(2, '2026-11-05 23:59:56,000 INFO 线索检查', 'clue'),
        logLine(3, '2026-11-06 00:00:01,000 INFO 线索读取', 'clue'),
        logLine(4, '2026-11-06 00:00:02,000 INFO 线索检查', 'clue')
      ]
    })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map((entry) => entry.props['data-group'])
    ).toEqual(['clue', 'clue'])
  })

  it('shows the real one-line shop boundary from the clue screenshot without inventing another record', () => {
    const messages = [
      ['clue', '13', '基建：线索'],
      ['recognition', '15', 'Scene 205: 基建放大查看'],
      ['recognition', '18', 'Scene 203: 线索主界面'],
      ['clue', '18', '快速摆放线索'],
      ['clue', '21', '检测到产物收取提示，等待消失'],
      ['clue', '22', '检测到产物收取提示，等待消失'],
      ['recognition', '25', 'Scene 9: 正在提交反馈至神经'],
      ['recognition', '28', 'Scene 202: 基建待办事项'],
      ['recognition', '29', 'Scene 213: 传递线索'],
      ['recognition', '31', 'Scene 203: 线索主界面'],
      ['recognition', '32', 'Scene 205: 基建放大查看'],
      ['recognition', '33', 'Scene 201: 基建全局视角'],
      ['recognition', '34', 'Scene 205: 基建放大查看'],
      ['recognition', '36', 'Scene 203: 线索主界面'],
      ['recognition', '38', 'Scene 213: 传递线索'],
      ['recognition', '40', 'Scene 203: 线索主界面'],
      ['recognition', '42', 'Scene 205: 基建放大查看'],
      ['clue', '43', '线索交流结束时间：2026-11-05 09:54:21.106648'],
      ['credit-shop', '43', 'Start: 信用商店购物'],
      ['recognition', '44', 'Scene 5: 导航栏返回']
    ]
    const lines = messages.map(([group, second, body], index) =>
      logLine(index, `2026-11-05 09:42:${second},000 INFO ${body}`, group)
    )
    const page = mount({ lines })
    const bars = page.all().filter((entry) => hasClass(entry, 'log-group'))
    expect(bars.map((bar) => bar.props['data-group'])).toEqual(['clue', 'credit-shop'])
    expect(bars.map(text)).toEqual(['线索', '信用商店购物'])
    expect(page.rows()).toHaveLength(20)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('groups one facility through a mixed technical block but never absorbs a multi-facility plan', () => {
    const room = 'room_2_2'
    const lines = [
      { ...logLine(1, 'INFO 制造站 B202：读取设施状态', 'base-scheduler'), room },
      logLine(2, 'INFO Scene 221: 设施详情', 'recognition'),
      logLine(3, 'INFO Scene 222: 干员选择', 'recognition'),
      logLine(4, 'INFO 设备连接正常', 'device-control'),
      { ...logLine(5, 'INFO 制造站 B202：选人页当前选中：清流', 'base-scheduler'), room },
      {
        ...logLine(6, 'INFO 完整安排\n制造站 B202：清流\n宿舍1：砾', 'base-scheduler'),
        room,
        task: {
          header: '完整安排',
          title: '安排干员',
          rooms: [
            { id: room, label: '制造站 B202', agents: ['清流'] },
            { id: 'dormitory_1', label: '宿舍1', agents: ['砾'] }
          ],
          targets: [],
          backups: [],
          actions: []
        }
      },
      { ...logLine(7, 'INFO 制造站 B202：读取订单', 'base-scheduler'), room }
    ]
    const page = mount({ lines, facilityPlan: { [room]: { name: '制造站' } } })
    expect(
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-facility-heading'))
        .map(headingText)
    ).toEqual(['制造站 B202'])
    expect(hasClass(page.rows()[5], 'log-line--nested')).toBe(false)
    expect(hasClass(page.rows()[6], 'log-line--nested')).toBe(false)
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('labels the existing MAA business group as MAA daily tasks', () => {
    const page = mount({
      lines: [
        logLine(1, 'INFO 没有启用的 MAA 日常任务，跳过日常', 'maa-integration'),
        logLine(2, 'INFO 3时59分后开始做日常任务', 'maa-integration')
      ]
    })
    const bars = page.all().filter((element) => hasClass(element, 'log-group'))
    expect(bars).toHaveLength(1)
    expect(bars[0].props['data-group']).toBe('maa-integration')
    expect(text(bars[0])).toBe('MAA日常')
  })

  it('keeps streamed grouping equal to replay and preserves a real one-line business switch', async () => {
    const lines = [
      logLine(1, 'INFO 读取公招', 'recruitment'),
      logLine(2, 'INFO 公招标签', 'recruitment'),
      logLine(3, 'INFO Scene 801: 公招主界面', 'recognition'),
      logLine(4, 'INFO 公招结果', 'recruitment'),
      logLine(5, 'INFO 公招结束', 'recruitment'),
      logLine(6, 'INFO 仓库扫描完成', 'depot-recognition'),
      logLine(7, 'INFO 再次检查公招', 'recruitment'),
      logLine(8, 'INFO 公招等待时间已记录', 'recruitment')
    ]
    const streamed = mount()
    for (const line of lines) {
      streamed.props.lines.push(line)
      await nextTick()
    }
    const replay = mount({ lines })
    const groups = (page) =>
      page
        .all()
        .filter((entry) => hasClass(entry, 'log-group'))
        .map((entry) => entry.props['data-group'])
    expect(groups(streamed)).toEqual(['recruitment', 'depot-recognition', 'recruitment'])
    expect(groups(replay)).toEqual(groups(streamed))
    expect(streamed.rows().map(text)).toEqual(replay.rows().map(text))
  })

  it.each([true, false])('shows the recorded business switches, compact=%s', (compact) => {
    const messages = [
      ['device-control', '切回主界面'],
      ['base-scheduler', '第72次任务结束'],
      ['base-scheduler', '休息 4 分 15 秒，至 10:33:54，随后执行「趴体」'],
      [
        'base-scheduler',
        '实时心情计算耗时：基建调度，模型同步与预测累计 0.002 秒，计算调用 1 次，完成'
      ],
      ['depot-recognition', '仓库扫描未到时间，将在 1.0小时之内开始扫描'],
      ['maa-integration', '2 小时 40 分钟后开始做日常任务'],
      ['device-control', '切回主界面'],
      ['base-scheduler', '第73次任务结束'],
      ['base-scheduler', '休息 21 分 51 秒，至 10:56:29，随后执行「跑单」']
    ]
    const lines = messages.map(([group, message], index) =>
      logLine(index + 1, `INFO ${message}`, group)
    )
    const page = mount({ compact, lines })
    const bars = page.all().filter((entry) => hasClass(entry, 'log-group'))
    expect(bars.map((entry) => entry.props['data-group'])).toEqual([
      'base-scheduler',
      'depot-recognition',
      'maa-integration',
      'base-scheduler'
    ])
    expect(page.rows().map((row) => row.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('preserves a business section header when unrelated earlier rows leave the buffer', async () => {
    const page = mount({
      lines: [
        logLine(1, 'INFO 开始'),
        logLine(2, 'INFO 公招读取', 'recruitment'),
        logLine(3, 'INFO 公招结果', 'recruitment')
      ]
    })
    const header = page.all().find((entry) => hasClass(entry, 'log-group'))
    page.props.lines.shift()
    await nextTick()
    expect(page.all().find((entry) => hasClass(entry, 'log-group'))).toBe(header)
    expect(page.rows()).toHaveLength(2)
  })

  it.each(['recognition', 'device-control'])(
    'keeps a single %s INFO line inside its business section',
    (group) => {
      const page = mount({
        lines: [
          logLine(1, 'INFO 公招开始', 'recruitment'),
          logLine(2, 'INFO 辅助操作', group),
          logLine(3, 'INFO 公招结果', 'recruitment')
        ]
      })
      expect(
        page
          .all()
          .filter((element) => hasClass(element, 'log-group'))
          .map((bar) => bar.props['data-group'])
      ).toEqual(['recruitment'])
      expect(page.rows()).toHaveLength(3)
    }
  )

  it('renders structured entities once and invalidates cached metadata', async () => {
    const page = mount({
      operatorNames: ['但书', '龙舌兰'],
      facilityPlan: { room_2_1: { name: '贸易站' } },
      lines: [
        {
          ...logLine(1, 'INFO 安排干员：但书、龙舌兰 → B201'),
          room: 'room_2_1',
          agents: ['但书', '龙舌兰']
        }
      ]
    })
    expect(portraits(page.rows()[0]).map((item) => item.props['data-operator-name'])).toEqual([
      '但书',
      '龙舌兰'
    ])
    expect(visibleText(page.rows()[0])).toBe('INFO 安排干员：但书、龙舌兰 → 贸易站 B201')
    page.props.lines[0].room = 'room_3_1'
    await nextTick()
    expect(page.rows()[0].children.some((item) => item.props['data-room-id'] === 'room_2_1')).toBe(
      false
    )
    expect(visibleText(page.rows()[0])).toBe('INFO 安排干员：但书、龙舌兰 → B201')
  })

  it('refreshes cached facility tokens when the existing plan changes a room type', async () => {
    const source = 'INFO 安排干员 → 制造站 B201'
    const page = mount({
      facilityPlan: { room_2_1: { name: '贸易站' } },
      lines: [{ ...logLine(1, source), room: 'room_2_1' }]
    })

    page.props.facilityPlan.room_2_1.name = '制造站'
    await nextTick()

    expect(visibleText(page.rows()[0])).toBe(source)
    const room = page.all().find((entry) => entry.props['data-room-id'] === 'room_2_1')
    expect(room.props['data-source-text']).toBe('制造站 B201')
  })

  it('starts a new facility segment after an unlinked warning for the same facility', () => {
    const lines = [
      'INFO 会客室：开始读取',
      'INFO 会客室：读取完成',
      'WARNING 会客室：结果需复核',
      'INFO 会客室：开始复核',
      'INFO 会客室：复核完成'
    ].map((source, index) => ({
      ...logLine(index, source, 'base-scheduler'),
      room: 'meeting'
    }))
    const page = mount({ lines })

    const headings = page.all().filter((entry) => hasClass(entry, 'log-facility-heading'))
    expect(headings.map(headingText)).toEqual(['会客室', '会客室'])
    expect(visibleText(page.rows()[2])).toBe(lines[2].text)
    expect(page.rows().map((entry) => entry.props['data-log-source'])).toEqual(
      lines.map((line) => line.text)
    )
  })

  it('inserts a group bar only for runs of two or more lines', () => {
    const page = mount({
      lines: [
        logLine(1, '2026-11-02 18:00:00,000 INFO 安排干员：但书', 'base-scheduler'),
        logLine(2, '2026-11-02 18:00:01,000 INFO 读取房间心情', 'base-scheduler'),
        logLine(3, '2026-11-02 18:00:02,000 INFO Scene 201: 基建全局视角', 'recognition'),
        logLine(4, '2026-11-02 18:00:03,000 INFO 开始刷理智：1-7', 'local-operation'),
        logLine(5, '2026-11-02 18:00:04,000 INFO 1-7 本轮完成 6 次作战', 'local-operation')
      ]
    })

    const bars = page.all().filter((element) => hasClass(element, 'log-group'))
    expect(bars.map((bar) => bar.props['data-group'])).toEqual([
      'base-scheduler',
      'local-operation'
    ])
    expect(bars.map(text)).toEqual(['基建排班', 'Mower日常'])
    expect(page.rows()).toHaveLength(5)
  })

  it('keeps unlinked records without a structured group outside the preceding business', () => {
    const page = mount({
      lines: [
        logLine(1, '2026-11-02 18:00:00,000 INFO 安排干员：但书', 'base-scheduler'),
        logLine(2, '2026-11-02 18:00:01,000 INFO 无分组行'),
        logLine(3, '2026-11-02 18:00:02,000 INFO 仍无分组行')
      ]
    })

    const bars = page.all().filter((element) => hasClass(element, 'log-group'))
    expect(bars).toHaveLength(0)
    expect(page.rows()).toHaveLength(3)
  })

  it('keeps the diamond loader on the original waiting scene while later details arrive', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-02T18:00:00.000'))
    const now = Date.now()
    const page = mount({
      running: true,
      lines: [
        logLine(
          1,
          '2026-11-02 17:59:57,000 INFO Scene 9998: 场景跳转时的等待界面',
          'recognition',
          now - 3000
        ),
        logLine(
          2,
          '2026-11-02 17:59:57,500 INFO 本次【场景跳转时的等待界面】使用联网等待补偿',
          'recognition',
          now - 2500
        )
      ]
    })

    const loader = page.all().find((element) => hasClass(element, 'log-wait-loader'))
    expect(loader).toBeDefined()
    expect(page.rows()[0].children).toContain(loader)
    expect(visibleText(loader.parent)).toContain('Scene 9998: 场景跳转时的等待界面')
    expect(page.all().some((element) => hasClass(element, 'log-lifecycle-active'))).toBe(false)
    expect(page.all().some((element) => hasClass(element, 'log-wait-duration'))).toBe(false)
    expect(page.warnings).toEqual([])
  })

  it('does not add the wait animation while stopped', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-02T18:00:00.000'))
    const now = Date.now()
    const page = mount({
      running: false,
      lines: [
        logLine(
          1,
          '2026-11-02 17:59:57,000 INFO Scene 9998: 场景跳转时的等待界面',
          'recognition',
          now - 3000
        )
      ]
    })

    expect(page.all().some((element) => hasClass(element, 'log-wait-loader'))).toBe(false)
  })

  it('does not revive a stopped wait before the next run receives its log stream', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-11-02T18:00:00.000'))
    const waiting = (id, at) =>
      logLine(
        id,
        '2026-11-02 17:59:57,000 INFO Scene 9998: 场景跳转时的等待界面',
        'recognition',
        at
      )
    const loader = (page) => page.all().find((element) => hasClass(element, 'log-wait-loader'))
    const page = mount({ running: true, lines: [waiting('old:1', Date.now() - 3000)] })
    expect(loader(page)).toBeDefined()

    page.props.running = false
    await nextTick()
    expect(loader(page)).toBeUndefined()

    page.props.running = true
    await nextTick()
    expect(loader(page)).toBeUndefined()

    page.props.lines = [waiting('new:1', Date.now())]
    await nextTick()
    expect(loader(page)).toBeUndefined()
    await vi.advanceTimersByTimeAsync(1500)
    expect(page.rows()[0].children).toContain(loader(page))
  })

  it('writes the finished wait duration back onto the waiting scene line', () => {
    const now = Date.now()
    const page = mount({
      running: true,
      lines: [
        logLine(
          1,
          '2026-11-02 17:59:50,000 INFO Scene 9998: 场景跳转时的等待界面',
          'recognition',
          now - 10000
        ),
        logLine(
          2,
          '2026-11-02 17:59:53,000 INFO 本次【场景跳转时的等待界面】使用联网等待补偿',
          'recognition',
          now - 7000
        ),
        logLine(
          3,
          '2026-11-02 17:59:57,000 INFO Scene 201: 基建全局视角',
          'recognition',
          now - 3000
        )
      ]
    })

    const badge = page.all().find((element) => hasClass(element, 'log-wait-duration'))
    expect(badge).toBeDefined()
    expect(text(badge)).toBe('等待 7.0s')
    expect(page.all().some((element) => hasClass(element, 'log-wait-loader'))).toBe(false)
    expect(page.warnings).toEqual([])
  })

  it('fades only genuinely appended lines and leaves large batches static', async () => {
    const page = mount({ lines: [logLine(1, 'INFO 第一条')] })
    expect(hasClass(page.rows()[0], 'log-line--enter')).toBe(false)

    page.props.lines = [page.props.lines[0], logLine(2, 'INFO 第二条')]
    await nextTick()
    expect(hasClass(page.rows()[1], 'log-line--enter')).toBe(true)

    const batch = Array.from({ length: 10 }, (_, index) =>
      logLine(10 + index, `INFO 批量 ${index}`)
    )
    page.props.lines = [...page.props.lines, ...batch]
    await nextTick()
    const batchRows = page.rows().slice(2)
    expect(batchRows).toHaveLength(10)
    expect(batchRows.some((row) => hasClass(row, 'log-line--enter'))).toBe(false)
  })

  it('keeps row nodes stable across eviction when lines carry stable ids', async () => {
    const lines = [logLine(1, 'INFO 甲'), logLine(2, 'INFO 乙'), logLine(3, 'INFO 丙')]
    const page = mount({ lines })
    const initial = page.rows()

    page.props.lines = [...lines.slice(1), logLine(4, 'INFO 丁')]
    await nextTick()

    expect(page.rows()).toHaveLength(3)
    expect(page.rows()[0]).toBe(initial[1])
    expect(page.rows()[1]).toBe(initial[2])
  })
})

describe('runtime log navigation', () => {
  it('jumps once without enabling follow and hides the control at the latest position', async () => {
    const page = mount({ autoScroll: false, lines: [logLine(1, 'INFO 记录')] })
    const container = {
      scrollTop: 0,
      scrollHeight: 600,
      clientHeight: 200,
      getBoundingClientRect: () => ({ top: 0 }),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    }
    page.all().find((entry) => hasClass(entry, 'log-output')).querySelector = () => container
    await nextTick()
    await nextTick()
    const jumpControl = () => page.all().find((entry) => hasClass(entry, 'log-jump-latest'))
    const [eventName, onScroll] = container.addEventListener.mock.calls[0]
    expect(eventName).toBe('scroll')
    jumpControl().props.onClick({ currentTarget: jumpControl() })
    await nextTick()
    expect(container.scrollTop).toBe(400)
    expect(jumpControl()).toBeUndefined()
    expect(page.props.autoScroll).toBe(false)

    container.scrollTop = 397
    onScroll()
    await nextTick()
    expect(jumpControl()).toBeUndefined()

    container.scrollTop = 396
    onScroll()
    await nextTick()
    expect(jumpControl()).toBeDefined()
    page.props.showAlternateView = true
    await nextTick()
    expect(jumpControl()).toBeUndefined()
  })

  it('offers the time of a warning or error with a usable timestamp', () => {
    const at = 1794226000000
    const history = vi.fn(({ at }) => h('a', { class: 'log-history-link', 'data-at': at }))
    const lines = [
      { ...logLine(1, '2026-11-09 15:00:00 INFO 等待'), at },
      { ...logLine(2, '2026-11-09 15:00:01 ERROR 无法确认场景'), at: at + 1000 },
      logLine(3, '2026-11-09 15:00:02 WARNING 缺少时间')
    ]
    const page = mount({ lines }, { history })
    const links = page.all().filter((entry) => hasClass(entry, 'log-history-link'))
    expect(links.map((entry) => entry.props['data-at'])).toEqual([at + 1000])
  })
})
