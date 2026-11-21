import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApp, effectScope, ref } from 'vue'
import { createPinia } from 'pinia'
import Email from './Email.vue'
import { useConfigStore } from '@/stores/config'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

let scope
let store
let component
let http

beforeEach(() => {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  http = { get: vi.fn() }
  app.provide('axios', http)
  store = app.runWithContext(() => useConfigStore())
  scope = effectScope()
  component = scope.run(() => app.runWithContext(() => Email.setup({}, { expose: vi.fn() })))
})

afterEach(() => {
  scope.stop()
  store.$dispose()
})

describe('test email feedback', () => {
  it('keeps test sending available when ordinary email notifications are disabled', async () => {
    store.mail_enable = false
    http.get.mockResolvedValue({ data: '邮件发送成功！' })

    await component.test_email()

    expect(http.get).toHaveBeenCalledExactlyOnceWith(expect.stringContaining('/test-email'))
    expect(component.test_result.value).toBe('邮件发送成功！')
    expect(component.testing.value).toBe(false)
    expect(component.test_error.value).toBe(false)
    expect(store.mail_enable).toBe(false)
  })

  it('prevents repeated sends until the active send finishes', async () => {
    let finish
    http.get.mockReturnValue(new Promise((resolve) => (finish = resolve)))

    const sending = component.test_email()
    await component.test_email()

    expect(component.testing.value).toBe(true)
    expect(component.test_result.value).toBe('正在发送……')
    expect(http.get).toHaveBeenCalledTimes(1)
    finish({ data: '邮件发送成功！' })
    await sending
    expect(component.testing.value).toBe(false)
  })

  it('shows a request failure and permits a later retry', async () => {
    http.get.mockRejectedValueOnce(new Error('连接中断'))
    await component.test_email()
    expect(component.test_result.value).toBe('连接中断')
    expect(component.test_error.value).toBe(true)
    expect(component.testing.value).toBe(false)

    http.get.mockResolvedValueOnce({ data: '邮件发送成功！' })
    await component.test_email()
    expect(component.test_result.value).toBe('邮件发送成功！')
    expect(component.test_error.value).toBe(false)
    expect(http.get).toHaveBeenCalledTimes(2)
  })

  it('keeps the backend send failure visible even when the request succeeds', async () => {
    http.get.mockResolvedValue({ data: '邮件发送失败！\nSMTP 登录被拒绝' })

    await component.test_email()

    expect(component.test_result.value).toBe('邮件发送失败！\nSMTP 登录被拒绝')
    expect(component.test_error.value).toBe(true)
    expect(component.testing.value).toBe(false)
  })
})
