import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, nextTick, ref } from 'vue'
import { createPinia } from 'pinia'
import { compileScript, parse } from '@vue/compiler-sfc'
import { readFileSync } from 'node:fs'
import axios from 'axios'
import { usePlanStore, useRescuePlanStore } from './plan'

vi.mock('axios', () => ({ default: { post: vi.fn(), get: vi.fn() } }))

const { descriptor } = parse(readFileSync(new URL('../pages/Plan.vue', import.meta.url), 'utf8'))
const script = compileScript(descriptor, { id: 'plan-validation-test' })
const handlerNode = script.scriptSetupAst.find((node) => node.id?.name === 'validate_plan')
const handlerCode = descriptor.scriptSetup.content
  .slice(handlerNode.start, handlerNode.end)
  .replaceAll('import.meta.env.VITE_HTTP_URL', JSON.stringify(import.meta.env.VITE_HTTP_URL))

let store

afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

function setup(rescue) {
  const app = createApp({})
  app.use(createPinia())
  app.provide('loaded', ref(false))
  store = app.runWithContext(() => (rescue ? useRescuePlanStore() : usePlanStore()))
  store.plan = store.fill_empty({})
  const message = { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
  const validate = new Function(
    'plan_store',
    'nextTick',
    'axios',
    'rescue',
    'token',
    'message',
    `${handlerCode}; return validate_plan`
  )(store, nextTick, axios, rescue, 'fixture-token', message)
  return { validate, message }
}

describe('manual schedule validation', () => {
  it.each([false, true])(
    'saves the latest zero-mood edit after pending saves (rescue=%s)',
    async (rescue) => {
      const { validate, message } = setup(rescue)
      let finishOldSave
      axios.post.mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishOldSave = resolve
          })
      )
      axios.post.mockResolvedValue({ data: { success: true, message: '验证通过' } })
      const pendingSave = store.save_plan()
      await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
      store.workaholic = ['银灰', '陈', '能天使']

      const validation = validate()
      await nextTick()
      expect(axios.post).toHaveBeenCalledTimes(1)
      finishOldSave({ data: {} })
      await pendingSave
      await validation

      expect(axios.post).toHaveBeenCalledTimes(3)
      expect(axios.post.mock.calls[1][0]).toBe(
        `${import.meta.env.VITE_HTTP_URL}/${rescue ? 'rescue-plan' : 'plan'}`
      )
      expect(axios.post.mock.calls[1][1].conf.workaholic).toBe('银灰,陈,能天使')
      expect(axios.post.mock.calls[2]).toEqual([
        `${import.meta.env.VITE_HTTP_URL}/${rescue ? 'rescue-plan/validate' : 'validate-plan'}`,
        {},
        { headers: { token: 'fixture-token' } }
      ])
      expect(message.success).toHaveBeenCalledWith('验证通过')
    }
  )

  it('does not validate stale configuration when saving fails', async () => {
    const { validate, message } = setup(false)
    axios.post.mockRejectedValue(new Error('保存失败'))

    await validate()

    expect(axios.post).toHaveBeenCalledTimes(1)
    expect(axios.post.mock.calls[0][0]).toBe(`${import.meta.env.VITE_HTTP_URL}/plan`)
    expect(message.error).toHaveBeenCalledWith('验证失败: 保存失败')
    expect(message.success).not.toHaveBeenCalled()
  })
})
