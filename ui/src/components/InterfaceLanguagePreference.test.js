import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { createPinia, disposePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { compile, createRenderer, defineComponent, h, nextTick, ssrContextKey } from 'vue'
import axios from 'axios'
import { NDropdown } from 'naive-ui'
import { i18n, getInterfaceLanguageOptions } from '@/i18n'
import { useGuiStore } from '@/stores/gui'
import Preference from './InterfaceLanguagePreference.vue'
import AppMenuBar from './AppMenuBar.vue'

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
vi.mock('naive-ui', async (original) => {
  const { defineComponent, h } = await import('vue')
  return {
    ...(await original()),
    NDropdown: defineComponent({
      props: ['options'],
      emits: ['select'],
      setup:
        (props, { emit, slots }) =>
        () =>
          h(
            'menu',
            {
              options: props.options,
              onSelect: (option) => emit('select', option.key, option)
            },
            slots.default?.()
          )
    })
  }
})

const { descriptor } = parse(
  readFileSync(new URL('./InterfaceLanguagePreference.vue', import.meta.url), 'utf8')
)
const clientPreference = {
  ...Preference,
  ssrRender: undefined,
  render: compile(descriptor.template.content),
  setup: (props, context) => ({ ...Preference.setup(props, context) })
}
const menuDescriptor = parse(
  readFileSync(new URL('./AppMenuBar.vue', import.meta.url), 'utf8')
).descriptor
const clientMenu = {
  ...AppMenuBar,
  components: { NDropdown },
  ssrRender: undefined,
  render: compile(menuDescriptor.template.content),
  setup: (props, context) => ({ ...AppMenuBar.setup(props, context) })
}
const node = (tag, value = '') => ({ tag, text: value, props: {}, children: [], parent: null })
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const mounted = []

function mount(copies = 1, withMenu = false) {
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
      h('div', [
        ...Array.from({ length: copies }, () => h(clientPreference)),
        ...(withMenu
          ? [
              h(clientMenu, {
                interfaceLanguage: gui.interfaceLanguage,
                languageDisabled: gui.interfaceLanguageDisabled,
                'onView-action': (action) =>
                  gui.setInterfaceLanguage(action.slice('language:'.length))
              })
            ]
          : [])
      ])
  })
  const pinia = createPinia()
  app.use(pinia)
  app.provide(ssrContextKey, { modules: new Set() })
  app.component('NFormItem', {
    props: { label: String },
    setup:
      (props, { attrs, slots }) =>
      () =>
        h('div', attrs, [h('label', props.label), slots.default?.()])
  })
  app.component(
    'NSelect',
    defineComponent({
      props: { value: String, options: Array, disabled: Boolean, loading: Boolean },
      emits: ['update:value'],
      setup:
        (props, { attrs, emit }) =>
        () =>
          h(
            'select',
            {
              ...attrs,
              value: props.value,
              disabled: props.disabled,
              'aria-busy': props.loading,
              onChange: (event) => {
                if (!props.disabled) emit('update:value', event.target.value)
              }
            },
            props.options.map((option) => h('option', { value: option.value }, option.label))
          )
    })
  )
  for (const [name, tag] of [
    ['NAlert', 'div'],
    ['NButton', 'button']
  ]) {
    app.component(name, {
      setup:
        (_, { attrs, slots }) =>
        () =>
          h(tag, attrs, slots.default?.())
    })
  }
  const gui = useGuiStore(pinia)
  const root = node('root')
  app.mount(root)
  mounted.push({ app, pinia })
  return {
    gui,
    select: () => all(root).find((element) => element.tag === 'select'),
    selectors: () => all(root).filter((element) => element.tag === 'select'),
    retry: () => all(root).find((element) => element.tag === 'button'),
    error: () => all(root).find((element) => element.props.role === 'alert'),
    menu: () =>
      all(root).find(
        (element) =>
          element.tag === 'menu' &&
          element.props.options.some((option) => option.key === 'view-language')
      ),
    text: () => text(root)
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

beforeEach(() => {
  i18n.global.locale.value = 'zh-CN'
  axios.get.mockResolvedValue({
    data: { software_version_display: 'channel', software_version_language: 'zh' }
  })
  axios.put.mockImplementation(async (_url, payload) => ({ data: payload }))
})

afterEach(() => {
  for (const { app, pinia } of mounted.splice(0)) {
    app.unmount()
    disposePinia(pinia)
  }
  i18n.global.locale.value = 'zh-CN'
  vi.resetAllMocks()
  vi.unstubAllGlobals()
})

describe('interface language preference with the shared GUI store', () => {
  it('shares system mode across the settings selector and menu and saves only the preference', async () => {
    vi.stubGlobal('window', new EventTarget())
    vi.stubGlobal('navigator', { languages: ['ja-JP'] })
    const page = mount(1, true)
    await flush()
    const systemOption = () =>
      page
        .menu()
        .props.options.find((option) => option.key === 'view-language')
        .children.find((option) => option.language === 'system')
    page.menu().props.onSelect(systemOption())
    await flush()
    expect(page.select().props.value).toBe('system')
    expect(page.gui.resolvedInterfaceLanguage).toBe('ja-JP')
    expect(systemOption()).toMatchObject({ checked: true, disabled: true })
    expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringMatching(/\/gui\/appearance$/),
      { ui_language: 'system' },
      { timeout: 5000 }
    )
    page.select().props.onChange({ target: { value: 'en-US' } })
    await flush()
    expect(systemOption()).toMatchObject({ checked: false, disabled: false })
    page.select().props.onChange({ target: { value: 'system' } })
    await flush()
    expect(systemOption()).toMatchObject({ checked: true, disabled: true })
    i18n.global.locale.value = page.gui.resolvedInterfaceLanguage
    await flush()
    expect(systemOption().label).toBe('システムに従う')
    expect(text(page.select().children[0])).toBe('システムに従う')
    expect(axios.get).toHaveBeenCalledOnce()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: 'system' },
      { ui_language: 'en-US' },
      { ui_language: 'system' }
    ])
  })

  it('saves only ui_language and updates mounted labels without changing language identities', async () => {
    const page = mount(2)
    await flush()
    expect(axios.get).toHaveBeenCalledOnce()
    const labels = {
      'zh-CN': '界面语言',
      'en-US': 'Interface Language',
      'ja-JP': '表示言語',
      'zh-TW': '介面語言'
    }
    for (const locale of ['en-US', 'ja-JP', 'zh-TW', 'zh-CN']) {
      page.select().props.onChange({ target: { value: locale } })
      await flush()
      expect(page.selectors().map((select) => select.props.value)).toEqual([locale, locale])
      const writes = axios.put.mock.calls.length
      i18n.global.locale.value = locale
      await nextTick()
      expect(axios.put).toHaveBeenCalledTimes(writes)
      for (const select of page.selectors()) {
        expect(select.props['aria-label']).toBe(labels[locale])
        expect(
          select.children.map((option) => ({ value: option.props.value, label: text(option) }))
        ).toEqual(getInterfaceLanguageOptions())
      }
      expect(page.gui.softwareVersionLanguage).toBe('zh')
      expect(page.gui.softwareVersionDisplay).toBe('channel')
    }
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: 'en-US' },
      { ui_language: 'ja-JP' },
      { ui_language: 'zh-TW' },
      { ui_language: 'zh-CN' }
    ])
    for (const [url, , options] of axios.put.mock.calls) {
      expect(url).toMatch(/\/gui\/appearance$/)
      expect(options).toEqual({ timeout: 5000 })
    }
  })

  it('keeps choices disabled after a failed read and retries the read without saving a default', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'))
    const page = mount()
    await flush()
    expect(page.select().props.disabled).toBe(true)
    expect(text(page.error())).toContain('界面语言读取失败')
    expect(page.retry().props.disabled).toBe(false)
    page.select().props.onChange({ target: { value: 'en-US' } })
    expect(axios.put).not.toHaveBeenCalled()

    const read = deferred()
    axios.get.mockReturnValueOnce(read.promise)
    page.retry().props.onClick()
    await nextTick()
    expect(page.retry()).toBeUndefined()
    expect(page.gui.loading).toBe(true)
    expect(page.select().props.disabled).toBe(true)
    read.resolve({ data: { software_version_display: 'version', ui_language: 'en-US' } })
    await flush()
    expect(page.select().props.value).toBe('en-US')
    expect(page.select().props.disabled).toBe(false)
    expect(page.error()).toBeUndefined()
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(axios.put).not.toHaveBeenCalled()
  })

  it('shows a pending save, restores a failed choice and retries the requested language', async () => {
    const page = mount()
    await flush()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    page.select().props.onChange({ target: { value: 'ja-JP' } })
    await nextTick()
    expect(page.select().props.value).toBe('ja-JP')
    expect(page.select().props.disabled).toBe(true)
    expect(page.select().props['aria-busy']).toBe(true)
    page.select().props.onChange({ target: { value: 'en-US' } })
    expect(axios.put).toHaveBeenCalledOnce()

    save.reject(new Error('offline'))
    await flush()
    expect(page.select().props.value).toBe('zh-CN')
    expect(page.select().props.disabled).toBe(false)
    expect(text(page.error())).toContain('已恢复原来的语言')
    page.retry().props.onClick()
    await flush()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: 'ja-JP' },
      { ui_language: 'ja-JP' }
    ])
    expect(page.select().props.value).toBe('ja-JP')
    expect(page.error()).toBeUndefined()
  })

  it('blocks both language controls while another appearance preference is saving', async () => {
    const page = mount()
    await flush()
    axios.put.mockRejectedValueOnce(new Error('offline'))
    page.select().props.onChange({ target: { value: 'zh-TW' } })
    await flush()
    const save = deferred()
    axios.put.mockReturnValueOnce(save.promise)
    const pending = page.gui.setSoftwareVersionDisplay('version')
    await nextTick()
    expect(page.select().props.disabled).toBe(true)
    expect(page.retry().props.disabled).toBe(true)
    page.select().props.onChange({ target: { value: 'en-US' } })
    await page.retry().props.onClick()
    expect(axios.put).toHaveBeenCalledTimes(2)

    save.resolve({ data: { software_version_display: 'version' } })
    await pending
    await flush()
    expect(page.retry().props.disabled).toBe(false)
    page.retry().props.onClick()
    await flush()
    expect(axios.put.mock.calls.map(([, payload]) => payload)).toEqual([
      { ui_language: 'zh-TW' },
      { software_version_display: 'version' },
      { ui_language: 'zh-TW' }
    ])
    expect(page.gui.interfaceLanguage).toBe('zh-TW')
    expect(page.gui.softwareVersionLanguage).toBe('zh')
  })
})
