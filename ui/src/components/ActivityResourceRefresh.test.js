import { createRenderer, h, reactive, ref, ssrContextKey } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import WeeklyPlanSelector from './WeeklyPlanSelector.vue'
import MaaStageInventory from './MaaStageInventory.vue'

const state = vi.hoisted(() => ({ config: {}, refs: {}, resource: null }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/resourceVersion', () => ({ useResourceVersionStore: () => state.resource }))
vi.mock('pinia', () => ({ storeToRefs: () => state.refs }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ success: vi.fn(), error: vi.fn() }) }))

const mounted = []
function mountSetup(component) {
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    setText() {},
    setElementText() {},
    patchProp() {},
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null
  })
  const app = renderer.createApp({ ...component, render: () => h('div') })
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount({})
  mounted.push(app)
  return app._instance.setupState
}

beforeEach(() => {
  state.resource = reactive({ info: { current_version: 'old' } })
  state.refs = {
    maa_weekly_plan: ref([{ weekday: '周一', stage: ['YW-8'] }]),
    maa_weekly_plan_active: ref('活动'),
    maa_weekly_plan_options: ref(['活动', '常规']),
    maa_weekly_plan_activity_fallbacks: ref({ 活动: '常规' }),
    maa_weekly_plan_activity_switch_times: ref({}),
    maa_weekly_plan_activity_end_times: ref({ 活动: 200 }),
    maa_stage_inventory_enable: ref(true),
    maa_stage_limit_rules: ref([]),
    maa_stage_ratio_rules: ref([])
  }
  state.config = {
    refresh_weekly_plan_metadata: vi.fn(async () => {
      state.refs.maa_weekly_plan_activity_end_times.value = { 活动: 1792699199 }
    })
  }
  axios.get.mockReset().mockResolvedValue({ data: { stages: [], items: [] } })
})
afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
})

describe('活动数据随资源版本刷新', () => {
  it('资源切换后更新默认结束时间，保留自定切换时间', async () => {
    const selector = mountSetup(WeeklyPlanSelector)
    expect(selector.localFallbackTime).toBe(200000)
    state.resource.info.current_version = 'new'
    await vi.waitFor(() => expect(selector.localFallbackTime).toBe(1792699199000))
    state.refs.maa_weekly_plan_activity_switch_times.value = { 活动: 150 }
    state.resource.info.current_version = 'newer'
    await vi.waitFor(() =>
      expect(state.config.refresh_weekly_plan_metadata).toHaveBeenCalledTimes(2)
    )
    expect(selector.localFallbackTime).toBe(150000)
    expect(state.refs.maa_weekly_plan.value[0].stage).toEqual(['YW-8'])
  })

  it('旧库存请求迟到时保留新资源建议', async () => {
    let finishOld
    axios.get.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finishOld = resolve
        })
    )
    const inventory = mountSetup(MaaStageInventory)
    const suggestion = { name: '昨日海', members: [{ stage: 'YW-8' }] }
    axios.get.mockResolvedValue({
      data: { stages: [], items: [], activity_ratio_suggestion: suggestion }
    })
    state.resource.info.current_version = 'new'
    await vi.waitFor(() => expect(inventory.activityRatioSuggestion).toEqual(suggestion))
    finishOld({ data: { stages: [], items: [] } })
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(inventory.activityRatioSuggestion).toEqual(suggestion)
  })

  it('资源切换后重读库存活动建议，保留已编辑规则', async () => {
    const inventory = mountSetup(MaaStageInventory)
    await vi.waitFor(() => expect(inventory.loading).toBe(false))
    state.refs.maa_stage_limit_rules.value = [{ stage: 'YW-8', items: [] }]
    const suggestion = { name: '昨日海', members: [{ stage: 'YW-8' }] }
    axios.get.mockResolvedValue({
      data: {
        stages: [{ value: 'YW-8' }],
        items: [],
        activity_ratio_suggestion: suggestion
      }
    })
    state.resource.info.current_version = 'new'
    await vi.waitFor(() => expect(inventory.activityRatioSuggestion).toEqual(suggestion))
    expect(inventory.stageOptions).toEqual([{ value: 'YW-8' }])
    expect(axios.get).toHaveBeenCalledTimes(2)
    expect(state.refs.maa_stage_limit_rules.value).toEqual([{ stage: 'YW-8', items: [] }])
  })
})
