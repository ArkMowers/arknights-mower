import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  defineComponent,
  getCurrentInstance,
  h,
  nextTick,
  reactive,
  ref,
  ssrContextKey
} from 'vue'
import { routeLocationKey } from 'vue-router'
import axios from 'axios'
import TaskWorkflow from './TaskWorkflow.vue'
import TaskConfiguration from './TaskConfiguration.vue'
import TaskChecklistNavigation from './TaskChecklistNavigation.vue'
import TaskSettingsPanels from '@/components/TaskSettingsPanels.vue'
import { i18n } from '@/i18n'

const state = vi.hoisted(() => ({
  config: null,
  gui: null,
  panels: [],
  reveals: []
}))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/gui', () => ({ useGuiStore: () => state.gui }))
vi.mock('axios', () => ({
  default: Object.fromEntries(
    ['get', 'post', 'patch', 'put', 'delete', 'request'].map((key) => [key, vi.fn()])
  )
}))
vi.mock('@/components/TaskSettingsPanels.vue', () => ({
  default: defineComponent({
    props: { active: String, checklist: Boolean, layout: String },
    emits: ['select'],
    setup(props, { emit, expose }) {
      const probe = { instance: getCurrentInstance(), draft: ref(''), revealActive: vi.fn() }
      expose({ revealActive: probe.revealActive })
      state.panels.push(probe)
      return () =>
        h(
          'section',
          {
            'data-active-editor': props.active,
            'data-checklist': props.checklist,
            'data-layout': props.layout
          },
          [
            h('input', {
              'aria-label': '本地草稿',
              value: probe.draft.value,
              onInput: (event) => (probe.draft.value = event.target.value)
            }),
            h(
              'button',
              { 'data-related-credit': '', onClick: () => emit('select', 'credit') },
              '访友与信用'
            ),
            h('a', { href: '#task-base' }, '排班设置'),
            h('section', { 'data-task-editor': 'idle' }, [
              h('span', { class: 'n-form-item-label' }, '任务结束后')
            ]),
            h('section', { 'data-task-editor': 'daily' }, [
              h('div', { 'data-task-editor': 'mail' }, [
                h('span', { class: 'n-form-item-label' }, '跳过清除已读')
              ])
            ]),
            h('section', { 'data-task-editor': 'credit' }, [
              props.active === 'shop' && state.config.maa_mall_mode === 'mower'
                ? h('div', { 'data-task-editor': 'shop' }, [
                    h('span', { class: 'n-form-item-label' }, '按需领取信用')
                  ])
                : null
            ])
          ]
        )
    }
  })
}))

function clientComponent(component, filename) {
  const { descriptor } = parse(readFileSync(new URL(filename, import.meta.url), 'utf8'))
  return {
    ...component,
    ssrRender: undefined,
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context) })
  }
}
const ClientWorkflow = clientComponent(TaskWorkflow, './TaskWorkflow.vue')
const ClientConfiguration = clientComponent(TaskConfiguration, './TaskConfiguration.vue')
const ClientChecklist = clientComponent(TaskChecklistNavigation, './TaskChecklistNavigation.vue')
const NInput = defineComponent({
  props: ['value', 'inputProps'],
  emits: ['update:value'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        ...props.inputProps,
        value: props.value,
        onInput: (event) => emit('update:value', event.target.value)
      })
  }
})
const NIcon = defineComponent({
  props: ['component'],
  setup: () => () => h('span', { 'data-ui-icon': '' })
})
const NPopover = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('span', slots.trigger?.())
})
let app
let root

function hostNode(tag, text = '') {
  return {
    tag,
    text,
    props: {},
    children: [],
    parent: null,
    style: {},
    focus: vi.fn(),
    getAttribute(key) {
      return this.props[key]
    },
    get textContent() {
      return this.text + this.children.map((node) => node.textContent).join('')
    },
    querySelectorAll(selector) {
      return nodes(this)
        .slice(1)
        .filter((node) =>
          selector === '[data-task-editor]'
            ? node.props['data-task-editor']
            : node.props.class === 'n-form-item-label'
        )
    },
    closest(selector) {
      for (let node = this; node; node = node.parent) {
        if (selector === '.task-workspace' && String(node.props.class).includes('task-workspace'))
          return node
        if (
          selector === 'a[href^="#"]' &&
          node.tag === 'a' &&
          node.props.href?.startsWith('#task-')
        )
          return node
      }
      return null
    }
  }
}
async function flush() {
  await nextTick()
  await nextTick()
}
async function mount(hash = '', queue = []) {
  const renderer = createRenderer({
    createElement: (tag) => hostNode(tag),
    createText: (text) => hostNode('#text', text),
    createComment: (text) => hostNode('#comment', text),
    setText: (node, text) => (node.text = text),
    setElementText(node, text) {
      node.text = text
      node.children = []
    },
    parentNode: (node) => node.parent,
    nextSibling: (node) => node.parent?.children[node.parent.children.indexOf(node) + 1] ?? null,
    patchProp(node, key, _previous, value) {
      if (key.startsWith('.')) node[key.slice(1)] = value
      else node.props[key] = value
    },
    insert(node, parent, anchor = null) {
      if (node.parent) {
        const siblings = node.parent.children
        siblings.splice(siblings.indexOf(node), 1)
      }
      node.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
    },
    remove(node) {
      const siblings = node.parent?.children
      if (siblings) siblings.splice(siblings.indexOf(node), 1)
      node.parent = null
    }
  })
  const route = reactive({ hash })
  const queueState = ref(queue)
  let configuration
  app = renderer.createApp(
    defineComponent({
      setup: () => () =>
        h(ClientConfiguration, {
          ref: (instance) => (configuration = instance),
          queue: queueState.value,
          onReveal: () => state.reveals.push(route.hash)
        })
    })
  )
  app.provide(ssrContextKey, { modules: new Set() })
  app.provide(routeLocationKey, route)
  app.component('TaskWorkflow', ClientWorkflow)
  app.component('TaskChecklistNavigation', ClientChecklist)
  app.component('TaskSettingsPanels', TaskSettingsPanels)
  app.component('NInput', NInput)
  app.component('NIcon', NIcon)
  app.component('NPopover', NPopover)
  root = hostNode('root')
  app.mount(root)
  await flush()
  return {
    route,
    async openEditor(id) {
      configuration.openEditor(id)
      await flush()
    },
    async setQueue(value) {
      queueState.value = value
      await flush()
    }
  }
}
function nodes(node = root) {
  return [node, ...node.children.flatMap((child) => nodes(child))]
}
function find(predicate) {
  const node = nodes().find(predicate)
  expect(node).toBeTruthy()
  return node
}
function text(node) {
  return node.text + node.children.map(text).join('')
}
async function click(node) {
  const event = { target: node, preventDefault: vi.fn() }
  for (let current = node; current; current = current.parent) current.props.onClick?.(event)
  await flush()
  return event
}
function row(id) {
  return find((node) => node.props['data-task-id'] === id)
}
function task(id) {
  return nodes(row(id)).find((node) => node.tag === 'button')
}
function checkbox(id) {
  return nodes(row(id)).find((node) => node.props.type === 'checkbox')
}
function selected() {
  return find((node) => node.props['data-active-editor'] !== undefined).props['data-active-editor']
}
function heading() {
  return find((node) => node.props.class === 'checklist-mobile-toggle')
}
function visibleTasks() {
  return nodes()
    .filter((node) => node.props['data-task-id'])
    .map((node) => node.props['data-task-id'])
}
function searchInput() {
  return find((node) => node.props['aria-label'] === '查找设置')
}
async function search(value) {
  searchInput().props.onInput({ target: { value } })
  await flush()
}
async function check(id, value) {
  checkbox(id).props.onChange({ target: { checked: value } })
  await flush()
}

const switches = {
  clue: 'enable_party',
  training: 'enable_mastery',
  trust: 'trust_rotation_enable',
  skland: 'skland_enable',
  mail: 'check_mail_enable',
  'event-sign-in': 'event_sign_in_enable',
  report: 'report_enable',
  recruit: 'recruit_enable',
  depot: 'maa_depot_enable',
  visit: 'visit_friend_enable',
  'credit-fight': 'maa_credit_fight',
  shop: 'maa_mall_enable',
  'stage-plan': 'stage_plan_enable',
  long: 'maa_rg_enable'
}
beforeEach(() => {
  state.gui = reactive({ taskSettingsLayout: 'checklist' })
  state.config = reactive({
    ...Object.fromEntries(Object.values(switches).map((key) => [key, false])),
    maa_rg_enable: 0,
    theme: 'light',
    maa_long_task_type: 'sf',
    stage_plan_runner: 'mower',
    visit_friend_mode: 'mower',
    maa_mall_mode: 'maa',
    maa_gap: 3,
    drone_interval: 4,
    recruit_gap: 9,
    trust_rotation_interval: 24,
    drone_room: 'room_1_1',
    automatic_rescue_enable: true,
    workshop_manual_settings: [{ enabled: true, operator: '九色鹿' }],
    maa_mail: false,
    maa_recruit: true,
    maa_orundum: false,
    maa_mining: false,
    maa_specialaccess: false,
    maa_signinevent: false
  })
  state.panels = []
  state.reveals = []
})
afterEach(() => {
  app?.unmount()
  app = null
  vi.clearAllMocks()
  i18n.global.locale.value = 'zh-CN'
})

describe('production task checklist interactions', () => {
  it('updates mounted English directory text and searches without replacing drafts or saving configuration', async () => {
    await mount()
    const before = JSON.stringify(state.config)
    const panel = state.panels[0]
    panel.draft.value = 'unsaved device draft'
    expect(text(task('recruit'))).toBe('公开招募')

    i18n.global.locale.value = 'en-US'
    await flush()

    expect(text(task('recruit'))).toBe('Recruitment')
    expect(text(heading())).toBe('Automatic rescue')
    expect(find((node) => node.props['aria-label'] === 'Enable Recruitment').props.checked).toBe(
      false
    )
    const input = find((node) => node.props['aria-label'] === 'Search settings')
    input.props.onInput({ target: { value: '5-star recruitment' } })
    await flush()
    expect(visibleTasks()).toEqual(['recruit'])
    await click(task('recruit'))
    expect(selected()).toBe('recruit')
    expect(state.panels).toHaveLength(1)
    expect(panel.draft.value).toBe('unsaved device draft')
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of ['get', 'post', 'patch', 'put', 'delete', 'request'])
      expect(axios[method]).not.toHaveBeenCalled()
  })
  it.each(['checklist', 'waterfall'])(
    'omits managed connection navigation in %s layout',
    async (layout) => {
      state.config.manager_owned_device = true
      state.gui.taskSettingsLayout = layout
      await mount('#task-devices')
      expect(selected()).toBe('base')
      expect(nodes().find((node) => node.props['aria-label'] === '配置连接与启动')).toBeUndefined()
      await search('任务结束后')
      expect(nodes().find((node) => node.props['aria-label'] === '配置连接与启动')).toBeUndefined()
      state.config.manager_owned_device = false
      await nextTick()
      await search('')
      await click(find((node) => node.props['aria-label'] === '配置连接与启动'))
      expect(selected()).toBe('device')
      state.config.manager_owned_device = true
      await nextTick()
      expect(selected()).toBe('base')
    }
  )

  it('opens base scheduling with persistent panels and concise names without gear buttons or automatic labels', async () => {
    await mount()
    expect(selected()).toBe('base')
    expect(text(heading())).toBe('自动救急')
    expect(
      find((node) => node.props['data-active-editor'] !== undefined).props['data-checklist']
    ).toBe(false)
    const navigation = find((node) => node.tag === 'nav')
    for (const label of ['连接与启动', '基建任务', '日常任务', '作战与空闲', '运行配置'])
      expect(text(navigation)).toContain(label)
    expect(
      nodes(navigation).filter((node) => node.props['data-ui-icon'] !== undefined)
    ).toHaveLength(2)
    expect(nodes(navigation).filter((node) => node.tag === 'small')).toHaveLength(0)
    expect(nodes(navigation).some((node) => node.text.trim() === '自动')).toBe(false)
    for (const button of nodes(navigation).filter((node) => node.tag === 'button'))
      expect(text(button).trim() || button.props['aria-label']).toBeTruthy()
    for (const id of ['base', 'runorder', 'drone', 'workshop']) expect(checkbox(id)).toBeUndefined()
    expect(checkbox('training')).toBeTruthy()
    expect(checkbox('rewards')).toBeTruthy()
  })

  it('selects disabled tasks by name without saving configuration or closing the selected editor', async () => {
    await mount()
    const before = JSON.stringify(state.config)
    await click(task('recruit'))
    expect(selected()).toBe('recruit')
    expect(text(heading())).toBe('公开招募')
    expect(task('recruit').props['aria-pressed']).toBe(true)
    expect(checkbox('recruit').props.checked).toBe(false)
    await click(task('recruit'))
    expect(selected()).toBe('recruit')
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('updates the reward DOM checkbox through partial, all and empty selections without selecting a card', async () => {
    await mount()
    const input = checkbox('rewards')
    const before = { ...state.config }
    expect(input.props.checked).toBe(false)
    expect(input.indeterminate).toBe(true)
    expect(input.props['aria-checked']).toBe('mixed')
    await check('rewards', true)
    expect(input.props.checked).toBe(true)
    expect(input.indeterminate).toBe(false)
    expect(input.props['aria-checked']).toBe(true)
    expect(selected()).toBe('base')
    state.config.maa_mail = false
    await flush()
    expect(input.indeterminate).toBe(true)
    expect(input.props['aria-checked']).toBe('mixed')
    await check('rewards', false)
    expect(input.props.checked).toBe(false)
    expect(input.indeterminate).toBe(false)
    expect(input.props['aria-checked']).toBe(false)
    expect(state.config).toEqual({ ...before, maa_recruit: false })
    expect(selected()).toBe('base')
    expect(state.reveals).toEqual([])
    expect(nodes().some((node) => node.focus.mock.calls.length)).toBe(false)
  })

  it('opens the compact directory and closes it after selecting an entry while retaining drafts and switches', async () => {
    const page = await mount()
    const before = JSON.stringify(state.config)
    const panels = state.panels[0]
    find((node) => node.props['aria-label'] === '本地草稿').props.onInput({
      target: { value: '未保存的设备地址' }
    })
    const toggle = () => find((node) => node.props.class === 'checklist-mobile-toggle')
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(toggle().props['aria-label']).toBe('选择配置：自动救急')
    const contentId = toggle().props['aria-controls']
    expect(find((node) => node.props.id === contentId).props.class).toBe('checklist-content')
    await click(toggle())
    expect(toggle().props['aria-expanded']).toBe(true)
    await click(task('recruit'))
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(toggle().props['aria-label']).toBe('选择配置：公开招募')
    expect(toggle().focus).toHaveBeenCalledWith({ preventScroll: true })
    expect(selected()).toBe('recruit')
    await click(toggle())
    await click(task('recruit'))
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(toggle().focus).toHaveBeenCalledTimes(2)
    await click(toggle())
    await click(find((node) => node.props['aria-label'] === '配置连接与启动'))
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(toggle().props['aria-label']).toBe('选择配置：连接与启动')
    await click(toggle())
    await page.openEditor('runtime')
    expect(toggle().props['aria-expanded']).toBe(false)
    expect(toggle().props['aria-label']).toBe('选择配置：运行参数')
    expect(state.panels).toEqual([panels])
    expect(find((node) => node.props['aria-label'] === '本地草稿').props.value).toBe(
      '未保存的设备地址'
    )
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it.each(Object.entries(switches))(
    'changes only the real flag for %s without changing selection',
    async (id, key) => {
      await mount()
      const before = JSON.parse(JSON.stringify(state.config))
      await check(id, true)
      expect(state.config).toEqual({ ...before, [key]: id === 'long' ? 1 : true })
      expect(selected()).toBe('base')
      expect(checkbox(id).props.checked).toBe(true)
      await check(id, false)
      expect(state.config).toEqual(before)
      expect(selected()).toBe('base')
    }
  )

  it('returns directory focus to its visible toggle after selecting runtime settings', async () => {
    await mount()
    const toggle = find((node) => node.props.class === 'checklist-mobile-toggle')
    await click(toggle)
    await click(task('runtime'))
    expect(toggle.props['aria-expanded']).toBe(false)
    expect(toggle.focus).toHaveBeenCalledWith({ preventScroll: true })
    expect(selected()).toBe('runtime')
  })

  it('folds and restores the waterfall directory without replacing its search, selection or editor draft', async () => {
    state.gui.taskSettingsLayout = 'waterfall'
    await mount()
    await search('截图')
    await click(task('runtime'))
    const panels = state.panels[0]
    const input = searchInput()
    const draft = find((node) => node.props['aria-label'] === '本地草稿')
    draft.props.onInput({ target: { value: '未保存的截图设置' } })
    await flush()
    const navigation = find((node) => node.tag === 'nav')
    const toggle = find((node) => node.props.class === 'checklist-desktop-toggle')
    const directory = find((node) => node.props.id === toggle.props['aria-controls'])
    const workspace = find((node) => node.props.class?.split(' ').includes('task-workspace'))
    const before = JSON.stringify({ config: state.config, gui: state.gui })
    const revealCount = panels.revealActive.mock.calls.length
    expect(toggle.props['aria-expanded']).toBe(true)
    expect(toggle.props['aria-label']).toBe('收起配置导航')
    expect(directory.props.class).toBe('checklist-content')
    expect(workspace.props.class.split(' ')).not.toContain('task-workspace--navigation-collapsed')

    await click(toggle)
    expect(workspace.props.class.split(' ')).toContain('task-workspace--navigation-collapsed')
    expect(navigation.props.class.split(' ')).toContain('is-collapsed')
    expect(toggle.props['aria-expanded']).toBe(false)
    expect(toggle.props['aria-label']).toBe('展开配置导航')
    expect(find((node) => node.props.id === toggle.props['aria-controls'])).toBe(directory)
    await click(toggle)
    expect(workspace.props.class.split(' ')).not.toContain('task-workspace--navigation-collapsed')
    expect(navigation.props.class.split(' ')).not.toContain('is-collapsed')
    expect(toggle.props['aria-expanded']).toBe(true)
    expect(toggle.props['aria-label']).toBe('收起配置导航')
    expect(find((node) => node.props.class === 'checklist-desktop-toggle')).toBe(toggle)
    expect(searchInput()).toBe(input)
    expect(input.props.value).toBe('截图')
    expect(selected()).toBe('runtime')
    expect(task('runtime').props['aria-pressed']).toBe(true)
    expect(nodes().some((node) => node.props['aria-label'] === '配置分类')).toBe(false)
    expect(find((node) => node.props['aria-label'] === '本地草稿')).toBe(draft)
    expect(draft.props.value).toBe('未保存的截图设置')
    expect(state.panels).toEqual([panels])
    expect(panels.revealActive).toHaveBeenCalledTimes(revealCount)
    expect(JSON.stringify({ config: state.config, gui: state.gui })).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('keeps continuous settings and a folded directory when an obsolete layout preference changes', async () => {
    await mount()
    await search('公招')
    await click(task('recruit'))
    const panels = state.panels[0]
    const input = searchInput()
    const workspace = find((node) => node.props.class?.split(' ').includes('task-workspace'))
    await click(find((node) => node.props.class === 'checklist-desktop-toggle'))
    for (const layout of ['checklist', 'waterfall']) {
      state.gui.taskSettingsLayout = layout
      await flush()
      expect(workspace.props.class.split(' ')).toContain('task-workspace--navigation-collapsed')
      expect(searchInput()).toBe(input)
      expect(input.props.value).toBe('公招')
      expect(selected()).toBe('recruit')
      expect(state.panels).toEqual([panels])
    }
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('keeps the mobile directory disclosure independent of the desktop waterfall fold', async () => {
    state.gui.taskSettingsLayout = 'waterfall'
    await mount()
    const desktopToggle = find((node) => node.props.class === 'checklist-desktop-toggle')
    const mobileToggle = find((node) => node.props.class === 'checklist-mobile-toggle')
    await click(desktopToggle)
    expect(desktopToggle.props['aria-expanded']).toBe(false)
    expect(mobileToggle.props['aria-expanded']).toBe(false)
    await click(mobileToggle)
    expect(mobileToggle.props['aria-expanded']).toBe(true)
    expect(desktopToggle.props['aria-expanded']).toBe(false)
    await search('公招')
    await click(task('recruit'))
    expect(mobileToggle.props['aria-expanded']).toBe(false)
    expect(desktopToggle.props['aria-expanded']).toBe(false)
    expect(selected()).toBe('recruit')
    await click(mobileToggle)
    await click(desktopToggle)
    expect(desktopToggle.props['aria-expanded']).toBe(true)
    expect(mobileToggle.props['aria-expanded']).toBe(true)
    expect(searchInput().props.value).toBe('公招')
  })

  it('omits global select and clear actions while keeping individual task controls', async () => {
    await mount()
    expect(nodes().some((node) => node.props['aria-label'] === '批量启用任务')).toBe(false)
    expect(
      nodes().some((node) => node.tag === 'button' && ['全选', '清空'].includes(text(node)))
    ).toBe(false)
    await check('recruit', false)
    expect(state.config.recruit_enable).toBe(false)
    expect(state.config.workshop_manual_settings[0].enabled).toBe(true)
  })

  it('uses noninteractive group headings and a separate interval editor while retaining legacy destinations', async () => {
    const page = await mount()
    const before = JSON.stringify(state.config)
    for (const title of ['基建任务', '日常任务', '作战与空闲']) {
      const groupHeading = find((node) => node.tag === 'h3' && text(node) === title)
      await click(groupHeading)
      expect(selected()).toBe('base')
      expect(nodes(groupHeading).some((node) => node.tag === 'button')).toBe(false)
      expect(nodes().some((node) => node.props['aria-label'] === `配置${title}`)).toBe(false)
    }
    await click(task('intervals'))
    expect(selected()).toBe('intervals')
    expect(text(heading())).toBe('执行间隔')
    expect(checkbox('intervals')).toBeUndefined()
    await click(find((node) => node.tag === 'h3' && text(node) === '运行配置'))
    expect(selected()).toBe('intervals')
    await click(find((node) => node.props['aria-label'] === '配置连接与启动'))
    expect(selected()).toBe('device')
    expect(text(heading())).toBe('连接与启动')
    await page.openEditor('credit')
    expect(selected()).toBe('credit')
    expect(text(heading())).toBe('访友与信用')
    await page.openEditor('idle')
    expect(selected()).toBe('idle')
    expect(
      find((node) => node.props['aria-label'] === '配置连接与启动').props['aria-pressed']
    ).toBe(true)
    expect(JSON.stringify(state.config)).toBe(before)
  })

  it('shows task, runtime and Mower settings together and searches without replacing drafts', async () => {
    const page = await mount()
    const before = JSON.stringify(state.config)
    const panels = state.panels[0]
    await click(task('recruit'))
    find((node) => node.props['aria-label'] === '本地草稿').props.onInput({
      target: { value: '未保存的设备地址' }
    })
    expect(visibleTasks()).toEqual(
      expect.arrayContaining([
        'recruit',
        'intervals',
        'runtime',
        'accounts',
        'maa',
        'mower-interface',
        'mower-profiles',
        'mower-data'
      ])
    )
    expect(nodes().some((node) => node.props['aria-label'] === '配置分类')).toBe(false)
    await click(task('accounts'))
    await click(task('mower-profiles'))
    expect(selected()).toBe('mower-profiles')
    expect(text(heading())).toBe('档案与运行')
    await click(task('mower-interface'))
    expect(selected()).toBe('mower-interface')
    await search('公招')
    expect(visibleTasks()).toEqual(['recruit'])
    await click(task('recruit'))
    await page.openEditor('maa')
    expect(searchInput().props.value).toBe('')
    expect(visibleTasks()).toContain('mower-data')
    expect(state.panels).toEqual([panels])
    expect(find((node) => node.props['aria-label'] === '本地草稿').props.value).toBe(
      '未保存的设备地址'
    )
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('retains the same panels instance and local draft across task, interval and connection selections', async () => {
    const page = await mount()
    const panels = state.panels[0]
    find((node) => node.props['aria-label'] === '本地草稿').props.onInput({
      target: { value: '未保存的设备地址' }
    })
    await click(task('recruit'))
    await click(task('intervals'))
    await click(find((node) => node.props['aria-label'] === '配置连接与启动'))
    await page.openEditor('base')
    expect(state.panels).toHaveLength(1)
    expect(state.panels[0]).toBe(panels)
    expect(find((node) => node.props['aria-label'] === '本地草稿').props.value).toBe(
      '未保存的设备地址'
    )
  })

  it('retains the device editor and unsaved draft independently of the retired layout preference', async () => {
    const page = await mount()
    await click(find((node) => node.props['aria-label'] === '配置连接与启动'))
    const panels = state.panels[0]
    find((node) => node.props['aria-label'] === '本地草稿').props.onInput({
      target: { value: '未保存的设备地址' }
    })
    const before = JSON.stringify(state.config)
    for (const layout of ['waterfall', 'checklist']) {
      state.gui.taskSettingsLayout = layout
      await flush()
      expect(selected()).toBe('device')
      expect(state.panels).toEqual([panels])
      expect(find((node) => node.props['aria-label'] === '本地草稿').props.value).toBe(
        '未保存的设备地址'
      )
      expect(JSON.stringify(state.config)).toBe(before)
      expect(page.route.hash).toBe('')
    }
  })

  it('keeps current configuration selected when polling replaces or clears queued tasks', async () => {
    const queue = [{ time: '2026-10-21T12:00:00', type: { value: 'recruit' } }]
    const before = JSON.stringify(queue)
    const page = await mount('', queue)
    await click(task('recruit'))
    const panels = state.panels[0]
    await page.setQueue([{ time: '2026-10-21T12:01:00', type: { value: 'run_order' } }, ...queue])
    expect(selected()).toBe('recruit')
    await page.setQueue([])
    expect(selected()).toBe('recruit')
    expect(state.panels).toEqual([panels])
    expect(JSON.stringify(queue)).toBe(before)
  })

  it('reveals the same waterfall destination on each explicit related link and legacy link click', async () => {
    await mount()
    const panels = state.panels[0]
    const before = JSON.stringify(state.config)
    state.gui.taskSettingsLayout = 'waterfall'
    await flush()
    const related = find((node) => node.props['data-related-credit'] !== undefined)
    for (let count = 1; count <= 2; count += 1) {
      await click(related)
      expect(selected()).toBe('credit')
      expect(panels.revealActive).toHaveBeenCalledTimes(count)
    }
    const legacy = find((node) => node.tag === 'a' && node.props.href === '#task-base')
    for (let count = 3; count <= 4; count += 1) {
      const event = await click(legacy)
      expect(event.preventDefault).toHaveBeenCalledOnce()
      expect(selected()).toBe('base')
      expect(panels.revealActive).toHaveBeenCalledTimes(count)
    }
    expect(state.panels).toEqual([panels])
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('searches and repeatedly reveals waterfall entries without saving or replacing editors', async () => {
    await mount()
    const before = JSON.stringify(state.config)
    const panels = state.panels[0]
    find((node) => node.props['aria-label'] === '本地草稿').props.onInput({
      target: { value: '未保存的设备地址' }
    })
    state.gui.taskSettingsLayout = 'waterfall'
    await flush()
    await search('公招')
    expect(visibleTasks()).toEqual(['recruit'])
    expect(selected()).toBe('base')
    for (let count = 1; count <= 2; count += 1) {
      await click(task('recruit'))
      expect(selected()).toBe('recruit')
      expect(panels.revealActive).toHaveBeenCalledTimes(count)
    }
    await search('')
    await click(task('intervals'))
    expect(selected()).toBe('intervals')
    expect(visibleTasks()).toEqual(
      expect.arrayContaining([
        'recruit',
        'intervals',
        'runtime',
        'accounts',
        'maa',
        'mower-interface',
        'mower-notifications',
        'mower-profiles',
        'mower-updates',
        'mower-data'
      ])
    )
    expect(panels.revealActive).toHaveBeenCalledTimes(3)
    for (const id of ['runtime', 'accounts', 'maa']) {
      await click(task(id))
      expect(selected()).toBe(id)
    }
    expect(panels.revealActive).toHaveBeenCalledTimes(6)
    await search('不存在的任务')
    expect(visibleTasks()).toEqual([])
    expect(selected()).toBe('maa')
    expect(state.panels).toEqual([panels])
    expect(find((node) => node.props['aria-label'] === '本地草稿').props.value).toBe(
      '未保存的设备地址'
    )
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('searches the public-recruitment alias and clears an incompatible query for an external editor request', async () => {
    const page = await mount()
    await search('公招')
    expect(visibleTasks()).toEqual(['recruit'])
    expect(selected()).toBe('base')
    await page.openEditor('long')
    expect(selected()).toBe('long')
    expect(searchInput().props.value).toBe('')
    expect(visibleTasks()).toContain('long')
  })

  it.each([
    [' MAA   奖励 ', 'rewards'],
    ['ＭＡＡ　奖励', 'rewards'],
    ['截图 超时', 'runtime'],
    ['葛朗台 缓冲', 'runorder'],
    ['活动 补领', 'event-sign-in'],
    ['肉鸽 分队', 'long'],
    ['理智 药', 'stage-plan'],
    ['跳过清除已读', 'mail'],
    ['按需领取信用', 'shop'],
    ['按性价比购物', 'shop'],
    ['五星词条组合唯一时自动选择', 'recruit'],
    ['导能单元', 'long'],
    ['单次最大组装轮数', 'long'],
    ['关卡体力默认值', 'stage-plan'],
    ['支援 机械', 'recruit']
  ])('finds real fields across directories with %s without saving', async (query, id) => {
    await mount()
    const before = JSON.stringify(state.config)
    await search(query)
    expect(visibleTasks()).toContain(id)
    await click(task(id))
    expect(selected()).toBe(id)
    expect(JSON.stringify(state.config)).toBe(before)
    for (const method of Object.values(axios)) expect(method).not.toHaveBeenCalled()
  })

  it('finds connection settings across directories without reporting an empty result', async () => {
    const page = await mount('#task-runtime')
    for (const query of ['设备', '启动', 'ADB', '任务结束后', '启动命令', '旋转截图']) {
      await search(query)
      const connection = find((node) => node.props['aria-label'] === '配置连接与启动')
      expect(connection.parent.style.display).not.toBe('none')
      expect(text(root)).not.toContain('没有找到匹配的功能')
      await click(connection)
      expect(selected()).toBe('device')
    }
    await page.openEditor('base')
    expect(searchInput().props.value).toBe('')
  })

  it('reveals the selected card without resetting a separate content scroll pane', async () => {
    await mount()
    const panels = state.panels[0]
    await click(task('recruit'))
    expect(panels.revealActive).toHaveBeenCalled()
    expect(selected()).toBe('recruit')
    expect(nodes().some((node) => node.props.class === 'inspector-heading')).toBe(false)
  })

  it('shows an empty search result without changing selection and repeats external requests for the same editor', async () => {
    const page = await mount()
    await search('不存在的任务')
    expect(visibleTasks()).toEqual([])
    expect(text(root)).toContain('没有找到匹配的功能')
    expect(selected()).toBe('base')
    await page.openEditor('base')
    expect(searchInput().props.value).toBe('')
    expect(visibleTasks()).toContain('base')
    expect(selected()).toBe('base')
    await page.openEditor('unknown')
    expect(selected()).toBe('base')
    expect(state.reveals).toHaveLength(1)
  })

  it('follows changing legacy hashes, related shared settings and in-panel hash links without saves', async () => {
    const page = await mount('#task-runtime')
    const before = JSON.stringify(state.config)
    expect(selected()).toBe('runtime')
    page.route.hash = '#task-long'
    await flush()
    expect(selected()).toBe('long')
    await click(find((node) => node.props['data-related-credit'] !== undefined))
    expect(selected()).toBe('credit')
    const event = await click(find((node) => node.tag === 'a' && node.props.href === '#task-base'))
    expect(event.preventDefault).toHaveBeenCalledOnce()
    expect(selected()).toBe('base')
    expect(page.route.hash).toBe('#task-long')
    expect(JSON.stringify(state.config)).toBe(before)
  })

  it('omits the queue shortcut while selecting task parameters without changing configuration', async () => {
    await mount()
    await click(task('drone'))
    const before = JSON.stringify(state.config)
    expect(text(root)).not.toContain('查看待执行任务')
    expect(selected()).toBe('drone')
    expect(JSON.stringify(state.config)).toBe(before)
  })
})
