import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import TaskDialog from './TaskDialog.vue'
import axios from 'axios'

const state = vi.hoisted(() => ({ plan: null, config: null, mower: null }))
vi.mock('pinia', () => ({ storeToRefs: (store) => store.refs }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() }),
  inject: (key, fallback) => {
    if (key === 'show_task' || key === 'add_task') return ref(true)
    if (key === 'planStore') return state.plan
    return fallback
  }
}))
vi.mock('@/stores/plan', () => ({ usePlanStore: () => state.plan }))
vi.mock('@/stores/config', () => ({ useConfigStore: () => state.config }))
vi.mock('@/stores/mower', () => ({ useMowerStore: () => state.mower }))
vi.mock('naive-ui', () => ({ useMessage: () => ({ warning: vi.fn() }) }))
vi.mock('axios', () => ({ default: { post: vi.fn() } }))
vi.mock('@/utils/op_select', () => ({ render_op_option: vi.fn(), render_op_label: vi.fn() }))

const additionalTypes = [
  '日常任务',
  '公招',
  '森空岛签到',
  '信用购物',
  '领取邮件',
  '读取基报',
  '访问好友',
  '领取任务奖励',
  '作战计划',
  '集成战略 (MAA)',
  '保全派驻 (MAA)',
  '生息演算 (MAA)',
  '生息演算',
  '隐秘战线'
]

describe('manual task dialog', () => {
  let scope
  let component
  beforeEach(() => {
    state.plan = {
      plan: {},
      refs: { sub_plan: ref('main'), backup_plans: ref({}), operators: ref([]) }
    }
    state.config = { refs: { workshop_settings: ref([]) } }
    state.mower = { get_tasks: vi.fn() }
    axios.post.mockReset().mockResolvedValue({ data: '添加任务成功！' })
    scope = effectScope()
    component = scope.run(() => TaskDialog.setup({}, { expose: vi.fn() }))
  })
  afterEach(() => scope.stop())

  it.each(additionalTypes)('submits %s at the chosen time without a stale roster', async (kind) => {
    expect(component.taskTypeOptions.some((option) => option.value === kind)).toBe(true)
    component.task_type.value = kind
    component.task_time.value = 1792800000000
    component.task_list.value = [{ room: 'train', operators: ['陈'] }]
    await component.saveTasks()
    expect(axios.post).toHaveBeenCalledWith(expect.stringContaining('/task'), {
      task: { time: new Date(1792800000000), task_type: kind, plan: {}, meta_data: '' }
    })
    expect(component.error.value).toBe(false)
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
  })

  it('keeps room arrangements for an empty task', async () => {
    component.task_list.value = [{ room: 'train', operators: ['陈'] }]
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task.plan).toEqual({ train: ['陈'] })
  })

  it('shows server rejection without refreshing the queue', async () => {
    component.task_type.value = '日常任务'
    axios.post.mockResolvedValueOnce({ data: '添加任务失败！！请确保Mower正在运行' })
    await component.saveTasks()
    expect(component.error.value).toBe(true)
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })
})
