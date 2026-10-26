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

const dailyTypes = [
  '日常任务',
  '公招',
  '森空岛签到',
  '信用购物',
  '领取邮件',
  '读取基报',
  '访问好友',
  '领取任务奖励'
]
const additionalTypes = [
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
      refs: { sub_plan: ref('main'), backup_plans: ref([]), operators: ref([]) }
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
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/task'),
      { task: { time: new Date(1792800000000), task_type: kind, plan: {}, meta_data: '' } },
      { timeout: 30000 }
    )
    expect(component.error.value).toBe(false)
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
  })

  it.each(dailyTypes)('submits daily selection %s from the second selector', async (kind) => {
    expect(component.dailyTaskOptions.some((option) => option.value === kind)).toBe(true)
    if (kind !== '日常任务') {
      expect(component.taskTypeOptions.some((option) => option.value === kind)).toBe(false)
    }
    component.task_type.value = '日常任务'
    component.daily_task.value = kind
    component.task_time.value = 1792800000000
    component.task_list.value = [{ room: 'train', operators: ['陈'] }]
    await component.saveTasks()
    expect(axios.post).toHaveBeenCalledWith(
      expect.stringContaining('/task'),
      { task: { time: new Date(1792800000000), task_type: kind, plan: {}, meta_data: '' } },
      { timeout: 30000 }
    )
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
  })

  it('resets daily selection to all and preserves independent stage selection', async () => {
    component.daily_task.value = '公招'
    component.task_type.value = '作战计划'
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task.task_type).toBe('作战计划')
    component.clear()
    expect(component.daily_task.value).toBe('日常任务')
  })

  function selectMastery() {
    component.task_type.value = '技能专精'
    component.mastery_operator.value = '陈'
    component.mastery_skill.value = 2
    component.mastery_target_level.value = 3
    component.mastery_support_mode.value = 'route'
  }

  it.each(['inserted', 'queued'])('saves a mastery plan with confirmed %s task', async (status) => {
    selectMastery()
    axios.post.mockResolvedValueOnce({
      data: { results: [{ status: 'added', id: 23, task: { status, reason: '任务已入队' } }] }
    })
    await component.saveTasks()
    expect(axios.post).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/mastery-plan'),
      {
        create_task: true,
        items: [{ name: '陈', skill_index: 1, target_level: 3, support_mode: 'route' }]
      },
      { timeout: 30000 }
    )
    expect(component.msg.value).toContain('已加入专精计划；任务已入队')
    expect(component.error.value).toBe(false)
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
    expect(component.saving.value).toBe(false)
  })

  it.each(['blocked', 'insufficient', undefined])(
    'does not claim queue success for an uninserted mastery task (%s)',
    async (status) => {
      selectMastery()
      axios.post.mockResolvedValueOnce({
        data: {
          results: [{ status: 'existing', id: 23, task: { status, reason: '材料不足' } }]
        }
      })
      await component.saveTasks()
      expect(component.msg.value).toContain('已在专精计划中；尚未生成任务：材料不足')
      expect(component.error.value).toBe(true)
      expect(state.mower.get_tasks).not.toHaveBeenCalled()
    }
  )

  it('does not insert another task for active training', async () => {
    selectMastery()
    axios.post.mockResolvedValueOnce({
      data: { results: [{ status: 'existing', task: { status: 'active', reason: '已在训练' } }] }
    })
    await component.saveTasks()
    expect(component.msg.value).toContain('未重复生成任务')
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })

  it('reports a rejected plan and allows retry after a network failure', async () => {
    selectMastery()
    axios.post.mockResolvedValueOnce({
      data: { results: [{ status: 'error', reason: '目标已完成' }] }
    })
    await component.saveTasks()
    expect(component.msg.value).toBe('目标已完成')
    expect(component.error.value).toBe(true)
    axios.post.mockRejectedValueOnce(new Error('网络中断'))
    await component.saveTasks()
    expect(component.msg.value).toContain('未确认提交结果')
    expect(component.saving.value).toBe(false)
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })

  it('blocks duplicate mastery submissions until the first completes', async () => {
    selectMastery()
    let resolve
    axios.post.mockReturnValueOnce(new Promise((done) => (resolve = done)))
    const first = component.saveTasks()
    await component.saveTasks()
    expect(axios.post).toHaveBeenCalledOnce()
    resolve({ data: { results: [{ status: 'error', reason: '稍后重试' }] } })
    await first
    expect(component.saving.value).toBe(false)
  })

  it('keeps room arrangements for an empty task', async () => {
    component.task_list.value = [{ room: 'train', operators: ['陈'] }]
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task.plan).toEqual({ train: ['陈'] })
  })

  it.each(['计划暂停', '计划停止'])('submits %s with a default ten minute window', async (kind) => {
    component.task_type.value = kind
    component.task_list.value = [{ room: 'train', operators: ['陈'] }]
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task).toMatchObject({
      task_type: kind,
      plan: {},
      meta_data: '',
      duration_minutes: 10,
      maintenance_mode: 'prepare'
    })
  })

  it('submits direct pause and resets the inputs to defaults', async () => {
    component.task_type.value = '计划暂停'
    component.duration_minutes.value = 25
    component.maintenance_mode.value = 'pause'
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task).toMatchObject({
      duration_minutes: 25,
      maintenance_mode: 'pause'
    })
    component.clear()
    expect(component.duration_minutes.value).toBe(10)
    expect(component.maintenance_mode.value).toBe('prepare')
  })

  it('always uses maintenance backups for server updates after choosing direct flash pause', async () => {
    component.maintenance_mode.value = 'pause'
    component.task_type.value = '计划停止'
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task.maintenance_mode).toBe('prepare')
  })

  it('submits zero duration for server shutdown without a timed start', async () => {
    component.task_type.value = '计划停止'
    component.duration_minutes.value = 0
    await component.saveTasks()
    expect(axios.post.mock.calls[0][1].task).toMatchObject({
      task_type: '计划停止',
      duration_minutes: 0,
      maintenance_mode: 'prepare'
    })
    component.clear()
    expect(component.duration_minutes.value).toBe(10)
  })

  it.each([null, 0, -1, 1.5, 10081])(
    'rejects invalid duration %s before submitting',
    async (duration) => {
      component.task_type.value = '计划暂停'
      component.duration_minutes.value = duration
      await component.saveTasks()
      expect(axios.post).not.toHaveBeenCalled()
      expect(component.error.value).toBe(true)
    }
  )

  it('shows server rejection without refreshing the queue', async () => {
    component.task_type.value = '日常任务'
    axios.post.mockResolvedValueOnce({ data: '添加任务失败！！请确保Mower正在运行' })
    await component.saveTasks()
    expect(component.error.value).toBe(true)
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })

  it.each(['日常任务', '技能专精'])(
    'shows the profile conflict message and retains the %s selection for reload',
    async (kind) => {
      selectMastery()
      component.task_type.value = kind
      component.daily_task.value = '领取邮件'
      axios.post.mockRejectedValueOnce({
        response: {
          status: 409,
          data: {
            error: 'configuration_changed',
            message: '当前配置已切换，请刷新页面后再操作'
          }
        }
      })
      await component.saveTasks()
      expect(component.msg.value).toBe('当前配置已切换，请刷新页面后再操作')
      expect(component.error.value).toBe(true)
      expect(component.task_type.value).toBe(kind)
      expect(component.daily_task.value).toBe('领取邮件')
      expect(component.mastery_operator.value).toBe('陈')
      expect(component.saving.value).toBe(false)
      expect(state.mower.get_tasks).not.toHaveBeenCalled()
    }
  )

  it('reports an unconfirmed ordinary submission and releases the saving state', async () => {
    component.task_type.value = '作战计划'
    axios.post.mockRejectedValueOnce(new Error('网络中断'))
    await component.saveTasks()
    expect(component.msg.value).toContain('未确认提交结果：网络中断')
    expect(component.error.value).toBe(true)
    expect(component.saving.value).toBe(false)
    expect(state.mower.get_tasks).not.toHaveBeenCalled()
  })

  it('blocks duplicate ordinary submissions until the first completes', async () => {
    component.task_type.value = '日常任务'
    let resolve
    axios.post.mockReturnValueOnce(new Promise((done) => (resolve = done)))
    const first = component.saveTasks()
    expect(component.saving.value).toBe(true)
    await component.saveTasks()
    expect(axios.post).toHaveBeenCalledOnce()
    resolve({ data: '添加任务成功！' })
    await first
    expect(component.saving.value).toBe(false)
    expect(state.mower.get_tasks).toHaveBeenCalledOnce()
  })
})
