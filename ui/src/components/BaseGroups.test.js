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
  it('未拥有干员默认按满练估算，保留已拥有实际练度和选择', async () => {
    const { page, scope, props } = setup([
      {
        avatar: '能天使',
        ownership: 'owned',
        childSkill: [{ skill_key: 0, skill_level: 0, status: 'active' }]
      },
      { avatar: '蕾缪安', ownership: 'unowned', childSkill: [] }
    ])
    const group = page.groups.find((group) => group.id === 'builtin-exusiai')
    const previous = JSON.stringify(props.items)
    for (const name of group.core) page.toggleMember(group, name)
    await nextTick()
    expect(page.estimates.value[group.id].valid).toBe(true)
    expect(page.estimates.value[group.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 65,
      unit: '%'
    })
    expect(page.ownershipSummary(group)).toBe('已拥有 1 / 2')
    expect(JSON.stringify(props.items)).toBe(previous)
    await nextTick()
    expect(page.estimates.value[group.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 65,
      unit: '%'
    })
    await nextTick()
    expect(page.estimates.value[group.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 65,
      unit: '%'
    })
    expect(page.selections.value[group.id]).toEqual(group.core)
    scope.stop()
  })
  it('无练度先用满练度假设，后续有效同步立即使用实际技能', async () => {
    const { page, scope, props } = setup()
    const group = page.groups.find((group) => group.id === 'builtin-exusiai')
    for (const name of group.core) page.toggleMember(group, name)
    expect(page.estimates.value[group.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 80,
      unit: '%'
    })
    expect(page.estimates.value[group.id].assumptions).toEqual(group.core)
    props.items = group.core.map((avatar) => ({
      avatar,
      ownership: 'owned',
      childSkill: [{ skill_key: 0, skill_level: 0, status: 'active' }]
    }))
    await nextTick()
    expect(page.estimates.value[group.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 40,
      unit: '%'
    })
    expect(page.estimates.value[group.id].assumptions).toEqual([])
    scope.stop()
  })
  it('核心、备选、挂件都可反复勾选，筛选保留选择', async () => {
    const { page, scope } = setup()
    const group = page.groups.find((group) => group.id === 'builtin-automation')
    for (const section of page.memberSections(group)) {
      for (const member of section.members) {
        const selected = page.selections.value[group.id].includes(member.name)
        page.toggleMember(group, member.name)
        expect(page.selections.value[group.id].includes(member.name)).toBe(!selected)
        page.toggleMember(group, member.name)
        expect(page.selections.value[group.id].includes(member.name)).toBe(selected)
      }
    }
    page.toggleMember(group, group.core[0])
    const selected = [...page.selections.value[group.id]]
    page.search.value = '能天使'
    await nextTick()
    page.search.value = ''
    await nextTick()
    expect(page.selections.value[group.id]).toEqual(selected)
    scope.stop()
  })
  it('设施快照自动填充，后续同步立即更新，跑单干员不参与勾选', async () => {
    const { page, scope, props } = setup([], { power: 3, factories: 4, recruits: 0, dormLevel: 2 })
    const smoke = page.groups.find((group) => group.title === '人间烟火')
    const perception = page.groups.find((group) => group.title === '感知信息')
    expect(page.conditions.value[smoke.id]).toMatchObject({ power: 3, factories: 4, recruits: 0 })
    expect(page.conditions.value[perception.id].dormLevel).toBe(2)
    page.conditions.value['single-玛露西尔'].cuisineDorm = 5
    props.baseConditions = { power: 2, dormLevel: 4 }
    await nextTick()
    expect(page.conditions.value[smoke.id].power).toBe(2)
    expect(page.conditions.value[perception.id].dormLevel).toBe(4)
    expect(page.conditions.value['single-莱欧斯-会客'].cuisineDorm).toBe(4)
    expect(page.conditions.value['single-玛露西尔'].cuisineDorm).toBe(5)
    const runOrder = page.allOptions.find((group) => group.id === 'builtin-run-order')
    page.toggleMember(runOrder, '但书')
    expect(page.selections.value[runOrder.id]).toEqual([])
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
    await nextTick()
    expect(page.visibleGroups.value).toHaveLength(4)
    expect(page.visibleGroups.value.every((group) => group.facility === '金属')).toBe(true)
    for (const operation of Object.values(storage)) expect(operation).not.toHaveBeenCalled()
    scope.stop()
  })
  it('默认仅选中挂件，无练度自动使用满练度假设，筛选保留勾选', async () => {
    const { page, scope } = setup()
    const smoke = page.groups.find((group) => group.title === '人间烟火')
    expect(page.selections.value[smoke.id]).toEqual(['余', '年'])
    expect(page.conditions.value[smoke.id].dorm).toBe(20)
    page.toggleMember(smoke, '桑葚')
    await nextTick()
    expect(page.estimates.value[smoke.id].valid).toBe(true)
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
  it('勾选干员后显示用尽平均，不提供最高效率开关', async () => {
    const { page, scope } = setup()
    const elite = page.groups.find((group) => group.id === 'builtin-tianmao')
    const cloud = page.groups.find((group) => group.id === 'builtin-cloud')
    page.toggleMember(elite, '机械师')
    for (const name of ['红云', '稀音', '帕拉斯']) page.toggleMember(cloud, name)
    await nextTick()
    expect(page.estimates.value[elite.id].metrics).toContainEqual({
      label: '经验制造生产力',
      value: 36.75,
      unit: '%'
    })
    expect(page.estimates.value[cloud.id].metrics).toContainEqual({
      label: '经验制造生产力',
      value: 105.1875,
      unit: '%'
    })
    expect(page.conditions.value[elite.id]).not.toHaveProperty('average')
    expect(page.conditions.value[cloud.id]).not.toHaveProperty('average')
    scope.stop()
  })
  it('孑默认跟随同步练度，手选阶段保持优先并可切回自动', async () => {
    const { page, scope, props } = setup([
      {
        avatar: '孑',
        ownership: 'owned',
        childSkill: [
          { skill_key: 0, skill_level: 0, status: 'active' },
          { skill_key: 1, skill_level: 0, status: 'locked' }
        ]
      }
    ])
    const group = page.groups.find((group) => group.id === 'builtin-karlan')
    for (const name of group.core) page.toggleMember(group, name)
    expect(page.conditions.value[group.id].jayeStage).toBe('跟随森空岛')
    const efficiency = () =>
      page.estimates.value[group.id].metrics.find((metric) => metric.label === '贸易订单效率').value
    await nextTick()
    expect(efficiency()).toBe(145)
    page.conditions.value[group.id].jayeStage = '精一及以上'
    await nextTick()
    expect(efficiency()).toBe(129)
    page.conditions.value[group.id].jayeStage = '未精英化'
    props.items[0].childSkill[1].status = 'active'
    props.baseConditions = { jayeStage: '跟随森空岛' }
    await nextTick()
    expect(page.conditions.value[group.id].jayeStage).toBe('未精英化')
    expect(efficiency()).toBe(145)
    page.conditions.value[group.id].jayeStage = '跟随森空岛'
    await nextTick()
    expect(efficiency()).toBe(129)
    props.items[0].childSkill[1].status = 'locked'
    await nextTick()
    expect(efficiency()).toBe(145)
    props.items = []
    await nextTick()
    expect(page.estimates.value[group.id].valid).toBe(true)
    expect(efficiency()).toBe(129)
    expect(page.estimates.value[group.id].assumptions).toContain('孑')
    page.conditions.value[group.id].jayeStage = '精一及以上'
    await nextTick()
    expect(efficiency()).toBe(129)
    page.applyRecommended(group)
    await nextTick()
    expect(page.conditions.value[group.id].jayeStage).toBe('未精英化')
    expect(efficiency()).toBe(145)
    scope.stop()
  })
  it('孑的方案切换保留各自选择，单人视图和筛选不写入存储', async () => {
    const { page, scope } = setup()
    const parent = page.groups.find((g) => g.id === 'builtin-karlan')
    page.chooseVariant(parent, 'builtin-jaye-siracusa')
    const variant = page.displayedGroups.value.find((g) => g.parentId === parent.id)
    page.applyRecommended(variant)
    await nextTick()
    expect(page.conditions.value[parent.id].jayeStage).toBe('未精英化')
    expect(page.estimates.value[variant.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 138,
      unit: '%'
    })
    expect(page.variantOptions(variant).map((option) => option.efficiency)).toEqual([
      145, 138, 127, 126, 131
    ])
    page.chooseVariant(variant, parent.id)
    expect(page.selections.value[parent.id]).toEqual([])
    page.chooseVariant(parent, variant.id)
    expect(page.selections.value[variant.id]).toEqual(variant.recommended)
    page.view.value = 'singles'
    page.facility.value = '贸易'
    await nextTick()
    expect(page.visibleGroups.value.map((g) => g.title)).toEqual([
      '跑单干员',
      '吉星',
      '冻河',
      '孑',
      '深巡',
      '伺夜',
      '贝洛内',
      '风絮',
      '空弦',
      '赫德雷',
      '石英',
      '雷狼龙S空爆',
      '雪雉',
      '能天使',
      '海蒂'
    ])
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
    expect(page.visibleGroups.value).toHaveLength(25)
    expect(page.visibleGroups.value[0].title).toBe('人间烟火')
    scope.stop()
  })
  it('散件按设施、产物与当前效率归组，修改条件后重新分组', async () => {
    const { page, scope } = setup()
    page.view.value = 'singles'
    page.facility.value = '经验'
    const exp = page.recommendationSections.value.find((section) => section.metric.value === 35)
    expect(exp.groups.map((group) => group.title)).toEqual([
      '断罪者',
      '裂响',
      '酒神',
      '食铁兽',
      '弑君者'
    ])
    expect(page.recommendationSections.value.find((section) => section.average).metric.value).toBe(
      36.75
    )
    page.facility.value = '贸易'
    const quartz = () =>
      page.recommendationSections.value.find((section) =>
        section.groups.some((group) => group.id === 'single-石英')
      )
    expect(page.recommendationSections.value[0]).toMatchObject({ roster: true })
    expect(quartz().metric.value).toBe(36)
    page.conditions.value['single-石英'].formulaKinds = 2
    await nextTick()
    expect(quartz().metric.value).toBe(34)
    scope.stop()
  })
  it('中枢按具体作用归类，逐人保留全部效果，联动成员移到组合', () => {
    const { page, scope } = setup()
    page.view.value = 'singles'
    page.facility.value = '中枢'
    expect(page.recommendationSections.value.map((section) => section.title)).toEqual([
      '中枢 · 制造支援',
      '中枢 · 贸易支援',
      '中枢 · 制造 / 贸易切换',
      '中枢 · 办公支援',
      '中枢 · 会客支援'
    ])
    const tradeSection = page.recommendationSections.value.find(
      (section) => section.effect === '贸易支援'
    )
    const ascalon = tradeSection.groups.find((group) => group.title === '阿斯卡纶')
    expect(
      page.visibleMetrics(ascalon, tradeSection).map((metric) => [metric.label, metric.value])
    ).toEqual([
      ['所有贸易站·每站订单效率', 7],
      ['专精训练速度', 5]
    ])
    expect(page.visibleGroups.value.map((group) => group.title)).not.toContain('维什戴尔')
    page.view.value = 'groups'
    expect(page.visibleGroups.value.map((group) => group.title)).toEqual([
      '巴别塔中枢',
      '玛恩纳中枢减耗',
      'Ave Mujica 乐队'
    ])
    scope.stop()
  })
  it('能天使与新约能天使在同一拉特兰条目切换，条件独立，不会套用孑标题', () => {
    const { page, scope } = setup()
    const parent = page.groups.find((group) => group.id === 'builtin-exusiai')
    expect(parent.title).toBe('拉特兰贸易')
    expect(page.variantOptions(parent).map((group) => group.id)).toEqual([
      'builtin-exusiai',
      'builtin-laterano'
    ])
    page.chooseVariant(parent, 'builtin-laterano')
    const selected = page.displayedGroups.value.find((group) => group.parentId === parent.id)
    expect(page.groupDisplayTitle(selected)).toBe('拉特兰贸易')
    page.applyRecommended(selected)
    expect(page.estimates.value[selected.id].metrics).toContainEqual({
      label: '贸易订单效率',
      value: 105,
      unit: '%'
    })
    expect(page.groups.some((group) => group.id === 'builtin-laterano')).toBe(false)
    for (const group of page.allOptions.filter((group) => group.facility === '中枢')) {
      expect(
        page
          .visibleEstimateFields(group)
          .some((field) => ['factories', 'trade', 'power', 'eligibleGoldLines'].includes(field.key))
      ).toBe(false)
    }
    scope.stop()
  })
  it('宿舍恢复备注覆盖当前全部相关散件，支持搜索并在同档优先，锁定技能不冒充已生效', async () => {
    const { page, props, scope } = setup()
    page.view.value = 'singles'
    page.search.value = '宿舍恢复'
    expect(page.visibleGroups.value.map((group) => group.title).sort()).toEqual(
      [
        '冻河',
        '虎狼丸',
        '珊比',
        '裂响',
        '响石',
        '遥',
        '缪尔赛思',
        '斥罪',
        '断罪者',
        '阿米娅'
      ].sort()
    )
    expect(page.dormRecovery.value['single-裂响'].description).toBe('自身+0.55')
    page.search.value = ''
    page.facility.value = '发电'
    const power = page.recommendationSections.value.find((section) => section.metric.value === 25)
    expect(power.groups.map((group) => group.title)).toEqual(['缪尔赛思', '承曦格雷伊'])
    props.items = [
      {
        avatar: '缪尔赛思',
        ownership: 'owned',
        childSkill: [
          { skill_key: 0, skill_level: 0, status: 'locked' },
          { skill_key: 1, skill_level: 0, status: 'active' }
        ]
      }
    ]
    await nextTick()
    expect(page.dormRecovery.value['single-缪尔赛思'].available).toBe(false)
    expect(
      page.recommendationSections.value
        .find((section) => section.metric.value === 25)
        .groups.map((group) => group.title)
    ).toEqual(['承曦格雷伊', '缪尔赛思'])
    scope.stop()
  })
})
