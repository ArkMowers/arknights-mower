import { describe, expect, it } from 'vitest'
import { builtinGroups } from '@/data/baseGroups'
import catalog from '../../../arknights_mower/data/building_skill.json'
import { filterGroups, groupFacilities, groupMembers } from './baseGroups'

const automation = builtinGroups.find((group) => group.title === '自动化')

describe('只读基建组合', () => {
  it('预置顺序、分类与名称保持可解析，跑单干员置顶', () => {
    const names = new Set(catalog.map((operator) => operator.name))
    expect(builtinGroups.map((group) => group.title)).toEqual([
      '跑单干员',
      '人间烟火',
      '感知信息',
      '龙门近卫局',
      '怪物猎人小队',
      '自动化',
      '深海猎人',
      '红松林',
      '精英干员',
      '莱茵科技',
      '结城理·S.E.E.S.',
      '鸿雪杜林组',
      '叙拉古',
      '能天使',
      '格拉斯哥帮',
      '喀兰贸易',
      '金属工艺',
      '泡泡仓库',
      '红云经验',
      '黑钢标准化'
    ])
    expect(builtinGroups[0].core).toEqual(['但书', '龙舌兰', '佩佩', '可露希尔'])
    expect(new Set(builtinGroups.map((group) => group.id)).size).toBe(builtinGroups.length)
    expect(
      Object.fromEntries(
        groupFacilities.map((facility) => [
          facility,
          builtinGroups.filter((group) => group.facility === facility).length
        ])
      )
    ).toEqual({ 通用: 9, 金属: 3, 贸易: 6, 经验: 2 })
    for (const group of builtinGroups) {
      const members = [...group.core, ...group.support, ...group.accessory]
      expect(group.core.length).toBeGreaterThan(0)
      expect(members.every((name) => names.has(name))).toBe(true)
      expect(new Set(members).size).toBe(members.length)
      expect(Object.keys(group.memberNotes).every((name) => members.includes(name))).toBe(true)
    }
  })
  it('预置集合、角色数组与条件备注均不可修改', () => {
    expect(() => builtinGroups.pop()).toThrow(TypeError)
    expect(() => {
      automation.title = '修改'
    }).toThrow(TypeError)
    for (const role of ['core', 'support', 'accessory']) {
      expect(() => automation[role].pop()).toThrow(TypeError)
    }
    expect(() => {
      automation.memberNotes['清流'] = '修改'
    }).toThrow(TypeError)
  })
  it('读取成员保留核心、备选、挂件和条件，不将条件拼入干员名称', () => {
    const members = groupMembers(automation, [])
    expect(members.filter((member) => member.role === 'core').map((m) => m.name)).toEqual([
      '森蚺',
      '温蒂',
      '承曦格雷伊',
      '清流',
      '冬时'
    ])
    expect(members.find((member) => member.name === '清流')).toMatchObject({
      role: 'core',
      note: '非153'
    })
    expect(members.find((member) => member.name === '冬时')).toMatchObject({
      role: 'core',
      note: '3电'
    })
    expect(members.filter((member) => member.role === 'support').map((m) => m.name)).toEqual([
      '流明'
    ])
    expect(members.find((member) => member.name === 'Lancet-2')).toMatchObject({
      role: 'accessory',
      note: '0心情'
    })
  })
  it('搜索覆盖挂件、拼音和条件，同时保持原始预置顺序与内容', () => {
    const previous = JSON.stringify(builtinGroups)
    expect(filterGroups(builtinGroups, [], { search: 'Lancet-2' })).toEqual([automation])
    expect(filterGroups(builtinGroups, [], { search: '0心情', facility: '金属' })).toEqual([
      automation
    ])
    expect(filterGroups(builtinGroups, [], { search: 'dongshi' })).toEqual([automation])
    expect(filterGroups(builtinGroups, [], { search: '不存在' })).toEqual([])
    expect(JSON.stringify(builtinGroups)).toBe(previous)
  })
  it('条件备注与备选优先级保留', () => {
    const byTitle = Object.fromEntries(builtinGroups.map((group) => [group.title, group]))
    expect(byTitle['人间烟火'].note).toBe('同时有5名岁干员在工作设施，如在意公招效率，不推荐使用')
    expect(byTitle['精英干员'].note).toBe('至少5名精英干员位于不同设施')
    expect(byTitle['精英干员'].core).not.toContain('真言')
    expect(byTitle['精英干员'].support).toEqual(['真言'])
    expect(byTitle['精英干员'].accessory).toEqual(['迷迭香', '煌', '逻各斯', '电弧'])
    expect(byTitle['鸿雪杜林组'].support).toEqual(['绮良', '褐果'])
    expect(byTitle['鸿雪杜林组'].core).toEqual(['鸿雪', '图耶'])
    expect(byTitle['黑钢标准化'].coreTitle).toBeUndefined()
    expect(
      groupMembers(byTitle['精英干员'], []).find((member) => member.name === '真言')
    ).toMatchObject({ role: 'support', note: '目前5精干35%贸易' })
    expect(byTitle['莱茵科技'].note).toBe('需要5名莱茵生命干员（不含缪尔赛思）')
    expect(byTitle['感知信息'].note).toBe('如在意公招效率，不推荐使用')
    expect(byTitle['深海猎人'].support).toEqual(['深巡'])
    expect(byTitle['红松林'].facility).toBe('经验')
    expect(byTitle['红松林'].core[0]).toBe('薇薇安娜')
    expect(byTitle['怪物猎人小队'].core).toEqual(['火龙S黑角', '麒麟R夜刀', '泰拉大陆调查团'])
    expect(byTitle['鸿雪杜林组'].memberNotes['绮良']).toBe('4赤使用')
    for (const name of byTitle['鸿雪杜林组'].accessory) {
      expect(byTitle['鸿雪杜林组'].memberNotes[name]).toBe('不可0心情')
    }
    expect(byTitle['泡泡仓库'].support).toEqual(['圣约送葬人', '贝娜'])
    expect(byTitle['泡泡仓库'].memberNotes['圣约送葬人']).toBe('经验')
  })
  it('缺失快照保持未知，挂件缺员不影响核心持有筛选', () => {
    expect(groupMembers(automation, []).every((m) => m.ownership === 'unknown')).toBe(true)
    expect(filterGroups([automation], [], { ownership: 'missing' })).toHaveLength(0)
    expect(filterGroups([automation], [], { ownership: 'core-owned' })).toHaveLength(0)
    expect(filterGroups([automation], [], { ownership: 'unknown' })).toHaveLength(1)
    const items = [
      ...automation.core.map((avatar) => ({ avatar, ownership: 'owned', progression: '精2 1级' })),
      { avatar: 'Lancet-2', ownership: 'unowned' }
    ]
    expect(filterGroups([automation], items, { ownership: 'core-owned' })).toHaveLength(1)
    expect(filterGroups([automation], items, { ownership: 'missing' })).toHaveLength(1)
    expect(groupMembers(automation, items)[0].progression).toBe('精2 1级')
  })
})
