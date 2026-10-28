import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  defineComponent,
  h,
  nextTick,
  reactive,
  ref,
  ssrContextKey,
  toRaw,
  toRefs
} from 'vue'
import MaaRogue from './MaaRogue.vue'
import { i18n } from '@/i18n'
import { createTaskWorkflow } from '@/task-workflow/model'
import { getMaaThemeOptions } from '@/utils/maa_theme_options'
import {
  blackflow_animals,
  blackflow_rewards,
  modes_for_theme,
  rogue_themes
} from '@/utils/roguelike_options'

const state = vi.hoisted(() => ({ config: null, plan: null }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))
vi.mock('pinia', () => ({ storeToRefs: (store) => toRefs(store) }))
const Container = defineComponent({
  props: ['label'],
  setup:
    (props, { slots }) =>
    () =>
      h('section', [slots.label?.() || props.label, slots.default?.()])
})
const Select = defineComponent({
  props: ['value', 'options'],
  emits: ['update:value'],
  setup:
    (props, { emit }) =>
    () =>
      h(
        'select',
        { value: props.value, onChange: (value) => emit('update:value', value) },
        (props.options || []).map((option) => h('option', { value: option.value }, option.label))
      )
})
const { descriptor } = parse(readFileSync(new URL('./MaaRogue.vue', import.meta.url), 'utf8'))
const Client = {
  ...MaaRogue,
  ssrRender: undefined,
  setup: (props, context) => ({ ...MaaRogue.setup(props, context) }),
  render: compile(descriptor.template.content, { hoistStatic: false }),
  components: {
    NForm: Container,
    NFormItem: Container,
    NCheckbox: Container,
    NSelect: Select,
    NFlex: Container,
    NText: Container,
    MaaRogueRecruit: Container,
    HelpText: Container,
    NInput: { render: () => null }
  }
}
const node = (tag) => ({ tag, props: {}, children: [], parent: null, text: '' })
function remove(element) {
  const siblings = element.parent?.children
  if (siblings) siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => {
    element.text = text
  },
  setElementText: (element, text) => {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1],
  patchProp: (element, key, _old, value) => {
    element.props[key] = value
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
let app
afterEach(() => {
  app?.unmount()
  app = null
  i18n.global.locale.value = 'zh-CN'
})

it('keeps every CN task, editor, theme, squad, mode and option ID when the mounted settings change among four interface languages', async () => {
  state.config = reactive({
    maa_rg_theme: 'BlackFlow',
    rogue: {
      mode: 30001,
      squad: '本源研修分队',
      roles: '坚不可摧',
      core_char: '机械师',
      use_support: true,
      use_nonfriend_support: false,
      investment_enabled: true,
      blackflow_cultivation_target: 'swaddled_cat',
      start_with_elite_two: false,
      only_start_with_elite_two: false
    }
  })
  state.plan = reactive({ operators: [{ label: '机械师', value: '机械师' }] })
  const saved = JSON.parse(JSON.stringify(toRaw(state.config)))
  const root = node('root')
  app = renderer.createApp(Client)
  app.provide('mobile', ref(false))
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  const vm = app._instance.setupState
  const values = (options) => options.map(({ value }) => value)
  const snapshot = () => {
    const workflow = createTaskWorkflow(state.config)
    return {
      tasks: workflow.tasks.map(({ id }) => id),
      editors: workflow.editors.map(({ id }) => id),
      themes: values(rogue_themes),
      homeThemes: values(getMaaThemeOptions()),
      squads: Object.fromEntries(
        Object.entries(vm.squad).map(([theme, options]) => [theme, values(options)])
      ),
      modes: Object.fromEntries(
        rogue_themes.map(({ value }) => [value, values(modes_for_theme(value))])
      ),
      paradigms: values(vm.col_list),
      roles: values(vm.roles),
      animals: values(vm.blackflow_target_options),
      playtime: values(vm.find_playtime_options),
      selects: all(root)
        .filter((element) => element.tag === 'select')
        .map((element) => ({
          value: element.props.value,
          options: values(element.children.map((child) => ({ value: child.props.value })))
        }))
    }
  }
  const source = snapshot()
  const labels = {
    'zh-CN': ['沉沦者的黑流树海', '襁褓中的猫'],
    'en-US': ["The Drowned's Blackflow Forest", 'Swaddled Cat'],
    'ja-JP': ['沈みゆく者の黒流樹海', 'くるまれた猫'],
    'zh-TW': ['沉淪者的黑流樹海', '襁褓中的貓']
  }
  for (const locale of Object.keys(labels)) {
    i18n.global.locale.value = locale
    await nextTick()
    expect(snapshot(), locale).toEqual(source)
    for (const label of labels[locale]) expect(text(root), locale).toContain(label)
    expect(state.config, locale).toEqual(saved)
  }
  i18n.global.locale.value = 'ja-JP'
  await nextTick()
  const animals = all(root).find(
    (element) => element.tag === 'select' && element.props.value === 'swaddled_cat'
  )
  animals.props.onChange('swaddled_feathered_serpent')
  await nextTick()
  expect(state.config.rogue.blackflow_cultivation_target).toBe('swaddled_feathered_serpent')
  expect(state.config.rogue.squad).toBe('本源研修分队')
  expect(state.config.maa_rg_theme).toBe('BlackFlow')
  expect(vm.squad.Sami.find((option) => option.value === '生活至上分队').label).toBe('生活重視分隊')
  expect(vm.col_list.find((option) => option.value === '去量化').label).toBe('数的崩壊')
})

function setupOpening() {
  state.config = reactive({
    maa_rg_theme: 'BlackFlow',
    rogue: {
      mode: 30003,
      squad: '',
      blackflow_start_rewards: 0,
      blackflow_start_animals: []
    }
  })
  state.plan = reactive({ operators: [] })
  app = renderer.createApp(Client)
  app.provide('mobile', ref(false))
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(node('root'))
  return app._instance.setupState
}

it('saves selected rewards as the documented mask and restores their names', () => {
  const component = setupOpening()
  component.blackflow_reward_values = ['unnumbered_item', 'golden_crow']
  expect(state.config.rogue.blackflow_start_rewards).toBe(2049)
  state.config.rogue.blackflow_start_rewards = 3
  expect(component.blackflow_reward_values).toEqual(['unnumbered_item', 'survey_advance'])
})

it('preserves duplicate animal requirements and supports clearing either slot', () => {
  const component = setupOpening()
  component.set_animal(0, 'swaddled_cat')
  component.set_animal(1, 'swaddled_cat')
  expect(state.config.rogue.blackflow_start_animals).toEqual(['swaddled_cat', 'swaddled_cat'])
  component.set_animal(0, null)
  expect(state.config.rogue.blackflow_start_animals).toEqual(['swaddled_cat'])
})

it('localizes the mounted preparation run controls while preserving reward masks, animal requirements and recruit identities', async () => {
  state.config = reactive({
    maa_rg_theme: 'BlackFlow',
    rogue: {
      mode: 30003,
      squad: '特勤分队',
      roles: '坚不可摧',
      core_char: '机械师',
      core_char_list: [{ name: '机械师', use_support: true }],
      use_support: false,
      use_nonfriend_support: true,
      collectible_mode_squad: '堡垒战术分队',
      collectible_mode_roles: '稳扎稳打',
      collectible_mode_core_char_list: [{ name: '维什戴尔', use_support: false }],
      blackflow_start_animals: ['swaddled_cat', 'swaddled_cat'],
      blackflow_start_rewards: 2049,
      blackflow_start_reward_priority: ['golden_crow', 'unnumbered_item'],
      blackflow_start_utopia: true
    }
  })
  state.plan = reactive({ operators: [{ label: '机械师', value: '机械师' }] })
  const saved = JSON.parse(JSON.stringify(toRaw(state.config)))
  const root = node('root')
  app = renderer.createApp(Client)
  app.provide('mobile', ref(false))
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  const selectSnapshot = () =>
    all(root)
      .filter((element) => element.tag === 'select')
      .map((element) => ({
        value: element.props.value,
        options: element.children.map((option) => option.props.value)
      }))
  const before = selectSnapshot()
  for (const locale of ['zh-CN', 'en-US', 'ja-JP', 'zh-TW']) {
    i18n.global.locale.value = locale
    await nextTick()
    expect(text(root), locale).toContain(i18n.global.t('maaActivities.prepAnimals'))
    expect(text(root), locale).toContain(i18n.global.t('maaActivities.rewardPriorityHelp'))
    expect(text(root), locale).toContain(i18n.global.t('tasks.allowNonFriendSupport'))
    expect(selectSnapshot(), locale).toEqual(before)
    expect(state.config, locale).toEqual(saved)
    expect(blackflow_rewards.map(({ mask }) => mask)).toEqual(
      Array.from({ length: 12 }, (_, index) => 1 << index)
    )
    expect(blackflow_animals[0].value).toBe('swaddled_cat')
  }
  const rewards = all(root).find(
    (element) => element.tag === 'select' && element.props.value?.includes?.('unnumbered_item')
  )
  rewards.props.onChange(['survey_advance', 'golden_crow'])
  await nextTick()
  expect(state.config.rogue.blackflow_start_rewards).toBe(2050)
  expect(state.config.rogue.core_char_list).toEqual(saved.rogue.core_char_list)
})
