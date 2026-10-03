import { afterEach, expect, it, vi } from 'vitest'
import { createApp, ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import axios from 'axios'
import { usePlanStore, useRescuePlanStore } from './plan'

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
let stores = []
afterEach(() => {
  stores.forEach((store) => store.$dispose())
  stores = []
  vi.clearAllMocks()
})

it('救急页首次加载前不保存，主副表保存不改动正常排班', async () => {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  app.provide('loaded', ref(false))
  const [normal, rescue] = app.runWithContext(() => [usePlanStore(), useRescuePlanStore()])
  stores = [normal, rescue]
  axios.post.mockResolvedValue({ data: {} })
  let resolveLoad
  axios.get.mockReturnValue(
    new Promise((resolve) => {
      resolveLoad = resolve
    })
  )
  const loading = rescue.load_plan()
  await nextTick()
  expect(axios.post).not.toHaveBeenCalled()
  resolveLoad({
    data: {
      conf: {},
      plan1: { central: { plans: [{ agent: '红' }] } },
      backup_plans: [
        {
          name: '副表',
          conf: {},
          plan: { central: { plans: [{ agent: '初雪' }] } },
          trigger: { left: '1', operator: '==', right: '1' }
        }
      ]
    }
  })
  await loading
  rescue.plan.central.plans[0].agent = '砾'
  rescue.backup_plans[0].plan.central.plans[0].agent = '斑点'
  await nextTick()
  await rescue.wait_for_plan_save()
  expect(normal.plan).toEqual({})
  expect(normal.backup_plans).toEqual([])
  expect(axios.post.mock.calls.every(([url]) => url.endsWith('/rescue-plan'))).toBe(true)
  const saved = axios.post.mock.lastCall[1]
  expect(saved.plan1.central.plans[0].agent).toBe('砾')
  expect(saved.backup_plans[0].plan.central.plans[0].agent).toBe('斑点')
})

it('救急宿舍保留空床索引，副表空白位置继承主表', async () => {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  app.provide('loaded', ref(false))
  const store = app.runWithContext(() => useRescuePlanStore())
  stores = [store]
  axios.post.mockResolvedValue({ data: {} })
  axios.get.mockResolvedValue({
    data: { conf: {}, plan1: {}, backup_plans: [{ name: '副表', conf: {}, plan: {}, trigger: {} }] }
  })
  await store.load_plan()
  store.plan.dormitory_1.plans[2].agent = '菲亚梅塔'
  store.plan.dormitory_1.plans[2].replacement = ['歌蕾蒂娅']
  store.backup_plans[0].plan.dormitory_1.plans[0].agent = '杜林'
  const saved = store.build_plan()
  expect(saved.plan1.dormitory_1.plans.map((slot) => slot.agent)).toEqual([
    'Free',
    'Free',
    '菲亚梅塔',
    'Free',
    'Free'
  ])
  expect(saved.backup_plans[0].plan.dormitory_1.plans.map((slot) => slot.agent)).toEqual([
    '杜林',
    'Current',
    'Current',
    'Current',
    'Current'
  ])
  expect(saved.backup_plans[0].plan).not.toHaveProperty('dormitory_2')
  expect(saved.plan1.dormitory_1.plans[2].replacement).toEqual(['歌蕾蒂娅'])
})

it('导入主表只复制设施，保留救急副表与独立配置', async () => {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  app.provide('loaded', ref(false))
  const store = app.runWithContext(() => useRescuePlanStore())
  stores = [store]
  axios.post.mockResolvedValue({ data: {} })
  axios.get.mockResolvedValueOnce({
    data: {
      conf: { resting_priority: '红' },
      plan1: {},
      backup_plans: [{ name: '救急副表', conf: {}, plan: {}, trigger: {} }]
    }
  })
  await store.load_plan()
  const backups = JSON.stringify(store.backup_plans)
  const source = {
    central: { plans: [{ agent: '阿米娅', group: '中枢', replacement: ['红'] }] },
    dormitory_1: {
      plans: [
        { agent: '杜林' },
        { agent: 'Free' },
        { agent: '菲亚梅塔', replacement: ['歌蕾蒂娅'] }
      ]
    }
  }
  axios.get.mockResolvedValueOnce({ data: { plan1: source, conf: {}, backup_plans: [] } })
  store.sub_plan = 0
  await store.import_main_plan()
  await nextTick()
  await store.wait_for_plan_save()
  expect(axios.get.mock.lastCall[0]).toMatch(/\/plan$/)
  expect(store.sub_plan).toBe('main')
  expect(store.plan.central.plans[0]).toEqual(source.central.plans[0])
  expect(store.plan.dormitory_1.plans[2].replacement).toEqual(['歌蕾蒂娅'])
  expect(JSON.stringify(store.backup_plans)).toBe(backups)
  expect(store.resting_priority).toEqual(['红'])
  expect(axios.post.mock.calls.every(([url]) => url.endsWith('/rescue-plan'))).toBe(true)
  store.plan.central.plans[0].agent = '陈'
  expect(source.central.plans[0].agent).toBe('阿米娅')
  axios.get.mockRejectedValueOnce(new Error('offline'))
  await expect(store.import_main_plan()).rejects.toThrow('offline')
  expect(store.plan.central.plans[0].agent).toBe('陈')
})

it('清空救急主副表绑组与普通替班，保留全部跑单干员和充能对象', async () => {
  const app = createApp({})
  const pinia = createPinia()
  setActivePinia(pinia)
  app.use(pinia)
  app.provide('loaded', ref(false))
  const [normal, rescue] = app.runWithContext(() => [usePlanStore(), useRescuePlanStore()])
  stores = [normal, rescue]
  const runners = ['但书', '龙舌兰', '佩佩', '可露希尔']
  const source = {
    room_1_1: {
      name: '贸易站',
      plans: [{ agent: '阿米娅', group: '一组', replacement: ['红', ...runners, '砾'] }]
    },
    dormitory_1: {
      plans: [
        { agent: '菲亚梅塔', group: '充能组', replacement: ['歌蕾蒂娅'] },
        { agent: '杜林', group: '宿管组', replacement: ['芬'] }
      ]
    }
  }
  normal.plan = JSON.parse(JSON.stringify(source))
  const backups = [
    {
      name: '副表',
      conf: {},
      trigger: { left: '1' },
      task: {},
      plan: {
        room_1_1: { plans: [{ agent: '但书', group: '另一组', replacement: ['砾', ...runners] }] },
        dormitory_1: { plans: [{ agent: 'Current', group: '继承组', replacement: ['斯卡蒂'] }] }
      }
    }
  ]
  axios.post.mockResolvedValue({ data: {} })
  axios.get.mockResolvedValueOnce({
    data: {
      conf: {},
      plan1: JSON.parse(JSON.stringify(source)),
      backup_plans: backups
    }
  })
  await rescue.load_plan()
  rescue.clear_rescue_bindings()
  expect(normal.plan).toEqual(source)
  expect(rescue.plan.room_1_1.plans[0]).toEqual({
    agent: '阿米娅',
    group: '',
    replacement: runners
  })
  expect(rescue.plan.dormitory_1.plans[0].replacement).toEqual(['歌蕾蒂娅'])
  expect(rescue.plan.dormitory_1.plans[1].replacement).toEqual([])
  expect(rescue.backup_plans[0].plan.room_1_1.plans[0]).toEqual({
    agent: '但书',
    group: '',
    replacement: runners
  })
  expect(rescue.backup_plans[0].plan.dormitory_1.plans[0]).toEqual({
    agent: 'Current',
    group: '',
    replacement: ['斯卡蒂']
  })
  expect(rescue.backup_plans[0].trigger).toEqual({ left: '1' })
  const cleared = JSON.stringify(rescue.build_plan())
  rescue.clear_rescue_bindings()
  expect(JSON.stringify(rescue.build_plan())).toBe(cleared)
  axios.post.mockResolvedValue({ data: {} })
  await rescue.save_plan()
  expect(axios.post.mock.lastCall[0]).toMatch(/\/rescue-plan$/)
  normal.clear_rescue_bindings()
  expect(normal.plan).toEqual(source)
})
