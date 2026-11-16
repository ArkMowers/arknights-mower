import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import axios from 'axios'
import BasementSkill from './BasementSkill.vue'
import { useBasementSkill } from '@/stores/basementSkill'

const state = useBasementSkill()
const planState = reactive({ plan: {}, facility_levels: {} })
vi.mock('@/stores/plan', () => ({ usePlanStore: () => planState }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('vue', async (original) => ({
  ...(await original()),
  onMounted: vi.fn(),
  useSSRContext: () => ({ modules: new Set() })
}))
const catalog = [
  {
    name: '能天使',
    child_skill: [
      { skill_key: 0, skill_level: 0, skillname: '物流', roomType: '贸易站', des: '效率' }
    ]
  }
]
const owned = {
  has_data: true,
  operators: [
    {
      name: '能天使',
      owned: true,
      phase: 0,
      level: 1,
      skills: [{ skill_key: 0, skill_level: 0, status: 'active' }]
    }
  ]
}
function setup() {
  const scope = effectScope()
  const component = scope.run(() => BasementSkill.setup({}, { expose: vi.fn() }))
  scope.stop()
  return component
}
beforeEach(() => {
  vi.clearAllMocks()
  state.skill.value = catalog
  state.snapshot.value = null
  planState.plan = {}
  planState.facility_levels = {}
})
describe('基建技能森空岛数据读取', () => {
  it('默认不显示持有标签，进入读取只请求本地快照', async () => {
    const page = setup()
    expect(page.skill_items.value[0].ownership).toBe('unknown')
    expect(page.ownershipLabels.unknown).toBeUndefined()
    axios.get.mockResolvedValue({ data: owned })
    await page.loadOwnedOperators()
    expect(axios.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/basement-skill/operators')
    )
    expect(page.skill_items.value[0].ownership).toBe('owned')
  })
  it('显式同步成功后再读本地解析状态', async () => {
    const page = setup()
    axios.get
      .mockResolvedValueOnce({ data: { success: true } })
      .mockResolvedValueOnce({ data: owned })
    await page.syncCultivate()
    expect(axios.get.mock.calls.map(([url]) => url.split('/').at(-1))).toEqual([
      'cultivate-fetch',
      'operators'
    ])
    expect(page.skill_items.value[0].childSkill[0].status).toBe('active')
    expect(page.syncing.value).toBe(false)
  })
  it('同步失败展示具体原因并保留现有快照', async () => {
    const page = setup()
    page.snapshot.value = owned
    axios.get.mockResolvedValue({ data: { success: false, message: '未配置森空岛账号' } })
    await page.syncCultivate()
    expect(page.error.value).toBe('未配置森空岛账号')
    expect(axios.get).toHaveBeenCalledOnce()
    expect(page.skill_items.value[0].ownership).toBe('owned')
    expect(page.syncing.value).toBe(false)
  })
  it('读取失败仍展示技能目录、不显示缺失的状态', async () => {
    const page = setup()
    axios.get.mockRejectedValue(new Error('连接失败'))
    await page.loadOwnedOperators()
    expect(page.error.value).toContain('连接失败')
    expect(page.filteredItems.value).toHaveLength(1)
    expect(page.skillStatusLabels[page.skill_items.value[0].childSkill[0].status]).toBeUndefined()
    expect(page.loading.value).toBe(false)
  })
  it('优先取当前主排班，最高宿舍等级覆盖快照，缺失字段保留快照', () => {
    planState.plan = {
      room_1_1: { name: '制造站', product: 'gold', plans: [] },
      room_1_2: { name: '发电站', plans: [] },
      dormitory_1: { name: '', plans: [{ agent: 'Free' }] },
      dormitory_2: { name: '', plans: [{ agent: 'Free' }] }
    }
    planState.facility_levels = { room_1_1: 3, room_1_2: 3, dormitory_1: 1, dormitory_2: 4 }
    state.snapshot.value = { base_conditions: { dormLevel: 2, power: 3, droneCap: 200 } }
    const before = JSON.stringify(planState)
    const page = setup()
    expect(page.baseConditions.value).toMatchObject({
      power: 1,
      factories: 1,
      dormLevel: 4,
      dormLevels: 5,
      droneCap: 200
    })
    expect(page.conditionSource.value).toContain('当前主排班')
    expect(JSON.stringify(planState)).toBe(before)
  })
})
