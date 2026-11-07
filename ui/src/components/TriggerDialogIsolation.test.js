import { afterEach, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { compile, createRenderer, h, nextTick, ref, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import * as NaiveUI from 'naive-ui'
import axios from 'axios'
import TriggerDialog from './TriggerDialog.vue'
import TriggerEditor from './TriggerEditor.vue'
import TriggerString from './TriggerString.vue'
import { usePlanStore, useRescuePlanStore } from '@/stores/plan'
import { useConfigStore } from '@/stores/config'
import { usedepotStore } from '@/stores/depot'
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'
import { maintenance_trigger } from '@/utils/trigger_maintenance'

vi.mock('axios')
vi.mock('@/stores/config', async () => {
  const { defineStore } = await import('pinia')
  return {
    useConfigStore: defineStore('trigger-config-test', {
      state: () => ({ product_switching: { enable: false } })
    })
  }
})
vi.mock('naive-ui', () => {
  const content = {
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.())
  }
  const input = {
    props: ['value'],
    emits: ['update:value'],
    setup:
      (props, { emit }) =>
      () =>
        h('input', { value: props.value, onInput: (value) => emit('update:value', value) })
  }
  return {
    ...Object.fromEntries(
      [
        'NModal',
        'NScrollbar',
        'NForm',
        'NFormItem',
        'NRadioGroup',
        'NRadioButton',
        'NText',
        'NSpace',
        'NFlex',
        'NButton',
        'NPopconfirm',
        'NCard',
        'NCode',
        'NCollapse',
        'NCollapseItem',
        'NAlert',
        'NTable'
      ].map((name) => [name, content])
    ),
    NInput: input,
    NAutoComplete: input,
    NSelect: {
      props: ['value', 'defaultValue', 'options', 'onUpdate:value'],
      setup: (props) => {
        const initial = props.defaultValue
        return () =>
          h('select', {
            value: props.value ?? initial,
            onChange: props['onUpdate:value']
          })
      }
    },
    NDynamicInput: {
      props: ['value'],
      setup:
        (props, { slots }) =>
        () =>
          h(
            'div',
            props.value.map((value, index) => slots.default?.({ value, index }))
          )
    },
    NAvatar: content
  }
})

const cleanups = []
afterEach(() => {
  cleanups.splice(0).forEach((cleanup) => cleanup())
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

const binary = (left, right) => ({ left, operator: '>', right })
const copy = (value) => JSON.parse(JSON.stringify(value))

function clientComponent(component, file) {
  const { descriptor } = parse(readFileSync(new URL(file, import.meta.url), 'utf8'))
  return {
    ...component,
    ssrRender: undefined,
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context) })
  }
}

async function mount(rescue) {
  let saved = {
    conf: {},
    plan1: {},
    backup_groups: [
      { id: 'default', name: '默认分组', trigger: {} },
      { id: 'a', name: '分组甲', trigger: binary('10', '1') },
      { id: 'b', name: '分组乙', trigger: binary('20', '2') }
    ],
    backup_plans: ['3', '4'].map((right) => ({
      conf: {},
      plan: {},
      group_ids: ['a', 'b'],
      type: 'global',
      trigger: binary('30', right)
    }))
  }
  axios.get.mockImplementation(async () => ({ data: copy(saved) }))
  axios.post.mockImplementation(async (_url, payload) => {
    saved = copy(payload)
    return { data: {} }
  })
  const renderer = createRenderer({
    createElement: (type) => ({ type, props: {}, children: [] }),
    createText: (text) => ({ text }),
    createComment: (text) => ({ text }),
    insert(node, parent, anchor) {
      if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
      node.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      if (index < 0) parent.children.push(node)
      else parent.children.splice(index, 0, node)
    },
    remove(node) {
      node.parent.children.splice(node.parent.children.indexOf(node), 1)
    },
    setText(node, text) {
      node.text = text
    },
    setElementText(node, text) {
      node.text = text
      node.children = []
    },
    patchProp(node, key, _previous, value) {
      node.props[key] = value
    },
    parentNode: (node) => node.parent,
    nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1]
  })
  const pinia = createPinia()
  const loaded = ref(false)
  const app = renderer.createApp(clientComponent(TriggerDialog, './TriggerDialog.vue'))
  for (const [name, component] of Object.entries(NaiveUI)) app.component(name, component)
  app.component('HelpText', NaiveUI.NText)
  app.component('MowerInputNumber', NaiveUI.NInput)
  app.component('TriggerEditor', clientComponent(TriggerEditor, './TriggerEditor.vue'))
  app.component('TriggerString', clientComponent(TriggerString, './TriggerString.vue'))
  app.use(pinia)
  app.provide('loaded', loaded)
  app.provide(ssrContextKey, {})
  const store = app.runWithContext(() => (rescue ? useRescuePlanStore() : usePlanStore()))
  const other = app.runWithContext(() => (rescue ? usePlanStore() : useRescuePlanStore()))
  other.autosave_paused = true
  useConfigStore(pinia).product_switching.enable = false
  vi.spyOn(usedepotStore(pinia), 'loadInventory').mockResolvedValue({})
  vi.spyOn(useFacilityStore(pinia), 'load').mockResolvedValue({})
  vi.spyOn(useMasteryStore(pinia), 'loadPlanSummary').mockResolvedValue({})
  await store.load_plan()
  store.sub_plan = 0
  loaded.value = true
  await nextTick()
  await store.wait_for_plan_save()
  app.provide('planStore', store)
  app.provide('show_trigger_editor', ref(true))
  app.provide('planEditLocked', ref(false))
  const root = { children: [] }
  app.mount(root)
  cleanups.push(() => {
    app.unmount()
    for (const entry of pinia._s.values()) entry.$dispose()
  })
  const nodes = (type) => {
    const result = []
    function visit(node) {
      if (node.type === type) result.push(node)
      node.children?.forEach(visit)
    }
    visit(root)
    return result
  }
  const selectGroup = async (id) => {
    nodes('select')
      .find((node) => node.props.placeholder === '选择要编辑条件的分组')
      .props.onChange(id)
    await nextTick()
  }
  const inputs = () => nodes('input').filter((node) => !node.props.placeholder)
  const persist = async () => {
    await nextTick()
    await store.wait_for_plan_save()
    return copy(saved)
  }
  return { store, other, selectGroup, inputs, selects: () => nodes('select'), persist }
}

it.each([false, true])(
  'keeps group and backup conditions independent through switching and reload (rescue=%s)',
  async (rescue) => {
    const { store, other, selectGroup, inputs, persist } = await mount(rescue)
    const untouched = copy(other.backup_groups)
    await selectGroup('a')
    expect(inputs().map((node) => node.props.value)).toEqual(['10', '>', '1', '30', '>', '3'])
    const beforeSwitch = axios.post.mock.calls.length
    await selectGroup('b')
    expect(inputs().map((node) => node.props.value)).toEqual(['20', '>', '2', '30', '>', '3'])
    await persist()
    expect(axios.post).toHaveBeenCalledTimes(beforeSwitch)
    inputs()[2].props.onInput('9')
    let saved = await persist()
    expect(saved.backup_groups[1].trigger).toEqual(binary('10', '1'))
    expect(saved.backup_groups[2].trigger).toEqual(binary('20', '9'))
    await selectGroup('a')
    expect(inputs()[2].props.value).toBe('1')
    store.sub_plan = 1
    await nextTick()
    expect(inputs()[5].props.value).toBe('4')
    inputs()[5].props.onInput('8')
    saved = await persist()
    expect(saved.backup_plans.map((backup) => backup.trigger)).toEqual([
      binary('30', '3'),
      binary('30', '8')
    ])
    await store.load_plan()
    await nextTick()
    expect(store.backup_groups[2].trigger).toEqual(binary('20', '9'))
    expect(inputs()[5].props.value).toBe('8')
    expect(other.backup_groups).toEqual(untouched)
  }
)

it('refreshes nested function arguments and saves edits only to the selected group', async () => {
  const { store, selectGroup, inputs, persist } = await mount(false)
  const a = { function: 'max', args: ['11', binary('12', '13')] }
  const b = { function: 'sum', args: ['21', binary('22', '23')] }
  store.backup_groups[1].trigger = copy(a)
  store.backup_groups[2].trigger = copy(b)
  await selectGroup('a')
  expect(
    inputs()
      .slice(0, 4)
      .map((node) => node.props.value)
  ).toEqual(['11', '12', '>', '13'])
  await selectGroup('b')
  expect(
    inputs()
      .slice(0, 4)
      .map((node) => node.props.value)
  ).toEqual(['21', '22', '>', '23'])
  inputs()[3].props.onInput('24')
  const saved = await persist()
  expect(saved.backup_groups[1].trigger).toEqual(a)
  expect(saved.backup_groups[2].trigger).toEqual({
    function: 'sum',
    args: ['21', binary('22', '24')]
  })
  const input = inputs()[3]
  input.props.onInput('25')
  await persist()
  expect(inputs()[3]).toBe(input)
  expect(input.props.value).toBe('25')
})

it('does not copy the previous group operands into the edited group', async () => {
  const { selectGroup, inputs, persist } = await mount(false)
  await selectGroup('a')
  await selectGroup('b')
  inputs()[2].props.onInput('9')
  const saved = await persist()
  expect(saved.backup_groups[1].trigger).toEqual(binary('10', '1'))
  expect(saved.backup_groups[2].trigger).toEqual(binary('20', '9'))
})

it('opens an empty imported condition without writing it back', async () => {
  const { store, selectGroup, inputs, persist } = await mount(false)
  store.backup_groups[2].trigger = {}
  await persist()
  await selectGroup('a')
  const beforeSwitch = axios.post.mock.calls.length
  await selectGroup('b')
  expect(
    inputs()
      .slice(0, 3)
      .map((node) => node.props.value)
  ).toEqual(['', undefined, ''])
  await persist()
  expect(axios.post).toHaveBeenCalledTimes(beforeSwitch)
  expect(store.backup_groups[2].trigger).toEqual({})
})

it('refreshes operator and attribute selections when switching groups', async () => {
  const { store, selectGroup, selects, persist } = await mount(false)
  store.backup_groups[1].trigger = binary("op_data.operators['阿米娅'].current_mood()", '1')
  store.backup_groups[2].trigger = binary("op_data.operators['陈'].is_working()", '2')
  await selectGroup('a')
  expect(selects().map((node) => node.props.value)).toContain('阿米娅')
  await selectGroup('b')
  expect(selects().map((node) => node.props.value)).toContain('陈')
  expect(selects().map((node) => node.props.value)).toContain('working')
  expect(selects().map((node) => node.props.value)).not.toContain('阿米娅')
  selects()
    .find((node) => node.props.value === 'working')
    .props.onChange('mood')
  const saved = await persist()
  expect(saved.backup_groups[2].trigger.left).toBe("op_data.operators['陈'].current_mood()")
  expect(saved.backup_groups[1].trigger.left).toBe("op_data.operators['阿米娅'].current_mood()")
})

it('refreshes maintenance advance and duration fields without overwriting another group', async () => {
  const { store, selectGroup, inputs, persist } = await mount(false)
  const a = maintenance_trigger(12, '>=', 6)
  store.backup_groups[1].trigger = a
  store.backup_groups[2].trigger = maintenance_trigger(3, '<', 4)
  await selectGroup('a')
  expect(
    inputs()
      .slice(0, 2)
      .map((node) => node.props.value)
  ).toEqual([12, 6])
  await selectGroup('b')
  expect(
    inputs()
      .slice(0, 2)
      .map((node) => node.props.value)
  ).toEqual([3, 4])
  inputs()[0].props.onInput(8)
  const saved = await persist()
  expect(saved.backup_groups[1].trigger).toEqual(a)
  expect(saved.backup_groups[2].trigger).toEqual(maintenance_trigger(8, '<', 4))
})

it('does not save imported conditions just because their object fields have a different order', async () => {
  const { store, selectGroup, persist } = await mount(false)
  store.backup_groups[1].trigger = {
    args: [{ right: '1', operator: '>', left: '10' }],
    function: 'max'
  }
  store.backup_groups[2].trigger = {
    args: [{ right: '2', operator: '<', left: '20' }],
    function: 'min'
  }
  await persist()
  const beforeSwitch = axios.post.mock.calls.length
  await selectGroup('b')
  await persist()
  expect(axios.post).toHaveBeenCalledTimes(beforeSwitch)
})
