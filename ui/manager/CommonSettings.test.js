import { describe, expect, it, vi } from 'vitest'
import CommonSettings from './CommonSettings.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

function setup(values = {}) {
  const props = {
    values,
    fields: [
      { key: 'device.screenshot_backend', default: 'droidcast', group: '连接方式' },
      { key: 'device.touch_backend', default: 'scrcpy', group: '连接方式' },
      { key: 'account', default: '', group: '邮件发信人' },
      { key: 'startup_mode', default: 'window', group: '实例启动' }
    ]
  }
  const emit = vi.fn((event, next) => {
    if (event === 'update:values') props.values = next
  })
  const component = CommonSettings.setup(props, { expose() {}, emit })
  return { props, emit, component }
}

describe('manager common settings', () => {
  it('opts into one field without copying unrelated defaults', () => {
    const { props, component } = setup()
    component.toggle(props.fields[2], true)
    expect(props.values).toEqual({ account: '' })
    component.change(props.fields[2], 'sender@example.com')
    expect(props.values).toEqual({ account: 'sender@example.com' })
    component.toggle(props.fields[2], false)
    expect(props.values).toEqual({})
  })

  it('selects screenshot and touch together and preserves the MuMu pair', () => {
    const { props, component } = setup({ account: 'keep' })
    component.toggle(props.fields[0], true)
    expect(props.values['device.touch_backend']).toBe('scrcpy')
    component.change(props.fields[0], 'mumu_ipc')
    expect(props.values['device.touch_backend']).toBe('mumu_ipc')
    component.change(props.fields[1], 'maatouch')
    expect(props.values['device.screenshot_backend']).toBe('droidcast')
    component.toggle(props.fields[1], false)
    expect(props.values).toEqual({ account: 'keep' })
  })

  it('keeps the startup mode as an explicit draft and permits returning to the default', () => {
    const { props, component } = setup({ account: 'keep' })
    const field = props.fields[3]
    component.toggle(field, true)
    expect(props.values).toEqual({ account: 'keep', startup_mode: 'window' })
    component.change(field, 'background')
    expect(props.values).toEqual({ account: 'keep', startup_mode: 'background' })
    component.toggle(field, false)
    expect(props.values).toEqual({ account: 'keep' })
  })
})
