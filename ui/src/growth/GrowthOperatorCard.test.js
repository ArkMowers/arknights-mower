import { describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import GrowthOperatorCard from './GrowthOperatorCard.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))

const ORDINAL = ['一', '二', '三']

function recommendation(skillIndex, skillName, currentLevel) {
  return { skill_index: skillIndex, skill_name: skillName, current_level: currentLevel }
}

function operator(overrides = {}) {
  return {
    char_id: 'char_test',
    name: '测试干员',
    rarity: 6,
    profession: 'WARRIOR',
    elite: 2,
    level: 60,
    skill_levels: [0, 0, 0],
    modules: [],
    recommendations: [],
    ...overrides
  }
}

function setup(overrides = {}) {
  const props = reactive({
    operator: operator(),
    survey: null,
    planned: false,
    plannedCount: 0,
    rank: null,
    layout: 'grid',
    ...overrides
  })
  const scope = effectScope()
  const emit = vi.fn()
  const component = scope.run(() => GrowthOperatorCard.setup(props, { expose: vi.fn(), emit }))
  return { props, component, emit, stop: () => scope.stop() }
}

const fullOperator = () =>
  operator({
    skill_levels: [2, 3, 0],
    recommendations: [
      recommendation(0, '一技能·重进酒', 2),
      recommendation(1, '二技能·笑鸣瑟', 3),
      recommendation(2, '三技能·宁作吾', 0)
    ]
  })

const surveyRates = (rates, extra = {}) => ({
  skills: rates.map((rate, index) => ({ index, rate })),
  modules: [],
  ...extra
})

describe('干员卡技能段读数', () => {
  it('只为干员实际拥有的技能显示进度和专三计数', () => {
    const { component, stop } = setup({
      operator: operator({
        rarity: 5,
        skill_levels: [3, 3],
        recommendations: []
      })
    })
    expect(component.skillRows.value.map((row) => row.name)).toEqual(['一技能', '二技能'])
    expect(component.skills.value).toEqual([3, 3])
    expect(component.masteredCount.value).toBe(2)
    stop()
  })

  it('按已选比例门槛标出匹配的技能、模组与精英化目标', () => {
    const { props, component, stop } = setup({
      operator: operator({
        skill_levels: [0, 1],
        recommendations: [recommendation(0, '攻击强化', 0), recommendation(1, '突袭', 1)],
        modules: [{ id: 'mod_x', name: '防护装置', current_level: 0 }]
      }),
      survey: { skillHighlights: [1], moduleHighlights: ['mod_x'], eliteHighlight: true }
    })
    expect(component.skillRows.value.map((row) => row.highlighted)).toEqual([false, true])
    expect(component.surveyMatches.value).toBe(true)
    expect(component.surveyMatchLabel.value).toBe('达到筛选门槛：精英化目标、突袭、防护装置')
    props.survey = { skillHighlights: [], moduleHighlights: [], eliteHighlight: false }
    expect(component.skillRows.value.every((row) => !row.highlighted)).toBe(true)
    expect(component.surveyMatches.value).toBe(false)
    expect(component.surveyMatchLabel.value).toBe('')
    stop()
  })

  it('默认选中未专三技能里公开专三率最高的那个，而不是固定一技能', () => {
    const { component, stop } = setup({
      operator: fullOperator(),
      // 二技能公开率最高，但已专三；剩余技能中三技能 59.5% 最高。
      survey: surveyRates([5.9, 95.1, 59.5])
    })
    expect(component.activeSkillIndex.value).toBe(2)
    expect(component.statusLine.value).toEqual({ tone: 'low', text: '三技能·宁作吾 · 未专精' })
    expect(component.activeRate.value).toBe(59.5)
    expect(component.activeRateLabel.value).toBe('专三率')
    stop()
  })

  it('没有公开样本时默认选第一个未专三技能', () => {
    const { component, stop } = setup({ operator: fullOperator() })
    expect(component.activeSkillIndex.value).toBe(0)
    expect(component.statusLine.value).toEqual({ tone: 'warn', text: '一技能·重进酒 · 专二' })
    stop()
  })

  it('公开样本异步到达后自动改选推荐技能，用户点过技能段后不再自动改选', async () => {
    const { props, component, stop } = setup({ operator: fullOperator() })
    expect(component.activeSkillIndex.value).toBe(0)
    props.survey = surveyRates([30, 99, 60])
    await Promise.resolve()
    expect(component.activeSkillIndex.value).toBe(2)
    component.selectSkill(0)
    props.survey = surveyRates([30, 99, 80])
    await Promise.resolve()
    expect(component.activeSkillIndex.value).toBe(0)
    stop()
  })

  it('点击任意技能段只切换读数与底部比例，不改变技能等级或选中之外的数据', () => {
    const { component, stop } = setup({
      operator: fullOperator(),
      survey: surveyRates([30, 99, 60])
    })
    const before = component.skills.value.slice()
    component.selectSkill(1)
    expect(component.statusLine.value).toEqual({ tone: 'done', text: '二技能·笑鸣瑟 · 专三' })
    expect(component.activeRate.value).toBe(99)
    component.selectSkill(2)
    expect(component.statusLine.value).toEqual({ tone: 'low', text: '三技能·宁作吾 · 未专精' })
    expect(component.activeRate.value).toBe(60)
    expect(component.skills.value).toEqual(before)
    stop()
  })

  it('读数不再出现「还差 / 下一项」这类推测文案', () => {
    const { component, stop } = setup({ operator: fullOperator() })
    for (const index of [0, 1, 2]) {
      component.selectSkill(index)
      expect(component.statusLine.value.text).not.toMatch(/还差|下一项/)
    }
    stop()
  })

  it('读数颜色按专精等级区分：专三 accent、专一专二 warn、未专精 muted', () => {
    const { component, stop } = setup({
      operator: operator({
        skill_levels: [3, 2, 0],
        recommendations: [
          recommendation(0, '一技能', 3),
          recommendation(1, '二技能', 2),
          recommendation(2, '三技能', 0)
        ]
      })
    })
    component.selectSkill(0)
    expect(component.statusLine.value.tone).toBe('done')
    component.selectSkill(1)
    expect(component.statusLine.value.tone).toBe('warn')
    component.selectSkill(2)
    expect(component.statusLine.value.tone).toBe('low')
    stop()
  })

  it('没有 recommendations 与 skill_names 时技能名回退为序数技能名', () => {
    const { component, stop } = setup({ operator: operator({ skill_levels: [1, 0, 0] }) })
    expect(component.skillRows.value.map((row) => row.name)).toEqual(
      ORDINAL.map((name) => name + '技能')
    )
    expect(component.statusLine.value).toEqual({ tone: 'warn', text: '一技能 · 专一' })
    component.selectSkill(2)
    expect(component.statusLine.value).toEqual({ tone: 'low', text: '三技能 · 未专精' })
    stop()
  })

  it('已专三技能也能显示真名而不是只回退序数', () => {
    const { component, stop } = setup({
      operator: operator({
        skill_levels: [0, 3],
        skill_names: ['一技能·真名一', '二技能·真名二']
      })
    })
    expect(component.skillRows.value.map((row) => row.name)).toEqual([
      '一技能·真名一',
      '二技能·真名二'
    ])
    stop()
  })

  it('技能名按 skill_index 匹配而不是数组顺序', () => {
    const { component, stop } = setup({
      operator: operator({
        skill_levels: [3, 0, 1],
        recommendations: [
          recommendation(2, '三技能·宁作吾', 1),
          recommendation(0, '一技能·重进酒', 3)
        ]
      })
    })
    expect(component.skillRows.value.map((row) => row.name)).toEqual([
      '一技能·重进酒',
      '二技能',
      '三技能·宁作吾'
    ])
    stop()
  })

  it('聚合读数沿用专三计数，供「专三 x/3」标签使用', () => {
    const { component, stop } = setup({ operator: operator({ skill_levels: [3, 2, 3] }) })
    expect(component.masteredCount.value).toBe(2)
    stop()
  })

  it('每个技能段暴露状态 tone，供选中/悬停发光按专精等级取色', () => {
    const { component, stop } = setup({ operator: operator({ skill_levels: [3, 2, 0] }) })
    expect(component.skillRows.value.map((row) => row.tone)).toEqual(['done', 'warn', 'low'])
    component.selectSkill(1)
    expect(component.skillRows.value.map((row) => row.tone)).toEqual(['done', 'warn', 'low'])
    stop()
  })
})

describe('干员卡模组目标', () => {
  it('技能全部专三、只剩未满模组时默认显示模组目标与公开解锁率', () => {
    const { component, stop } = setup({
      operator: operator({
        skill_levels: [3, 3],
        recommendations: [],
        modules: [{ id: 'mod_x', type: 'EXE-X', current_level: 0, max_level: 3 }]
      }),
      survey: {
        skills: [
          { index: 0, rate: 90 },
          { index: 1, rate: 80 }
        ],
        modules: [{ id: 'mod_x', rate: 71.5 }]
      }
    })
    expect(component.moduleTarget.value).toMatchObject({ id: 'mod_x', rate: 71.5 })
    expect(component.statusLine.value).toEqual({ tone: 'low', text: 'EXE-X · 0/3' })
    expect(component.activeRate.value).toBe(71.5)
    expect(component.activeRateLabel.value).toBe('解锁率')
    stop()
  })

  it('模组目标段可切回模组读数', () => {
    const { component, stop } = setup({
      operator: operator({
        skill_levels: [3, 3],
        recommendations: [],
        modules: [{ id: 'mod_x', type: 'EXE-X', current_level: 2, max_level: 3 }]
      }),
      survey: { skills: [], modules: [{ id: 'mod_x', rate: 71.5 }] }
    })
    component.selectSkill(1)
    expect(component.activeRateLabel.value).toBe('专三率')
    component.selectModule()
    expect(component.activeRateLabel.value).toBe('解锁率')
    expect(component.activeRate.value).toBe(71.5)
    stop()
  })
})

describe('不支持专精的干员卡', () => {
  it('保留「等级养成」一行，不渲染技能读数', () => {
    const { component, stop } = setup({
      operator: operator({ rarity: 2, max_phase: 0, skill_levels: [0, 0, 0] })
    })
    expect(component.supportsMastery.value).toBe(false)
    expect(component.statusLine.value).toEqual({ tone: 'low', text: '等级养成' })
    stop()
  })

  it('有已解锁模组时显示「等级与模组养成」', () => {
    const { component, stop } = setup({
      operator: operator({
        rarity: 3,
        max_phase: 1,
        modules: [{ id: 'uniequip_001', current_level: 1 }]
      })
    })
    expect(component.supportsMastery.value).toBe(false)
    expect(component.statusLine.value).toEqual({ tone: 'low', text: '等级与模组养成' })
    stop()
  })
})
