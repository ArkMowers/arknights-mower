import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import axios from 'axios'
import MasteryRecommendation from './MasteryRecommendation.vue'

const state = vi.hoisted(() => ({
  config: null,
  plan: null,
  feedback: { warning: vi.fn(), info: vi.fn(), error: vi.fn(), success: vi.fn() }
}))
vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))
vi.mock('naive-ui', async (original) => ({
  ...(await original()),
  useMessage: () => state.feedback,
  useThemeVars: () => ref({})
}))
vi.mock('vue', async (original) => ({
  ...(await original()),
  onMounted: vi.fn(),
  onUnmounted: vi.fn(),
  useSSRContext: () => ({ modules: new Set() })
}))

let scope
function setup() {
  scope = effectScope()
  return scope.run(() => MasteryRecommendation.setup({}, { expose: vi.fn() }))
}
const savedPlan = (id, char_id, skill_index = 0) => ({ id, char_id, skill_index, status: 'idle' })

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  setActivePinia(createPinia())
  state.config = defineStore('form-test-config', {
    state: () => ({
      workshop_min_bonus: 80,
      workshop_protect_t2_device_rock: true,
      workshop_deer_fodder: [],
      fodder_operators: [],
      t5_operators: [],
      book_operators: []
    })
  })()
  state.plan = defineStore('form-test-plan', {
    state: () => ({ operators: [], plan: {}, backup_plans: [] })
  })()
  axios.get.mockResolvedValue({ data: { plans: [] } })
  axios.post.mockResolvedValue({ data: { material_summary: { available: true } } })
})
afterEach(() => {
  scope?.stop()
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('阿米娅跨形态专精提示', () => {
  it('同形态多个技能不提示，跨形态持续提示且移除后清除', async () => {
    const page = setup()
    page.plan.value = { char_002_amiya_0: true, char_002_amiya_1: true, char_123_other_0: true }
    await nextTick()
    expect(page.crossFormWarning.value).toBe('')
    expect(state.feedback.warning).not.toHaveBeenCalled()
    page.plan.value.char_1001_amiya2_0 = true
    await nextTick()
    expect(page.crossFormWarning.value).toContain('术师、近卫')
    expect(page.crossFormWarning.value).toContain('Mower 不会自动切换形态')
    expect(page.crossFormWarning.value).toContain('在轮到对应形态训练前及时在游戏内手动切换形态')
    expect(page.crossFormWarning.value).not.toContain('关闭')
    expect(state.feedback.warning).toHaveBeenCalledWith(page.crossFormWarning.value, {
      duration: 10000
    })
    page.filterProfession.value = ['医疗']
    page.searchQuery.value = '能天使'
    expect(page.crossFormWarning.value).toContain('术师、近卫')
    page.plan.value.char_1037_amiya3_0 = true
    await nextTick()
    expect(page.crossFormWarning.value).toContain('术师、近卫、医疗')
    delete page.plan.value.char_002_amiya_0
    delete page.plan.value.char_002_amiya_1
    delete page.plan.value.char_1001_amiya2_0
    await nextTick()
    expect(page.crossFormWarning.value).toBe('')
  })

  it('重新载入保存计划后提示，不依赖推荐列表或已完成计划', async () => {
    const page = setup()
    axios.get.mockResolvedValue({
      data: {
        plans: [savedPlan(1, 'char_002_amiya'), savedPlan(2, 'char_1037_amiya3')]
      }
    })
    await page.refreshPlanFromServer()
    await nextTick()
    expect(page.crossFormWarning.value).toContain('术师、医疗')
    axios.get.mockResolvedValue({
      data: {
        plans: [
          { ...savedPlan(1, 'char_002_amiya'), status: 'completed' },
          savedPlan(2, 'char_1037_amiya3')
        ]
      }
    })
    await page.refreshPlanFromServer()
    await nextTick()
    expect(page.crossFormWarning.value).toBe('')
  })

  it.each(['toggleSkillPlan', 'addAllToPlan'])('%s 提交选中的形态 ID', async (method) => {
    const page = setup()
    const rec = { skill_index: 0, current_level: 0, target_level: 3 }
    const op = { name: '阿米娅', char_id: 'char_1001_amiya2', recommendations: [rec] }
    await page[method](op, rec)
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining('/mastery-plan'), {
      planning: true,
      items: [{ name: '阿米娅', char_id: 'char_1001_amiya2', skill_index: 0, target_level: 3 }]
    })
  })
})
