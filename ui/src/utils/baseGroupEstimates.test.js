import { describe, expect, it } from 'vitest'
import catalog from '../../../arknights_mower/data/building_skill.json'
import { allGroupOptions, builtinGroups, singleRecommendations } from '@/data/baseGroups'
import {
  applyEstimateConditions,
  defaultEstimateOptions,
  defaultEstimateSelection,
  estimateFields,
  estimateGroup
} from './baseGroupEstimates'

const group = (suffix) =>
  [...allGroupOptions, ...singleRecommendations].find((entry) => entry.id === `builtin-${suffix}`)
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
  it.each([0, 1, 2])('精%s玛露西尔的散件和料理组合按当前技能计算制造加成', (phase) => {
    const names = ['玛露西尔', '森西']
    const items = roster(names, { 玛露西尔: phase })
    const entries = [
      singleRecommendations.find((entry) => entry.id === 'single-玛露西尔'),
      group('cuisine')
    ]
    for (const entry of entries) {
      const result = estimateGroup(entry, names, { cuisineDorm: 5 }, items)
      expect(result.valid).toBe(true)
      expect(result.assumptions).toEqual([])
      expect(value(result, '通用制造生产力')).toBe(phase === 2 ? 35 : 20)
      const alone = estimateGroup(entry, ['玛露西尔'], { cuisineDorm: 5 }, items)
      expect(value(alone, '通用制造生产力')).toBe(phase === 2 ? 30 : 20)
    }
  })
  it.each([0, 1, 2])('精%s怒潮凛冬仅在联动技能解锁且烈夏同站时获得额外加成', (phase) => {
    const result = estimate('ursus', ['怒潮凛冬', '烈夏'], {}, { 怒潮凛冬: phase, 烈夏: 0 })
    expect(result.valid).toBe(true)
    expect(result.assumptions).toEqual([])
    expect(value(result, '经验制造生产力')).toBe(phase === 2 ? 40 : 30)
    expect(value(estimate('ursus', ['怒潮凛冬'], {}, { 怒潮凛冬: phase }), '经验制造生产力')).toBe(
      30
    )
  })
  it.each([0, 1, 2])('精%s维什戴尔按当前技能为赫德雷和精零孑提供订单上限', (phase) => {
    const result = estimate(
      'jaye-parts',
      ['孑', '赫德雷', '维什戴尔'],
      {},
      { 孑: 0, 维什戴尔: phase }
    )
    expect(result.valid).toBe(true)
    expect(result.assumptions).toEqual([])
    expect(value(result, '赫德雷·搭档贡献')).toBe(phase === 2 ? 38 : 34)
    expect(value(result, '贸易订单效率')).toBe(phase === 2 ? 78 : 74)
    expect(result.details).toContain(
      `其他干员 30% + 孑 ${phase === 2 ? 48 : 44}%，空单状态，订单上限${phase === 2 ? 12 : 11}`
    )
  })
  it('未选维什戴尔不增加订单上限，缺少她的有效练度则明确采用满练假设', () => {
    const names = ['孑', '赫德雷', '维什戴尔']
    const items = roster(names, { 孑: 0, 维什戴尔: 0 })
    const absent = estimateGroup(group('jaye-parts'), ['孑', '赫德雷'], {}, items)
    expect(value(absent, '贸易订单效率')).toBe(70)
    const assumed = estimateGroup(group('jaye-parts'), names, {}, items.slice(0, 2))
    expect(assumed.valid).toBe(true)
    expect(assumed.assumptions).toEqual(['维什戴尔'])
    expect(value(assumed, '贸易订单效率')).toBe(78)
  })
  it('未拥有默认按满练估算，保留已拥有实际练度且不修改快照', () => {
    const names = ['能天使', '蕾缪安']
    const items = roster(names, { 能天使: 0 })
    items[1].ownership = 'unowned'
    items[1].childSkill = []
    const previous = JSON.stringify(items)
    const result = estimateGroup(group('exusiai'), names, {}, items)
    expect(result.valid).toBe(true)
    expect(value(result, '贸易订单效率')).toBe(65)
    expect(result.details).toContain('未拥有干员按满练度计算：蕾缪安')
    expect(JSON.stringify(items)).toBe(previous)
    expect(estimateGroup(group('exusiai'), names, {}, []).assumptions).toEqual(names)
  })
  it('未拥有的孑按满练计算，手选阶段优先，已拥有孑仍跟随森空岛', () => {
    const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const items = roster(names)
    items[0].ownership = 'unowned'
    items[0].childSkill = []
    const result = estimateGroup(group('karlan'), names, {}, items)
    expect(result.valid).toBe(true)
    expect(value(result, '贸易订单效率')).toBe(129)
    expect(result.details).toContain('孑精一及以上，使用未拥有满练度假设')
    const manual = estimateGroup(group('karlan'), names, { jayeStage: '未精英化' }, items)
    expect(value(manual, '贸易订单效率')).toBe(145)
    expect(manual.details).toContain('孑未精英化，使用手动选择')
    expect(manual.details.some((line) => line.includes('未拥有干员按满练度计算：孑'))).toBe(false)
    const owned = estimateGroup(group('karlan'), names, {}, roster(names, { 孑: 0 }))
    expect(value(owned, '贸易订单效率')).toBe(145)
    expect(owned.details).toContain('孑未精英化，使用森空岛练度')
  })
  it('未拥有的挂件默认提供阵营人数，不叠加自身技能', () => {
    const names = ['结城理', '埃癸斯', '岳羽由加莉', '虎狼丸']
    const items = roster(names)
    items[2].ownership = 'unowned'
    items[2].childSkill = []
    const result = estimateGroup(group('makoto'), names, {}, items)
    expect(value(result, 'S.E.E.S.在岗人数')).toBe(4)
    expect(value(result, '通用制造生产力')).toBe(40)
    expect(value(result, '无人机充能速度')).toBe(20)
  })
  it('默认20人宿舍，挂件默认勾选，其余干员不选，不修改预置', () => {
    const previous = JSON.stringify(builtinGroups)
    for (const item of builtinGroups) {
      const selected = defaultEstimateSelection(item)
      expect(selected).toEqual(item.defaultAccessories || item.accessory)
      selected.push('测试')
      expect(item.accessory).not.toContain('测试')
      expect(estimateGroup(item, item.accessory).hasSelection).toBe(false)
    }
    expect(defaultEstimateOptions(group('smoke')).dorm).toBe(20)
    expect(defaultEstimateOptions(group('perception')).dorm).toBe(20)
    expect(defaultEstimateOptions(group('perception')).dormLevel).toBe(1)
    expect(defaultEstimateOptions(group('karlan')).jayeStage).toBe('跟随森空岛')
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
    expect(missing.valid).toBe(true)
    expect(value(missing, '公招联络速度')).toBe(20)
    expect(missing.assumptions).toEqual(['桑葚'])
  })
  it('无练度自动使用满练度假设，已有实际练度仍保持有效', () => {
    expect(
      value(estimateGroup(group('exusiai'), ['能天使', '蕾缪安'], {}, []), '贸易订单效率')
    ).toBe(80)
    const selected = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const items = roster(selected, { 孑: 0, 银灰: 0 })
    const max = estimateGroup(group('karlan'), selected, {}, items)
    expect(value(max, '订单上限')).toBe(18)
    expect(value(max, '贸易订单效率')).toBe(124)
    const promoted = estimateGroup(group('karlan'), selected, { jayeStage: '精一及以上' }, [])
    expect(value(promoted, '订单上限')).toBe(18)
    expect(value(promoted, '贸易订单效率')).toBe(129)
    const manual = estimateGroup(group('karlan'), ['孑'], { jayeStage: '未精英化' })
    expect(manual.valid).toBe(true)
    expect(value(manual, '贸易订单效率')).toBe(40)
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
  it('挂件只提供阵营条件，不产生自身技能效率，已知未拥有挂件计入人数', () => {
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
    expect(estimateGroup(group('makoto'), names, {}, items).valid).toBe(true)
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
    expect(value(elite, '经验制造生产力')).toBe(36.75)
    expect(elite.metrics.some((metric) => metric.label === '感知信息')).toBe(false)
  })
  it('阵营增益不把维娜当格拉斯哥成员', () => {
    expect(
      value(estimate('glasgow', ['摩根', '推进之王', '戴菲恩', '维娜·维多利亚']), '贸易订单效率')
    ).toBe(135)
  })
  it('孑默认跟随森空岛精零或精一', () => {
    const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const zero = estimateGroup(group('karlan'), names, {}, roster(names, { 孑: 0 }))
    const promoted = estimateGroup(group('karlan'), names, {}, roster(names, { 孑: 1 }))
    expect(value(zero, '贸易订单效率')).toBe(145)
    expect(value(promoted, '贸易订单效率')).toBe(129)
    expect(zero.details).toContain('孑未精英化，使用森空岛练度')
    expect(promoted.details).toContain('孑精一及以上，使用森空岛练度')
  })
  it('孑手选阶段优先于森空岛练度', () => {
    const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const promoted = estimateGroup(
      group('karlan'),
      names,
      { jayeStage: '精一及以上' },
      roster(names, { 孑: 0 })
    )
    const zero = estimateGroup(
      group('karlan'),
      names,
      { jayeStage: '未精英化' },
      roster(names, { 孑: 1 })
    )
    expect(value(promoted, '贸易订单效率')).toBe(129)
    expect(value(zero, '贸易订单效率')).toBe(145)
    expect(promoted.details).toContain('孑精一及以上，使用手动选择')
    expect(zero.details).toContain('孑未精英化，使用手动选择')
  })
  it.each(['missing', 'unknown', 'incomplete'])(
    '孑练度%s时自动使用满练度假设，手选阶段仍优先',
    (state) => {
      const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
      const items = roster(names)
      const jaye = items[0]
      if (state === 'missing') items.shift()
      else if (state === 'incomplete') jaye.childSkill[1].status = 'unknown'
      else {
        jaye.ownership = state
        jaye.childSkill.forEach((skill) => {
          skill.status = state
        })
      }
      const before = JSON.stringify(items)
      const automatic = estimateGroup(group('karlan'), names, {}, items)
      expect(automatic.valid).toBe(true)
      expect(value(automatic, '贸易订单效率')).toBe(129)
      expect(automatic.assumptions).toContain('孑')
      const zero = estimateGroup(group('karlan'), names, { jayeStage: '未精英化' }, items)
      const promoted = estimateGroup(group('karlan'), names, { jayeStage: '精一及以上' }, items)
      expect(zero.valid).toBe(true)
      expect(promoted.valid).toBe(true)
      expect(value(zero, '贸易订单效率')).toBe(145)
      expect(value(promoted, '贸易订单效率')).toBe(129)
      expect(promoted.details).toContain('孑精一及以上，使用手动选择')
      expect(JSON.stringify(items)).toBe(before)
    }
  )
  it('未拥有的孑自动按精一及以上假设计算', () => {
    const names = ['孑', '银灰', '琳琅诗怀雅', '灵知']
    const items = roster(names)
    items[0].ownership = 'unowned'
    items[0].childSkill = []
    const result = estimateGroup(group('karlan'), names, {}, items)
    expect(result.valid).toBe(true)
    expect(value(result, '贸易订单效率')).toBe(129)
    expect(result.details).toContain('孑精一及以上，使用未拥有满练度假设')
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
    expect(value(estimateGroup(group('tianmao'), names, {}, items), '精英干员设施')).toBe(7)
    expect(estimateFields(group('tianmao')).some((field) => field.key === 'eliteRooms')).toBe(false)
  })
  it('时间技能始终计算用尽平均，不接受旧时长和最高效率选项', () => {
    for (const item of builtinGroups) {
      expect(estimateFields(item).some((field) => ['hours', 'average'].includes(field.key))).toBe(
        false
      )
    }
    expect(
      value(estimate('tianmao', ['机械师'], { hours: 1, average: false }), '经验制造生产力')
    ).toBe(36.75)
    expect(value(estimate('tianmao', ['机械师'], {}, { 机械师: 0 }), '经验制造生产力')).toBe(30)
    // A three-person room gives Scene 24 / 0.65 hours; warmup loses 30 percentage-hours.
    expect(value(estimate('cloud', ['稀音']), '通用制造生产力')).toBeCloseTo(24.1875)
    // A three-person room gives Ceobe 60 hours; warmup loses 15 percentage-hours.
    expect(value(estimate('cloud', ['刻俄柏']), '通用制造生产力')).toBeCloseTo(24.75)
  })
  it('红云组按最早耗尽者统一结束，独立设施不缩短机械师的周期', () => {
    const cloud = estimate('cloud', ['红云', '稀音', '帕拉斯'])
    // Scene consumes 0.65/h; the other two consume 0.40/h. Stop at 24 / 0.65.
    expect(value(cloud, '经验制造生产力')).toBeCloseTo(105.1875)
    expect(cloud.details).toContain(
      '从满心情24开始，按稀音最先用尽计算平均效率，工作36.92小时；红云每小时消耗0.4心情，稀音每小时消耗0.65心情，帕拉斯每小时消耗0.4心情'
    )
    const pair = estimate('cloud', ['稀音', '刻俄柏'])
    expect(value(pair, '通用制造生产力')).toBeCloseTo(48.78125)
    const elite = estimate('tianmao', ['机械师', '烛煌', '真言'])
    expect(value(elite, '经验制造生产力')).toBe(36.75)
  })
  it('泡泡仓库加入刻俄柏，容量转换和暖机均按练度与整组用尽计算', () => {
    const full = estimate('bubble', ['泡泡', '火神', '刻俄柏'])
    // All three consume 0.40/h: 60 hours, 75% capacity bonus, -5% Vulcan, 24.75% Ceobe.
    expect(value(full, '仓库容量加成')).toBe(37)
    expect(value(full, '通用制造生产力')).toBeCloseTo(94.75)
    const lowVulcan = estimate('bubble', ['泡泡', '火神', '刻俄柏'], {}, { 火神: 0 })
    // Unpromoted Vulcan consumes 0.50/h, ending the group at 48 hours.
    expect(value(lowVulcan, '通用制造生产力')).toBeCloseTo(53.6875)
    const lowCeobe = estimate('bubble', ['泡泡', '火神', '刻俄柏'], {}, { 刻俄柏: 0 })
    expect(value(lowCeobe, '通用制造生产力')).toBe(70)
  })
  it('淬羽赫默参与同站技能转换，不增加莱茵生命人数，发电站独立', () => {
    const names = ['多萝西', '娜斯提', '淬羽赫默']
    const result = estimate('nasti', names)
    expect(value(result, '其他莱茵生命干员')).toBe(2)
    expect(value(result, '通用制造生产力')).toBe(95)
    expect(value(result, '赤金制造生产力')).toBe(101)
    const power = estimate('nasti', [...names, '缪尔赛思'])
    expect(value(power, '通用制造生产力')).toBe(95)
    expect(value(power, '赤金制造生产力')).toBe(104)
    expect(value(power, '无人机充能速度')).toBe(16)
    expect(value(estimate('nasti', names, {}, { 淬羽赫默: 0 }), '通用制造生产力')).toBe(60)
    expect(value(estimate('nasti', ['淬羽赫默']), '通用制造生产力')).toBe(30)
  })
  it('杏仁赤金加成计自身及同站黑钢人数，中枢加成独立且不占制造位', () => {
    const names = ['杏仁', '杰西卡', '香草']
    expect(value(estimate('standardization', names), '通用制造生产力')).toBe(50)
    expect(value(estimate('standardization', names), '赤金制造生产力')).toBe(81)
    const control = estimate('standardization', [...names, '涤火杰西卡'])
    expect(value(control, '赤金制造生产力')).toBe(96)
    expect(value(estimate('standardization', ['杏仁']), '赤金制造生产力')).toBe(27)
    expect(value(estimate('standardization', names, {}, { 杏仁: 0 }), '赤金制造生产力')).toBe(75)
    const overflow = estimate('standardization', [...names, '水月', '涤火杰西卡'])
    expect(overflow.valid).toBe(false)
    expect(overflow.metrics).toEqual([])
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
  it.each([
    [['孑', '银灰', '琳琅诗怀雅', '灵知'], '精一及以上', 18, 129],
    [['锏', '银灰', '琳琅诗怀雅', '灵知'], '未精英化', 20, 125],
    [['孑', '银灰', '锏', '灵知'], '精一及以上', 14, 121],
    [['孑', '银灰', '琳琅诗怀雅', '灵知'], '未精英化', 20, 145],
    [['孑', '银灰', '锏', '灵知'], '未精英化', 20, 145]
  ])('喀兰组合按技能结算顺序计算：%j，孑%s', (names, jayeStage, cap, efficiency) => {
    const result = estimate(
      'karlan',
      names,
      { jayeStage },
      { 孑: jayeStage === '未精英化' ? 0 : 1 }
    )
    expect(result.valid).toBe(true)
    expect(value(result, '订单上限')).toBe(cap)
    expect(value(result, '贸易订单效率')).toBe(efficiency)
  })
  it('订单转效率不含设施基础上限，锏先结算，孑扣减后再结算琳琅', () => {
    const names = ['银灰', '琳琅诗怀雅', '锏', '灵知']
    const low = estimate('karlan', names, { orderCap: 6 })
    const high = estimate('karlan', names, { orderCap: 10 })
    expect(low.valid).toBe(false)
    expect(low.metrics).toEqual([])
    expect(value(high, '贸易订单效率')).toBe(125)
    expect(value(high, '订单上限')).toBe(20)
    const promoted = estimate('karlan', ['孑', '琳琅诗怀雅', '锏', '灵知'], {
      jayeStage: '精一及以上'
    })
    expect(promoted.details).toContain(
      '琳琅诗怀雅 0% + 锏 0%，仅转换干员净增加的订单上限，不含设施基础值'
    )
    expect(value(promoted, '订单上限')).toBe(7)
    expect(value(promoted, '贸易订单效率')).toBe(58)
    const reduced = estimate('karlan', ['孑', '银灰', '琳琅诗怀雅', '灵知'], {
      jayeStage: '精一及以上'
    })
    expect(reduced.details).toContain(
      '琳琅诗怀雅 32% + 锏 0%，仅转换干员净增加的订单上限，不含设施基础值'
    )
    expect(value(estimate('karlan', ['锏']), '贸易订单效率')).toBe(25)
    expect(value(estimate('karlan', ['银灰', '锏']), '贸易订单效率')).toBe(45)
    expect(
      value(estimate('karlan', ['孑', '银灰', '崖心'], { jayeStage: '精一及以上' }), '贸易订单效率')
    ).toBe(95)
    expect(
      value(
        estimate('karlan', ['孑', '银灰', '崖心', '灵知'], { jayeStage: '精一及以上' }),
        '贸易订单效率'
      )
    ).toBe(125)
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
    ['cloud', ['红云', '稀音', '帕拉斯'], '经验制造生产力', 105.1875],
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
