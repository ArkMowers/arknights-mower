import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  createSSRApp,
  defineComponent,
  h,
  nextTick,
  ref,
  ssrContextKey
} from 'vue'
import { createPinia } from 'pinia'
import axios from 'axios'
import PlanEditor from '@/components/PlanEditor.vue'
import PlanFacilityLevels from '@/components/PlanFacilityLevels.vue'
import PlanIncomeDialog from '@/components/PlanIncomeDialog.vue'
import MoodLimitsEditor from '@/components/MoodLimitsEditor.vue'
import RenameDialog from '@/components/RenameDialog.vue'
import TriggerDialog from '@/components/TriggerDialog.vue'
import TaskDialog from '@/components/TaskDialog.vue'
import { usePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'
import { useMowerStore } from '@/stores/mower'
import { plan_facility_type_options } from '@/utils/base_facilities'
import { factory_product_options } from '@/utils/base_products'
import { inventory_expression, inventory_options_with_counts } from '@/utils/trigger_inventory'
import { i18n } from '@/i18n'
import { localizedPlanOptions } from './plans'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }))
vi.mock('@/riic/incomeArchive', () => ({
  loadIncomeArchive: vi.fn(async () => null),
  saveIncomeArchive: vi.fn(async () => {})
}))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => ({ warning: vi.fn() })
}))

const Select = defineComponent({
  props: ['value', 'options'],
  emits: ['update:value'],
  setup:
    (props, { attrs, emit }) =>
    () =>
      h(
        'select',
        { ...attrs, value: props.value, onChange: (value) => emit('update:value', value) },
        (props.options || []).map((option) => h('option', { value: option.value }, option.label))
      )
})
const Container = defineComponent({
  inheritAttrs: false,
  setup:
    (_, { attrs, slots }) =>
    () =>
      h('section', attrs, [slots.header?.(), slots.label?.(), slots.default?.(), slots.footer?.()])
})
const Input = defineComponent({
  props: ['value'],
  emits: ['update:value'],
  setup:
    (props, { attrs, emit }) =>
    () =>
      h('input', { ...attrs, value: props.value, onInput: (value) => emit('update:value', value) })
})
const Empty = { render: () => null }
const DynamicInput = defineComponent({
  props: ['value'],
  setup:
    (props, { slots }) =>
    () =>
      h(
        'dynamic-input',
        (props.value || []).map((value, index) => slots.default?.({ value, index }))
      )
})
const components = {
  NSelect: Select,
  NInput: Input,
  NAutoComplete: Input,
  NDatePicker: Input,
  NInputNumber: Input,
  NDynamicInput: DynamicInput,
  NDynamicTags: Empty,
  NCode: Empty,
  MowerInputNumber: Input,
  NForm: Container,
  NFormItem: Container,
  NButton: Container,
  NCheckbox: Container,
  NCard: Container,
  NModal: Container,
  NText: Container,
  NTable: Container,
  NScrollbar: Container,
  NRadioGroup: Container,
  NRadioButton: Container,
  NSpace: Container,
  NCollapse: Container,
  NCollapseItem: Container,
  NAlert: Container,
  NTabs: Container,
  NTabPane: Container,
  NProgress: Container,
  NPagination: Container,
  NSpin: Empty,
  NEmpty: Empty,
  NSwitch: Input,
  NPopconfirm: Container,
  HelpText: Container,
  NAvatar: Empty,
  NIcon: Empty,
  NTag: Container,
  SlickOperatorSelect: Empty,
  TriggerEditor: Empty
}
function client(component, name, extra = {}) {
  const { descriptor } = parse(
    readFileSync(new URL(`../components/${name}.vue`, import.meta.url), 'utf8')
  )
  return {
    ...component,
    ssrRender: undefined,
    components: { ...components, ...extra },
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context) })
  }
}
const ClientLevels = client(PlanFacilityLevels, 'PlanFacilityLevels')
const ClientEditor = client(PlanEditor, 'PlanEditor', { PlanFacilityLevels: ClientLevels })
const ClientMood = client(MoodLimitsEditor, 'MoodLimitsEditor')
const ClientRename = client(RenameDialog, 'RenameDialog')
const ClientTrigger = client(TriggerDialog, 'TriggerDialog')
const ClientTask = client(TaskDialog, 'TaskDialog')
const ClientIncome = client(PlanIncomeDialog, 'PlanIncomeDialog', {
  IncomeTimeline: Empty,
  IncomeActivity: Empty
})

const node = (tag) => ({ tag, props: {}, style: {}, children: [], parent: null, text: '' })
function remove(element) {
  const siblings = element.parent?.children
  if (siblings) siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => (element.text = text),
  setElementText(element, text) {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1],
  patchProp: (element, key, _old, value) => (element.props[key] = value),
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
let pinia
let loaded
const mounted = []
beforeEach(() => {
  i18n.global.locale.value = 'zh-CN'
  pinia = createPinia()
  loaded = ref(false)
  const context = createSSRApp(Empty)
  context.use(pinia)
  context.provide('loaded', loaded)
  const plan = context.runWithContext(() => usePlanStore(pinia))
  context.runWithContext(() => useConfigStore(pinia))
  axios.post.mockResolvedValue({ data: {} })
  axios.put.mockResolvedValue({ data: {} })
  plan.plan = plan.fill_empty({
    room_1_1: {
      name: '制造站',
      product: 'gold',
      plans: [{ agent: '阿米娅', group: '我的组', replacement: ['令'] }]
    }
  })
  plan.operators = [
    { label: '阿米娅', value: '阿米娅' },
    { label: '令', value: '令' }
  ]
  vi.spyOn(usedepotStore(pinia), 'loadInventory').mockResolvedValue({})
  vi.spyOn(useFacilityStore(pinia), 'load').mockResolvedValue({})
  vi.spyOn(useMasteryStore(pinia), 'loadPlanSummary').mockResolvedValue({})
})
afterEach(() => {
  mounted.splice(0).forEach((app) => app.unmount())
  pinia._s.forEach((store) => store.$dispose())
  i18n.global.locale.value = 'zh-CN'
  vi.restoreAllMocks()
  vi.clearAllMocks()
})
function mount(component, props = {}, provides = {}) {
  const root = node('root')
  const app = renderer.createApp(component, props)
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide('loaded', loaded)
  app.provide('mobile', ref(false))
  app.provide('planStore', usePlanStore(pinia))
  app.provide('facility', ref('room_1_1'))
  app.provide('planEditLocked', ref(false))
  for (const [key, value] of Object.entries(provides)) app.provide(key, value)
  app.mount(root)
  mounted.push(app)
  return { root, component: app._instance.setupState }
}

it('updates an open income dialog in every language without resubmitting or changing its plan and settings', async () => {
  const plan = usePlanStore(pinia).build_plan()
  const snapshot = { plan, label: '我的中文排班', image: new Blob(['original']) }
  const { root, component } = mount(ClientIncome, { snapshot }, { axios })
  await nextTick()
  component.state.progress = { label: '统计 2.5 / 24 小时', fraction: 0.1 }
  component.state.running = true
  component.state.error = '收益记录存储被其他窗口占用'
  await nextTick()
  const original = JSON.stringify({
    plan,
    settings: component.settings,
    progress: component.state.progress
  })
  axios.get.mockClear()
  axios.post.mockClear()
  axios.put.mockClear()
  for (const [locale, progress, error] of [
    ['en-US', 'Sample 2.5 / 24 h', 'Income storage is occupied by another window'],
    ['ja-JP', '集計 2.5 / 24 時間', '収益記録ストレージを別のウィンドウが使用しています'],
    ['zh-TW', '統計 2.5 / 24 小時', '收益記錄儲存被其他視窗佔用']
  ]) {
    i18n.global.locale.value = locale
    await nextTick()
    expect(text(root)).toContain(progress)
    expect(text(root)).toContain(error)
    expect(
      JSON.stringify({ plan, settings: component.settings, progress: component.state.progress })
    ).toBe(original)
    expect(axios.get).not.toHaveBeenCalled()
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.put).not.toHaveBeenCalled()
  }
})

describe('plan display language', () => {
  it('updates the locally calculated power warning without changing saved facility levels', async () => {
    const plan = usePlanStore(pinia)
    const before = JSON.stringify(plan.build_plan())
    const { root } = mount(ClientLevels)
    expect(text(root)).toContain('存在电力赤字')
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(text(root)).toContain('Total base power consumption')
    expect(text(root)).toContain('exceeds generation')
    expect(text(root)).not.toContain('存在电力赤字')
    expect(JSON.stringify(plan.build_plan())).toBe(before)
    expect(axios.post).not.toHaveBeenCalled()
  })
  it('localizes options without changing facility, product or condition values', () => {
    i18n.global.locale.value = 'en-US'
    const facilities = localizedPlanOptions(plan_facility_type_options)
    expect(facilities[0]).toEqual({ label: 'Trading Post', value: '贸易站' })
    expect(localizedPlanOptions(factory_product_options)[0]).toEqual({
      label: 'Pure Gold',
      value: 'gold'
    })
    const stock = inventory_options_with_counts({ 赤金: 42 })[0]
    expect(stock).toMatchObject({ value: '赤金', name: 'Pure Gold', inventoryText: '42' })
    expect(inventory_expression(stock.value)).toBe("op_data.inventory_count('赤金')")
    expect(plan_facility_type_options[0].label).toBe('贸易站')
  })

  it('updates a mounted facility editor and saves original facility values and custom groups', async () => {
    const plan = usePlanStore(pinia)
    const config = useConfigStore(pinia)
    config.maa_mall_buy = []
    config.maa_mall_blacklist = []
    config.product_switching.enable = true
    const before = JSON.stringify(plan.build_plan())
    const { root } = mount(ClientEditor)
    loaded.value = true
    await nextTick()
    await plan.wait_for_plan_save()
    axios.post.mockClear()
    axios.put.mockClear()
    expect(text(root)).toContain('制造站')
    const typeSelect = all(root).find(
      (element) => element.tag === 'select' && element.props.value === '制造站'
    )
    expect(typeSelect).toBeTruthy()
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(text(root)).toContain('Factory')
    expect(text(root)).toContain('Trading Post')
    expect(text(root)).toContain('阿米娅')
    expect(all(root).some((element) => element.props.value === '我的组')).toBe(true)
    expect(typeSelect.props.value).toBe('制造站')
    expect(JSON.stringify(plan.build_plan())).toBe(before)
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.put).not.toHaveBeenCalled()
    typeSelect.props.onChange('贸易站')
    await nextTick()
    await plan.wait_for_plan_save()
    expect(plan.build_plan().plan1.room_1_1.name).toBe('贸易站')
    expect(plan.build_plan().plan1.room_1_1.plans[0].group).toBe('我的组')
    expect(plan.build_plan().plan1.room_1_1.plans[0].agent).toBe('阿米娅')
    expect(axios.post.mock.lastCall[1].plan1.room_1_1).toMatchObject({
      name: '贸易站',
      plans: [{ agent: '阿米娅', group: '我的组', replacement: ['令'] }]
    })
  })

  it('updates personal morale controls without emitting model edits on language changes', async () => {
    const updateDefaults = vi.fn(),
      updateOverrides = vi.fn()
    const { root } = mount(ClientMood, {
      defaults: { lower: 0, upper: 24 },
      overrides: { 阿米娅: { lower: 2, upper: 20 } },
      operators: [{ label: '令', value: '令' }],
      'onUpdate:defaults': updateDefaults,
      'onUpdate:overrides': updateOverrides
    })
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(text(root)).toContain('Lower limit')
    expect(text(root)).toContain('Amiya')
    expect(
      all(root).some((element) => element.props['aria-label'] === 'Amiya morale upper limit')
    ).toBe(true)
    expect(
      all(root).some(
        (element) => element.props.placeholder === 'Choose an operator for personal limits'
      )
    ).toBe(true)
    expect(updateDefaults).not.toHaveBeenCalled()
    expect(updateOverrides).not.toHaveBeenCalled()
    for (const [locale, name, label] of [
      ['ja-JP', 'アーミヤ', 'アーミヤ の体力上限'],
      ['zh-TW', '阿米婭', '阿米婭心情上限']
    ]) {
      i18n.global.locale.value = locale
      await nextTick()
      expect(text(root)).toContain(name)
      expect(all(root).some((element) => element.props['aria-label'] === label)).toBe(true)
      expect(updateDefaults).not.toHaveBeenCalled()
      expect(updateOverrides).not.toHaveBeenCalled()
    }
  })

  it('updates open backup dialogs while preserving user plan names, group names and conditions', async () => {
    const plan = usePlanStore(pinia)
    plan.backup_plans = [
      {
        name: '自用副表',
        group_ids: ['default'],
        type: 'global',
        trigger: { left: "op_data.inventory_count('赤金')", operator: '>', right: '42' }
      }
    ]
    plan.sub_plan = 0
    const before = JSON.stringify(plan.backup_plans)
    const rename = mount(ClientRename, {}, { show_name_editor: ref(true) })
    const conditions = mount(ClientTrigger, {}, { show_trigger_editor: ref(true) })
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(all(rename.root).some((element) => element.props.title === 'Rename')).toBe(true)
    expect(all(rename.root).some((element) => element.props.value === '自用副表')).toBe(true)
    expect(
      all(conditions.root).some((element) => element.props.title === 'Backup conditions')
    ).toBe(true)
    expect(text(conditions.root)).toContain('Global backup')
    expect(text(conditions.root)).toContain('Default group')
    expect(JSON.stringify(plan.backup_plans)).toBe(before)
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('updates an open shared task dialog and submits the unchanged Chinese task type', async () => {
    vi.spyOn(useMowerStore(pinia), 'get_tasks').mockResolvedValue([])
    const { root, component } = mount(ClientTask, {}, { show_task: ref(true), add_task: ref(true) })
    const taskSelect = all(root).find(
      (element) => element.tag === 'select' && element.props.value === '空任务'
    )
    expect(taskSelect).toBeTruthy()
    i18n.global.locale.value = 'en-US'
    await nextTick()
    expect(text(root)).toContain('Scheduled stop')
    expect(taskSelect.props.value).toBe('空任务')
    expect(axios.post).not.toHaveBeenCalled()
    taskSelect.props.onChange('计划停止')
    component.duration_minutes = 0
    await nextTick()
    expect(text(root)).toContain('Duration (minutes):')
    axios.post.mockResolvedValueOnce({ data: '添加任务成功！' })
    await component.saveTasks()
    await nextTick()
    expect(axios.post.mock.lastCall[1].task).toMatchObject({
      task_type: '计划停止',
      duration_minutes: 0,
      maintenance_mode: 'prepare',
      plan: {}
    })
    expect(text(root)).toContain('Task added successfully.')
    i18n.global.locale.value = 'zh-CN'
    await nextTick()
    expect(text(root)).toContain('添加任务成功！')
    expect(axios.post).toHaveBeenCalledTimes(1)
  })
})
