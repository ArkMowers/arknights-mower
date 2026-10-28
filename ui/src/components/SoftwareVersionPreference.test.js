import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, h, nextTick, ssrContextKey } from 'vue'
import { createPinia } from 'pinia'
import * as NaiveUI from 'naive-ui'
import axios from 'axios'
import { useGuiStore } from '@/stores/gui'
import { i18n } from '@/i18n'
import SoftwareVersionPreference from './SoftwareVersionPreference.vue'
import SoftwareVersionBadge from './SoftwareVersionBadge.vue'
import SettingsSegmented from './SettingsSegmented.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('naive-ui', async () => {
  const { defineComponent, Fragment, h } = await import('vue')
  const flatten = (nodes) =>
    nodes.flatMap((node) => (node.type === Fragment ? flatten(node.children) : [node]))
  const wrapper = defineComponent({
    inheritAttrs: false,
    setup:
      (_, { attrs, slots }) =>
      () =>
        h('div', attrs, [slots.label?.(), slots.default?.()])
  })
  return {
    NFormItem: wrapper,
    NAlert: wrapper,
    NIcon: wrapper,
    NTabs: defineComponent({
      inheritAttrs: false,
      props: { value: String, type: String, animated: Boolean, size: String },
      emits: ['update:value'],
      setup(props, { attrs, emit, slots }) {
        return () => {
          const tabs = flatten(slots.default?.() ?? [])
          return h(
            'select',
            {
              ...attrs,
              value: props.value,
              disabled: tabs.every((tab) => tab.props.disabled),
              'data-tabs-type': props.type,
              'data-tabs-animated': props.animated,
              onChange: (event) => {
                const selected = tabs.find((tab) => tab.props.name === event.target.value)
                if (selected && !selected.props.disabled) emit('update:value', event.target.value)
              }
            },
            tabs
          )
        }
      }
    }),
    NTab: defineComponent({
      props: { name: String, disabled: Boolean },
      setup:
        (props, { slots }) =>
        () =>
          h('option', { value: props.name, disabled: props.disabled }, slots.default?.())
    }),
    NButton: defineComponent({
      inheritAttrs: false,
      setup:
        (_, { attrs, slots }) =>
        () =>
          h('button', attrs, slots.default?.())
    }),
    NTooltip: defineComponent({
      setup:
        (_, { slots }) =>
        () =>
          slots.trigger?.()
    })
  }
})

function clientComponent(component, filename, components = {}) {
  const { descriptor } = parse(readFileSync(new URL(filename, import.meta.url), 'utf8'))
  return {
    ...component,
    components,
    ssrRender: undefined,
    render: compile(descriptor.template.content, { hoistStatic: false }),
    setup: (props, context) => ({ ...component.setup(props, context) })
  }
}

const ClientBadge = clientComponent(SoftwareVersionBadge, './SoftwareVersionBadge.vue', {
  ...NaiveUI
})
const ClientSegmented = clientComponent(SettingsSegmented, './SettingsSegmented.vue', {
  ...NaiveUI
})
const ClientPreference = clientComponent(
  SoftwareVersionPreference,
  './SoftwareVersionPreference.vue',
  { ...NaiveUI, SoftwareVersionBadge: ClientBadge, SettingsSegmented: ClientSegmented }
)
const mounted = []
const exampleVersions = {
  source: '4.1.6-alpha.12+8c3f2a1',
  alpha: '4.1.6-alpha.12',
  nightly: '4.1.6-alpha.12.g8c3f2a19',
  stable: '4.1.6'
}
const exampleKinds = ['source', 'alpha', 'nightly', 'stable']

function node(tag, text = '') {
  return { tag, text, props: {}, style: {}, children: [], parent: null }
}
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')

function visible(element) {
  for (let current = element; current; current = current.parent) {
    if ([true, 'true'].includes(current.props['aria-hidden'])) return false
  }
  return true
}

function expectBuildDiagram(page, mode, language = 'en') {
  const badges = page.badges()
  const labels = language === 'zh' ? ['源码部署', '公测版', '开发版', '正式版'] : exampleKinds
  expect(badges.map(text)).toEqual(
    mode === 'channel' ? labels : exampleKinds.map((kind) => exampleVersions[kind])
  )
  expect(badges.every((badge) => badge.props.disabled)).toBe(true)
  for (const [index, kind] of exampleKinds.entries()) {
    expect(badges[index].props['aria-pressed']).toBeUndefined()
    expect(badges[index].props.title).not.toContain('点击检查')
    expect(badges[index].props.class).toContain(`sidebar-brand-channel--${kind}`)
  }
  const diagram = page.nodes().find((element) => element.props.class === 'version-build-workflow')
  expect(diagram).toBeTruthy()
  const source = all(diagram).find((element) => element.props['data-version-kind'] === 'source')
  const targets = all(diagram).find((element) => element.props.class === 'version-workflow-targets')
  expect(targets).toBeTruthy()
  expect(targets.tag).not.toBe('ol')
  expect(all(targets)).not.toContain(source)
  const branches = all(targets).filter((element) => element.props['data-version-kind'])
  expect(branches.map((element) => element.props['data-version-kind'])).toEqual([
    'alpha',
    'nightly',
    'stable'
  ])
  expect(all(source)).toContain(badges[0])
  for (const [index, branch] of branches.entries()) expect(all(branch)).toContain(badges[index + 1])
  if (mode === 'channel') {
    for (const version of Object.values(exampleVersions))
      expect(text(diagram)).not.toContain(version)
  }
}

function deferred() {
  let resolve, reject
  const promise = new Promise((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, resolve, reject }
}

async function flush() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function mount(copies = 1) {
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
  const app = renderer.createApp({
    render: () =>
      h(
        'div',
        Array.from({ length: copies }, () => h(ClientPreference))
      )
  })
  const pinia = createPinia()
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  const gui = useGuiStore(pinia)
  const root = node('root')
  app.mount(root)
  mounted.push({ app, stores: [gui] })
  const find = (predicate) => {
    const element = all(root).find(predicate)
    expect(element).toBeTruthy()
    return element
  }
  return {
    gui,
    nodes: () => all(root),
    selector: () =>
      find((element) => element.tag === 'select' && element.props['aria-label'] === '软件版本显示'),
    languageSelector: () =>
      find((element) => element.tag === 'select' && element.props['aria-label'] === '版本类型语言'),
    badges: () =>
      all(root).filter(
        (element) =>
          element.tag === 'button' &&
          element.props.class?.includes('sidebar-brand-channel') &&
          visible(element)
      ),
    retry: () => find((element) => element.tag === 'button' && text(element).trim() === '重试')
  }
}

beforeEach(() => {
  axios.get.mockResolvedValue({ data: { software_version_display: 'version' } })
  axios.put.mockImplementation(async (_url, data) => ({ data }))
})

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
  for (const { app, stores } of mounted.splice(0)) {
    app.unmount()
    for (const store of stores) store.$dispose()
  }
  vi.resetAllMocks()
})

describe('software version preference with the build workflow preview', () => {
  it('updates a mounted interface while keeping the independently saved version type language', async () => {
    axios.get.mockResolvedValue({
      data: { software_version_display: 'channel', software_version_language: 'zh' }
    })
    const page = mount()
    await flush()
    expect(text(page.badges()[1])).toBe('公测版')

    i18n.global.locale.value = 'en-US'
    await nextTick()

    expect(text(page.nodes()[0])).toContain('Version type')
    expect(text(page.badges()[1])).toBe('公测版')
    expect(page.badges()[0].props.title).toContain('Started from source')
    expect(page.gui.softwareVersionLanguage).toBe('zh')
    expect(page.gui.softwareVersionDisplay).toBe('channel')
    expect(axios.put).not.toHaveBeenCalled()
    const language = page
      .nodes()
      .find(
        (element) =>
          element.tag === 'select' && element.props['aria-label'] === 'Version Type Language'
      )
    expect(language.props.value).toBe('zh')
    language.props.onChange({ target: { value: 'en' } })
    await flush()
    expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { software_version_language: 'en' },
      { timeout: 5000 }
    )
    expect(i18n.global.locale.value).toBe('en-US')
    expect(text(page.badges()[1])).toBe('alpha')
  })

  it('keeps the preview visible and its searchable language control inside the preview', async () => {
    const page = mount()
    await flush()
    const preview = page
      .nodes()
      .find((element) => element.props['aria-label'] === '软件版本显示预览')
    expect(preview).toBeTruthy()
    expect(page.nodes().some((element) => element.tag === 'details')).toBe(false)
    expect(all(preview)).toContain(page.languageSelector())
    expect(page.languageSelector().props['data-settings-label']).toBe('版本类型语言')
    expect(page.languageSelector().props['data-settings-keywords']).toContain('中文 English')
    expect(text(preview)).toContain('显示预览')
    expectBuildDiagram(page, 'version')
  })

  it('loads the saved mode and shows source with three independent build targets', async () => {
    const read = deferred()
    axios.get.mockReturnValueOnce(read.promise)
    const page = mount()
    expect(axios.get).toHaveBeenCalledOnce()
    expect(page.selector().props['data-tabs-type']).toBe('segment')
    expect(page.selector().props['data-tabs-animated']).toBe(true)
    expect(page.selector().props.disabled).toBe(true)
    expect(
      page
        .nodes()
        .filter((element) => element.tag === 'option')
        .map((tab) => Boolean(tab.props.disabled))
    ).toEqual([true, true, true, true])
    expectBuildDiagram(page, 'version')
    expect(
      page
        .nodes()
        .filter(
          (element) =>
            element.tag === 'button' && element.props.class?.includes('sidebar-brand-channel')
        )
    ).toHaveLength(4)
    expect(
      page.nodes().some((element) => element.props.class?.includes('sidebar-brand-resource'))
    ).toBe(false)
    expect(
      page
        .nodes()
        .some((element) => element.tag === 'option' && text(element).trim() === '版本类型')
    ).toBe(true)

    read.resolve({ data: { software_version_display: 'channel' } })
    await flush()
    expect(page.selector().props.value).toBe('channel')
    expect(page.selector().props.disabled).toBe(false)
    expect(
      page
        .nodes()
        .filter((element) => element.tag === 'option')
        .map((tab) => Boolean(tab.props.disabled))
    ).toEqual([false, false, false, false])
    expectBuildDiagram(page, 'channel')
    expect(page.badges()[0].props.title).toContain('源码启动')
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('updates the four read-only diagram labels while saving the shared selector choice', async () => {
    const page = mount()
    await flush()
    expectBuildDiagram(page, 'version')
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    page.selector().props.onChange({ target: { value: 'channel' } })
    await nextTick()
    expect(page.gui.softwareVersionDisplay).toBe('channel')
    expect(page.selector().props.value).toBe('channel')
    expectBuildDiagram(page, 'channel')
    expect(page.selector().props.disabled).toBe(true)
    expect(page.badges().every((badge) => badge.props.disabled)).toBe(true)
    expect(
      page
        .nodes()
        .some((element) => element.props.role === 'status' && text(element) === '正在保存…')
    ).toBe(true)
    expect(axios.put).toHaveBeenCalledOnce()

    save.resolve({ data: { software_version_display: 'channel' } })
    await flush()
    expect(page.selector().props.disabled).toBe(false)
    page.selector().props.onChange({ target: { value: 'version' } })
    await flush()
    expect(page.gui.softwareVersionDisplay).toBe('version')
    expect(page.selector().props.value).toBe('version')
    expectBuildDiagram(page, 'version')
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { software_version_display: 'channel' },
      { software_version_display: 'version' }
    ])
  })

  it('shows an initial read failure and retries before enabling edits', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const page = mount()
    await flush()
    expect(page.selector().props.disabled).toBe(true)
    expect(page.badges().every((badge) => badge.props.disabled)).toBe(true)
    expect(
      page
        .nodes()
        .some((element) => element.props.role === 'alert' && text(element).includes('读取失败'))
    ).toBe(true)
    expect(page.retry().props.disabled).toBe(false)
    page.retry().props.onClick()
    await flush()
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(page.selector().props.disabled).toBe(false)
    expect(page.badges().every((badge) => badge.props.disabled)).toBe(true)
    expect(page.nodes().some((element) => element.props.role === 'alert')).toBe(false)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('rolls back the selector and diagram labels after a failed save and retries the mode', async () => {
    const page = mount()
    await flush()
    expectBuildDiagram(page, 'version')
    axios.put.mockRejectedValueOnce(new Error('offline'))
    page.selector().props.onChange({ target: { value: 'channel' } })
    await flush()
    expect(page.gui.softwareVersionDisplay).toBe('version')
    expect(page.selector().props.value).toBe('version')
    expectBuildDiagram(page, 'version')
    expect(
      page
        .nodes()
        .some(
          (element) => element.props.role === 'alert' && text(element).includes('已恢复原来的显示')
        )
    ).toBe(true)
    page.retry().props.onClick()
    await flush()
    expect(page.selector().props.value).toBe('channel')
    expectBuildDiagram(page, 'channel')
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { software_version_display: 'channel' },
      { software_version_display: 'channel' }
    ])
    expect(page.nodes().some((element) => element.props.role === 'alert')).toBe(false)
  })

  it('shares one backend read and one preference between mounted settings copies', async () => {
    const page = mount(2)
    await flush()
    expect(axios.get).toHaveBeenCalledOnce()
    page.selector().props.onChange({ target: { value: 'channel' } })
    await flush()
    const selectors = page
      .nodes()
      .filter(
        (element) => element.tag === 'select' && element.props['aria-label'] === '软件版本显示'
      )
    const badges = page.badges()
    expect(selectors).toHaveLength(2)
    expect(badges).toHaveLength(8)
    expect(selectors.map((element) => element.props.value)).toEqual(['channel', 'channel'])
    expect(badges.map(text)).toEqual([...exampleKinds, ...exampleKinds])
    expect(axios.put).toHaveBeenCalledOnce()
  })

  it('translates the four version types with the update-channel names and preserves full versions', async () => {
    axios.get.mockResolvedValueOnce({
      data: { software_version_display: 'channel', software_version_language: 'en' }
    })
    const page = mount()
    await flush()
    const language = page.languageSelector()
    expect(language.children.map(text)).toEqual(['中文', 'English'])
    language.props.onChange({ target: { value: 'zh' } })
    await flush()
    expectBuildDiagram(page, 'channel', 'zh')
    expect(page.languageSelector().props.value).toBe('zh')
    expect(page.badges()[1].props.title).toContain('公测版')
    expect(axios.put).toHaveBeenLastCalledWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { software_version_language: 'zh' },
      { timeout: 5000 }
    )
    page.selector().props.onChange({ target: { value: 'version' } })
    await flush()
    expectBuildDiagram(page, 'version', 'zh')
    expect(page.gui.softwareVersionLanguage).toBe('zh')
    expect(text(page.nodes()[0])).not.toContain('选择侧栏显示版本号或版本类型')
  })

  it.each([
    ['en', 'zh'],
    ['zh', 'en']
  ])(
    'restores preview labels after a failed save from %s to %s and retries that choice',
    async (previous, requested) => {
      axios.get.mockResolvedValueOnce({
        data: { software_version_display: 'channel', software_version_language: previous }
      })
      const page = mount()
      await flush()
      axios.put.mockRejectedValueOnce(new Error('offline'))
      page.languageSelector().props.onChange({ target: { value: requested } })
      await flush()
      expectBuildDiagram(page, 'channel', previous)
      expect(page.languageSelector().props.value).toBe(previous)
      expect(page.nodes().some((element) => element.props.role === 'alert')).toBe(true)
      page.retry().props.onClick()
      await flush()
      expectBuildDiagram(page, 'channel', requested)
      expect(page.languageSelector().props.value).toBe(requested)
      expect(page.nodes().some((element) => element.props.role === 'alert')).toBe(false)
    }
  )
})
