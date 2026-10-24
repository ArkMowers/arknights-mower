import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import axios from 'axios'
import MasteryRecommendation from './MasteryRecommendation.vue'
import { useMasteryStore } from '@/stores/mastery'

const state = vi.hoisted(() => ({
  unmount: [],
  mount: [],
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
  onMounted: (fn) => state.mount.push(fn),
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
  state.mount = []
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

describe('公开统计加载隔离', () => {
  it('远端统计等待不阻塞本地推荐和路线初始化', async () => {
    const page = setup()
    const store = useMasteryStore()
    const local = [{ char_id: 'local', name: '本地干员', recommendations: [], modules: [] }]
    axios.get.mockImplementation(async (url) => {
      if (url.endsWith('/growth-survey')) return new Promise(() => {})
      if (url.endsWith('/mastery-recommendation')) return { data: { operators: local } }
      if (url.endsWith('/operator')) return { data: [] }
      if (url.endsWith('/mastery-route')) return { data: { routes: [], defaults: {} } }
      return { data: { plans: [] } }
    })
    await state.mount.at(-1)()
    expect(store.recommendations).toBe(local)
    expect(page.surveyLoading.value).toBe(true)
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/mastery-route'))
  })

  it('公开统计请求失败保留已有样本和干员列表', async () => {
    const page = setup()
    const store = useMasteryStore()
    const local = operators()
    store.recommendations = local
    page.survey.value = { operators: [{ charId: 'old', own: 1 }], fetched_at: 123 }
    axios.get.mockRejectedValueOnce(new Error('network'))
    await page.loadSurvey()
    expect(page.survey.value.operators).toEqual([{ charId: 'old', own: 1 }])
    expect(page.survey.value.stale).toBe(true)
    expect(page.surveyLoading.value).toBe(false)
    expect(store.recommendations).toBe(local)
  })
})

describe('大数据养成筛选', () => {
  it('读取专精统计后按门槛筛选，完成与未达门槛的干员隐藏，未知数据保留', async () => {
    const page = setup()
    const store = useMasteryStore()
    const roster = operators()
      .slice(0, 4)
      .map((op, index) => ({
        ...op,
        skill_levels: [index === 1 ? 3 : 0]
      }))
    store.recommendations = roster
    const plan = JSON.stringify(page.plan.value)
    axios.get.mockResolvedValueOnce({
      data: {
        operators: [
          { charId: 'char_0', own: 100, skill1: { 0: 19, 3: 81 } },
          { charId: 'char_1', own: 100, skill1: { 0: 19, 3: 81 } },
          { charId: 'char_2', own: 100, skill1: { 0: 21, 3: 79 } }
        ],
        stale: false,
        error: null
      }
    })
    await page.loadSurvey()
    page.surveyFilters.value.mastery = 80
    expect(page.displayList.value.map((op) => op.char_id)).toEqual(['char_0', 'char_3'])
    expect(page.surveyFor(roster[0]).skillHighlights).toEqual([0])
    expect(page.surveyFor(roster[3]).skills[0].rate).toBeNull()
    page.surveyFilters.value.mastery = 90
    expect(page.displayList.value.map((op) => op.char_id)).toEqual(['char_3'])
    page.surveyFilters.value.hideCompleted = false
    expect(page.displayList.value).toHaveLength(4)
    expect(JSON.stringify(page.plan.value)).toBe(plan)
    expect(store.recommendations).toEqual(roster)
    expect(axios.post).not.toHaveBeenCalled()
  })
})

describe('按筛选一键添加养成计划', () => {
  let roster
  let goals
  let plans
  const rec = (skill_index) => ({ skill_index, current_level: 0 })
  const module = (id, type) => ({ id, type, current_level: 0, max_level: 3 })
  const row = (charId, extra = {}) => ({
    charId,
    own: 100,
    skill1: { 0: 10, 3: 90 },
    skill2: { 0: 80, 3: 20 },
    modX: { 0: 10, 1: 90 },
    modY: { 0: 80, 1: 20 },
    elite: { 0: 5, 1: 5, 2: 90 },
    ...extra
  })
  function prepare(page, count = 1) {
    roster = operators()
      .slice(0, count)
      .map((op) => ({
        ...op,
        skill_levels: [0, 0],
        recommendations: [rec(0), rec(1)],
        modules: [module('x', 'MOD-X'), module('y', 'MOD-Y')],
        level_goals: [
          { id: 'elite1', elite: 1, level: 1 },
          { id: 'elite2', elite: 2, level: 1 },
          { id: 'elite2_max', elite: 2, level: 90 }
        ]
      }))
    goals = []
    plans = []
    useMasteryStore().recommendations = roster
    page.survey.value = { operators: roster.map((op) => row(op.char_id)) }
    axios.post.mockImplementation(async (url, body) => {
      if (url.endsWith('/mastery-plan')) {
        return {
          data: {
            results: body.items.map((item, index) => {
              plans.push({ ...item, id: index + 1, status: 'idle' })
              return { id: index + 1, status: 'added' }
            })
          }
        }
      }
      if (url.endsWith('/growth-plan')) {
        goals = goals.filter(
          (goal) => goal.char_id !== body.char_id || goal.module_id !== body.module_id
        )
        goals.push(body)
        return { data: { goals: [...goals] } }
      }
      return { data: { material_summary: { available: true } } }
    })
    axios.get.mockImplementation(async (url) => ({
      data: url.endsWith('/mastery-plan') ? { plans } : { operators: roster, goals }
    }))
  }
  const writes = () =>
    axios.post.mock.calls.filter(
      ([url]) => url.endsWith('/growth-plan') || url.endsWith('/mastery-plan')
    )

  it('没有比例筛选时不添加，精一率筛选只添加精一目标', async () => {
    const page = setup()
    prepare(page)
    expect(page.filteredPlanItems.value).toEqual([])
    await page.addFilteredToPlan()
    expect(writes()).toEqual([])
    page.surveyFilters.value.elite1 = 80
    await page.addFilteredToPlan()
    expect(writes().map(([, body]) => body)).toEqual([
      { char_id: 'char_0', module_id: 'elite1', selected: true }
    ])
    expect(page.filteredPlanItems.value).toEqual([])
  })

  it('专三率只添加达到门槛的技能，缺少样本的可见干员不误加入', async () => {
    const page = setup()
    prepare(page, 2)
    page.survey.value.operators = [row('char_0')]
    page.surveyFilters.value.mastery = 80
    page.targets.value.char_0_0 = 2
    expect(page.displayList.value).toHaveLength(2)
    await page.addFilteredToPlan()
    expect(writes().map(([, body]) => body)).toEqual([
      {
        planning: true,
        items: [{ char_id: 'char_0', name: '干员0', skill_index: 0, target_level: 2 }]
      }
    ])
  })

  it('模组率只添加匹配模组并沿用目标，跳过已有计划与已满级模组', async () => {
    const page = setup()
    prepare(page, 3)
    roster[2].modules[0].current_level = 3
    useMasteryStore().goals = [{ char_id: 'char_1', module_id: 'x', target_level: 1 }]
    page.moduleTargets.value['char_0:x'] = 2
    page.surveyFilters.value.module = 80
    await page.addFilteredToPlan()
    expect(writes().map(([, body]) => body)).toEqual([
      { char_id: 'char_0', module_id: 'x', target_level: 2, selected: true }
    ])
  })

  it('精一精二取较高目标，跳过已完成及已有更高目标，保留三星精一', async () => {
    const page = setup()
    prepare(page, 5)
    roster[1].elite = 2
    roster[3].rarity = 3
    roster[3].max_phase = 1
    roster[3].level_goals = [
      { id: 'elite1', elite: 1, level: 1 },
      { id: 'level_max', elite: 1, level: 55 }
    ]
    useMasteryStore().goals = [{ char_id: 'char_2', module_id: 'elite2_max' }]
    page.survey.value.operators[4] = row('char_4', { elite: { 0: 5, 1: 90, 2: 5 } })
    page.surveyFilters.value.elite1 = 80
    page.surveyFilters.value.elite2 = 80
    await page.addFilteredToPlan()
    expect(writes().map(([, body]) => body)).toEqual([
      { char_id: 'char_0', module_id: 'elite2', selected: true },
      { char_id: 'char_3', module_id: 'elite1', selected: true },
      { char_id: 'char_4', module_id: 'elite1', selected: true }
    ])
  })

  it('跨全部分页添加，同时遵守名称和职业筛选以及已有技能计划', async () => {
    const page = setup()
    prepare(page, 33)
    page.surveyFilters.value.mastery = 80
    page.plan.value.char_0_0 = true
    expect(page.pagedOperators.value).toHaveLength(30)
    expect(page.filteredPlanItems.value).toHaveLength(32)
    page.searchQuery.value = '干员32'
    page.filterProfession.value = ['医疗']
    expect(page.filteredPlanItems.value).toHaveLength(0)
    page.filterProfession.value = ['狙击']
    page.searchQuery.value = ''
    await page.addFilteredToPlan()
    expect(writes()[0][1].items).toHaveLength(32)
    expect(writes()[0][1].items.at(-1).char_id).toBe('char_32')
    expect(writes()[0][1].items.some((item) => item.char_id === 'char_0')).toBe(false)
  })

  it('多个门槛分别添加匹配技能、模组和较高精英化目标', async () => {
    const page = setup()
    prepare(page)
    Object.assign(page.surveyFilters.value, { mastery: 80, module: 80, elite1: 80, elite2: 80 })
    await page.addFilteredToPlan()
    expect(writes().map(([, body]) => body)).toEqual([
      {
        planning: true,
        items: [{ char_id: 'char_0', name: '干员0', skill_index: 0, target_level: 3 }]
      },
      { char_id: 'char_0', module_id: 'x', target_level: 3, selected: true },
      { char_id: 'char_0', module_id: 'elite2', selected: true }
    ])
    expect(page.filteredPlanItems.value).toHaveLength(0)
  })

  it('技能逐项拒绝时不误报全部成功，仍保存其余匹配目标', async () => {
    const page = setup()
    prepare(page)
    page.surveyFilters.value.mastery = 10
    const save = axios.post.getMockImplementation()
    axios.post.mockImplementation(async (url, body, options) => {
      if (url.endsWith('/mastery-plan'))
        return {
          data: {
            results: [
              { id: 1, status: 'added' },
              { status: 'error', reason: '材料数据无效' }
            ]
          }
        }
      return save(url, body, options)
    })
    await page.addFilteredToPlan()
    expect(state.feedback.warning).toHaveBeenCalledWith('已保存 1 项计划，1 项未加入：材料数据无效')
    expect(state.feedback.success).not.toHaveBeenCalled()
  })

  it('重复点击不重复保存，保存期间修改筛选不改变已点击的项目', async () => {
    const page = setup()
    prepare(page)
    page.surveyFilters.value.module = 80
    let finish
    axios.post.mockImplementationOnce(
      (_url, body) =>
        new Promise((resolve) => {
          finish = () => {
            goals = [body]
            resolve({ data: { goals } })
          }
        })
    )
    const saving = page.addFilteredToPlan()
    page.surveyFilters.value.module = 10
    await page.addFilteredToPlan()
    expect(writes()).toHaveLength(1)
    finish()
    await saving
    expect(writes()).toHaveLength(1)
    expect(page.batchAdding.value).toBe(false)
  })

  it('部分保存后失败保留成功目标，重新读取服务端并提示未确认项目', async () => {
    const page = setup()
    prepare(page)
    page.surveyFilters.value.module = 10
    const save = axios.post.getMockImplementation()
    axios.post.mockImplementationOnce(save).mockRejectedValueOnce(new Error('网络中断'))
    await page.addFilteredToPlan()
    expect(useMasteryStore().goals.map((goal) => goal.module_id)).toEqual(['x'])
    expect(state.feedback.error).toHaveBeenCalledWith(
      expect.stringContaining('已确认保存 1 项，另有 1 项未确认保存')
    )
    expect(axios.get).toHaveBeenCalledWith(expect.stringContaining('/mastery-plan'))
    expect(page.batchAdding.value).toBe(false)
  })

  it('离开页面取消当前保存且不继续保存剩余目标', async () => {
    const page = setup()
    prepare(page)
    page.surveyFilters.value.module = 10
    let finish
    axios.post.mockImplementationOnce(
      (_url, body) =>
        new Promise((resolve) => {
          finish = () => resolve({ data: { goals: [body] } })
        })
    )
    const saving = page.addFilteredToPlan()
    const signal = writes()[0][2].signal
    state.unmount.forEach((fn) => fn())
    expect(signal.aborted).toBe(true)
    finish()
    await saving
    expect(writes()).toHaveLength(1)
    expect(axios.get).not.toHaveBeenCalled()
    expect(state.feedback.success).not.toHaveBeenCalled()
  })
})
