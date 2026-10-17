import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import axios from 'axios'
import BasementSkill from './BasementSkill.vue'

const state = vi.hoisted(() => ({ load: null, skill: null }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('@/stores/basementSkill', () => ({ useBasementSkill: () => state }))
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
  state.skill = ref(catalog)
  state.load = vi.fn()
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
})
