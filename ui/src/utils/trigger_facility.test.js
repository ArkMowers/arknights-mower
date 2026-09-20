import { describe, expect, it } from 'vitest'

import {
  facility_expression,
  parse_facility_expression,
  parse_facility_product
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

  it('只把支持的产物和订单识别为设施状态值', () => {
    expect(parse_facility_product('orirock_device')).toBe('orirock_device')
    expect(parse_facility_product('orundum')).toBe('orundum')
    expect(parse_facility_product('unknown')).toBeUndefined()
  })
})
