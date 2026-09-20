import { describe, expect, it } from 'vitest'

import {
  expression_value_option,
  facility_expression,
  facility_product_count_expression,
  facility_product_type_count_expression,
  parse_facility_expression,
  parse_facility_product_count_expression,
  summarize_facility_products
} from './trigger_facility.js'

describe('设施状态副表表达式', () => {
  it('自动补全显示中文但写入表达式值', () => {
    expect(expression_value_option('赤金', 'gold')).toEqual({
      label: 'gold',
      value: 'gold',
      displayLabel: '赤金'
    })
  })

  it('生成并解析设施产物表达式', () => {
    const expression = facility_expression('room_1_2')
    expect(expression).toBe("op_data.facility_product('room_1_2')")
    expect(parse_facility_expression(expression)).toEqual({
      room: 'room_1_2',
      status: 'product'
    })
  })

  it('生成并解析设施干员数量表达式', () => {
    const expression = facility_expression('central', 'operator_count')
    expect(expression).toBe("op_data.facility_operator_count('central')")
    expect(parse_facility_expression(expression)).toEqual({
      room: 'central',
      status: 'operator_count'
    })
  })

  it('生成并解析设施类型表达式', () => {
    const expression = facility_expression('room_1_2', 'type')
    expect(expression).toBe("op_data.facility_type('room_1_2')")
    expect(parse_facility_expression(expression)).toEqual({
      room: 'room_1_2',
      status: 'type'
    })
  })

  it('生成并解析训练室专精状态表达式', () => {
    expect(facility_expression('train', 'mastery_plan')).toBe(
      "op_data.facility_has_mastery_plan('train')"
    )
    expect(parse_facility_expression("op_data.facility_has_mastery_plan('train')")).toEqual({
      room: 'train',
      status: 'mastery_plan'
    })
    expect(facility_expression('train', 'training')).toBe("op_data.facility_is_training('train')")
    expect(parse_facility_expression("op_data.facility_is_training('train')")).toEqual({
      room: 'train',
      status: 'training'
    })
  })

  it('生成并解析生产设施统计', () => {
    const expression = facility_product_count_expression('gold')
    expect(expression).toBe("op_data.facility_product_count('gold')")
    expect(parse_facility_product_count_expression(expression)).toBe('gold')
    expect(
      parse_facility_product_count_expression("op_data.facility_product_count('unknown')")
    ).toBeUndefined()
    expect(facility_product_type_count_expression).toBe('op_data.facility_product_type_count()')
  })

  it('无缓存时按主表统计，有缓存时按房间覆盖', () => {
    const plan = {
      room_1_1: { name: '贸易站', product: 'lmd' },
      room_1_2: { name: '制造站', product: 'gold' },
      room_1_3: { name: '制造站', product: 'gold' },
      room_2_1: { name: '发电站' }
    }

    expect(summarize_facility_products(plan)).toEqual({
      products: { room_1_1: 'lmd', room_1_2: 'gold', room_1_3: 'gold' },
      counts: { gold: 2, exp3: 0, orirock: 0, orirock_device: 0, lmd: 1, orundum: 0 },
      typeCount: 2
    })
    expect(
      summarize_facility_products(plan, {
        room_1_2: { facility: 'factory', product: 'exp3' },
        room_2_2: { facility: 'trade', product: 'orundum' }
      })
    ).toEqual({
      products: {
        room_1_1: 'lmd',
        room_1_2: 'exp3',
        room_1_3: 'gold',
        room_2_2: 'orundum'
      },
      counts: { gold: 1, exp3: 1, orirock: 0, orirock_device: 0, lmd: 1, orundum: 1 },
      typeCount: 4
    })
  })
})
