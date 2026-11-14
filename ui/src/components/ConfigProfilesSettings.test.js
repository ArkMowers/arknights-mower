import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, createSSRApp, nextTick, reactive, ref, ssrContextKey } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { configProfilesKey, createConfigProfiles } from '@/composables/configProfiles'
import ConfigProfilesController from './ConfigProfilesController.vue'
import ConfigProfilesSettings from './ConfigProfilesSettings.vue'

vi.mock('naive-ui', async (original) => {
  const library = await original()
  const { defineComponent, h } = await import('vue')
  const wrapper = defineComponent({
    props: ['show', 'title', 'value', 'checked', 'indeterminate', 'disabled', 'contentStyle'],
    setup:
      (props, { slots }) =>
      () =>
        props.show === false
          ? null
          : h('section', { 'data-value': props.value }, [
              props.title,
              slots.default?.(),
              slots.footer?.(),
              slots.action?.()
            ])
  })
  return {
    ...library,
    ...Object.fromEntries(
      Object.keys(library)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, wrapper])
    )
  }
})

const { descriptor } = parse(
  readFileSync(new URL('./ConfigProfilesSettings.vue', import.meta.url), 'utf8')
)
const ClientSettings = {
  ...ConfigProfilesSettings,
  components: { NCard: 'section', NButton: 'button' },
  ssrRender: undefined,
  render: compile(descriptor.template.content, { hoistStatic: false }),
  setup: (props, context) => ({ ...ConfigProfilesSettings.setup(props, context) })
}
const mounted = []
const node = (tag, text = '') => ({ tag, text, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')

function mount(controller) {
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
        const siblings = element.parent.children
        siblings.splice(siblings.indexOf(element), 1)
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
  const app = renderer.createApp(ClientSettings)
  app.provide(ssrContextKey, { modules: new Set() })
  if (controller) app.provide(configProfilesKey, controller)
  const root = node('root')
  app.mount(root)
  mounted.push(app)
  return {
    text: () => text(root),
    button: (label) =>
      all(root).find((element) => element.tag === 'button' && text(element).trim() === label)
  }
}

afterEach(() => mounted.splice(0).forEach((app) => app.unmount()))

async function setup() {
  const events = []
  const config = reactive({
    autosave_paused: false,
    flush_config_saves: vi.fn(async () => events.push('config'))
  })
  const plan = reactive({
    autosave_paused: false,
    wait_for_plan_save: vi.fn(async () => events.push('plan'))
  })
  const axios = {
    defaults: { headers: { common: {} } },
    get: vi.fn(async () => ({
      data: {
        ok: true,
        active_id: 'first',
        generation: '0',
        busy: false,
        profiles: [{ id: 'first', name: '主账号' }],
        groups: [
          { key: 'device', label: '设备与游戏连接', section: '连接与运行' },
          { key: 'runtime', label: '运行参数', section: '连接与运行' },
          { key: 'inventory', label: '仓库库存', section: '数据' }
        ]
      }
    })),
    post: vi.fn(),
    patch: vi.fn()
  }
  const blocked = ref(false)
  const download = vi.fn(async () => events.push('download'))
  const controller = createConfigProfiles({
    axios,
    config,
    plan,
    blocked: () => blocked.value,
    download
  })
  await controller.bootstrap()
  const open = vi.spyOn(controller, 'open')
  return { controller, open, axios, config, blocked, download, events }
}

describe('settings configuration profile actions', () => {
  it('opens the existing profile import dialog with the same selectable groups', async () => {
    const { controller, open, axios } = await setup()
    const sections = controller.sections.value
    const page = mount(controller)
    expect(page.text()).toContain('主账号')
    page.button('导入档案').props.onClick()
    expect(open).toHaveBeenCalledExactlyOnceWith('import')
    expect(controller.dialog.value.action).toBe('import')
    expect(controller.sections.value).toBe(sections)
    expect(controller.selected.value).toEqual([])
    controller.toggleSection(sections[0], true)
    expect(controller.selected.value).toEqual(['device', 'runtime'])
    const html = await renderToString(createSSRApp(ConfigProfilesController, { controller }))
    expect(html).toContain('导入 ZIP 备份会创建一份新档案')
    expect(html).toContain('设备与游戏连接')
    expect(html).toContain('运行参数')
    expect(html).toContain('仓库库存')
    expect(axios.post).not.toHaveBeenCalled()
    expect(axios.get).toHaveBeenCalledExactlyOnceWith('/config-profiles')
  })

  it('exports through the shared profile flow after draining its save queues', async () => {
    const { controller, open, axios, download, events } = await setup()
    const page = mount(controller)
    await page.button('导出当前档案').props.onClick()
    expect(open).toHaveBeenCalledExactlyOnceWith('export')
    expect(events).toEqual(['config', 'plan', 'config', 'download'])
    expect(download).toHaveBeenCalledExactlyOnceWith(axios, '/config-profiles/export')
    expect(axios.post).not.toHaveBeenCalled()
  })

  it('shares write restrictions while allowing the existing read-only export', async () => {
    const { controller, blocked, open } = await setup()
    const page = mount(controller)
    blocked.value = true
    await nextTick()
    expect(page.button('导入档案').props.disabled).toBe(true)
    expect(page.button('导出当前档案').props.disabled).toBe(false)
    page.button('导入档案').props.onClick()
    expect(open).not.toHaveBeenCalled()
    controller.stale.value = true
    await nextTick()
    expect(page.button('导出当前档案').props.disabled).toBe(true)
    page.button('导出当前档案').props.onClick()
    expect(open).not.toHaveBeenCalled()
  })

  it('disables both actions with an explanation when no shared controller is provided', () => {
    const page = mount()
    expect(page.text()).toContain('档案管理尚未载入')
    for (const label of ['导入档案', '导出当前档案']) {
      expect(page.button(label).props.disabled).toBe(true)
      expect(() => page.button(label).props.onClick()).not.toThrow()
    }
  })
})
