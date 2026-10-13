import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick, reactive } from 'vue'
import BaseGroups from './BaseGroups.vue'
import { builtinGroups } from '@/data/baseGroups'

vi.mock('vue', async (original) => ({
  ...(await original()),
  onMounted: vi.fn(),
  useSSRContext: () => ({ modules: new Set() })
}))
function setup(items = [], baseConditions = {}) {
  const scope = effectScope()
  const props = reactive({ items, baseConditions })
  const page = scope.run(() => BaseGroups.setup(props, { expose: vi.fn() }))
  return { page, scope, props }
}
afterEach(() => vi.unstubAllGlobals())

describe('基建组合只读浏览', () => {
  it('设施快照自动填充，后续同步立即更新，跑单干员不参与勾选', async () => {
    const { page, scope, props } = setup([], { power: 3, factories: 4, recruits: 0, dormLevel: 2 })
    const smoke = page.groups.find((group) => group.title === '人间烟火')
    const perception = page.groups.find((group) => group.title === '感知信息')
    expect(page.conditions.value[smoke.id]).toMatchObject({ power: 3, factories: 4, recruits: 0 })
    expect(page.conditions.value[perception.id].dormLevel).toBe(2)
    props.baseConditions = { power: 2, dormLevel: 4 }
    await nextTick()
    expect(page.conditions.value[smoke.id].power).toBe(2)
    expect(page.conditions.value[perception.id].dormLevel).toBe(4)
    page.toggleMember(page.groups[0], '但书')
    expect(page.selections.value[page.groups[0].id]).toEqual([])
    scope.stop()
  })
  it('忽略旧自定义数据，进入及筛选不访问浏览器存储', async () => {
    const storage = {
      getItem: vi.fn(() => JSON.stringify({ groups: [{ id: 'custom-test', title: '旧组合' }] })),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn()
    }
    vi.stubGlobal('window', { localStorage: storage })
    vi.stubGlobal('localStorage', storage)
    const { page, scope } = setup()
    expect(page.groups).toBe(builtinGroups)
    page.facility.value = '金属'
    page.toggleMember(page.groups[1], '桑葚')
    page.conditions.value[page.groups[1].id].dorm = 10
    page.maxLevel.value = true
    await nextTick()
    expect(page.visibleGroups.value).toHaveLength(3)
    expect(page.visibleGroups.value.every((group) => group.facility === '金属')).toBe(true)
    for (const operation of Object.values(storage)) expect(operation).not.toHaveBeenCalled()
    scope.stop()
  })
  it('默认仅选中挂件，勾选和满练度开关更新估算，筛选保留勾选', async () => {
    const { page, scope } = setup()
    const smoke = page.groups.find((group) => group.title === '人间烟火')
    expect(page.maxLevel.value).toBe(false)
    expect(page.selections.value[smoke.id]).toEqual(['余', '年'])
    expect(page.conditions.value[smoke.id].dorm).toBe(20)
    page.toggleMember(smoke, '桑葚')
    await nextTick()
    expect(page.estimates.value[smoke.id].valid).toBe(false)
    page.maxLevel.value = true
    await nextTick()
    expect(page.estimates.value[smoke.id].metrics).toContainEqual({
      label: '人间烟火',
      value: 20,
      unit: '点'
    })
    page.search.value = '自动化'
    await nextTick()
    page.search.value = ''
    await nextTick()
    expect(page.selections.value[smoke.id]).toContain('桑葚')
    page.toggleMember(smoke, '桑葚')
    expect(page.selections.value[smoke.id]).toEqual(['余', '年'])
    scope.stop()
  })
  it('每组的平均效率开关独立更新计算', async () => {
    const { page, scope } = setup()
    const elite = page.groups.find((group) => group.id === 'builtin-tianmao')
    page.maxLevel.value = true
    page.toggleMember(elite, '机械师')
    await nextTick()
    expect(page.estimates.value[elite.id].metrics).toContainEqual({
      label: '经验制造生产力',
      value: 36,
      unit: '%'
    })
    page.conditions.value[elite.id].average = false
    await nextTick()
    expect(page.estimates.value[elite.id].metrics).toContainEqual({
      label: '经验制造生产力',
      value: 40,
      unit: '%'
    })
    expect(page.conditions.value['builtin-cloud'].average).toBe(true)
    scope.stop()
  })
  it('筛选直接展示全部匹配组合，角色与条件保留', async () => {
    const { page, scope } = setup()
    expect(page.ownershipSummary(page.groups[0])).toBe('持有状态未知')
    page.search.value = '不存在'
    await nextTick()
    expect(page.visibleGroups.value).toEqual([])
    page.facility.value = '金属'
    page.search.value = '自动化'
    await nextTick()
    expect(page.visibleGroups.value.map((group) => group.title)).toEqual(['自动化'])
    const sections = page.memberSections(page.visibleGroups.value[0])
    expect(sections[0].members.map((member) => member.name)).toEqual([
      '森蚺',
      '温蒂',
      '承曦格雷伊',
      '清流',
      '冬时'
    ])
    expect(sections[1].title).toBe('备选干员')
    expect(sections[2].title).toBe('挂件')
    expect(sections[2].members[0]).toMatchObject({
      name: 'Lancet-2',
      note: '0心情'
    })
    page.facility.value = null
    page.search.value = ''
    await nextTick()
    expect(page.visibleGroups.value).toHaveLength(20)
    expect(page.visibleGroups.value[0].title).toBe('跑单干员')
    scope.stop()
  })
})
