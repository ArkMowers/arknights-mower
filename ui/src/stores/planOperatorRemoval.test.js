import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApp, ref } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { usePlanStore } from './plan'
import {
  OPERATOR_CONF_FIELDS,
  apply_operator_replace,
  collect_plan_operators
} from '@/utils/plan_edit'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let store
afterEach(() => {
  store?.$dispose()
  vi.clearAllMocks()
})

async function load(data) {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  const loaded = ref(false)
  app.provide('loaded', loaded)
  store = app.runWithContext(() => usePlanStore())
  axios.get.mockResolvedValue({ data: structuredClone(data) })
  axios.post.mockResolvedValue({ data: {} })
  await store.load_plan()
  return loaded
}

describe('副表干员移除名单', () => {
  it('旧副表名单继续添加，移除名单默认留空', async () => {
    await load({
      conf: { rest_in_full: '陈' },
      plan1: {},
      backup_plans: [{ plan: {}, conf: { rest_in_full: '红' } }]
    })
    expect(store.rest_in_full).toEqual(['陈'])
    expect(store.backup_plans[0].conf.rest_in_full).toEqual(['红'])
    for (const field of OPERATOR_CONF_FIELDS) {
      expect(store.backup_plans[0].conf.removed_operators[field]).toEqual([])
    }
    expect(store.build_plan().backup_plans[0].conf.removed_operators).toEqual({})
  })

  it('全部选项的增减名单独立自动保存，导入导出保持完整且不改主表', async () => {
    const added = Object.fromEntries(OPERATOR_CONF_FIELDS.map((field) => [field, '红']))
    const removed = Object.fromEntries(OPERATOR_CONF_FIELDS.map((field) => [field, '陈']))
    const loaded = await load({
      conf: { rest_in_full: '陈' },
      plan1: {},
      backup_plans: [{ plan: {}, conf: { ...added, removed_operators: removed } }]
    })
    const first = store.build_plan()
    expect(first.backup_plans[0].conf.removed_operators).toEqual(removed)
    loaded.value = true
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1))
    for (const field of OPERATOR_CONF_FIELDS) {
      store.backup_plans[0].conf.removed_operators[field].push('初雪')
    }
    await vi.waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2))
    const payload = axios.post.mock.calls[1][1]
    expect(payload.conf.rest_in_full).toBe('陈')
    for (const field of OPERATOR_CONF_FIELDS) {
      expect(payload.backup_plans[0].conf[field]).toBe('红')
      expect(payload.backup_plans[0].conf.removed_operators[field]).toBe('陈,初雪')
      expect(first.backup_plans[0].conf.removed_operators[field]).toBe('陈')
    }
    loaded.value = false
    axios.get.mockResolvedValue({ data: structuredClone(payload) })
    await store.load_plan()
    expect(store.build_plan()).toEqual(payload)
    store.backup_plans[0].conf.removed_operators.rest_in_full = []
    expect(store.build_plan().backup_plans[0].conf.removed_operators).not.toHaveProperty(
      'rest_in_full'
    )
  })

  it.each(OPERATOR_CONF_FIELDS)('一键替换保留 %s 的移除含义', async (field) => {
    await load({
      conf: {},
      plan1: {},
      backup_plans: [{ plan: {}, conf: { removed_operators: { [field]: '陈' } } }]
    })
    const state = { main_plan: store.plan, main_conf: {}, backup_plans: store.backup_plans }
    expect(collect_plan_operators(state)).toContain('陈')
    apply_operator_replace(state, '陈', '初雪')
    expect(collect_plan_operators(state)).not.toContain('陈')
    expect(store.build_plan().backup_plans[0].conf.removed_operators[field]).toBe('初雪')
  })
})
