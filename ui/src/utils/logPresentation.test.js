import { describe, expect, it } from 'vitest'

import { createLogPresenter } from './logPresentation.js'

const presentLine = createLogPresenter([
  '但书',
  '巫恋',
  '龙舌兰',
  '德克萨斯',
  '缄默德克萨斯',
  '陈',
  '假日威龙陈',
  '令',
  '年',
  '山',
  'W',
  'Current',
  'Free',
  '_'
])

function tokensOf(line, type) {
  return presentLine(line)
    .tokens.filter((token) => token.type === type)
    .map((token) => token.text)
}

describe('typed operator markers', () => {
  const present = createLogPresenter([
    '歌蕾蒂娅',
    '见行者',
    '红',
    '空',
    '年',
    '令',
    '山',
    '夕',
    'W',
    '德克萨斯',
    '缄默德克萨斯'
  ])
  const operators = (row) => row.tokens.filter((token) => token.type === 'operator')

  it.each([
    ['准备将[[operator:歌蕾蒂娅]]调整到第2位', '歌蕾蒂娅'],
    ['已确认[[operator:歌蕾蒂娅]]位于第2位', '歌蕾蒂娅'],
    ['重试后[[operator:歌蕾蒂娅]]已在计划位置', '歌蕾蒂娅'],
    ['将[[operator:见行者]]的驻员记录更新为空闲', '见行者'],
    ['将[[operator:空]]调整到第1位，其他位置保持空闲', '空'],
    ['重设[[operator:红]]至空闲', '红']
  ])('renders an exact typed marker from this record metadata: %s', (message, name) => {
    const source = `2026-11-05 02:00:00 INFO ${message}`
    const row = present(source, null, [name])
    expect(operators(row)).toEqual([{ type: 'operator', text: `[[operator:${name}]]`, name }])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
    expect(row.message.map((token) => token.text).join('')).toBe(message)
  })

  it.each([
    ['准备将歌蕾蒂娅调整到第2位', []],
    ['已确认歌蕾蒂娅位于第2位', []],
    ['将见行者的驻员记录更新为空闲', []],
    ['歌蕾蒂娅的心情恢复完成', []],
    ['将红调整到第1位', []],
    ['红色提示，今年仍有空闲，制造完成后下令，夕阳映在山间', []],
    ['char_歌蕾蒂娅 歌蕾蒂娅X _见行者 见行者_1 WXYZ myW', []],
    ['重设 红 至空闲', ['红']]
  ])('keeps the original conservative fallback for unmarked prose: %s', (message, names) => {
    const source = `INFO ${message}`
    const row = present(source, null, [
      '歌蕾蒂娅',
      '见行者',
      '红',
      '空',
      '年',
      '令',
      '山',
      '夕',
      'W'
    ])
    expect(operators(row).map((token) => token.name)).toEqual(names)
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it.each([
    ['[[operator:歌蕾蒂娅]]', []],
    ['[[operator:歌蕾蒂娅]]', ['见行者']],
    ['[[operator:歌蕾蒂娅]]', ['歌蕾']],
    ['[[operator:空闲]]', ['空']],
    ['[[operator:空]]', ['空闲']],
    ['[[room:红]]', ['红']],
    ['[[group:红]]', ['红']],
    ['[[backup:红]]', ['红']],
    ['[[unknown:红]]', ['红']],
    ['[[Operator:红]]', ['红']],
    ['[[operator:歌蕾蒂娅', ['歌蕾蒂娅']],
    ['[[operator:歌蕾蒂娅]', ['歌蕾蒂娅']],
    ['[[operator:[[operator:红]]]]', ['红']],
    ['[[operator:]]', ['']],
    ['[[operator:_]]', ['_']]
  ])(
    'preserves unknown, mismatched or incomplete typed markers as a whole: %s',
    (message, agents) => {
      const source = `INFO ${message}`
      const row = present(source, null, agents)
      expect(operators(row)).toEqual([])
      expect(row.tokens.some((token) => ['room', 'group', 'backup'].includes(token.type))).toBe(
        false
      )
      expect(row.tokens.map((token) => token.text).join('')).toBe(source)
    }
  )

  it('keeps a confirmed marker usable before the operator catalog is loaded', () => {
    const row = createLogPresenter()('INFO 准备将[[operator:见行者]]调整到第1位', null, ['见行者'])
    expect(operators(row)).toEqual([
      { type: 'operator', text: '[[operator:见行者]]', name: '见行者' }
    ])
  })

  it.each(['[[unknown:[[x]] 赤金]]', '[[unknown:x [[operator:红]] y [[operator:年]]]]'])(
    'preserves the complete nested unknown marker through operator and item parsing: %s',
    (marker) => {
      const source = `INFO ${marker}`
      const row = present(source, null, ['红', '年'])
      expect(operators(row)).toEqual([])
      expect(row.tokens.filter((token) => ['item', 'order-operator'].includes(token.type))).toEqual(
        []
      )
      expect(row.tokens.find((token) => token.text === marker)?.type).toBe('text')
      expect(row.tokens.map((token) => token.text).join('')).toBe(source)
    }
  )

  it('recognizes five consecutive independent operator markers without losing source offsets', () => {
    const agents = ['歌蕾蒂娅', '见行者', '红', '空', '年']
    const message =
      '[[operator:歌蕾蒂娅]]、[[operator:见行者]]、[[operator:红]]、[[operator:空]]、[[operator:年]]'
    const source = `2026-11-05 02:00:00 INFO ${message}`
    const row = present(source, null, agents)
    expect(operators(row).map((token) => token.name)).toEqual(agents)
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
    expect(row.message.map((token) => token.text).join('')).toBe(message)
  })

  it('ends an unclosed outer marker at the newline and recognizes the next line independently', () => {
    const source = 'INFO [[unknown:[[x]] 赤金\n[[operator:红]]已到位'
    const row = present(source, null, ['红'])
    expect(operators(row)).toEqual([{ type: 'operator', text: '[[operator:红]]', name: '红' }])
    expect(row.tokens.filter((token) => token.type === 'item')).toEqual([])
    expect(row.tokens.find((token) => token.text === '[[unknown:[[x]] 赤金')?.type).toBe('text')
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('keeps old nested Python lists outside the typed marker protocol', () => {
    const source = "INFO [['红'], ['年']]"
    const row = present(source)
    expect(operators(row).map((token) => token.name)).toEqual(['红', '年'])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it.each([
    ['[[room:赤金]]', ['赤金'], false],
    ['[[operator:无人机]]', ['无人机'], true],
    ['[[unknown:但书]]', ['但书'], false],
    ['[[unknown:当前为 但书 订单，订单价值为1000]]', ['但书'], false],
    ['[[room:赤金', ['赤金'], false]
  ])('protects complete marker spans from later item highlighting: %s', (marker, agents, named) => {
    const source = `INFO 赤金；${marker}`
    const row = present(source, null, agents)
    expect(operators(row).map((token) => token.name)).toEqual(named ? ['无人机'] : [])
    expect(row.tokens.filter((token) => token.type === 'order-operator')).toEqual([])
    expect(row.tokens.filter((token) => token.type === 'item').map((token) => token.text)).toEqual([
      '赤金'
    ])
    expect(row.tokens.find((token) => token.text === marker)?.type).toBe(
      named ? 'operator' : 'text'
    )
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('keeps complete backup names ahead of operator markers with the same visible name', () => {
    const source = 'INFO 已激活的副表：[[operator:红]]'
    const row = present(source, null, ['红'], null, null, [
      { name: '[[operator:红]]', active: true }
    ])
    expect(operators(row)).toEqual([])
    expect(row.tokens.filter((token) => token.type === 'backup')).toEqual([
      { type: 'backup', text: '[[operator:红]]' }
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('preserves old single-quoted lists, shift labels and task-title brackets', () => {
    const source = "INFO ['红', '空', '年', '令', '山', '夕', 'W']；随后执行「红上班」"
    const row = present(source)
    expect(operators(row).map((token) => token.name)).toEqual([
      '红',
      '空',
      '年',
      '令',
      '山',
      '夕',
      'W',
      '红'
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })
})

describe('historical backup names', () => {
  const present = createLogPresenter(['红松', '深海'], {}, ['深海', '红松'])

  it('keeps complete metadata names ahead of group and operator matches', () => {
    const source = 'INFO 已激活的副表：深海下班、红松上班；已停用的副表：夜班'
    const row = present(source, null, null, null, null, [
      { name: '深海下班', active: true },
      { name: '红松上班', active: true },
      { name: '夜班', active: false }
    ])
    expect(
      row.tokens.filter((token) => token.type === 'backup').map((token) => token.text)
    ).toEqual(['深海下班', '红松上班', '夜班'])
    expect(row.tokens.some((token) => ['group', 'operator'].includes(token.type))).toBe(false)
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('protects full names in legacy activation fields without guessing from current plans', () => {
    const source = 'INFO 已激活的副表：深海下班；已停用的副表：红松上班'
    const row = present(source)
    expect(
      row.tokens.filter((token) => token.type === 'backup').map((token) => token.text)
    ).toEqual(['深海下班', '红松上班'])
    expect(row.tokens.some((token) => ['group', 'operator'].includes(token.type))).toBe(false)
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('accepts current and legacy selected-tag wording without losing source text', () => {
    for (const label of ['选择标签：', '标签：']) {
      const source = `INFO 1号招募位：开始招募，${label}治疗、费用回复，时长：9小时`
      const row = present(source, null, null, null, {
        event: 'start',
        tags: ['治疗', '费用回复'],
        rarity: 4
      })
      expect(row.tokens.filter((token) => token.type === 'recruit-tags')).toHaveLength(1)
      expect(row.tokens.map((token) => token.text).join('')).toBe(source)
    }
  })
})

describe('inline base products and orders', () => {
  it('keeps the order operator distinct while retaining order text and the later operator', () => {
    const source = 'INFO 当前为 但书 订单, 订单价值为: 2500；安排干员：但书'
    const row = presentLine(source)
    expect(
      row.tokens.filter((token) => token.type === 'order-operator').map((token) => token.name)
    ).toEqual(['但书'])
    expect(
      row.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
    ).toEqual(['但书'])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('keeps full backup names intact when they contain a product name', () => {
    const source = 'INFO 已激活的副表：赤金夜班；当前制造产物：赤金'
    const row = presentLine(source, null, null, null, null, [{ name: '赤金夜班', active: true }])
    expect(
      row.tokens.filter((token) => token.type === 'backup').map((token) => token.text)
    ).toEqual(['赤金夜班'])
    expect(row.tokens.filter((token) => token.type === 'item').map((token) => token.text)).toEqual([
      '赤金'
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })
})

describe('recruitment tag groups', () => {
  it('keeps every rare combination together without merging shared tags or keeping only the last', () => {
    const combinations = [
      { tags: ['先锋干员', '支援'], rarity: 5 },
      { tags: ['近战位', '控场'], rarity: 5 },
      { tags: ['先锋干员', '控场'], rarity: 5 }
    ]
    const text = 'INFO 2号招募位：发现稀有标签：先锋干员＋支援；近战位＋控场；先锋干员＋控场'
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'rare',
      rarity: 5,
      combinations
    })
    expect(row.tokens.filter((token) => token.type.startsWith('recruit-'))).toEqual([
      { type: 'recruit-notice', text: '发现稀有标签', rarity: 5 },
      {
        type: 'recruit-combinations',
        text: '先锋干员＋支援；近战位＋控场；先锋干员＋控场',
        combinations
      }
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
    expect(row.tokens.some((token) => token.type === 'operator')).toBe(false)
  })

  it('retains per-combination rarities independently from the notice rarity', () => {
    const combinations = [
      { tags: ['治疗', '费用回复'], rarity: 4 },
      { tags: ['资深干员'], rarity: 5 },
      { tags: ['高级资深干员'], rarity: 6 }
    ]
    const text = 'INFO 2号招募位：发现稀有标签：治疗＋费用回复；资深干员；高级资深干员'
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'rare',
      rarity: 6,
      combinations
    })
    expect(row.tokens.find((token) => token.type === 'recruit-notice').rarity).toBe(6)
    expect(row.tokens.find((token) => token.type === 'recruit-combinations').combinations).toEqual(
      combinations
    )
    combinations[0].tags.push('输出')
    expect(
      row.tokens.find((token) => token.type === 'recruit-combinations').combinations[0].tags
    ).toEqual(['治疗', '费用回复'])
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it('accepts all 25 combinations at the metadata bound', () => {
    const combinations = Array.from({ length: 25 }, (_, index) => ({
      tags: [`标签${index}`],
      rarity: 5
    }))
    const text =
      'INFO 2号招募位：发现稀有标签：' + combinations.map((choice) => choice.tags[0]).join('；')
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'rare',
      rarity: 5,
      combinations
    })
    expect(
      row.tokens.find((token) => token.type === 'recruit-combinations').combinations
    ).toHaveLength(25)
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it.each([
    null,
    [],
    [null],
    [[]],
    ['先锋干员'],
    [{ tags: [], rarity: 5 }],
    [{ tags: ['先锋干员', '支援', '控场', '近战位'], rarity: 5 }],
    [{ tags: ['先锋干员', '先锋干员'], rarity: 5 }],
    [{ tags: ['先锋干员'], rarity: 7 }],
    [{ tags: ['先锋干员'], rarity: '5' }],
    [{ tags: ['先'.repeat(33)], rarity: 5 }],
    [{ tags: ['先锋干员＋支援'], rarity: 5 }],
    Array.from({ length: 26 }, (_, index) => ({ tags: [`标签${index}`], rarity: 5 })),
    [{ tags: ['近战位', '控场'], rarity: 5 }]
  ])(
    'leaves invalid or incomplete multi-combination metadata as source text: %j',
    (combinations) => {
      const text = 'INFO 2号招募位：发现稀有标签：先锋干员＋支援；近战位＋控场'
      const row = presentLine(text, null, null, 'recruitment', {
        event: 'rare',
        rarity: 5,
        combinations
      })
      expect(row.tokens.some((token) => token.type.startsWith('recruit-'))).toBe(false)
      expect(row.tokens.map((token) => token.text).join('')).toBe(text)
    }
  )

  it('rejects mixed legacy tags and new combinations rather than choosing one schema', () => {
    const text = 'INFO 2号招募位：发现稀有标签：先锋干员＋支援'
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'rare',
      rarity: 5,
      tags: ['先锋干员', '支援'],
      combinations: [{ tags: ['先锋干员', '支援'], rarity: 5 }]
    })
    expect(row.tokens.some((token) => token.type.startsWith('recruit-'))).toBe(false)
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it.each(['9小时', '3小时50分'])('keeps the complete duration field together: %s', (duration) => {
    const text = `INFO 1号招募位：开始招募，标签：支援机械，时长：${duration}`
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'start',
      tags: ['支援机械'],
      rarity: 1
    })
    expect(row.tokens.filter((token) => token.type === 'recruit-duration')).toEqual([
      { type: 'recruit-duration', text: `时长：${duration}` }
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
    expect(presentLine(text).tokens.some((token) => token.type === 'recruit-duration')).toBe(false)
  })

  it.each([4, 5, 6])(
    'colors the confirmed %i-star combination as one source-preserving group',
    (rarity) => {
      const text = '2026-11-04 18:00:00 INFO 1号招募位：开始招募，标签：治疗、费用回复，时长：9小时'
      const row = presentLine(text, null, null, 'recruitment', {
        event: 'start',
        tags: ['治疗', '费用回复'],
        rarity
      })
      expect(row.tokens.filter((token) => token.type === 'recruit-tags')).toEqual([
        { type: 'recruit-tags', text: '治疗、费用回复', tags: ['治疗', '费用回复'], rarity }
      ])
      expect(row.tokens.map((token) => token.text).join('')).toBe(text)
      expect(row.message.map((token) => token.text).join('')).toBe(
        text.slice(text.indexOf('1号招募位'))
      )
    }
  )

  it('uses the same rarity for the rare notice and its complete combination', () => {
    const text = 'INFO 1号招募位：发现稀有标签：先锋干员、支援'
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'rare',
      tags: ['先锋干员', '支援'],
      rarity: 5
    })
    expect(row.tokens.filter((token) => token.type.startsWith('recruit-'))).toEqual([
      { type: 'recruit-notice', text: '发现稀有标签', rarity: 5 },
      { type: 'recruit-tags', text: '先锋干员、支援', tags: ['先锋干员', '支援'], rarity: 5 }
    ])
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it('keeps recognized tags neutral rather than claiming individual guarantees', () => {
    const text = 'INFO 4号招募位：识别标签：重装干员、辅助干员、治疗、费用回复、输出'
    const tags = ['重装干员', '辅助干员', '治疗', '费用回复', '输出']
    const row = presentLine(text, null, null, 'recruitment', { event: 'tags', tags, rarity: 6 })
    expect(row.tokens.filter((token) => token.type === 'recruit-tags')).toEqual([
      { type: 'recruit-tags', text: tags.join('、'), tags, rarity: null }
    ])
  })

  it.each([
    null,
    [],
    { event: 'unknown', tags: ['治疗'], rarity: 4 },
    { event: {}, tags: ['治疗'], rarity: 4 },
    { event: 'start', tags: ['治疗'], rarity: 7 },
    { event: 'start', tags: ['治疗'], rarity: '4' },
    { event: 'start', tags: ['治疗'], rarity: undefined },
    { event: 'start', tags: ['治疗', '治疗'], rarity: 4 },
    { event: 'start', tags: ['治疗\n'], rarity: 4 },
    { event: 'start', tags: ['治疗', '费用回复'], rarity: 4 },
    { event: 'rare', tags: ['治疗'], rarity: 4 }
  ])('leaves old text and mismatched metadata unchanged: %j', (recruitment) => {
    const text = 'INFO 1号招募位：开始招募，标签：治疗，时长：9小时'
    const row = presentLine(text, null, null, 'recruitment', recruitment)
    expect(row.tokens.some((token) => token.type.startsWith('recruit-'))).toBe(false)
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it('does not create a separate portrait when a tag contains a known operator name', () => {
    const text = 'INFO 1号招募位：开始招募，标签：山，时长：9小时'
    const row = presentLine(text, null, ['山'], 'recruitment', {
      event: 'start',
      tags: ['山'],
      rarity: 4
    })
    expect(row.tokens.filter((token) => token.type === 'operator')).toEqual([])
    expect(row.tokens.find((token) => token.type === 'recruit-tags').text).toBe('山')
  })

  it('does not color only the first tag of a longer combination', () => {
    const text = 'INFO 1号招募位：开始招募，标签：治疗、费用回复，时长：9小时'
    const row = presentLine(text, null, null, 'recruitment', {
      event: 'start',
      tags: ['治疗'],
      rarity: 4
    })
    expect(row.tokens.some((token) => token.type.startsWith('recruit-'))).toBe(false)
    expect(row.tokens.map((token) => token.text).join('')).toBe(text)
  })
})

describe('log presentation tokens', () => {
  it('recognizes an idle transition in historical prose while retaining the original action text', () => {
    const source = '2026-11-05 14:58:49 INFO 红松上班；桑葚休息；陈转为空闲'
    const row = createLogPresenter(['桑葚', '陈'], {}, ['红松'])(source)
    expect(
      row.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
    ).toEqual(['桑葚', '陈'])
    expect(row.tokens.filter((token) => token.type === 'group').map((token) => token.text)).toEqual(
      ['红松']
    )
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })
  it('highlights configured shift groups without mistaking ordinary operator mentions for groups', () => {
    const present = createLogPresenter(['红', '巫恋'], {}, ['红松', '红', '巫恋'])
    const source = '2026-11-04 18:00:00 INFO 红松上班、巫恋休息；安排干员：红、巫恋'
    const row = present(source)
    expect(row.tokens.filter((token) => token.type === 'group').map((token) => token.text)).toEqual(
      ['红松', '巫恋']
    )
    expect(
      row.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
    ).toEqual(['红', '巫恋'])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)
  })

  it('recognizes live timestamps, levels, facility identifiers and quoted operator lists', () => {
    const text =
      "2026-10-31 16:05:10,879 INFO 安排干员：['但书', '巫恋', '龙舌兰'] room_2_1 dormitory_3"
    const line = presentLine(text)

    expect(line.text).toBe(text)
    expect(line.tokens.map((token) => token.text).join('')).toBe(text)
    expect(tokensOf(text, 'date')).toEqual(['2026-10-31'])
    expect(tokensOf(text, 'time')).toEqual(['16:05:10,879'])
    expect(tokensOf(text, 'level')).toEqual(['INFO'])
    expect(tokensOf(text, 'room')).toEqual(['room_2_1', 'dormitory_3'])
    expect(line.tokens.filter((token) => token.type === 'operator')).toEqual([
      { type: 'operator', name: '但书', text: '但书' },
      { type: 'operator', name: '巫恋', text: '巫恋' },
      { type: 'operator', name: '龙舌兰', text: '龙舌兰' }
    ])
    expect(line).toMatchObject({ level: 'INFO', detail: false, classification: 'normal' })
  })

  it('renders structured entities in their original message positions', () => {
    const text = '2026-10-31 16:05:10,879 INFO 安排干员：但书、巫恋 → B201'
    const line = presentLine(text, 'room_2_1', ['但书', '巫恋', '龙舌兰'])
    expect(line.tokens.map((token) => token.text).join('')).toBe(text)
    expect(
      line.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
    ).toEqual(['但书', '巫恋'])
    expect(line.tokens.filter((token) => token.type === 'room')).toEqual([
      { type: 'room', text: 'B201', roomId: 'room_2_1' }
    ])
  })

  it('does not invent message entities or match unrelated room aliases', () => {
    const line = presentLine('INFO B201 B3010 myB301 → B301', 'room_3_1', ['未知干员'])
    expect(line.tokens.filter((token) => token.type === 'operator')).toEqual([])
    expect(line.tokens.filter((token) => token.type === 'room')).toEqual([
      { type: 'room', text: 'B301', roomId: 'room_3_1' }
    ])
  })

  it('falls back to regex extraction when structured fields are absent', () => {
    const text = "2026-10-31 16:05:10,879 INFO 安排干员：['但书', '巫恋'] room_2_1"
    // 不提供结构化字段时，仍从文本提取
    const line = presentLine(text)

    expect(tokensOf(text, 'room')).toEqual(['room_2_1'])
    expect(line.tokens.filter((token) => token.type === 'operator')).toEqual([
      { type: 'operator', name: '但书', text: '但书' },
      { type: 'operator', name: '巫恋', text: '巫恋' }
    ])
    expect(line.structuredRoom).toBeUndefined()
    expect(line.structuredAgents).toBeUndefined()
  })

  it('matches whole altered names before their shorter original names', () => {
    expect(tokensOf('缄默德克萨斯, 德克萨斯、假日威龙陈 / 陈', 'operator')).toEqual([
      '缄默德克萨斯',
      '德克萨斯',
      '假日威龙陈',
      '陈'
    ])
  })

  it('keeps complete operator names with middle dots and leaves unknown dotted names intact', () => {
    const present = createLogPresenter([
      '凯尔希',
      '凯尔希·思衡托',
      '维娜·维多利亚',
      '德·托莱多',
      '陈'
    ])
    const source =
      'INFO 凯尔希·思衡托上班；德·托莱多休息；安排干员：凯尔希、维娜·维多利亚、凯尔希·未知、凯尔希·思衡托·未知、未知·陈休息'
    const row = present(source)
    expect(
      row.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
    ).toEqual(['凯尔希·思衡托', '德·托莱多', '凯尔希', '维娜·维多利亚'])
    expect(row.tokens.map((token) => token.text).join('')).toBe(source)

    const forecast = createLogPresenter(['凯尔希·思衡托'], {}, ['凯尔希'], {
      structuredGroups: true
    })
    expect(forecast('凯尔希·思衡托上班').tokens).toEqual([
      { type: 'operator', name: '凯尔希·思衡托', text: '凯尔希·思衡托' },
      { type: 'text', text: '上班' }
    ])
  })

  it('excludes underscores, common character substrings and unknown longer names from avatars', () => {
    const text = 'Current, Free, _, 今年下令, 山间, 未知德克萨斯, 德克萨斯X, WXYZ, 令、年、山、W'
    expect(tokensOf(text, 'operator')).toEqual(['Current', 'Free', '令', '年', '山', 'W'])
  })

  it('recognizes Current and Free portraits without a roster while preserving word boundaries and copy text', () => {
    const text = "INFO ['Current', 'Free', '_'] CurrentTask Freezing myCurrent Free_1"
    const line = createLogPresenter()(text)
    expect(line.tokens.filter((token) => token.type === 'operator')).toEqual([
      { type: 'operator', name: 'Current', text: 'Current' },
      { type: 'operator', name: 'Free', text: 'Free' }
    ])
    expect(line.text).toBe(text)
    expect(line.tokens.map((token) => token.text).join('')).toBe(text)
  })

  it('escapes special characters in known names and reuses the compiled matcher without cursor state', () => {
    const special = createLogPresenter(new Set(['A+B', 'A.B', 'A[B]', '★A(β)', 'A+B']))
    const text = "['A+B', 'A.B', 'A[B]', '★A(β)'] AAB, AxB"
    const expected = ['A+B', 'A.B', 'A[B]', '★A(β)']
    for (let index = 0; index < 2; index++) {
      const line = special(text)
      expect(
        line.tokens.filter((token) => token.type === 'operator').map((token) => token.name)
      ).toEqual(expected)
      expect(line.tokens.map((token) => token.text).join('')).toBe(text)
    }
  })

  it.each([
    '',
    'unstructured\r\n  detail\twith spaces',
    '2026-10-31 16:05:10.123 ERROR <img src=x onerror="alert(1)"> & <script>巫恋</script>',
    'ERROR tap: (100, 200)\nTraceback (most recent call last):\n  <unknown>\n'
  ])('keeps untrusted and multiline source text unchanged: %j', (text) => {
    const line = presentLine(text)
    expect(line.text).toBe(text)
    expect(line.tokens.map((token) => token.text).join('')).toBe(text)
    expect(line.tokens.every((token) => typeof token.text === 'string')).toBe(true)
    expect(line.tokens.some((token) => 'html' in token)).toBe(false)
  })

  it('supports compact timestamps and facility suffixes without partial identifier matches', () => {
    const text = '16:05:10,879 INFO dormitory_1_low gaming_2 central train room_1_1X myroom_1_1'
    expect(tokensOf(text, 'date')).toEqual([])
    expect(tokensOf(text, 'time')).toEqual(['16:05:10,879'])
    expect(tokensOf(text, 'room')).toEqual(['dormitory_1_low', 'gaming_2', 'central', 'train'])
  })

  it.each([
    ['下次任务在17:22:51', 'time', ['17:22:51']],
    ['08:45:00之后开始任务', 'time', ['08:45:00']],
    ['任务于2026-10-31当天执行', 'date', ['2026-10-31']],
    ['记录时间：16:05:10,879。', 'time', ['16:05:10,879']],
    ['时间16:05:10.123已确认', 'time', ['16:05:10.123']]
  ])(
    'highlights dates and times beside Chinese prose and punctuation: %s',
    (line, type, expected) => {
      expect(tokensOf(line, type)).toEqual(expected)
      expect(
        presentLine(line)
          .tokens.map((token) => token.text)
          .join('')
      ).toBe(line)
    }
  )

  it.each([
    '编号12026-10-310',
    '编号2026-10-319',
    '编号117:22:51',
    '编号17:22:519',
    '编号17:22:51,1234567',
    '编号17:22:51.1234567',
    '编号20261031 172251123'
  ])('does not extract a partial timestamp from a longer numeric value: %s', (line) => {
    expect(tokensOf(line, 'date')).toEqual([])
    expect(tokensOf(line, 'time')).toEqual([])
    expect(
      presentLine(line)
        .tokens.map((token) => token.text)
        .join('')
    ).toBe(line)
  })
})

describe('facility token boundaries', () => {
  it.each([
    ['任务与当前房间相同，跳过安排room_1_1人员', ['room_1_1']],
    ['安排dormitory_1_low人员到gaming_2', ['dormitory_1_low', 'gaming_2']],
    [
      '返回central后打开contact与factory，检查meeting/train/recycle',
      ['central', 'contact', 'factory', 'meeting', 'train', 'recycle']
    ]
  ])('recognizes facility identifiers beside Chinese prose: %s', (line, expected) => {
    expect(tokensOf(line, 'room')).toEqual(expected)
    expect(
      presentLine(line)
        .tokens.map((token) => token.text)
        .join('')
    ).toBe(line)
  })

  it('does not extract facility identifiers inside longer ASCII identifiers', () => {
    const line =
      'myroom_1_1 room_1_1X dormitory_1X gaming_2x mycentral centralization contactX factory2'
    expect(tokensOf(line, 'room')).toEqual([])
    expect(
      presentLine(line)
        .tokens.map((token) => token.text)
        .join('')
    ).toBe(line)
  })
})

describe('conservative operation detail classification', () => {
  it.each([
    '2026-10-31 16:05:10,879 INFO 打开 ALL 筛选',
    'INFO 打开 SUPPORT 筛选',
    'INFO 关闭职业筛选',
    'INFO 等待动画',
    '2026-10-31 16:05:10,879 arknights_mower/solvers/base_mixin.py:1268 INFO profession_filter: 打开 MEDIC 筛选'
  ])('weakens the exact existing INFO filter and animation steps: %s', (text) => {
    expect(presentLine(text)).toMatchObject({
      level: 'INFO',
      detail: true,
      classification: 'operations'
    })
  })

  it.each([
    '2026-10-31 16:05:10,879 DEBUG tap: (100, 200)',
    'INFO tap: (-2, 50)',
    'DEBUG swipe: (100, 200) -> (300, 400), duration=100',
    '2026-10-31 16:05:10,879 DEBUG swipe_ext: points=[(1, 2), (3, 4)], durations=[100, 200], up_wait=200',
    'DEBUG keyevent: KEYCODE_BACK',
    'DEBUG keyevent: 3',
    '2026-10-31 16:05:10,879 arknights_mower/utils/device/device.py:895 DEBUG tap: tap: (100, 200)'
  ])('weakens only a complete known execution-detail format: %s', (text) => {
    expect(presentLine(text)).toMatchObject({ detail: true, classification: 'operations' })
  })

  it.each(['WARN', 'WARNING', 'ERROR', 'CRITICAL'])(
    'never weakens %s execution messages',
    (level) => {
      expect(presentLine(`${level} tap: (100, 200)`)).toMatchObject({
        level: level === 'WARN' ? 'WARNING' : level,
        detail: false,
        classification: 'normal'
      })
      for (const message of ['打开 ALL 筛选', '关闭职业筛选', '等待动画']) {
        expect(presentLine(`${level} ${message}`)).toMatchObject({
          detail: false,
          classification: 'normal'
        })
      }
    }
  )

  it('keeps the most severe level when a line contains several level markers', () => {
    expect(presentLine('INFO DEBUG WARNING ERROR CRITICAL tap: (100, 200)')).toMatchObject({
      level: 'CRITICAL',
      detail: false,
      classification: 'normal'
    })
    expect(presentLine('DEBUG INFO WARN WARNING ERROR')).toMatchObject({ level: 'ERROR' })
    expect(tokensOf('INFOGRAPHIC ERROR_CODE DEBUGGER', 'level')).toEqual([])
  })

  it.each([
    ['INFO', '比例规则「ERROR」的刷取比例相同（1:1），本轮选择 1-7', 'INFO'],
    ['WARN', '用户配置的名称为「CRITICAL」', 'WARNING']
  ])(
    'keeps the timestamped source level %s when the message names another level',
    (level, body, expected) => {
      const text = `2026-11-06 19:00:00,123 ${level} ${body}`
      const row = presentLine(text)
      expect(row.level).toBe(expected)
      expect(row.message.map((token) => token.text).join('')).toBe(body)
    }
  )

  it.each([
    'INFO 点击会客室信息板入口',
    'INFO 滑动验证码',
    'INFO 点击顺序：[1, 2, 3]',
    'DEBUG 干员 巫恋 已有蓝框，跳过再次点击',
    'INFO 打开 UNKNOWN 筛选',
    'INFO 打开 ALL 筛选失败',
    'INFO 打开 ALL 筛选后页面无响应',
    'INFO 无法关闭职业筛选',
    'INFO 关闭职业筛选失败，恢复原界面',
    'INFO 等待动画超时',
    'INFO 恢复期间等待动画',
    'INFO 等待动画后重试设备连接',
    'INFO Scene 207: 干员进驻设施排班界面',
    "INFO 安排干员：['巫恋']",
    'INFO 等待跑单 148.4 秒',
    'INFO 下一步可能调用 tap: (100, 200)',
    'DEBUG tap: (100, 200) 失败',
    'DEBUG swipe: invalid coordinates',
    'tap in a copied traceback',
    'DEBUG tap: (100, 200)\nERROR 设备无法响应'
  ])('leaves task stages, errors and incomplete operation phrases ordinary: %s', (text) => {
    expect(presentLine(text)).toMatchObject({ detail: false, classification: 'normal' })
  })
})

describe('leading log stamps', () => {
  function rebuild(text) {
    const stamp = presentLine(text).stamp
    const fields = [stamp.date ?? '', stamp.dateGap, stamp.time, stamp.fraction]
    return fields.concat(stamp.levelGap, stamp.level ?? '', stamp.gap).join('')
  }

  it('splits the live date, time, fraction and level and rebuilds the exact prefix', () => {
    const text = '2026-10-31 16:05:10,879 WARNING 截图识别结果需要复核'
    expect(presentLine(text).stamp).toEqual({
      length: 32,
      date: '2026-10-31',
      dateGap: ' ',
      time: '16:05:10',
      fraction: ',879',
      levelGap: ' ',
      level: 'WARNING',
      gap: ' '
    })
    expect(rebuild(text) + text.slice(32)).toBe(text)
  })

  it.each([
    '2026-10-31 16:05:11.123 INFO 等待动画',
    '2026-10-31 16:05:10 WARN 短级别',
    '16:05:10 INFO 只有时间',
    '2026-10-31 16:05:10,879 arknights_mower/utils/device/device.py:895 DEBUG tap: (100, 200)',
    '2026-10-31 16:05:10'
  ])('keeps every source character when reading %s', (text) => {
    const { stamp } = presentLine(text)
    expect(rebuild(text)).toBe(text.slice(0, stamp.length))
  })

  it('returns the message tokens after the stamp and the full tokens without one', () => {
    const text = "2026-10-31 16:05:10,879 INFO 安排干员：['巫恋'] room_2_1"
    const line = presentLine(text)
    expect(line.message.map((token) => token.text).join('')).toBe(text.slice(29))
    expect(line.message.map((token) => token.type)).toEqual(['text', 'operator', 'text', 'room'])
    const bare = presentLine('  File "scheduler.py", line 72')
    expect(bare.message).toBe(bare.tokens)
  })

  it('reads only a leading time and ignores dates, levels and times inside messages', () => {
    for (const text of [
      '2026-10-31 INFO 没有完整时间头',
      'INFO 下一次检查安排在 08:45:00',
      '  File "scheduler.py", line 72, in arrange',
      '12345 条任务仍在队列中',
      '16:05:10123 不是时间'
    ])
      expect(presentLine(text).stamp).toBeNull()
    expect(presentLine('2026-10-31 16:05:10 INFOGRAPHIC').stamp).toMatchObject({
      level: null,
      length: 20
    })
  })
})
