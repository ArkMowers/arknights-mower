import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, reactive, nextTick } from 'vue'
import Editor from './IncomeValueEditor.vue'
const io = vi.hoisted(() => ({ client: null, cleanup: null }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  inject: () => io.client,
  useSSRContext: () => ({ modules: new Set() }),
  onBeforeUnmount: (fn) => {
    io.cleanup = fn
  }
}))
let page, scope, emit, props
beforeEach(() => {
  io.client = { put: vi.fn() }
  emit = vi.fn()
  scope = effectScope()
  props = reactive({
    valuation: { prices: { 中级作战记录: 4, 装置: 8 }, lmd_sanity: 0.0036 },
    disabled: false
  })
  page = scope.run(() => Editor.setup(props, { expose: vi.fn(), emit }))
})
afterEach(() => {
  io.cleanup()
  scope.stop()
})
it('saves only the edited material and emits server-confirmed values', async () => {
  const confirmed = { ...props.valuation, prices: { 中级作战记录: 5, 装置: 8 } }
  io.client.put.mockResolvedValueOnce({ data: confirmed })
  page.materialValue.value = 5
  await page.saveValues('material')
  expect(io.client.put.mock.calls[0][1]).toEqual({ prices: { 中级作战记录: 5 } })
  expect(emit).toHaveBeenCalledWith('saved', confirmed)
  expect(emit).toHaveBeenCalledWith('busy', false)
  page.material.value = '龙门币'
  await nextTick()
  page.materialValue.value = 0.004
  io.client.put.mockResolvedValueOnce({ data: props.valuation })
  await page.saveValues('material')
  expect(io.client.put.mock.calls[1][1]).toEqual({ lmd_sanity: 0.004 })
})
it('preserves explicit zero and nullable overrides without writing unrelated settings', async () => {
  io.client.put.mockResolvedValueOnce({ data: props.valuation })
  page.unitValues.yellow_certificate = 0
  page.unitValues.credit = 0
  await page.saveValues('units')
  const patch = io.client.put.mock.calls[0][1]
  expect(Object.keys(patch)).toEqual(['income_unit_values', 'income_options'])
  expect(patch.income_unit_values).toMatchObject({
    yellow_certificate: 0,
    credit: 0,
    fragment: null
  })
})
it('retains the edit on failure and suppresses duplicate saves and late unmounted responses', async () => {
  page.materialValue.value = 7
  io.client.put.mockRejectedValueOnce({ response: { data: { error: '保存失败' } } })
  await page.saveValues('material')
  expect(page.materialValue.value).toBe(7)
  expect(page.error.value).toBe('保存失败')
  expect(emit).not.toHaveBeenCalledWith('saved', expect.anything())
  let resolve
  io.client.put.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      })
  )
  const pending = page.saveValues('material')
  await page.saveValues('units')
  expect(io.client.put).toHaveBeenCalledTimes(2)
  const signal = io.client.put.mock.calls[1][2].signal
  io.cleanup()
  expect(signal.aborted).toBe(true)
  resolve({ data: props.valuation })
  await pending
  expect(emit).not.toHaveBeenCalledWith('saved', expect.anything())
})

it('saves independent presets and clears only their manual overrides', async () => {
  io.client.put.mockResolvedValueOnce({ data: props.valuation })
  page.unitValues.yellow_certificate = 0
  page.unitValues.recruitment_certificates = 0.1
  page.unitValues.credit = 0
  page.selectPotentialPreset('full')
  page.selectYellowPreset('royal_token')
  await page.saveValues('units')
  expect(io.client.put.mock.calls[0][1]).toMatchObject({
    income_options: { potential_preset: 'full', yellow_preset: 'royal_token' },
    income_unit_values: { yellow_certificate: null, recruitment_certificates: null, credit: 0 }
  })
})
