import { readFileSync } from 'node:fs'
import { parse } from '@vue/compiler-sfc'
import { afterEach, expect, it, vi } from 'vitest'
import {
  compile,
  createRenderer,
  defineComponent,
  effectScope,
  h,
  nextTick,
  reactive,
  ssrContextKey
} from 'vue'
import axios from 'axios'
import GrowthHero from '@/growth/GrowthHero.vue'
import GrowthViewNav from '@/growth/GrowthViewNav.vue'
import GrowthLevelPlan from '@/components/GrowthLevelPlan.vue'
import GrowthSurveyFilters from '@/components/GrowthSurveyFilters.vue'
import GrowthCraftingOrder from '@/components/GrowthCraftingOrder.vue'
import GrowthOperatorCard from '@/growth/GrowthOperatorCard.vue'
import GrowthOperatorDetail from '@/growth/GrowthOperatorDetail.vue'
import GrowthOverview from '@/growth/GrowthOverview.vue'
import { i18n } from '@/i18n'
import { defaultSurveyFilters, surveyDimensions } from '@/utils/growthSurvey'
import { growthMetrics } from '@/utils/growthPlanning'
import { formatCompactNumber, materialDisplayName, professionName } from '@/growth/growthFormatters'
import { formatMaterialAmount } from '@/utils/masteryMaterials'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }))
const Container = defineComponent({
  setup:
    (_, { slots }) =>
    () =>
      h('section', [slots.default?.(), slots.header?.()])
})
const Empty = { render: () => null }
const Select = defineComponent({
  props: ['value', 'options'],
  emits: ['update:value'],
  setup:
    (props, { emit }) =>
    () =>
      h(
        'select',
        { value: props.value, onChange: (value) => emit('update:value', value) },
        props.options.map((option) => h('option', { value: option.value }, option.label))
      )
})
function client(component, relative) {
  const { descriptor } = parse(readFileSync(new URL(relative, import.meta.url), 'utf8'))
  return {
    ...component,
    ssrRender: undefined,
    setup: (props, context) => ({ ...component.setup(props, context) }),
    render: compile(descriptor.template.content, { hoistStatic: false }),
    components: {
      NButton: Container,
      NSwitch: Empty,
      NIcon: Empty,
      GrowthAvatar: Empty,
      HelpText: Empty,
      NAlert: Container,
      NCheckbox: Container,
      NSelect: Select,
      NTooltip: Container,
      NTag: Container,
      GrowthLevelPlan: Empty,
      GrowthOperatorCard: Empty,
      WorkshopStatus: Empty,
      MasteryMaterials: Empty
    }
  }
}
const node = (tag) => ({ tag, props: {}, children: [], text: '', parent: null })
function remove(element) {
  const siblings = element.parent?.children
  if (siblings) siblings.splice(siblings.indexOf(element), 1)
  element.parent = null
}
const renderer = createRenderer({
  createElement: node,
  createText: (text) => ({ ...node('#text'), text }),
  createComment: () => node('#comment'),
  setText: (element, text) => {
    element.text = text
  },
  setElementText: (element, text) => {
    element.text = text
    element.children = []
  },
  parentNode: (element) => element.parent,
  nextSibling: (element) => element.parent?.children[element.parent.children.indexOf(element) + 1],
  patchProp: (element, key, _old, value) => {
    element.props[key] = value
  },
  insert(element, parent, anchor) {
    remove(element)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove
})
const all = (element) => [element, ...element.children.flatMap(all)]
const text = (element) => element.text + element.children.map(text).join('')
const mounted = []
function mount(component, props = {}) {
  const root = node('root')
  const app = renderer.createApp(component, props)
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount(root)
  mounted.push(app)
  return { root, vm: app._instance.setupState }
}
afterEach(() => {
  for (const app of mounted.splice(0)) app.unmount()
  i18n.global.locale.value = 'zh-CN'
  vi.resetAllMocks()
})

it('updates mounted hero, navigation and official names while retaining emitted view IDs and source training data', async () => {
  const training = {
    entry: { status: 'training' },
    op: { name: '能天使' },
    rec: { skill_name: '三技能·过载模式', current_level: 1 },
    target: 3
  }
  const original = structuredClone(training)
  const { root } = mount(client(GrowthHero, '../growth/GrowthHero.vue'), {
    training,
    operators: [],
    totalGoals: 2
  })
  const selected = vi.fn()
  const navigation = mount(client(GrowthViewNav, '../growth/GrowthViewNav.vue'), {
    modelValue: 'materials',
    'onUpdate:modelValue': selected
  })
  expect(text(root)).toContain('养成规划')
  i18n.global.locale.value = 'en-US'
  await nextTick()
  expect(text(root)).toContain('Growth Planner')
  expect(text(root)).toContain('Exusiai is training S3 · Overloading Mode, targeting M3.')
  expect(text(navigation.root)).toContain('Materials')
  const operators = all(navigation.root).find(
    (element) => element.props.role === 'tab' && text(element).includes('Operators')
  )
  operators.props.onClick()
  expect(selected).toHaveBeenCalledExactlyOnceWith('operators')
  i18n.global.locale.value = 'ja-JP'
  await nextTick()
  expect(text(root)).toContain('育成計画')
  expect(text(root)).toContain('エクシアは「スキル3 · オーバーロード」を訓練中です。')
  expect(text(root)).toContain('Current training')
  expect(text(navigation.root)).toContain('オペレーター')
  expect(training).toEqual(original)
})

it('updates mounted survey options and delayed shared labels without changing filter enums or sample data', async () => {
  const filters = defaultSurveyFilters()
  filters.sort = 'recommendation'
  const changed = vi.fn()
  const { root } = mount(client(GrowthSurveyFilters, '../components/GrowthSurveyFilters.vue'), {
    modelValue: filters,
    survey: { operators: [{ own: 7 }] },
    'onUpdate:modelValue': changed
  })
  expect(text(root)).toContain('大数据筛选')
  i18n.global.locale.value = 'en-US'
  await nextTick()
  expect(text(root)).toContain('Survey Filters')
  expect(text(root)).toContain('Remaining M3 rate first')
  expect(text(root)).toContain('Remaining module unlock rate first')
  expect(surveyDimensions[0].label).toBe('M3 rate')
  expect(growthMetrics[0].label).toBe('Maxed Operators')
  const select = all(root).find((element) => element.tag === 'select')
  expect(select.props.value).toBe('recommendation')
  select.props.onChange('level')
  expect(changed).toHaveBeenCalledExactlyOnceWith({ ...filters, sort: 'level' })
  expect(filters.sort).toBe('recommendation')
  i18n.global.locale.value = 'ja-JP'
  await nextTick()
  expect(text(root)).toContain('統計で絞り込む')
  expect(surveyDimensions[0].label).toBe('特化III率')
  expect(all(root).find((element) => element.tag === 'select').props.value).toBe('recommendation')
})

it('switches a mounted card and dossier through four languages while retaining remaining-target selection and raw data', async () => {
  const operator = {
    char_id: 'char_103_angel',
    name: '能天使',
    rarity: 6,
    profession: 'SNIPER',
    elite: 2,
    level: 60,
    max_phase: 2,
    skill_levels: [3, 1, 0],
    skill_names: ['一技能·冲锋模式', '二技能·扫射模式', '三技能·过载模式'],
    recommendations: [
      { skill_index: 1, skill_name: '二技能·扫射模式', current_level: 1 },
      { skill_index: 2, skill_name: '三技能·过载模式', current_level: 0 }
    ],
    modules: []
  }
  const survey = {
    skills: [
      { index: 0, rate: 99 },
      { index: 1, rate: 30 },
      { index: 2, rate: 60 }
    ],
    modules: [],
    elite2: 90
  }
  const source = structuredClone({ operator, survey })
  const opened = vi.fn()
  const card = mount(client(GrowthOperatorCard, '../growth/GrowthOperatorCard.vue'), {
    operator,
    survey,
    onOpen: opened
  })
  const dossier = mount(client(GrowthOperatorDetail, '../growth/GrowthOperatorDetail.vue'), {
    operator,
    survey,
    completedSkills: [{ index: 0, name: operator.skill_names[0], current: 3, rate: 99 }]
  })
  for (const [locale, name, selectedSkill, completedSkill, highestLabel] of [
    ['zh-CN', '能天使', '三技能·过载模式', '一技能·冲锋模式', '最高专三率'],
    ['en-US', 'Exusiai', 'S3 · Overloading Mode', 'S1 · Charging Mode', 'Highest M3 rate'],
    ['ja-JP', 'エクシア', 'スキル3 · オーバーロード', 'スキル1 · アサルトモード', '最高特化III率'],
    ['zh-TW', '能天使', '三技能 · 超載模式', '一技能 · 衝鋒模式', '最高專三率']
  ]) {
    i18n.global.locale.value = locale
    await nextTick()
    expect(text(card.root)).toContain(name)
    expect(text(card.root)).toContain(selectedSkill)
    expect(text(card.root)).toContain('60.0%')
    expect(card.vm.activeSkillIndex).toBe(2)
    expect(card.vm.recommended).toMatchObject({ index: 2, name: '三技能·过载模式', rate: 60 })
    expect(text(dossier.root)).toContain(highestLabel)
    expect(text(dossier.root)).toContain(completedSkill)
    expect(text(dossier.root)).toContain('99.0%')
    expect(dossier.vm.surveyStats[0]).toMatchObject({ rate: 99, detail: completedSkill })
  }
  card.vm.selectSkill(0)
  i18n.global.locale.value = 'en-US'
  await nextTick()
  expect(card.vm.activeSkillIndex).toBe(0)
  expect(card.vm.activeRate).toBe(99)
  expect(card.vm.statusLine.text).toBe('S1 · Charging Mode · M3')
  card.vm.open()
  expect(opened).toHaveBeenCalledExactlyOnceWith(operator)
  expect({ operator, survey }).toEqual(source)
})

it('localizes remaining module goals and recommendation controls in four languages while retaining sort values and source labels', async () => {
  const operator = {
    name: '麦哲伦',
    rarity: 6,
    max_phase: 2,
    skill_levels: [3, 3, 3],
    recommendations: [],
    modules: [
      { id: 'uniequip_002_mgllan', name: '专业无人机操作模块', current_level: 0, max_level: 3 }
    ]
  }
  const survey = {
    skills: [{ index: 0, rate: 99 }],
    modules: [{ id: 'uniequip_002_mgllan', rate: 71.5 }]
  }
  const source = structuredClone({ operator, survey })
  const card = mount(client(GrowthOperatorCard, '../growth/GrowthOperatorCard.vue'), {
    operator,
    survey
  })
  const sorted = vi.fn()
  const overview = mount(client(GrowthOverview, '../growth/GrowthOverview.vue'), {
    pickSort: 'module',
    'onUpdate:pick-sort': sorted
  })
  const filters = defaultSurveyFilters()
  const filter = mount(client(GrowthSurveyFilters, '../components/GrowthSurveyFilters.vue'), {
    modelValue: filters,
    survey: { operators: [{ own: 7 }] }
  })
  for (const [locale, moduleName, unlock, masterySort, moduleSort] of [
    ['zh-CN', '专业无人机操作模块', '解锁率', '剩余专三率', '剩余模组解锁率'],
    [
      'en-US',
      'Drone Control Module.P',
      'Unlock rate',
      'Remaining M3 rate',
      'Remaining module unlock rate'
    ],
    [
      'ja-JP',
      'ドローン操作専門モジュール',
      '解放率',
      '未達成スキルの特化III率',
      '未完成モジュールの解放率'
    ],
    ['zh-TW', '專業無人機操作模組', '解鎖率', '剩餘專三率', '剩餘模組解鎖率']
  ]) {
    i18n.global.locale.value = locale
    await nextTick()
    expect(card.vm.activeModule).toBe(true)
    expect(text(card.root)).toContain(moduleName)
    expect(text(card.root)).toContain(unlock)
    expect(card.vm.activeRate).toBe(71.5)
    expect(card.vm.activeRateTitle).toContain(moduleName)
    expect(text(overview.root)).toContain(masterySort)
    expect(text(overview.root)).toContain(moduleSort)
    expect(text(overview.root)).toContain('Suggested next')
    expect(text(filter.root)).toContain(masterySort)
    expect(text(filter.root)).toContain(moduleSort)
    expect(overview.vm.pickSortOptions.map((option) => option.value)).toEqual([
      'mastery',
      'module',
      'rarity',
      'level'
    ])
    expect(filter.vm.sortOptions.map((option) => option.value)).toEqual([
      'default',
      'recommendation',
      'module',
      'level'
    ])
  }
  all(overview.root)
    .find((element) => element.tag === 'select')
    .props.onChange('mastery')
  expect(sorted).toHaveBeenCalledExactlyOnceWith('mastery')
  expect({ operator, survey }).toEqual(source)
})

it('keeps level-goal IDs and source labels while an existing target and mounted controls switch language', async () => {
  const operator = {
    char_id: 'char_002_amiya',
    rarity: 5,
    elite: 2,
    level: 10,
    level_goals: [
      { id: 'elite2', elite: 2, level: 1, label: '精二 1 级' },
      { id: 'elite2_max', elite: 2, level: 80, label: '精二 80 级' }
    ]
  }
  const original = structuredClone(operator)
  const applyTarget = vi.fn(async () => {})
  const { root, vm } = mount(client(GrowthLevelPlan, '../components/GrowthLevelPlan.vue'), {
    operator,
    selectedKey: 'elite2_max',
    applyTarget
  })
  i18n.global.locale.value = 'en-US'
  await nextTick()
  expect(text(root)).toContain('Elite 2 Lv. 80 (max)')
  expect(vm.draftKey).toBe('elite2_max')
  const clear = all(root).find(
    (element) => element.tag === 'button' && text(element).includes('Clear')
  )
  clear.props.onClick()
  await nextTick()
  expect(applyTarget).toHaveBeenCalledExactlyOnceWith(null)
  expect(operator).toEqual(original)
  expect(professionName('近卫')).toBe('Guard')
  expect(formatCompactNumber(23000)).toBe('23.0k')
  expect(formatMaterialAmount(23000)).toBe('23k')
  expect(materialDisplayName('growth_exp', '作战记录经验')).toBe('EXP')
})

it('localizes fixed growth-plan label wrappers without rewriting source records or the saved order payload', async () => {
  const items = [
    {
      key: 'skill:test',
      kind: 'skill',
      char_id: 'test',
      char_name: '用户干员',
      label: '用户技能 · 专二',
      locked: false,
      plan_id: 7
    },
    {
      key: 'goal:test',
      kind: 'goal',
      char_id: 'test',
      char_name: '用户干员',
      label: '自定义模组 · 模组 3 级',
      module_id: 'custom',
      locked: false
    }
  ]
  const original = structuredClone(items)
  const scope = effectScope()
  try {
    const page = scope.run(() =>
      GrowthCraftingOrder.setup(reactive({ recommendations: [], count: 2 }), {
        expose: vi.fn(),
        emit: vi.fn()
      })
    )
    page.accept({ items })
    i18n.global.locale.value = 'en-US'
    expect(page.itemLabel(items[0])).toBe('用户技能 · M2')
    expect(page.itemLabel(items[1])).toBe('自定义模组 · Module Lv. 3')
    const module = {
      kind: 'goal',
      module_id: 'uniequip_002_mgllan',
      label: '专业无人机操作模块 · 模组 2 级'
    }
    expect(page.itemLabel(module)).toBe('Drone Control Module.P · Module Lv. 2')
    i18n.global.locale.value = 'ja-JP'
    expect(page.itemLabel(module)).toContain('ドローン操作専門モジュール')
    expect(module.module_id).toBe('uniequip_002_mgllan')
    expect(module.label).toBe('专业无人机操作模块 · 模组 2 级')
    i18n.global.locale.value = 'en-US'
    page.commitDrag([...items].reverse())
    axios.put.mockResolvedValue({ data: { items: [...items].reverse() } })
    await page.save()
    expect(axios.put).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/growth-crafting-order'),
      { order: ['goal:test', 'skill:test'] }
    )
    expect(items).toEqual(original)
  } finally {
    scope.stop()
  }
})
