import { describe, expect, it } from 'vitest'
import catalog from '../../../arknights_mower/data/building_skill.json'
import { allGroupOptions, builtinGroups, singleRecommendations } from '@/data/baseGroups'
import { estimateGroup, defaultEstimateOptions, estimateFields } from './baseGroupEstimates'
const byId = (id) => [...allGroupOptions, ...singleRecommendations].find((g) => g.id === id)
const calc = (id, selected, input = {}, items = []) => {
  const group = byId(id)
  return estimateGroup(group, selected || group.recommended, input, items)
}
const metric = (r, label) => r.metrics.find((m) => m.label === label)?.value

describe('新增基建干员推荐', () => {
  it('核心、备选、挂件和方案引用均存在于共享目录，名称唯一且推荐不超出成员范围', () => {
    const names = new Set(catalog.map((o) => o.name))
    expect(singleRecommendations).toHaveLength(84)
    const all = [...allGroupOptions, ...singleRecommendations]
    expect(new Set(all.map((g) => g.id)).size).toBe(all.length)
    for (const g of all) {
      const members = [...g.core, ...g.support, ...g.accessory]
      expect(members.every((n) => names.has(n))).toBe(true)
      expect(new Set(members).size).toBe(members.length)
      expect((g.recommended || []).every((n) => members.includes(n))).toBe(true)
    }
    expect(builtinGroups.filter((g) => [g.core, g.support].flat().includes('孑'))).toHaveLength(1)
  })
  it('阿罗玛槐琥的第三人补足条件与两人实际房间分别计算', () => {
    const full = calc('builtin-aroma')
    expect(metric(full, '赤金制造生产力')).toBeCloseTo(82.020833333)
    expect(full.details.some((d) => d.includes('阿罗玛平均42.0208%'))).toBe(true)
    const without = calc('builtin-aroma', null, { thirdEfficiency: 0 })
    expect(metric(without, '赤金制造生产力')).toBeCloseTo(79.854166667)
    const two = calc('builtin-aroma', null, { factoryResidents: 2 })
    expect(metric(two, '赤金制造生产力')).toBeCloseTo(79.458333333)
  })
  it('熊团跨设施显示75%经验与30%贸易，古米离岗取消烈夏条件', () => {
    expect(metric(calc('builtin-ursus'), '经验制造生产力')).toBe(75)
    expect(metric(calc('builtin-ursus'), '贸易订单效率')).toBe(30)
    expect(metric(calc('builtin-ursus', ['怒潮凛冬', '烈夏']), '经验制造生产力')).toBe(40)
  })
  it.each([
    ['builtin-jaye-siracusa', {}, 138],
    ['builtin-jaye-siracusa', { reception: 2 }, 133],
    ['builtin-jaye-siracusa', { reception: 1 }, 128],
    ['builtin-jaye-hunters', {}, 127],
    ['builtin-jaye-penguin', {}, 126]
  ])('%s只在精零、三级贸易站条件下给出结果', (id, input, expected) => {
    expect(metric(calc(id, null, { ...input, jayeStage: '未精英化' }), '贸易订单效率')).toBe(
      expected
    )
    expect(calc(id, null, { jayeStage: '精一及以上' }).valid).toBe(false)
    expect(calc(id, null, { jayeStage: '未精英化', orderCap: 8 }).metrics).toEqual([])
  })
  it('取消海铃后叙拉古少10%，企鹅物流少5%', () => {
    expect(
      metric(
        calc('builtin-jaye-siracusa', ['孑', '伺夜', '贝洛内'], { jayeStage: '未精英化' }),
        '贸易订单效率'
      )
    ).toBe(128)
    expect(
      metric(
        calc('builtin-jaye-penguin', ['孑', '德克萨斯', '拉普兰德'], { jayeStage: '未精英化' }),
        '贸易订单效率'
      )
    ).toBe(121)
  })
  it('精零孑散件不重复计算基础40%，支援变化和超员都有效', () => {
    const result = calc('builtin-jaye-parts', null, { jayeStage: '未精英化' })
    expect(metric(result, '泰拉大陆调查团·搭档贡献')).toBe(49)
    expect(metric(result, '瑰盐·搭档贡献')).toBe(42)
    expect(metric(result, '贸易订单效率')).toBe(131)
    const hoed = calc('builtin-jaye-parts', ['孑', '赫德雷', '伊内丝', 'W', '维什戴尔'], {
      jayeStage: '未精英化'
    })
    expect(metric(hoed, '赫德雷·搭档贡献')).toBe(48)
    const chil = calc('builtin-jaye-parts', ['孑', '齐尔查克', '森西'], {
      jayeStage: '未精英化',
      cuisineDorm: 5
    })
    expect(metric(chil, '齐尔查克·搭档贡献')).toBe(39)
    expect(
      calc('builtin-jaye-parts', ['孑', '瑰盐', '齐尔查克', '赫德雷'], { jayeStage: '未精英化' })
        .metrics
    ).toEqual([])
  })
  it('拉特兰105%与料理跨设施贡献保留，予洁移为会客散件', () => {
    expect(metric(calc('builtin-laterano'), '贸易订单效率')).toBe(105)
    expect(metric(calc('single-予愿安洁莉娜-会客'), '会客技能效率（折合精二六星）')).toBe(22.5)
    expect(metric(calc('builtin-cuisine', null, { cuisineDorm: 5 }), '通用制造生产力')).toBe(35)
    expect(metric(calc('builtin-cuisine', null, { cuisineDorm: 5 }), '贸易订单效率')).toBe(35)
  })
  it.each([
    ['槐琥', '通用制造生产力', 40],
    ['至简', '通用制造生产力', 40],
    ['玛露西尔', '通用制造生产力', 31],
    ['机械师', '经验制造生产力', 36.75],
    ['酒神', '经验制造生产力', 35],
    ['断罪者', '经验制造生产力', 35],
    ['食铁兽', '经验制造生产力', 35],
    ['弑君者', '经验制造生产力', 35],
    ['裂响', '经验制造生产力', 35],
    ['阿罗玛', '赤金制造生产力', 40.875],
    ['引星棘刺', '赤金制造生产力', 36],
    ['砾', '赤金制造生产力', 35],
    ['褐果', '源石制造生产力', 45],
    ['炎熔', '源石制造生产力', 35],
    ['地灵', '源石制造生产力', 35],
    ['艾雅法拉', '源石制造生产力', 35],
    ['谬因', '源石制造生产力', 35],
    ['锡兰', '源石制造生产力', 35],
    ...['吉星', '冻河', '深巡', '伺夜', '贝洛内', '风絮', '空弦', '赫德雷'].map((name) => [
      name,
      '贸易订单效率',
      40
    ]),
    ...['承曦格雷伊', '缪尔赛思'].map((name) => [name, '无人机充能速度', 25]),
    ...['烛煌', '格雷伊', '炎狱炎熔', '天空盒', '雷蛇', '时隙', '海霓', '澄闪'].map((name) => [
      name,
      '无人机充能速度',
      20
    ]),
    ['空构', '无人机充能速度', 19.71875],
    ['石英', '贸易订单效率', 36],
    ...['雷狼龙S空爆', '雪雉', '能天使', '海蒂'].map((name) => [name, '贸易订单效率', 35])
  ])('单人%s的满技能默认条件为%s %s', (name, label, expected) => {
    expect(metric(calc('single-' + name), label)).toBeCloseTo(expected)
  })
  it.each([
    ['八幡海铃', '办公联络速度', 10],
    ['焰狐龙梓兰', '办公联络速度', 10],
    ...['Mon3tr', '凯尔希', '结城理', '布丁', '望'].map((name) => [
      name,
      '所有制造站·每站生产力',
      2
    ]),
    ...['阿米娅', '明椒', '阿斯卡纶'].map((name) => [name, '所有贸易站·每站订单效率', 7]),
    ['老鲤', '会客线索搜集速度', 25],
    ['魔王', '会客线索搜集速度', 15],
    ['摆渡人', '会客线索搜集速度', 25]
  ])('中枢单人%s的设施贡献独立标注', (name, label, expected) => {
    expect(metric(calc('single-' + name + '-中枢'), label)).toBeCloseTo(expected)
  })
  it.each([
    ['斥罪', 50],
    ['凯尔希·思衡托', 50],
    ...['艾雅法拉', '遥', '珊比', '地灵', '普罗旺斯', '水灯心', '圣聆初雪'].map((name) => [
      name,
      45
    ])
  ])('办公单人%s的默认条件为%s', (name, expected) => {
    expect(metric(calc('single-' + name + '-办公'), '办公联络速度')).toBe(expected)
  })
  it('烟火组合中的望与单人推荐计入相同的额外发电站数', () => {
    expect(metric(calc('builtin-smoke', ['望'], { virtualPower: 1 }), '所有贸易站订单效率')).toBe(7)
    expect(
      metric(calc('builtin-smoke', ['望'], { virtualPower: 0 }), '所有制造站·通用制造生产力')
    ).toBe(2)
  })
  it('中枢设施条件、心情和办公挂件分别控制结果', () => {
    expect(
      metric(calc('single-布丁-中枢', null, { workingPlatforms: 1 }), '所有制造站·每站生产力')
    ).toBe(0)
    expect(
      metric(calc('single-望-中枢', null, { virtualPower: 1 }), '所有贸易站·每站订单效率')
    ).toBe(7)
    expect(metric(calc('single-望-中枢', null, { factories: 4 }), '所有贸易站·每站订单效率')).toBe(
      7
    )
    expect(
      metric(
        calc('builtin-control-mujica', ['丰川祥子', '八幡海铃', '三角初华', '祐天寺若麦']),
        '非自动化赤金站·每站生产力'
      )
    ).toBe(3)
    expect(
      metric(
        calc('builtin-control-babel', ['维什戴尔', '魔王']),
        '制造/贸易/发电/办公/会客·心情消耗变化'
      )
    ).toBe(-0.2)
    expect(
      metric(
        calc('builtin-control-mlynar', ['玛恩纳', '临光', '杜宾']),
        '发电/办公/会客·心情消耗变化'
      )
    ).toBeCloseTo(-0.25)
    expect(metric(calc('single-摆渡人-中枢', null, { minosOthers: 0 }), '会客线索搜集速度')).toBe(5)
    expect(
      metric(calc('single-摆渡人-中枢', null, { sargonInControl: '有' }), '自身心情消耗变化')
    ).toBe(0.02)
    expect(metric(calc('single-凯尔希·思衡托-办公', null, { eliteRooms: 0 }), '办公联络速度')).toBe(
      30
    )
    expect(metric(calc('single-圣聆初雪-办公', ['圣聆初雪']), '办公联络速度')).toBe(35)
  })
  it('真实练度只计算当前已解锁技能，发电条件不会借用满技能值', () => {
    const items = [
      {
        avatar: '酒神',
        ownership: 'owned',
        childSkill: [
          { skill_key: 0, skill_level: 0, status: 'active' },
          { skill_key: 0, skill_level: 1, status: 'locked' }
        ]
      },
      {
        avatar: '裂响',
        ownership: 'owned',
        childSkill: [
          { skill_key: 0, skill_level: 0, status: 'active' },
          { skill_key: 1, skill_level: 0, status: 'locked' }
        ]
      },
      {
        avatar: '空构',
        ownership: 'owned',
        childSkill: [
          { skill_key: 0, skill_level: 0, status: 'active' },
          { skill_key: 0, skill_level: 1, status: 'locked' },
          { skill_key: 1, skill_level: 0, status: 'active' }
        ]
      }
    ]
    expect(metric(calc('single-酒神', null, {}, items), '经验制造生产力')).toBe(20)
    expect(metric(calc('single-裂响', null, {}, items), '经验制造生产力')).toBe(0)
    expect(metric(calc('single-空构', null, {}, items), '无人机充能速度')).toBeCloseTo(14.71875)
    expect(metric(calc('single-缪尔赛思', null, { rhineWorkers: 2 }), '无人机充能速度')).toBe(16)
  })
  it('单人条件可改，未知练度使用满练度假设，孑的手选阶段仍保留', () => {
    expect(metric(calc('single-机械师', null, { factoryResidents: 1 }), '经验制造生产力')).toBe(
      36.25
    )
    expect(metric(calc('single-石英', null, { formulaKinds: 2 }), '贸易订单效率')).toBe(34)
    expect(metric(calc('single-雪雉', null, { peerTradeEfficiency: 0 }), '贸易订单效率')).toBe(0)
    expect(metric(calc('single-伺夜', null, { reception: 1 }), '贸易订单效率')).toBe(30)
    expect(calc('single-阿罗玛', null, {}, []).assumptions).toEqual(['阿罗玛'])
    expect(calc('single-孑', null, { jayeStage: '精一及以上' }).valid).toBe(false)
    expect(calc('single-孑').valid).toBe(false)
    expect(metric(calc('single-孑', null, { jayeStage: '未精英化' }), '贸易订单效率')).toBe(40)
    expect(defaultEstimateOptions(byId('single-机械师')).factoryResidents).toBe(3)
  })
  it.each([
    ['三电 · 40%', 40],
    ['二电 · 1111宿舍 · 28%', 28],
    ['二电 · 2111宿舍 · 30%', 30],
    ['二电 · 3111宿舍 · 30%', 30]
  ])('至简固定配置%s', (dormLayout, expected) => {
    expect(estimateFields(byId('single-至简')).map((f) => f.key)).toEqual(['dormLayout'])
    expect(metric(calc('single-至简', null, { dormLayout }), '通用制造生产力')).toBe(expected)
  })
  it.each([
    ['跃跃', 37],
    ['克莱门莎', 35],
    ['见行者', 34],
    ['信仰搅拌机', 30],
    ['伊内丝', 29.0625],
    ['赤刃明霄陈', 29],
    ['莱欧斯', 29],
    ['响石', 29],
    ['陈', 25],
    ['伺夜', 25],
    ['红', 24],
    ['星极', 24],
    ['虎狼丸', 9]
  ])('会客%s按实际可达精英化与星级折算为%s', (name, expected) => {
    expect(
      metric(
        calc('single-' + name + '-会客', null, { cuisineDorm: 5 }),
        '会客技能效率（折合精二六星）'
      )
    ).toBeCloseTo(expected)
  })
  it.each(['国度', '行铃', '旅骨'])('回收%s按练度计算20或30，国度减耗单独列出', (name) => {
    expect(metric(calc('single-' + name + '-回收'), '材料转化效率')).toBe(30)
    const item = {
      avatar: name,
      ownership: 'owned',
      progression: '精0 1级',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 0, skill_level: 1, status: 'locked' }
      ]
    }
    const low = calc('single-' + name + '-回收', null, {}, [item])
    expect(metric(low, '材料转化效率')).toBe(20)
    expect(metric(low, '自身心情消耗变化')).toBe(name === '国度' ? -0.1 : undefined)
  })
  it('会客条件关闭、挂件缺席和实际精一均影响折算结果', () => {
    const label = '会客技能效率（折合精二六星）'
    expect(metric(calc('single-跃跃-会客', null, { clueExchange: '否' }), label)).toBe(7)
    expect(metric(calc('single-虎狼丸-会客', null, { clueExchange: '否' }), label)).toBe(-21)
    expect(metric(calc('single-信仰搅拌机-会客', ['信仰搅拌机']), label)).toBe(20)
    expect(metric(calc('single-克莱门莎-会客', null, { awakePeers: 0 }), label)).toBe(20)
    const item = {
      avatar: '跃跃',
      ownership: 'owned',
      progression: '精1 60级',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'active' }
      ]
    }
    expect(metric(calc('single-跃跃-会客', null, {}, [item]), label)).toBe(29)
  })
  it('予洁和风丸仅列为散件，不指定挂件；效率折半并保留实际精英阶段差异', () => {
    const label = '会客技能效率（折合精二六星）'
    const angel = byId('single-予愿安洁莉娜-会客')
    const wind = byId('single-风丸-会客')
    expect(angel.accessory).toEqual([])
    expect(wind.accessory).toEqual([])
    expect(
      builtinGroups.some((group) => ['builtin-angelina', 'builtin-kazemaru'].includes(group.id))
    ).toBe(false)
    expect(metric(calc(wind.id), label)).toBe(22)
    const low = {
      avatar: '风丸',
      ownership: 'owned',
      progression: '精1 70级',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
    // 精一五星：技能15 - 红脸进驻差5 + 星级4 + 精英化8 - 六星精二基准21，合计1再除以2。
    expect(metric(calc(wind.id, null, {}, [low]), label)).toBe(0.5)
    expect(metric(calc(angel.id), '自身心情消耗变化')).toBe(2)
  })
  it('巴别塔中枢按成员分别触发减耗、贸易与会客，取消魔王后额外减耗失效', () => {
    const full = calc('builtin-control-babel')
    expect(metric(full, '制造/贸易/发电/办公/会客·心情消耗变化')).toBe(-0.2)
    expect(metric(full, '魔王·自身心情消耗变化')).toBe(-0.1)
    expect(metric(full, '阿米娅·自身心情消耗变化')).toBe(-0.1)
    expect(metric(full, '魔王·会客线索搜集速度')).toBe(15)
    expect(metric(full, '伊内丝·会客线索搜集')).toBe(5)
    expect(metric(full, '所有贸易站·每站订单效率')).toBe(7)
    const alone = calc('builtin-control-babel', ['维什戴尔'])
    expect(metric(alone, '制造/贸易/发电/办公/会客·心情消耗变化')).toBe(-0.1)
    expect(metric(alone, '魔王·自身心情消耗变化')).toBeUndefined()
  })
  it('玛恩纳与Mon3tr的有效技能自动计入，制造加成单列，其他技能不可超过中枢人数', () => {
    const full = calc('builtin-control-mlynar')
    expect(metric(full, '制造/贸易·心情消耗变化')).toBe(-0.1)
    expect(metric(full, '发电/办公/会客·心情消耗变化')).toBe(-0.2)
    expect(metric(full, '中枢全员·心情消耗变化')).toBe(-0.1)
    expect(metric(full, '所有制造站·每站生产力')).toBe(2)
    expect(
      calc('builtin-control-mlynar', ['玛恩纳', 'Mon3tr', '临光', '杜宾', '红', '清道夫']).metrics
    ).toEqual([])
    const low = {
      avatar: '玛恩纳',
      ownership: 'owned',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
    expect(
      metric(calc('builtin-control-mlynar', null, {}, [low]), '制造/贸易·心情消耗变化')
    ).toBeCloseTo(0)
  })
  it('热情值由已选成员及宿舍人数产生，赤金和其他设施效果分别输出', () => {
    const full = calc('builtin-control-mujica')
    expect(metric(full, '热情值')).toBe(60)
    expect(metric(full, '非自动化赤金站·每站生产力')).toBe(4)
    expect(metric(full, '所有贸易站·每站订单效率')).toBe(7)
    expect(metric(full, '办公联络速度')).toBe(10)
    expect(metric(full, '会客线索搜集速度')).toBe(10)
    expect(metric(full, '丰川祥子·自身心情消耗变化')).toBeCloseTo(0)
    expect(metric(full, '若叶睦·自身心情消耗变化')).toBe(0)
    const withoutInitial = calc('builtin-control-mujica', [
      '丰川祥子',
      '八幡海铃',
      '祐天寺若麦',
      '若叶睦'
    ])
    expect(metric(withoutInitial, '热情值')).toBe(40)
    expect(metric(withoutInitial, '非自动化赤金站·每站生产力')).toBe(3)
    expect(metric(withoutInitial, '丰川祥子·自身心情消耗变化')).toBe(0.1)
    const two = calc('builtin-control-mujica', ['丰川祥子', '八幡海铃'])
    expect(metric(two, '非自动化赤金站·每站生产力')).toBe(1)
  })
  it('玛恩纳的16名相关干员全部列为备选，按所选技能自动计算且不再手填技能数', () => {
    const group = byId('builtin-control-mlynar')
    expect(group.core).toEqual(['玛恩纳'])
    expect([...group.support].sort()).toEqual(
      [
        'Mon3tr',
        '可露希尔',
        '电弧',
        '红隼',
        '薇薇安娜',
        '冰酿',
        '焰尾',
        '暴雨',
        '灰喉',
        '苇草',
        '送葬人',
        '坚雷',
        '临光',
        '红',
        '清道夫',
        '杜宾'
      ].sort()
    )
    expect(estimateFields(group).some((field) => field.key === 'extraMoodSkills')).toBe(false)
    const full = calc('builtin-control-mlynar', ['玛恩纳', 'Mon3tr', '临光', '杜宾', '红'])
    expect(metric(full, '制造/贸易·心情消耗变化')).toBe(-0.25)
    expect(metric(full, '发电/办公/会客·心情消耗变化')).toBeCloseTo(-0.35)
    expect(metric(full, '中枢全员·心情消耗变化')).toBe(-0.25)
  })
  it('红隼精二技能尚未解锁时不计入公事公办，解锁后才增加减耗', () => {
    const low = {
      avatar: '红隼',
      ownership: 'owned',
      childSkill: [
        { skill_key: 0, skill_level: 0, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
    const selected = ['玛恩纳', '红隼']
    expect(
      metric(calc('builtin-control-mlynar', selected, {}, [low]), '制造/贸易·心情消耗变化')
    ).toBe(-0.05)
    const high = {
      ...low,
      childSkill: low.childSkill.map((entry) => ({ ...entry, status: 'active' }))
    }
    expect(
      metric(calc('builtin-control-mlynar', selected, {}, [high]), '制造/贸易·心情消耗变化')
    ).toBe(-0.1)
  })
  it.each([
    'builtin-karlan',
    'builtin-jaye-siracusa',
    'builtin-jaye-hunters',
    'builtin-jaye-penguin',
    'builtin-jaye-parts',
    'single-孑'
  ])('%s一律限定三级贸易站', (id) => {
    const group = byId(id)
    const result = calc(id, group.recommended || group.core, { orderCap: 8, jayeStage: '未精英化' })
    expect(result.valid).toBe(false)
    expect(result.metrics).toEqual([])
    expect(result.warnings[0]).toContain('3级贸易站')
  })
  it('黑钢备选褐果与水月双人提供50%通用、80%源石，褐果低阶版本不补造30%源石', () => {
    expect(byId('builtin-standardization').support).toContain('褐果')
    const full = calc('builtin-standardization', ['水月', '褐果'])
    expect(metric(full, '通用制造生产力')).toBe(50)
    expect(metric(full, '源石制造生产力')).toBe(80)
    const low = {
      avatar: '褐果',
      ownership: 'owned',
      childSkill: [
        { skill_key: 0, skill_level: 0, skillname: '标准化·α', status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
    expect(
      metric(calc('builtin-standardization', ['水月', '褐果'], {}, [low]), '源石制造生产力')
    ).toBeUndefined()
  })
})
