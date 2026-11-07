import { describe, expect, it } from 'vitest'
import { logItemMatches } from './logItems.js'
import { BASE_PRODUCT_COLORS, ORDER_COLORS } from './baseReport.js'

describe('log item presentation', () => {
  it('keeps current base-report fields complete with spaced units, zero and unread values', () => {
    const items = [
      { name: '作战录像', value: 42, unit: '经验', item: '中级作战记录' },
      { name: '赤金制造价值', value: 0, unit: '龙门币', item: '赤金' },
      { name: '龙门币订单金额', value: 1000, unit: '龙门币', item: '龙门币' },
      { name: '龙门币订单数', value: 2, unit: '笔', item: '龙门币' },
      { name: '合成玉', value: null, unit: '个', item: '合成玉' },
      { name: '合成玉订单数', value: null, unit: '笔', item: '合成玉' }
    ]
    const parts = [
      '作战录像：42 经验',
      '赤金制造价值：0 龙门币',
      '龙门币订单金额：1000 龙门币',
      '龙门币订单数：2 笔',
      '合成玉：未读出',
      '合成玉订单数：未读出'
    ]
    const source = '已保存 2026-11-05 的基报：\n' + parts.join('\n')
    const matches = logItemMatches(source, { type: 'base-report', date: '2026-11-05', items })
    expect(matches.map((entry) => entry.text)).toEqual(parts)
    expect(matches.map((entry) => entry.icon)).toEqual(
      items.map((entry) => `/depot/${encodeURIComponent(entry.item)}.webp`)
    )
    expect(matches.every((entry) => source.slice(entry.start, entry.end) === entry.text)).toBe(true)
    expect(
      logItemMatches('本次Mower刷理智掉落结果已计入库存：固源岩×2', {
        type: 'operation-drops',
        items: [{ name: '固源岩', count: 2 }]
      }).map((entry) => entry.text)
    ).toEqual(['固源岩×2'])
  })
  it('retains signed crafting amounts and hyphens in material names without guessing other records', () => {
    const text = '蜜莓加工切削原液完成3次，库存变化：RMA70-12-3、切削原液+3'
    const event = {
      type: 'workshop-result',
      changes: [
        { name: 'RMA70-12', delta: -3 },
        { name: '切削原液', delta: 3 }
      ]
    }
    const changes = logItemMatches(text, event).filter((entry) => entry.type === 'inventory-change')
    expect(changes.map((entry) => [entry.text, entry.delta])).toEqual([
      ['RMA70-12-3', -3],
      ['切削原液+3', 3]
    ])
    expect(changes[0].icon).toContain('RMA70-12')
    expect(logItemMatches(text).filter((entry) => entry.type === 'inventory-change')).toEqual([])
    for (const changed of [
      { ...event, type: 'another-result' },
      { ...event, changes: event.changes.slice().reverse() },
      { ...event, changes: [{ name: 'RMA70-12', delta: 0 }] },
      { ...event, changes: [{ name: 'RMA70-12', delta: Number.MAX_SAFE_INTEGER + 1 }] }
    ])
      expect(
        logItemMatches(text, changed).filter((entry) => entry.type === 'inventory-change')
      ).toEqual([])
    expect(
      logItemMatches(text + '（尚未确认）', event).filter(
        (entry) => entry.type === 'inventory-change'
      )
    ).toEqual([])
  })
  it('uses report colors and existing item icons while retaining complete recipe names', () => {
    const text = '制造站 B202：当前产物为源石碎片（装置）；使用3架无人机'
    const matches = logItemMatches(text)
    expect(matches.map((item) => item.text)).toEqual(['源石碎片（装置）', '无人机'])
    expect(matches[0]).toMatchObject({
      lightColor: BASE_PRODUCT_COLORS.light.orundum,
      darkColor: BASE_PRODUCT_COLORS.dark.orundum
    })
    expect(matches[0].icon).toContain(encodeURIComponent('源石碎片'))
    expect(matches[1].lightColor).toBe(BASE_PRODUCT_COLORS.light.special)
    expect(matches[1].icon).toContain('drone.png')
    for (const match of matches) expect(text.slice(match.start, match.end)).toBe(match.text)
  })

  it('colors the actual order classification using its recorded value', () => {
    const text = '当前为 但书 订单, 订单价值为: 2500；当前为 佩佩 订单，订单价值为：2000'
    const matches = logItemMatches(text)
    expect(matches.map((item) => item.text)).toEqual(['但书', '佩佩'])
    expect(matches[0]).toMatchObject({ type: 'order-operator', name: '但书' })
    expect(matches[0].icon).toBeUndefined()
    expect(matches[0].lightColor).toBe(ORDER_COLORS.light.但书_2500)
    expect(matches[1].darkColor).toBe(ORDER_COLORS.dark.佩佩)
  })

  it('does not classify an operator mention as an order or lose repeated item occurrences', () => {
    expect(logItemMatches('安排干员：但书、佩佩')).toEqual([])
    const text = '赤金；赤金；龙门商法；开采协力'
    const first = logItemMatches(text)
    expect(first.map((item) => item.text)).toEqual(['赤金', '赤金', '龙门商法', '开采协力'])
    expect(logItemMatches(text)).toEqual(first)
  })
})
