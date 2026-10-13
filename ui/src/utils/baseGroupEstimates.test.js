import { describe, expect, it } from 'vitest'
import catalog from '../../../arknights_mower/data/building_skill.json'
import { builtinGroups } from '@/data/baseGroups'
import {
  applyEstimateConditions,
  defaultEstimateOptions,
  defaultEstimateSelection,
  estimateFields,
  estimateGroup
} from './baseGroupEstimates'

const group = (suffix) => builtinGroups.find((entry) => entry.id === `builtin-${suffix}`)
function roster(names, phases = {}) {
  return names.map((name) => {
    const source = catalog.find((entry) => entry.name === name)
    const unlocked = source.child_skill.filter(
      (skill) => Number(skill.phase_level.match(/精(\d)/)[1]) <= (phases[name] ?? 2)
    )
    const highest = new Map()
    for (const skill of unlocked)
      highest.set(skill.skill_key, Math.max(highest.get(skill.skill_key) ?? -1, skill.skill_level))
    return {
      avatar: name,
      ownership: 'owned',
      childSkill: source.child_skill.map((skill) => ({
        ...skill,
        status: !unlocked.includes(skill)
          ? 'locked'
          : highest.get(skill.skill_key) === skill.skill_level
            ? 'active'
            : 'replaced'
      }))
    }
  })
}
function estimate(id, names, options = {}, phases = {}) {
  return estimateGroup(group(id), names, options, roster(names, phases))
}
function value(result, label) {
  return result.metrics.find((metric) => metric.label === label)?.value
}

describe('基建组合效率估算', () => {
  it('默认20人宿舍，挂件默认勾选，其余干员不选，不修改预置', () => {
    const previous = JSON.stringify(builtinGroups)
    for (const item of builtinGroups) {
      const selected = defaultEstimateSelection(item)
      expect(selected).toEqual(item.accessory)
      selected.push('测试')
      expect(item.accessory).not.toContain('测试')
      expect(estimateGroup(item, item.accessory).hasSelection).toBe(false)
    }
    expect(defaultEstimateOptions(group('smoke')).dorm).toBe(20)
    expect(defaultEstimateOptions(group('perception')).dorm).toBe(20)
    expect(defaultEstimateOptions(group('perception')).dormLevel).toBe(1)
    expect(estimate('run-order', group('run-order').core).hasSelection).toBe(false)
    expect(JSON.stringify(builtinGroups)).toBe(previous)
  })
  it('按烟火模式合计75点，加乌有后95点，公招和生产分别计算', () => {
    const selected = ['重岳', '桑葚', '令', '夕']
    const result = estimate('smoke', selected)
    expect(value(result, '人间烟火')).toBe(75)
    expect(value(result, '公招联络速度')).toBe(20)
    const full = estimate('smoke', [...selected, '乌有', '截云', '黍', '余', '年'])
    expect(value(full, '人间烟火')).toBe(95)
    expect(value(full, '贸易订单效率')).toBe(95)
    expect(value(full, '通用制造生产力')).toBe(69)
    expect(full.metrics.some((metric) => /训练|副产品/.test(metric.label))).toBe(false)
  })
  it('感知信息的来源、转化和公招独立，令夕使用相反心情条件', () => {
    const result = estimate('perception', [
      '迷迭香',
      '黑键',
      '絮雨',
      '令',
      '夕',
      '爱丽丝',
      '车尔尼',
      '塑心',
      '琴柳'
    ])
    expect(value(result, '感知信息')).toBe(82)
    expect(value(result, '通用制造生产力')).toBe(82)
    expect(value(result, '无声共鸣')).toBe(87)
    expect(value(result, '贸易订单效率')).toBe(43)
    expect(value(result, '公招联络速度')).toBe(40)
  })
  it('森空岛练度只启用已解锁技能，升级版本不重复计入', () => {
    expect(
      value(estimate('exusiai', ['能天使', '蕾缪安'], {}, { 能天使: 0, 蕾缪安: 0 }), '贸易订单效率')
    ).toBe(40)
    expect(value(estimate('exusiai', ['能天使', '蕾缪安']), '贸易订单效率')).toBe(80)
    expect(
      value(estimate('smoke', ['重岳', '桑葚', '令', '夕'], {}, { 桑葚: 0, 令: 0 }), '人间烟火')
    ).toBe(40)
    const missing = estimateGroup(group('smoke'), ['桑葚'])
    expect(missing.valid).toBe(false)
    expect(missing.metrics).toEqual([])
    expect(missing.warnings[0]).toContain('森空岛')
  })
  it('满练度开关可演算未知干员，孑的精英阶段由计算条件控制', () => {
    expect(
      value(estimateGroup(group('exusiai'), ['能天使', '蕾缪安'], {}, [], true), '贸易订单效率')
    ).toBe(80)
    const selected = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const items = roster(selected, { 孑: 0, 银灰: 0 })
    const max = estimateGroup(group('karlan'), selected, {}, items, true)
    expect(value(max, '订单上限')).toBe(20)
    expect(value(max, '贸易订单效率')).toBe(145)
    const promoted = estimateGroup(group('karlan'), selected, { jayeStage: '精一及以上' }, [], true)
    expect(value(promoted, '订单上限')).toBe(14)
    expect(value(promoted, '贸易订单效率')).toBe(121)
    expect(estimateGroup(group('karlan'), ['孑']).valid).toBe(true)
    expect(value(estimateGroup(group('karlan'), ['孑']), '贸易订单效率')).toBe(40)
  })
  it('设施数据只填充有效数字，部分快照保留其余手工条件', () => {
    const item = group('smoke')
    const current = { ...defaultEstimateOptions(item), dorm: 16, sui: 3 }
    const filled = applyEstimateConditions(item, current, {
      trade: 1,
      factories: 5,
      power: 3,
      recruits: 0,
      dormLevel: 2,
      dorm: 'bad',
      sui: 99
    })
    expect(filled).toMatchObject({
      trade: 1,
      factories: 5,
      power: 3,
      recruits: 0,
      dorm: 16,
      sui: 3
    })
    expect(filled).not.toHaveProperty('dormLevel')
    expect(current.trade).toBe(2)
  })
  it('挂件只提供阵营条件，不产生自身技能效率，已知未拥有挂件不计人数', () => {
    const names = ['结城理', '埃癸斯', '岳羽由加莉', '虎狼丸']
    const result = estimate('makoto', names)
    expect(value(result, '通用制造生产力')).toBe(40)
    expect(value(result, '无人机充能速度')).toBe(20)
    expect(result.metrics.map((metric) => metric.label)).toEqual([
      'S.E.E.S.在岗人数',
      '通用制造生产力',
      '无人机充能速度'
    ])
    const items = roster(names)
    items[1].ownership = 'unowned'
    expect(estimateGroup(group('makoto'), names, {}, items).valid).toBe(false)
    expect(value(estimate('makoto', ['结城理', '岳羽由加莉', '虎狼丸']), '通用制造生产力')).toBe(35)
    const elite = estimate('tianmao', [
      '凯尔希·思衡托',
      '机械师',
      '烛煌',
      '真言',
      '迷迭香',
      '煌',
      '逻各斯',
      '电弧'
    ])
    expect(value(elite, '公招联络速度')).toBe(50)
    expect(value(elite, '贸易订单效率')).toBe(39)
    expect(value(elite, '经验制造生产力')).toBe(36)
    expect(elite.metrics.some((metric) => metric.label === '感知信息')).toBe(false)
  })
  it('阵营增益不把维娜当格拉斯哥成员，孑手选精一时不受同步练度影响', () => {
    expect(
      value(estimate('glasgow', ['摩根', '推进之王', '戴菲恩', '维娜·维多利亚']), '贸易订单效率')
    ).toBe(135)
    const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const empty = estimate('karlan', names, { jayeStage: '精一及以上' })
    const occupied = estimate('karlan', names, { jayeStage: '精一及以上' }, { 孑: 0 })
    expect(value(empty, '贸易订单效率')).toBe(121)
    expect(value(occupied, '贸易订单效率')).toBe(121)
  })
  it('森蚺只能选一处设施，制造站模式不同时提供中枢的虚拟发电站', () => {
    const names = ['森蚺', '温蒂', '清流', '承曦格雷伊', 'Lancet-2']
    const result = estimate('automation', names, { eunectesRoom: '制造站' })
    expect(value(result, '计入技能的发电站')).toBe(3)
    expect(value(result, '赤金制造生产力')).toBe(115)
    expect(result.valid).toBe(true)
  })
  it('制造站和贸易站容量冲突不输出虚假合计，跨设施人数允许分布', () => {
    for (const id of ['redpine', 'gold', 'bubble', 'cloud', 'karlan']) {
      const item = group(id)
      const names = [...item.core, ...item.support, ...item.accessory]
      const result = estimateGroup(item, names, {}, roster(names))
      expect(result.valid).toBe(false)
      expect(result.metrics).toEqual([])
      expect(result.warnings[0]).toContain('最多3人')
    }
    const abyss = estimate('abyss', group('abyss').core)
    expect(abyss.valid).toBe(true)
    expect(value(abyss, '制造站一·通用制造生产力')).toBe(80)
    expect(value(abyss, '制造站二·通用制造生产力')).toBe(80)
  })
  it('深海按每站人数分配全部猎人，每站一人可使用四站', () => {
    const names = group('abyss').core
    const four = estimate('abyss', names, { targetHunters: 1 })
    expect(four.valid).toBe(true)
    expect(four.metrics.map((metric) => metric.value)).toEqual([40, 40, 40, 40])
    expect(four.warnings).toEqual([])
    const uneven = estimate('abyss', names, { targetHunters: 3 })
    expect(uneven.metrics.map((metric) => metric.value)).toEqual([90, 40])
    const one = estimate('abyss', ['歌蕾蒂娅', '斯卡蒂'], { targetHunters: 2 })
    expect(one.metrics.map((metric) => metric.value)).toEqual([10])
    expect(estimate('abyss', ['歌蕾蒂娅']).metrics).toEqual([])
    const low = estimate('abyss', names, { targetHunters: 1 }, { 歌蕾蒂娅: 0 })
    expect(low.metrics.map((metric) => metric.value)).toEqual([20, 20, 20, 20])
  })
  it('精干设施数由已选精英干员计算，可超过五间且挂件不提供直接效率', () => {
    const names = ['凯尔希·思衡托', '机械师', '烛煌', '真言', '迷迭香', '煌', '逻各斯', '电弧']
    const result = estimate('tianmao', names)
    expect(value(result, '精英干员设施')).toBe(7)
    expect(value(result, '公招联络速度')).toBe(50)
    expect(value(result, '贸易订单效率')).toBe(39)
    expect(value(estimate('tianmao', ['真言', '迷迭香']), '精英干员设施')).toBe(2)
    expect(value(estimate('tianmao', ['真言', '迷迭香']), '贸易订单效率')).toBe(29)
    const items = roster(names)
    items.find((item) => item.avatar === '迷迭香').ownership = 'unowned'
    expect(value(estimateGroup(group('tianmao'), names, {}, items), '精英干员设施')).toBe(6)
    expect(estimateFields(group('tianmao')).some((field) => field.key === 'eliteRooms')).toBe(false)
  })
  it('时长控件已移除，时间技能按统一三十小时周期取平均', () => {
    for (const item of builtinGroups)
      expect(estimateFields(item).some((field) => field.key === 'hours')).toBe(false)
    expect(value(estimate('tianmao', ['机械师'], { hours: 1 }), '经验制造生产力')).toBe(36)
    expect(value(estimate('tianmao', ['机械师'], {}, { 机械师: 0 }), '经验制造生产力')).toBe(30)
    expect(value(estimate('cloud', ['稀音']), '通用制造生产力')).toBe(24)
    expect(value(estimate('cloud', ['刻俄柏']), '通用制造生产力')).toBe(24.5)
  })
  it('平均效率默认开启，关闭仅改变时间技能，不影响解锁条件或设施快照', () => {
    expect(defaultEstimateOptions(group('tianmao')).average).toBe(true)
    expect(defaultEstimateOptions(group('cloud')).average).toBe(true)
    expect(value(estimate('tianmao', ['机械师'], { average: false }), '经验制造生产力')).toBe(40)
    expect(
      value(estimate('tianmao', ['机械师'], { average: false }, { 机械师: 0 }), '经验制造生产力')
    ).toBe(30)
    expect(value(estimate('cloud', ['稀音', '刻俄柏'], { average: false }), '通用制造生产力')).toBe(
      50
    )
    expect(value(estimate('cloud', ['稀音', '刻俄柏']), '通用制造生产力')).toBe(48.5)
    expect(value(estimate('tianmao', ['机械师'], { average: 'false' }), '经验制造生产力')).toBe(36)
    expect(applyEstimateConditions(group('tianmao'), { average: false }, { average: 1 })).toEqual({
      average: false
    })
  })
  it('绮良仅用实际赤金生产线触发加成，杜林虚拟线不参与', () => {
    const names = ['鸿雪', '图耶', '绮良', ...group('pozy').accessory]
    const result = estimate('pozy', names, { goldLines: 4 })
    expect(value(result, '赤金生产线')).toBe(12)
    expect(value(result, '贸易订单效率')).toBe(160)
    expect(value(estimate('pozy', names, { goldLines: 0 }), '赤金生产线')).toBe(4)
    const low = estimate('pozy', names, { goldLines: 3 }, { 绮良: 0 })
    expect(value(low, '赤金生产线')).toBe(7)
  })
  it('订单转效率只用干员正向添加值，不含基础订单，不抵扣锏与孑减少值', () => {
    const names = ['银灰', '琳琅诗怀雅', '锏', '灵知']
    const low = estimate('karlan', names, { orderCap: 6 })
    const high = estimate('karlan', names, { orderCap: 10 })
    expect(value(low, '贸易订单效率')).toBe(174)
    expect(value(high, '贸易订单效率')).toBe(174)
    expect(value(low, '订单上限')).toBe(16)
    expect(value(high, '订单上限')).toBe(20)
    const promoted = estimate('karlan', ['孑', '琳琅诗怀雅', '锏', '灵知'], {
      jayeStage: '精一及以上'
    })
    expect(promoted.details).toContain(
      '琳琅诗怀雅 24% + 锏 25%，仅计干员增加的订单上限，不含设施基础值，不抵扣减少值'
    )
  })
  it('制造按产品分别给出含通用加成的结果，源石技能只作用于源石配方', () => {
    const brown = estimate('pozy', ['褐果'])
    expect(value(brown, '通用制造生产力')).toBe(15)
    expect(value(brown, '源石制造生产力')).toBe(45)
    expect(value(estimate('pozy', ['褐果'], {}, { 褐果: 0 }), '源石制造生产力')).toBeUndefined()
    const auto = estimate('automation', ['森蚺', '温蒂', '清流', '承曦格雷伊', 'Lancet-2'])
    expect(value(auto, '通用制造生产力')).toBe(75)
    expect(value(auto, '赤金制造生产力')).toBe(115)
    const pine = estimate('redpine', ['薇薇安娜', '焰尾', '远牙', '灰毫', '野鬃'])
    expect(value(pine, '通用制造生产力')).toBe(96)
    expect(value(pine, '经验制造生产力')).toBe(126)
    expect(value(pine, '赤金制造生产力')).toBe(66)
    const bubble = estimate('bubble', ['泡泡', '火神', '圣约送葬人'])
    expect(value(bubble, '通用制造生产力')).toBe(62)
    expect(value(bubble, '经验制造生产力')).toBe(96)
  })
  it.each([
    ['lgd', ['斩业星熊', '诗怀雅'], '所有制造站·通用制造生产力', 3],
    ['monster-hunter', ['火龙S黑角', '麒麟R夜刀', '泰拉大陆调查团'], '贸易订单效率', 41],
    ['automation', ['森蚺', '温蒂', '承曦格雷伊', '清流', 'Lancet-2'], '赤金制造生产力', 115],
    ['redpine', ['薇薇安娜', '焰尾', '远牙', '灰毫', '野鬃'], '经验制造生产力', 126],
    ['nasti', ['娜斯提', '缪尔赛思', '多萝西', '赫默', '伊芙利特', '塞雷娅'], '赤金制造生产力', 75],
    ['siracusa', ['伺夜', '贝洛内', '八幡海铃'], '贸易订单效率', 90],
    ['glasgow', ['摩根', '推进之王', '戴菲恩'], '贸易订单效率', 95],
    ['gold', ['苍苔', '引星棘刺', '砾'], '赤金制造生产力', 116],
    ['bubble', ['泡泡', '火神', '圣约送葬人'], '经验制造生产力', 96],
    ['cloud', ['红云', '稀音', '帕拉斯'], '经验制造生产力', 105],
    ['standardization', ['水月', '杰西卡', '香草', '涤火杰西卡'], '通用制造生产力', 100]
  ])('%s按所选干员和设施独立估算', (id, names, label, expected) => {
    expect(value(estimate(id, names), label)).toBe(expected)
  })
  it('所有预置均有规则，输入有界且不修改调用方选择、条件或快照', () => {
    for (const item of builtinGroups) {
      const names = [...item.core, ...item.support, ...item.accessory]
      const items = roster(names)
      const input = { dorm: 999, recruits: -5, hours: 'invalid', catRoom: '非法设施' }
      const previous = JSON.stringify({ names, items, input })
      const result = estimateGroup(item, names, input, items)
      expect(result.metrics.every((metric) => Number.isFinite(metric.value))).toBe(true)
      expect(JSON.stringify({ names, items, input })).toBe(previous)
    }
    expect(value(estimate('smoke', ['乌有'], { dorm: 999 }), '人间烟火')).toBe(20)
  })
})
