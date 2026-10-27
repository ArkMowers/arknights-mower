import { describe, expect, it } from 'vitest'
import {
  RECOMMEND_SORT_OPTIONS,
  compareRecommendedCards,
  operatorSkillRows,
  recommendationScore,
  hasRemainingTarget,
  recommendedTarget,
  remainingModuleRate,
  remainingModuleTargets,
  remainingSkillRate,
  remainingSkillTargets,
  sortRecommendedCards,
  surveyModuleRate,
  surveySkillRate
} from './growthRecommendation'

function operator(overrides = {}) {
  return {
    char_id: 'char_test',
    name: '测试干员',
    rarity: 6,
    elite: 2,
    level: 60,
    skill_levels: [0, 0, 0],
    skill_names: [],
    recommendations: [],
    modules: [],
    ...overrides
  }
}

function survey(overrides = {}) {
  return {
    skills: [
      { index: 0, current: 0, rate: 10 },
      { index: 1, current: 0, rate: 80 },
      { index: 2, current: 0, rate: 45 }
    ],
    modules: [],
    ...overrides
  }
}

describe('公开样本读数', () => {
  it('按技能索引与模组 id 取公开比例', () => {
    expect(surveySkillRate(survey(), 1)).toBe(80)
    expect(surveySkillRate(survey(), 9)).toBeNull()
    expect(surveyModuleRate({ modules: [{ id: 'm1', rate: 66.6 }] }, 'm1')).toBe(66.6)
    expect(surveyModuleRate({ modules: [] }, 'm1')).toBeNull()
  })
})

describe('全部技能行', () => {
  it('优先用推荐行真名，其次 skill_names，最后序数回退', () => {
    const rows = operatorSkillRows(
      operator({
        skill_levels: [3, 0, 1],
        skill_names: ['一技能·真名一', '二技能·真名二'],
        recommendations: [{ skill_index: 2, skill_name: '三技能·真名三', current_level: 1 }]
      })
    )
    expect(rows.map((row) => row.name)).toEqual(['一技能·真名一', '二技能·真名二', '三技能·真名三'])
    expect(rows.map((row) => row.current)).toEqual([3, 0, 1])
  })

  it('没有 skill_names 与推荐行时回退为序数技能名', () => {
    expect(operatorSkillRows(operator({ skill_levels: [0, 0] })).map((row) => row.name)).toEqual([
      '一技能',
      '二技能'
    ])
  })
})

describe('剩余目标', () => {
  it('remainingSkillTargets 只保留未专三技能', () => {
    const targets = remainingSkillTargets(
      operator({
        recommendations: [
          { skill_index: 0, skill_name: '一技能', current_level: 2 },
          { skill_index: 1, skill_name: '二技能', current_level: 3 }
        ]
      }),
      survey()
    )
    expect(targets.map((target) => target.index)).toEqual([0])
    expect(targets[0]).toMatchObject({ kind: 'skill', current: 2, rate: 10 })
  })

  it('remainingModuleTargets 只保留未满级模组', () => {
    const targets = remainingModuleTargets(
      operator({
        modules: [
          { id: 'mod_a', type: 'EXE-X', current_level: 1, max_level: 3 },
          { id: 'mod_b', type: 'EXE-Y', current_level: 3, max_level: 3 }
        ]
      }),
      { modules: [{ id: 'mod_a', rate: 12 }] }
    )
    expect(targets).toHaveLength(1)
    expect(targets[0]).toMatchObject({
      kind: 'module',
      id: 'mod_a',
      current: 1,
      target: 3,
      rate: 12
    })
  })
})

describe('推荐目标', () => {
  it('取未专三技能里公开专三率最高者，而不是全部技能里的最高值', () => {
    const op = operator({
      skill_levels: [0, 3, 0],
      recommendations: [
        { skill_index: 0, skill_name: '一技能', current_level: 0 },
        { skill_index: 2, skill_name: '三技能', current_level: 0 }
      ]
    })
    // 二技能公开率 95 已专三，不能作为推荐理由；剩余技能里三技能 59.5 最高。
    const rates = [5.9, 95.1, 59.5]
    const result = recommendedTarget(op, { skills: rates.map((rate, index) => ({ index, rate })) })
    expect(result).toMatchObject({ kind: 'skill', index: 2, name: '三技能', rate: 59.5 })
    expect(recommendationScore(op, { skills: rates.map((rate, index) => ({ index, rate })) })).toBe(
      59.5
    )
  })

  it('剩余技能都没有公开样本时回退到未满模组', () => {
    const op = operator({
      recommendations: [{ skill_index: 0, skill_name: '一技能', current_level: 0 }],
      modules: [{ id: 'mod_a', type: 'LOR-D', current_level: 0, max_level: 3 }]
    })
    expect(
      recommendedTarget(op, {
        skills: [{ index: 0, rate: null }],
        modules: [{ id: 'mod_a', rate: 71.5 }]
      })
    ).toMatchObject({ kind: 'module', id: 'mod_a', rate: 71.5 })
  })

  it('hasRemainingTarget 只看本地剩余目标，不依赖公开样本', () => {
    expect(
      hasRemainingTarget(operator({ recommendations: [{ skill_index: 0, current_level: 1 }] }))
    ).toBe(true)
    expect(
      hasRemainingTarget(operator({ modules: [{ id: 'm', current_level: 0, max_level: 3 }] }))
    ).toBe(true)
    expect(hasRemainingTarget(operator({ skill_levels: [3] }))).toBe(false)
  })

  it('全部练完或没有公开样本时没有推荐目标', () => {
    const done = operator({
      skill_levels: [3, 3],
      modules: [{ id: 'mod_a', current_level: 3, max_level: 3 }]
    })
    expect(recommendedTarget(done, survey())).toBeNull()
    const noSamples = operator({ recommendations: [{ skill_index: 0, current_level: 0 }] })
    expect(recommendedTarget(noSamples, { skills: [{ index: 0, rate: null }] })).toBeNull()
  })
})

describe('剩余比例与排序', () => {
  const cards = [
    {
      operator: operator({ char_id: 'a', name: '甲', rarity: 6, elite: 2, level: 90 }),
      survey: { skills: [{ index: 0, rate: 20 }], modules: [{ id: 'mod_a', rate: 91 }] }
    },
    {
      operator: operator({ char_id: 'b', name: '乙', rarity: 5, elite: 1, level: 70 }),
      survey: { skills: [{ index: 0, rate: 60 }], modules: [] }
    },
    {
      operator: operator({ char_id: 'c', name: '丙', rarity: 4, elite: 2, level: 40 }),
      survey: { skills: [], modules: [{ id: 'mod_c', rate: 30 }] }
    }
  ]
  cards[0].operator.recommendations = [{ skill_index: 0, current_level: 0 }]
  cards[0].operator.modules = [{ id: 'mod_a', current_level: 0, max_level: 3 }]
  cards[1].operator.recommendations = [{ skill_index: 0, current_level: 0 }]
  cards[2].operator.modules = [{ id: 'mod_c', current_level: 0, max_level: 3 }]

  it('剩余专三率只统计未专三技能', () => {
    expect(remainingSkillRate(cards[0].operator, cards[0].survey)).toBe(20)
    expect(remainingSkillRate(cards[2].operator, cards[2].survey)).toBeNull()
  })

  it('剩余模组解锁率只统计未满模组', () => {
    expect(remainingModuleRate(cards[0].operator, cards[0].survey)).toBe(91)
    expect(remainingModuleRate(cards[1].operator, cards[1].survey)).toBeNull()
  })

  it('默认按剩余专三率排序，只有模组的干员排在最后', () => {
    expect(sortRecommendedCards(cards, 'mastery').map((card) => card.operator.char_id)).toEqual([
      'b',
      'a',
      'c'
    ])
  })

  it('切到剩余模组解锁率后按模组比例排序', () => {
    expect(sortRecommendedCards(cards, 'module').map((card) => card.operator.char_id)).toEqual([
      'a',
      'c',
      'b'
    ])
  })

  it('稀有度与等级排序保持已有限定条件', () => {
    expect(sortRecommendedCards(cards, 'rarity').map((card) => card.operator.char_id)).toEqual([
      'a',
      'b',
      'c'
    ])
    expect(sortRecommendedCards(cards, 'level').map((card) => card.operator.char_id)).toEqual([
      'a',
      'c',
      'b'
    ])
    expect(compareRecommendedCards(cards[1], cards[0], 'mastery')).toBeLessThan(0)
  })

  it('排序条件文案与用户口径一致', () => {
    expect(RECOMMEND_SORT_OPTIONS.map((option) => option.value)).toEqual([
      'mastery',
      'module',
      'rarity',
      'level'
    ])
    expect(RECOMMEND_SORT_OPTIONS.map((option) => option.label)).toEqual([
      '剩余专三率',
      '剩余模组解锁率',
      '稀有度',
      '等级'
    ])
  })
})
