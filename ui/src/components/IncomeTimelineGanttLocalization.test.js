import { readFileSync } from 'node:fs'
import { compile } from '@vue/compiler-dom'
import { parse } from '@vue/compiler-sfc'
import { transpileModule, ScriptTarget } from 'typescript'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as Vue from 'vue'
import { createI18n } from 'vue-i18n'
import { toBlob, toPng } from 'html-to-image'
import ScheduleTimelineGantt from '@/riic/vendor/components/workbench/ScheduleTimelineGantt.vue'
import { timelineMessages } from '@/i18n/messages/timeline'

vi.mock('html-to-image', () => ({ toBlob: vi.fn(), toPng: vi.fn() }))

const { descriptor } = parse(
  readFileSync(
    new URL('../riic/vendor/components/workbench/ScheduleTimelineGantt.vue', import.meta.url),
    'utf8'
  )
)
const compiled = compile(descriptor.template.content, {
  isTS: true,
  expressionPlugins: ['typescript'],
  hoistStatic: false
}).code
const render = new Function(
  'Vue',
  transpileModule(compiled, { compilerOptions: { target: ScriptTarget.ES2022 } }).outputText
)(Vue)
const ClientGantt = {
  ...ScheduleTimelineGantt,
  ssrRender: undefined,
  render,
  setup: (props, context) => ({ ...ScheduleTimelineGantt.setup(props, context) })
}
const node = (tag) => ({
  tag,
  tagName: tag.toUpperCase(),
  props: {},
  style: {},
  children: [],
  parent: null,
  text: '',
  value: '',
  getRootNode: () => ({ activeElement: null }),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  get options() {
    return this.children.filter((child) => child.tag === 'option')
  }
})
function remove(element) {
  if (!element.parent) return
  const siblings = element.parent.children
  siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = Vue.createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText(element, text) {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => {
    const siblings = element.parent?.children || []
    return siblings[siblings.indexOf(element) + 1] || null
  },
  patchProp(element, key, _old, value) {
    element.props[key] = value
    if (key === 'value') element.value = value
  },
  insert(element, parent, anchor) {
    remove(element)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove
})
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const byTest = (root, key) => all(root).find((element) => element.props['data-test'] === key)
const mounted = []
let translations

beforeEach(() => {
  vi.stubGlobal('Document', class {})
  vi.stubGlobal('ShadowRoot', class {})
  translations = createI18n({
    legacy: false,
    locale: 'zh-CN',
    fallbackLocale: 'zh-CN',
    messages: Object.fromEntries(
      Object.entries(timelineMessages).map(([locale, timeline]) => [locale, { timeline }])
    )
  })
  vi.stubGlobal('window', new EventTarget())
  vi.stubGlobal('document', { activeElement: null, createElement: () => ({ click: vi.fn() }) })
  toPng.mockReset()
  toBlob.mockReset()
})
afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  translations.dispose()
  vi.unstubAllGlobals()
})

function fixtures() {
  const interval = {
    id: 'original-interval',
    start: 0,
    end: 12,
    duration: 12,
    operatorId: 'operator-original',
    operatorName: '原始干员名',
    avatarUrl: '',
    roomId: 'room-original',
    roomName: '用户设施名',
    roomType: 'manufacture',
    slotIndex: 0,
    slotKey: 'slot-original',
    isDormitory: false,
    status: 'working'
  }
  const report = { observedHours: 96, logs: [{ message: '原始日志正文：副表条件不满足' }] }
  const timelineData = {
    totalHours: 96,
    warmupHours: 0,
    observedHours: 96,
    facilityTracks: [
      {
        roomId: 'room-original',
        roomName: '用户设施名',
        roomType: 'manufacture',
        level: 3,
        averageEfficiency: 100,
        slots: [{ slotKey: 'slot-original', slotIndex: 0, role: 'work', intervals: [interval] }]
      }
    ],
    operatorTracks: [
      {
        operatorId: interval.operatorId,
        operatorName: interval.operatorName,
        avatarUrl: '',
        workHours: 12,
        restHours: 84,
        idleHours: 0,
        exhaustedHours: 0,
        workFraction: 0.125,
        intervals: [interval]
      }
    ],
    events: [
      {
        time: 4,
        type: 'backup-plan',
        label: '原始副表事件',
        description: '原始调度诊断正文',
        operatorIds: [interval.operatorId],
        icon: '↔',
        color: '#123456'
      }
    ]
  }
  return { report, timelineData }
}

function mount(data = fixtures(), translate = true) {
  const root = node('root')
  const simulate = vi.fn()
  const app = renderer.createApp(ClientGantt, {
    ...data,
    initialWindowHours: 24,
    initiallyCollapsed: true,
    ...(translate && {
      translate: (key, params) => translations.global.t(`timeline.${key}`, params ?? {})
    }),
    onRequestSimulate: simulate
  })
  app.provide(Vue.ssrContextKey, { modules: new Set() })
  app.mount(root)
  mounted.push(app)
  return { root, state: app._instance.setupState, simulate }
}
async function click(root, key) {
  byTest(root, key).props.onClick()
  await Vue.nextTick()
}

describe('translated calculator timeline presentation', () => {
  it('translates condensed interval labels while preserving the original intervals', async () => {
    const data = fixtures()
    const source = data.timelineData.facilityTracks[0].slots[0].intervals[0]
    const intervals = [
      { ...source, id: 'short-a', start: 0, end: 0.01, duration: 0.01 },
      { ...source, id: 'short-b', start: 0.01, end: 0.02, duration: 0.01 }
    ]
    data.timelineData.facilityTracks[0].slots[0].intervals = intervals
    data.timelineData.operatorTracks[0].intervals = intervals
    const original = JSON.stringify(data)
    const { root } = mount(data)
    await click(root, 'toggle-gantt-visibility')
    translations.global.locale.value = 'en-US'
    await Vue.nextTick()
    expect(text(root)).toContain('Dense switches (2 intervals)')
    expect(text(root)).not.toContain('密集切换')
    expect(JSON.stringify(data)).toBe(original)
  })

  it('updates operator display names and search without changing identities or the selected time window', async () => {
    const data = fixtures()
    const original = JSON.stringify(data)
    const { root, state } = mount({
      ...data,
      displayOperatorName: (name) =>
        translations.global.locale.value === 'en-US' ? 'Localized operator' : name,
      displayRoomName: (id, original) =>
        translations.global.locale.value === 'en-US' ? `Localized facility ${id}` : original
    })
    await click(root, 'toggle-gantt-visibility')
    const start = state.customWindowStart
    const end = state.customWindowEnd
    translations.global.locale.value = 'en-US'
    await Vue.nextTick()
    expect(text(root)).toContain('Localized operator')
    expect(text(root)).toContain('Localized facility room-original')
    state.searchQuery = 'localized operator'
    await Vue.nextTick()
    expect(state.filteredFacilityTracks[0].roomId).toBe('room-original')
    expect(state.filteredOperatorTracks[0].operatorId).toBe(
      data.timelineData.operatorTracks[0].operatorId
    )
    expect(state.customWindowStart).toBe(start)
    expect(state.customWindowEnd).toBe(end)
    state.searchQuery = 'localized facility'
    await Vue.nextTick()
    expect(state.filteredFacilityTracks[0].roomId).toBe('room-original')
    expect(state.filteredOperatorTracks[0].operatorId).toBe(
      data.timelineData.operatorTracks[0].operatorId
    )
    expect(JSON.stringify(data)).toBe(original)
  })

  it('keeps the pinned component Chinese when no translator is supplied', async () => {
    const { root } = mount(fixtures(), false)
    translations.global.locale.value = 'en-US'
    await Vue.nextTick()
    expect(text(root)).toContain('排班甘特图 / 时间轴可视化')
    expect(text(byTest(root, 'toggle-gantt-visibility'))).toBe('展开图表')
    await click(root, 'toggle-gantt-visibility')
    expect(text(root)).toContain('全部设施')
    expect(text(root)).toContain('上一周期')
  })

  it('updates mounted controls, tracks and export UI without changing source records', async () => {
    const data = fixtures()
    const original = JSON.stringify(data)
    const { root, state } = mount(data)
    translations.global.locale.value = 'en-US'
    await Vue.nextTick()
    expect(text(byTest(root, 'toggle-gantt-visibility'))).toBe('Expand chart')
    await click(root, 'toggle-gantt-visibility')
    for (const value of [
      'All facilities',
      'Factory',
      'Time window:',
      'Event markers',
      'Backup events (1)',
      'Slot 1'
    ])
      expect(text(root)).toContain(value)
    expect(
      all(root).find((element) => element.tag === 'input' && element.props.type === 'text').props
        .placeholder
    ).toBe('Search facilities or assigned operators...')
    expect(text(byTest(root, 'cycle-select'))).toContain('Day 1 (T+0h ~ T+24h)')
    expect(text(root)).toContain('用户设施名')
    expect(text(root)).toContain('原始干员名')
    expect(state.roomTypeLabel('unknown-user-type')).toBe('unknown-user-type')
    state.hoveredEvent = data.timelineData.events[0]
    await Vue.nextTick()
    expect(text(root)).toContain('原始副表事件')
    expect(text(root)).toContain('原始调度诊断正文')
    await click(root, 'export-gantt-btn')
    expect(text(byTest(root, 'gantt-export-modal'))).toContain('Export facility Gantt chart')
    expect(text(root)).toContain('Download PNG chart')
    expect(text(root)).toContain('Standard (12h window · 100px/h)')
    await click(root, 'scope-btn-volume')
    expect(text(byTest(root, 'volume-select'))).toContain('Volume 1: Days 1–3')
    expect(text(byTest(root, 'volume-days-select'))).toContain('3 days per volume')
    expect(state.getExportFilename()).toBe('base-schedule_facilities_volume-1_T+0h-72h.png')
    translations.global.locale.value = 'zh-CN'
    await Vue.nextTick()
    expect(text(byTest(root, 'toggle-gantt-visibility'))).toBe('收起图表')
    expect(text(root)).toContain('分卷超清 (推荐)')
    expect(JSON.stringify(data)).toBe(original)
    expect(data.report.logs[0].message).toBe('原始日志正文：副表条件不满足')
  })

  it('translates export errors and keeps the original diagnostic message', async () => {
    const data = fixtures()
    const original = JSON.stringify(data)
    const { root, state } = mount(data)
    translations.global.locale.value = 'en-US'
    await click(root, 'export-gantt-btn')
    toPng.mockRejectedValueOnce(new Error('原始导出诊断中文'))
    await state.handleDownloadGanttImage()
    await Vue.nextTick()
    expect(text(root)).toContain('Export failed: 原始导出诊断中文')
    expect(state.isExporting).toBe(false)
    toBlob.mockResolvedValueOnce(null)
    await state.handleCopyGanttImage()
    await Vue.nextTick()
    expect(text(root)).toContain('Copy failed: Could not generate image data')
    expect(JSON.stringify(data)).toBe(original)
  })

  it('translates the empty state and dispatches the original simulate event', async () => {
    const { root, simulate } = mount({ report: null, timelineData: null })
    translations.global.locale.value = 'en-US'
    await click(root, 'toggle-gantt-visibility')
    expect(text(root)).toContain('No timeline data yet')
    const button = all(root).find((element) => element.props.class === 'run-sim-btn')
    expect(text(button)).toBe('Run scheduling simulation')
    button.props.onClick()
    expect(simulate).toHaveBeenCalledOnce()
  })
})
