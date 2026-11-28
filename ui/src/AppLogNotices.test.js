import { readFileSync } from 'node:fs'
import { compile } from '@vue/compiler-dom'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { expect, it, vi } from 'vitest'

const { descriptor } = parse(readFileSync(new URL('./App.vue', import.meta.url), 'utf8'))
const { bindings } = compileScript(descriptor, { id: 'app-log-notices-test' })
const start = descriptor.template.content.indexOf('<ConfigSaveNotice')
const end = descriptor.template.content.indexOf('<router-view', start)
const { code } = compile(descriptor.template.content.slice(start, end), {
  mode: 'function',
  prefixIdentifiers: true,
  bindingMetadata: bindings
})
const elements = new Map()
const render = new Function('Vue', code)({
  ...Vue,
  resolveComponent: (name) => {
    if (!elements.has(name)) elements.set(name, { name })
    return elements.get(name)
  }
})
const configNotice = { name: 'ConfigSaveNotice' }
const recoveryNotice = { name: 'CrashRecoveryNotice' }
const { descriptor: configDescriptor } = parse(
  readFileSync(new URL('./components/ConfigSaveNotice.vue', import.meta.url), 'utf8')
)
const { bindings: configBindings } = compileScript(configDescriptor, {
  id: 'config-save-notice-test'
})
const { code: configCode } = compile(configDescriptor.template.content, {
  mode: 'function',
  prefixIdentifiers: true,
  bindingMetadata: configBindings
})
const renderConfigNotice = new Function('Vue', configCode)({
  ...Vue,
  resolveComponent: (name) => ({ name })
})

it('keeps save failures assertive when forwarding them to the floating notification', () => {
  const notice = renderConfigNotice(
    {},
    [],
    {},
    {
      StatusNotification: { name: 'StatusNotification' },
      config_save_error: '保存失败',
      config_saving: false,
      config: { save_config: vi.fn(async () => {}) }
    }
  )
  expect(notice.props).toMatchObject({
    show: true,
    role: 'alert',
    type: 'error',
    content: '保存失败。修改仍保留在当前页面。'
  })
})

it('keeps the save retry available in the notification action', async () => {
  const save = vi.fn(async () => {})
  const notice = renderConfigNotice(
    {},
    [],
    {},
    {
      StatusNotification: { name: 'StatusNotification' },
      config_save_error: '保存失败',
      config_saving: false,
      config: { save_config: save }
    }
  )
  await notice.children.action()[0].props.onClick()
  expect(save).toHaveBeenCalledOnce()
})

function notices(routeName) {
  const store = { save_config: vi.fn(async () => {}) }
  const setup = {
    ConfigSaveNotice: configNotice,
    CrashRecoveryNotice: recoveryNotice,
    config_save_error: '保存失败',
    config_saving: false,
    config_store: store,
    loaded: true
  }
  const tree = render({ $route: { name: routeName } }, [], {}, setup)
  return { nodes: tree.children, store }
}

it.each(['log', 'mowersettings', 'plan', 'record_line', 'log_schedule'])(
  'renders the two global notification components without inline alerts on %s',
  (routeName) => {
    const { nodes } = notices(routeName)
    expect(nodes.some((node) => node.type === configNotice)).toBe(true)
    expect(nodes.some((node) => node.type === recoveryNotice)).toBe(true)
    expect(nodes.some((node) => node.type.name === 'n-alert')).toBe(false)
  }
)

it('preserves both notification component identities across navigation', () => {
  const first = notices('log').nodes
  for (const route of ['plan', 'mowersettings', 'record_line', 'log']) {
    const next = notices(route).nodes
    for (const type of [configNotice, recoveryNotice]) {
      const previous = first.find((node) => node.type === type)
      const current = next.find((node) => node.type === type)
      expect(current?.type).toBe(previous.type)
      expect(current?.key).toBe(previous.key)
      expect(current?.props).toEqual(previous.props)
    }
  }
})
