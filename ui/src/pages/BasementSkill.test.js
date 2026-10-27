import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope } from 'vue'
import axios from 'axios'
import BasementSkill from './BasementSkill.vue'
import { useBasementSkill } from '@/stores/basementSkill'
import { i18n } from '@/i18n'
import bundledCatalog from '../../../arknights_mower/data/building_skill.json'

const state = useBasementSkill()
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
})
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})
describe('基建技能森空岛数据读取', () => {
  it('keeps the full catalog and raw filter values while searching current translated skill descriptions', () => {
    state.skill.value = bundledCatalog
    const page = setup()
    const before = JSON.stringify(state.skill.value)
    const identities = page.filteredItems.value.map((operator) => [
      operator.key,
      operator.childSkill.map((skill) => [skill.skill_key, skill.skill_level])
    ])
    expect(page.filteredSkillCount.value).toBe(929)
    i18n.global.locale.value = 'en-US'
    expect(page.filteredSkillCount.value).toBe(929)
    expect(
      page.filteredItems.value.map((operator) => [
        operator.key,
        operator.childSkill.map((skill) => [skill.skill_key, skill.skill_level])
      ])
    ).toEqual(identities)
    page.facility_select.value = '回收站'
    page.des_select.value = 'material conversion efficiency'
    expect(page.filteredItems.value.map((operator) => operator.avatar)).toContain('旅骨')
    expect(
      page.filteredItems.value
        .flatMap((operator) => operator.childSkill)
        .every((skill) => skill.roomType === '回收站')
    ).toBe(true)
    page.des_select.value = '材料转化效率'
    expect(page.filteredItems.value.map((operator) => operator.avatar)).toContain('旅骨')
    i18n.global.locale.value = 'ja-JP'
    expect(page.des_select.value).toBe('材料转化效率')
    expect(page.facility_select.value).toBe('回收站')
    page.des_select.value = '素材の変換効率'
    expect(page.filteredItems.value.map((operator) => operator.avatar)).toContain('旅骨')
    expect(JSON.stringify(state.skill.value)).toBe(before)
    expect(axios.get).not.toHaveBeenCalled()
  })

  it('updates a current frontend load error with the locale and retains its original diagnostic parameter', async () => {
    const page = setup()
    axios.get.mockRejectedValueOnce(new Error('原始服务诊断'))
    await page.loadOwnedOperators()
    expect(page.error.value).toContain('读取森空岛练度失败')
    i18n.global.locale.value = 'en-US'
    expect(page.error.value).toContain('Could not read')
    expect(page.error.value).toContain('原始服务诊断')
  })
  it('translates the real empty snapshot prompt while preserving the backend snapshot', async () => {
    const payload = {
      has_data: false,
      operators: [],
      base_conditions: {},
      message: '请同步森空岛干员数据'
    }
    axios.get.mockResolvedValueOnce({ data: payload })
    const page = setup()
    await page.loadOwnedOperators()
    for (const [locale, text] of [
      ['ja-JP', 'SKLand のオペレーターデータを同期してください'],
      ['en-US', 'Sync operator data from SKLand'],
      ['zh-TW', '請同步森空島幹員資料']
    ]) {
      i18n.global.locale.value = locale
      expect(page.dataMessage.value).toBe(text)
      expect(page.snapshot.value).toEqual(payload)
    }
    expect(axios.get).toHaveBeenCalledOnce()
    expect(payload.message).toBe('请同步森空岛干员数据')
  })

  it('localizes the failed sync prompt and retains the existing roster', async () => {
    const payload = { success: false, message: '未同步到干员数据，请检查森空岛账号及官服/B服选择' }
    const page = setup()
    page.snapshot.value = owned
    axios.get.mockResolvedValueOnce({ data: payload })
    await page.syncCultivate()
    for (const locale of ['en-US', 'ja-JP', 'zh-TW']) {
      i18n.global.locale.value = locale
      expect(page.error.value).toBe(i18n.global.t('operatorSync.emptyRoster'))
      expect(page.snapshot.value).toEqual(owned)
    }
    expect(axios.get).toHaveBeenCalledOnce()
    expect(payload.message).toBe('未同步到干员数据，请检查森空岛账号及官服/B服选择')
  })

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
