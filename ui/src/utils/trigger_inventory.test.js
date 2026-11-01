import { describe, expect, it } from 'vitest'
import {
  extract_inventory_counts,
  inventory_expression,
  inventory_options,
  inventory_options_with_counts,
  parse_inventory_expression
} from './trigger_inventory'

describe('副表仓库资源条件', () => {
  it('只提供指定的仓库资源', () => {
    expect(inventory_options.map(({ value }) => value)).toEqual([
      '赤金',
      '源石碎片',
      '固源岩',
      '装置',
      '龙门币',
      '全部经验（计算）'
    ])
    expect(inventory_options.find(({ value }) => value === '全部经验（计算）').icon).toBe('EXP')
  })

  it('生成并解析仓库资源表达式', () => {
    const expression = inventory_expression('固源岩')
    expect(expression).toBe("op_data.inventory_count('固源岩')")
    expect(parse_inventory_expression(expression)).toBe('固源岩')
    expect(parse_inventory_expression('42')).toBeUndefined()
  })

  it('从仓库接口提取数量并显示在选项中', () => {
    const inventory = extract_inventory_counts({
      depot: [
        {
          A常用: { 龙门币: { number: 123456 } },
          B经验卡: { '全部经验（计算）': { number: 12000 } },
          K未分类: { 源石碎片: { number: 8 } }
        }
      ]
    })
    const options = inventory_options_with_counts(inventory)

    const lmd = options.find(({ value }) => value === '龙门币')
    expect(lmd.label).toBe('龙门币（当前库存：123,456）')
    expect(lmd.name).toBe('龙门币')
    expect(lmd.inventoryText).toBe('123,456')
    expect(options.find(({ value }) => value === '全部经验（计算）').label).toBe(
      '全部经验（计算）（当前库存：12,000）'
    )
    expect(options.find(({ value }) => value === '固源岩').label).toBe('固源岩（当前库存：0）')
  })

  it('库存加载状态有明确提示', () => {
    expect(inventory_options_with_counts({}, 'loading')[0].label).toContain('读取中')
    expect(inventory_options_with_counts({}, 'error')[0].label).toContain('未知')
  })
})
