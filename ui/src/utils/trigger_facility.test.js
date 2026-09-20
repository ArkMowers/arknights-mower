import { describe, expect, it } from 'vitest'

import {
  facility_expression,
  facility_product_count_expression,
  facility_product_type_count_expression,
  operator_relation_expression,
  parse_facility_expression,
  parse_facility_type,
  parse_facility_product,
  parse_facility_product_count_expression,
  parse_operator_relation_expression,
  summarize_facility_products
} from './trigger_facility.js'

describe('设施状态副表表达式', () => {
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

  it('生成并解析设施类型表达式和值', () => {
    const expression = facility_expression('room_1_2', 'type')
    expect(expression).toBe("op_data.facility_type('room_1_2')")
    expect(parse_facility_expression(expression)).toEqual({
      room: 'room_1_2',
      status: 'type'
    })
    expect(parse_facility_type("'制造站'")).toBe('制造站')
    expect(parse_facility_type("'控制中枢'")).toBeUndefined()
  })

  it('只把支持的产物和订单识别为设施状态值', () => {
    expect(parse_facility_product('orirock_device')).toBe('orirock_device')
    expect(parse_facility_product('orundum')).toBe('orundum')
    expect(parse_facility_product('unknown')).toBeUndefined()
  })

  it('生成并解析同设施工作关系', () => {
    const expression = operator_relation_expression('阿米娅', '陈')
    expect(expression).toBe("op_data.operators_work_together('阿米娅', '陈')")
    expect(parse_operator_relation_expression(expression)).toEqual({
      first: '阿米娅',
      second: '陈'
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
