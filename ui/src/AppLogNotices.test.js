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

it('uses floating notices only on the running log route', () => {
  const { nodes } = notices('log')
  expect(nodes.some((node) => node.type === configNotice)).toBe(true)
  expect(nodes.some((node) => node.type.name === 'n-alert')).toBe(false)
  expect(nodes.find((node) => node.type === recoveryNotice).props.floating).toBe(true)
})

it.each(['mowersettings', 'plan', 'record_line', 'log_schedule'])(
  'preserves inline notices and the save retry on %s',
  async (routeName) => {
    const { nodes, store } = notices(routeName)
    expect(nodes.some((node) => node.type === configNotice)).toBe(false)
    expect(nodes.find((node) => node.type === recoveryNotice).props.floating).toBe(false)
    const alert = nodes.find((node) => node.type.name === 'n-alert')
    expect(alert.props.title).toBe('配置保存失败')
    await alert.children.action()[0].props.onClick()
    expect(store.save_config).toHaveBeenCalledOnce()
  }
)
