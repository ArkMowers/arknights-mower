import { describe, expect, it } from 'vitest'
import {
  annotateBasementSkills,
  filterBasementSkills,
  ownershipLabels,
  skillStatusLabels
} from './basementSkills'

const catalog = [
  {
    name: '能天使',
    child_skill: [
      {
        skill_key: 0,
        skill_level: 0,
        skillname: '企鹅物流·α',
        roomType: '贸易站',
        des: '订单效率<@cc.vup>+20%</>'
      },
      {
        skill_key: 0,
        skill_level: 1,
        skillname: '物流专家',
        roomType: '贸易站',
        des: '订单效率<@cc.vup>+35%</>'
      },
      {
        skill_key: 1,
        skill_level: 0,
        skillname: '加工测试',
        roomType: '加工站',
        des: '副产品概率提升'
      }
    ]
  },
  {
    name: '泡泡',
    child_skill: [
      { skill_key: 0, skill_level: 0, skillname: '囤积者', roomType: '制造站', des: '仓库容量增加' }
    ]
  }
]
const snapshot = {
  has_data: true,
  operators: [
    {
      name: '能天使',
      owned: true,
      phase: 2,
      level: 20,
      skills: [
        { skill_key: 0, skill_level: 0, status: 'replaced' },
        { skill_key: 0, skill_level: 1, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    },
    { name: '泡泡', owned: false, skills: [] }
  ]
}

describe('基建技能持有与解锁筛选', () => {
  it.each([
    null,
    { has_data: false, operators: snapshot.operators },
    { has_data: true, operators: [] }
  ])('未确认数据不推断未拥有或未解锁', (data) => {
    const items = annotateBasementSkills(catalog, data)
    expect(items.map((item) => item.ownership)).toEqual(['unknown', 'unknown'])
    expect(
      items.flatMap((item) => item.childSkill).every((skill) => skill.status === 'unknown')
    ).toBe(true)
    expect(ownershipLabels.unknown).toBeUndefined()
    expect(skillStatusLabels.unknown).toBeUndefined()
  })
  it('按服务器解析的技能版本区分解锁、替换和持有状态', () => {
    const items = annotateBasementSkills(catalog, snapshot)
    expect(items[0].ownership).toBe('owned')
    expect(items[0].progression).toBe('精2 20级')
    expect(items[0].childSkill.map((skill) => skill.status)).toEqual([
      'replaced',
      'active',
      'locked'
    ])
    expect(items[1].ownership).toBe('unowned')
    expect(items[1].childSkill[0].status).toBe('unowned')
    expect(catalog[0].child_skill[0].status).toBeUndefined()
  })
  it('持有已确认但练度或技能信息缺失时不显示练度标签', () => {
    const items = annotateBasementSkills(catalog, {
      has_data: true,
      operators: [{ name: '能天使', owned: true, phase: null, level: null, skills: [] }]
    })
    expect(items[0].ownership).toBe('owned')
    expect(items[0].progression).toBe('')
    expect(items[0].childSkill.every((skill) => skill.status === 'unknown')).toBe(true)
    expect(skillStatusLabels[items[0].childSkill[0].status]).toBeUndefined()
  })
  it('设施和解锁筛选只显示命中的技能行，重新计算行跨度', () => {
    const items = annotateBasementSkills(catalog, snapshot)
    const filtered = filterBasementSkills(items, {
      facility: '贸易站',
      status: 'active',
      ownership: 'owned'
    })
    expect(filtered).toHaveLength(1)
    expect(filtered[0].span).toBe(1)
    expect(filtered[0].childSkill.map((skill) => skill.skillname)).toEqual(['物流专家'])
    expect(items[0].childSkill).toHaveLength(3)
    expect(filterBasementSkills(items, { facility: '制造站', status: 'active' })).toEqual([])
  })
  it('名称和技能描述支持拼音，搜索结果不保留无关技能行', () => {
    const items = annotateBasementSkills(catalog, snapshot)
    expect(
      filterBasementSkills(items, { name: 'nengtianshi', description: 'zhuanjia' })[0].childSkill[0]
        .skillname
    ).toBe('物流专家')
    expect(filterBasementSkills(items, { description: '+35%' })[0].span).toBe(1)
    expect(filterBasementSkills(items, { description: 'vup' })).toEqual([])
    expect(filterBasementSkills(items, { ownership: 'unowned' })[0].avatar).toBe('泡泡')
  })
})
