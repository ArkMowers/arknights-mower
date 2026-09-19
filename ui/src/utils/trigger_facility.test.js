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
    expect(parse_facility_expression(expression)).toBe('room_1_2')
  })

  it('只把支持的产物和订单识别为设施状态值', () => {
    expect(parse_facility_product('orirock_device')).toBe('orirock_device')
    expect(parse_facility_product('orundum')).toBe('orundum')
    expect(parse_facility_product('unknown')).toBeUndefined()
  })
})
