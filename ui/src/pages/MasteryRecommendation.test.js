import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import axios from 'axios'
import MasteryRecommendation from './MasteryRecommendation.vue'
import { useMasteryStore } from '@/stores/mastery'

const state = vi.hoisted(() => ({
  unmount: [],
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
  onUnmounted: (fn) => state.unmount.push(fn),
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
  state.unmount = []
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
  state.unmount.forEach((fn) => fn())
  scope?.stop()
  vi.clearAllTimers()
  vi.useRealTimers()
})

describe('阿米娅专精升变提示', () => {
  it('任一形态即提示，跨形态更新且移除阿米娅后清除', async () => {
    const page = setup()
    page.plan.value = { char_123_other_0: true }
    await nextTick()
    expect(page.crossFormWarning.value).toBe('')
    expect(state.feedback.warning).not.toHaveBeenCalled()
    page.plan.value = { char_002_amiya_0: true, char_002_amiya_1: true, char_123_other_0: true }
    await nextTick()
    expect(page.crossFormWarning.value).toContain('术师形态专精')
    page.plan.value.char_1001_amiya2_0 = true
    await nextTick()
    expect(page.crossFormWarning.value).toContain('术师、近卫')
    expect(page.crossFormWarning.value).toContain('Mower 不会自动切换升变')
    expect(page.crossFormWarning.value).toContain('在轮到对应形态训练前及时在游戏内手动切换升变')
    expect(page.crossFormWarning.value).toContain('后续仍会进房检查')
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
    expect(page.crossFormWarning.value).toContain('医疗形态专精')
    delete page.plan.value.char_1037_amiya3_0
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
    expect(page.crossFormWarning.value).toContain('医疗形态专精')
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

function operators() {
  return Array.from({ length: 432 }, (_, i) => ({
    char_id: `char_${i}`,
    name: `干员${i}`,
    rarity: 6,
    elite: 0,
    level: 1,
    profession: 'SNIPER',
    recommendations: [],
    modules: []
  }))
}
async function flush() {
  for (let i = 0; i < 5; i++) await nextTick()
}

describe('养成规划按需详情', () => {
  it('限制渲染卡片数量，翻页与筛选保留完整列表且不自动请求详情', async () => {
    const page = setup()
    useMasteryStore().recommendations = operators()
    await flush()
    expect(page.displayList.value).toHaveLength(432)
    expect(page.pagedOperators.value).toHaveLength(30)
    page.operatorPage.value = 15
    await flush()
    expect(page.pagedOperators.value).toHaveLength(12)
    expect(page.pagedOperators.value[0].char_id).toBe('char_420')
    page.searchQuery.value = '干员431'
    await flush()
    expect(page.operatorPage.value).toBe(1)
    expect(page.pagedOperators.value.map((op) => op.char_id)).toEqual(['char_431'])
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('仅加载展开项，取消前项请求并忽略迟到响应，关闭释放详情', async () => {
    const page = setup()
    const resolves = []
    axios.get.mockImplementation(() => new Promise((resolve) => resolves.push(resolve)))
    page.expandedOperator.value = ['char_0']
    await flush()
    const firstSignal = axios.get.mock.calls[0][1].signal
    page.expandedOperator.value = ['char_1']
    await flush()
    expect(firstSignal.aborted).toBe(true)
    expect(axios.get.mock.calls[1][1].params).toEqual({ char_id: 'char_1' })
    resolves[1]({ data: { operators: [{ char_id: 'char_1', modules: [] }] } })
    await flush()
    resolves[0]({ data: { operators: [{ char_id: 'char_0' }] } })
    await flush()
    expect(page.operatorDetail.value.char_id).toBe('char_1')
    expect(page.detailLoading.value).toBe(false)
    page.expandedOperator.value = []
    await flush()
    expect(page.operatorDetail.value).toBeNull()
    expect(axios.get).toHaveBeenCalledTimes(2)
  })

  it('详情失败保留列表，重试后恢复，卸载取消未完成请求', async () => {
    const page = setup()
    useMasteryStore().recommendations = operators()
    await flush()
    axios.get.mockRejectedValueOnce(new Error('读取超时'))
    page.expandedOperator.value = ['char_0']
    await flush()
    expect(page.detailError.value).toBe('读取超时')
    expect(page.pagedOperators.value).toHaveLength(30)
    axios.get.mockResolvedValueOnce({ data: { operators: [{ char_id: 'char_0' }] } })
    await page.loadOperatorDetail('char_0')
    expect(page.detailError.value).toBe('')
    expect(page.operatorDetail.value.char_id).toBe('char_0')
    axios.get.mockReturnValueOnce(new Promise(() => {}))
    page.loadOperatorDetail('char_1')
    const signal = axios.get.mock.calls.at(-1)[1].signal
    state.unmount.forEach((fn) => fn())
    expect(signal.aborted).toBe(true)
  })
})
