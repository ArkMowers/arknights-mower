import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, ref } from 'vue'
import { createPinia, defineStore, setActivePinia } from 'pinia'
import axios from 'axios'
import MasteryRecommendation from './MasteryRecommendation.vue'
import { useMasteryStore } from '@/stores/mastery'
import { i18n } from '@/i18n'

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
  i18n.global.locale.value = 'zh-CN'
  state.unmount.forEach((fn) => fn())
  scope?.stop()
  vi.clearAllTimers()
  vi.useRealTimers()
})

it('updates swap-buffer descriptions in four languages without changing saved minute values or field keys', () => {
  const page = setup()
  state.plan.plan = { central: { plans: [{ agent: '阿斯卡纶' }] } }
  page.masterySettings.mastery_swap_buffers = { central: 8, central_unhalved_m2: 12, no_central: 9 }
  for (const [locale, expected] of [
    ['zh-CN', '有中枢加成'],
    ['en-US', 'With Control Center bonus'],
    ['ja-JP', '制御中枢ボーナスあり'],
    ['zh-TW', '有中樞加成']
  ]) {
    i18n.global.locale.value = locale
    expect(page.masteryBufferFields.value[0]).toEqual({ key: 'central', label: expected })
    expect(page.masteryBufferFields.value[1].key).toBe('central_unhalved_m2')
    expect(i18n.global.te('growthUpdates.swapBufferMinutes', locale)).toBe(true)
    expect(i18n.global.te('growthUpdates.swapBufferHelp', locale)).toBe(true)
    expect(page.masterySettings.mastery_swap_buffers).toEqual({
      central: 8,
      central_unhalved_m2: 12,
      no_central: 9
    })
  }
  state.plan.plan = {}
  expect(page.masteryBufferFields.value.map((item) => item.key)).toEqual(['no_central'])
  expect(axios.post).not.toHaveBeenCalled()
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
  it('离开干员视图释放选中详情并忽略迟到结果', async () => {
    const page = setup()
    let resolve
    axios.get.mockReturnValue(
      new Promise((done) => {
        resolve = done
      })
    )
    page.activeView.value = 'operators'
    await flush()
    page.expandedOperator.value = ['char_0']
    await flush()
    const signal = axios.get.mock.calls[0][1].signal
    page.activeView.value = 'materials'
    await flush()
    expect(signal.aborted).toBe(true)
    expect(page.expandedOperator.value).toEqual([])
    resolve({ data: { operators: [{ char_id: 'char_0' }] } })
    await flush()
    expect(page.operatorDetail.value).toBeNull()
  })
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

describe('养成工作区派生数据', () => {
  it('清除更高显式等级目标时保留专精最低前置', async () => {
    const page = setup()
    const op = {
      char_id: 'char_clear',
      name: '清除目标',
      rarity: 6,
      elite: 1,
      level: 1,
      max_phase: 2,
      modules: [],
      recommendations: [{ skill_index: 0, current_level: 0 }],
      level_goals: [
        { id: 'elite2', elite: 2, level: 1 },
        { id: 'elite2_max', elite: 2, level: 90 }
      ]
    }
    const store = useMasteryStore()
    store.recommendations = [op]
    store.goals = [{ char_id: op.char_id, module_id: 'elite2_max' }]
    page.plan.value = { char_clear_0: true }
    axios.post.mockResolvedValue({ data: { goals: [] } })
    await page.applyLevelTarget(op, null)
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/growth-plan'),
      expect.objectContaining({ char_id: op.char_id, module_id: 'elite2_max', selected: false })
    )
    expect(page.levelGoalFor(op)).toBe('elite2')
  })

  it('总览使用服务端保存的技能与手动目标混排顺序', async () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      {
        char_id: 'char_order',
        name: '排序干员',
        rarity: 6,
        elite: 2,
        recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 0 }],
        modules: [{ id: 'mod_x', name: '模组', max_level: 3 }],
        level_goals: []
      }
    ]
    store.goals = [{ char_id: 'char_order', module_id: 'mod_x', target_level: 3 }]
    axios.get.mockImplementation(async (url) =>
      url.endsWith('/growth-crafting-order')
        ? {
            data: {
              planning_items: [{ key: 'goal:char_order:mod_x' }, { key: 'skill:char_order:0' }]
            }
          }
        : { data: { plans: [savedPlan(1, 'char_order')] } }
    )
    await page.refreshPlanFromServer()
    expect(page.queueItems.value.map((row) => row.kind)).toEqual(['goal', 'skill'])
    expect(page.nextUpItem.value.label).toBe('模组 · 模组 3 级')
  })

  it('部分成品可合成时逐行统计，不用底层原料缺口数量相减', () => {
    const page = setup()
    page.planMaterials.value = {
      craftable: false,
      materials: [
        { id: 'ready', owned: 2, required: 2, craftable: true },
        { id: 'can_craft', owned: 0, required: 2, craftable: true },
        { id: 'cannot_craft', owned: 0, required: 2, craftable: false }
      ],
      missing: [{ id: 'raw_1' }, { id: 'raw_2' }]
    }
    expect(page.planMaterialStats.value).toMatchObject({ ready: 1, craftable: 1, missing: 2 })
  })

  it('同步失败的长提示不能变成已同步', () => {
    const page = setup()
    const store = useMasteryStore()
    store.cultivateOk = false
    store.cultivateMsg = '森空岛接口读取失败，请稍后重试'
    expect(page.syncHint.value).not.toContain('已同步')
  })
  it('总览沿用已合并升变形态的本地统计口径', () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      { char_id: 'char_002_amiya', name: '阿米娅', elite: 2, recommendations: [], modules: [] },
      { char_id: 'char_1001_amiya2', name: '阿米娅', elite: 2, recommendations: [], modules: [] },
      { char_id: 'char_1037_amiya3', name: '阿米娅', elite: 2, recommendations: [], modules: [] }
    ]
    store.personalStatistics = {
      rarities: { 5: { owned: 1, elite2: 1, skills: { 3: 5 }, modules: { 1: 1, 3: 2 } } }
    }
    expect(page.rosterStats.value).toEqual({ owned: 1, elite2: 1, masteries: 5, modules: 3 })
  })

  it('构建训练队列、进行中训练与材料备齐度', async () => {
    const page = setup()
    const store = useMasteryStore()
    axios.get.mockResolvedValue({
      data: {
        plans: [
          {
            id: 1,
            char_id: 'char_a',
            skill_index: 0,
            status: 'training',
            target_level: 3,
            priority: 0
          },
          { id: 2, char_id: 'char_b', skill_index: 1, status: 'idle', target_level: 2, priority: 1 }
        ]
      }
    })
    store.recommendations = [
      {
        char_id: 'char_a',
        name: '甲',
        rarity: 6,
        elite: 2,
        level: 90,
        recommendations: [
          { skill_index: 0, skill_name: '技能一', current_level: 1, total_time: 7200 }
        ],
        modules: [],
        level_goals: []
      },
      {
        char_id: 'char_b',
        name: '乙',
        rarity: 5,
        elite: 1,
        level: 50,
        recommendations: [{ skill_index: 1, skill_name: '技能二', current_level: 0 }],
        modules: [],
        level_goals: []
      }
    ]
    store.goals = [{ char_id: 'char_b', module_id: 'elite2' }]
    await page.refreshPlanFromServer()
    await nextTick()

    expect(page.queueItems.value.map((item) => item.status)).toEqual(['training', 'idle', 'manual'])
    expect(page.trainingCard.value.op.name).toBe('甲')
    expect(page.trainingCard.value.target).toBe(3)
    expect(page.trainingCard.value.totalTime).toBe(7200)
    expect(page.nextUpItem.value.name).toBe('乙')

    page.planMaterials.value = {
      materials: [
        { id: 'm1', owned: 5, required: 3 },
        { id: 'm2', owned: 1, required: 2 }
      ],
      missing: [{ id: 'm2' }],
      craftable: false
    }
    expect(page.planMaterialStats.value).toMatchObject({
      ready: 1,
      total: 2,
      missing: 1,
      percent: 50
    })
  })

  it('推荐卡跳过已计划干员，并按公开样本排序', () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      {
        char_id: 'char_new',
        name: '新干员',
        rarity: 6,
        elite: 2,
        level: 1,
        skill_levels: [0],
        recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 0 }],
        modules: []
      },
      {
        char_id: 'char_planned',
        name: '已计划',
        rarity: 6,
        elite: 2,
        level: 1,
        skill_levels: [0],
        recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 0 }],
        modules: []
      }
    ]
    store.goals = [{ char_id: 'char_planned', module_id: 'elite2' }]
    page.survey.value = {
      operators: [{ charId: 'char_new', own: 100, skill1: { 0: 10, 3: 90 } }]
    }
    expect(page.recommendedCards.value.map((card) => card.operator.char_id)).toEqual(['char_new'])
    expect(page.recommendedCards.value[0].score).toBe(90)
    expect(page.recommendedCards.value[0].planned).toBe(false)
  })

  it('推荐卡只保留仍有未完成技能或模组的干员', () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      {
        char_id: 'char_completed',
        name: '已完成模组',
        rarity: 6,
        recommendations: [],
        modules: [{ id: 'completed', current_level: 3, max_level: 3 }]
      },
      {
        char_id: 'char_mastered',
        name: '已完成专精',
        rarity: 6,
        recommendations: [{ skill_index: 0, current_level: 3 }],
        modules: []
      },
      {
        char_id: 'char_module',
        name: '模组待升级',
        rarity: 6,
        recommendations: [],
        modules: [{ id: 'unfinished', current_level: 1, max_level: 3 }]
      },
      {
        char_id: 'char_skill',
        name: '专精待完成',
        rarity: 6,
        recommendations: [{ skill_index: 0, current_level: 1 }],
        modules: [{ id: 'completed', current_level: 3, max_level: 3 }]
      }
    ]

    expect(page.recommendedCards.value.map((card) => card.operator.char_id)).toEqual([
      'char_module',
      'char_skill'
    ])
  })

  it('推荐卡只按未练完技能算比例，已专三技能不再作为推荐理由', () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      {
        char_id: 'char_a',
        name: '圣聆初雪',
        rarity: 6,
        elite: 2,
        level: 60,
        skill_levels: [0, 3, 0],
        recommendations: [
          { skill_index: 0, skill_name: '一技能', current_level: 0 },
          { skill_index: 2, skill_name: '三技能', current_level: 0 }
        ],
        modules: []
      }
    ]
    page.survey.value = {
      operators: [
        {
          charId: 'char_a',
          own: 100,
          skill1: { 0: 94, 3: 6 },
          skill2: { 0: 5, 3: 95 },
          skill3: { 0: 40, 3: 60 }
        }
      ]
    }
    const card = page.recommendedCards.value[0]
    expect(card.target).toMatchObject({ kind: 'skill', index: 2, rate: 60 })
    expect(card.score).toBe(60)
  })

  it('值得练可按剩余模组解锁率重新排序', () => {
    const page = setup()
    const store = useMasteryStore()
    store.recommendations = [
      {
        char_id: 'char_module',
        name: '模组高',
        rarity: 6,
        skill_levels: [0],
        recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 0 }],
        modules: [{ id: 'mod_x', type: 'EXE-X', current_level: 0, max_level: 3 }]
      },
      {
        char_id: 'char_skill',
        name: '专三率高',
        rarity: 6,
        skill_levels: [0],
        recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 0 }],
        modules: []
      }
    ]
    page.survey.value = {
      operators: [
        { charId: 'char_module', own: 100, skill1: { 0: 70, 3: 30 }, modX: { 0: 10, 1: 90 } },
        { charId: 'char_skill', own: 100, skill1: { 0: 40, 3: 60 } }
      ]
    }
    expect(page.recommendedCards.value.map((card) => card.operator.char_id)).toEqual([
      'char_skill',
      'char_module'
    ])
    page.pickSort.value = 'module'
    expect(page.recommendedCards.value.map((card) => card.operator.char_id)).toEqual([
      'char_module',
      'char_skill'
    ])
  })

  it('详情派生技能目标、模组目标与基础技能状态', () => {
    const page = setup()
    const store = useMasteryStore()
    const base = {
      char_id: 'char_detail',
      name: '档案干员',
      rarity: 6,
      elite: 2,
      level: 60,
      main_skill_level: 5,
      max_phase: 2,
      supports_basic_skill7: true,
      basic_skill_summary: null,
      basic_skill_prerequisite: { elite: 1, level: 1 },
      recommendations: [{ skill_index: 0, skill_name: '技能', current_level: 1 }],
      modules: [],
      level_goals: []
    }
    store.recommendations = [base]
    page.operatorDetail.value = {
      ...base,
      basic_skill_summary: { materials: [{ id: '3301', required: 3, owned: 0 }] },
      recommendations: [
        {
          skill_index: 0,
          skill_name: '技能',
          current_level: 0,
          targets: {
            3: {
              target_level: 3,
              remaining_levels: 3,
              total_time: 3600,
              skill_material_summary: { materials: [] }
            }
          }
        }
      ],
      modules: [
        {
          id: 'module_1',
          name: '战术装备',
          type: 'MOD-X',
          current_level: 0,
          max_level: 3,
          elite: 2,
          level: 40,
          targets: { 3: { opening_summary: { materials: [] } } }
        }
      ]
    }
    page.expandedOperator.value = ['char_detail']

    expect(page.selectedSkillRows.value[0].target).toBe(3)
    expect(page.selectedSkillRows.value[0].targetOptions.map((option) => option.value)).toEqual([
      1, 2, 3
    ])
    expect(page.selectedModuleRows.value[0].target).toBe(3)
    expect(page.selectedModuleRows.value[0].summary).toEqual({ materials: [] })
    expect(page.selectedBasicState.value).toMatchObject({
      supported: true,
      planned: false,
      achieved: false,
      disabled: false,
      materials: { materials: [{ id: '3301', required: 3, owned: 0 }] }
    })
    expect(page.selectedBasicState.value.note).toContain('基础技能材料按干员只计算一次')
  })
})
