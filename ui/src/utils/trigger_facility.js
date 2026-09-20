import { facility_product_options } from '@/utils/base_products'

const facilityProductIds = new Set(facility_product_options.map(({ value }) => value))

const facilityStatusMethods = {
  product: 'facility_product',
  operator_count: 'facility_operator_count'
}

export function facility_expression(room, status = 'product') {
  return `op_data.${facilityStatusMethods[status]}('${room}')`
}

export function parse_facility_expression(value) {
  const match = value.match(/^op_data\.(facility_product|facility_operator_count)\('(.+)'\)$/)
  if (!match) return undefined
  return {
    room: match[2],
    status: match[1] == 'facility_product' ? 'product' : 'operator_count'
  }
}

export function parse_facility_product(value) {
  return facilityProductIds.has(value) ? value : undefined
}

export function facility_operator_expression(room, operator) {
  return `op_data.facility_has_operator('${room}', '${operator}')`
}

export function parse_facility_operator_expression(value) {
  const match = value.match(/^op_data\.facility_has_operator\('(.+)', '(.+)'\)$/)
  if (!match) return undefined
  return { room: match[1], operator: match[2] }
}

export function operator_relation_expression(first, second) {
  return `op_data.operators_work_together('${first}', '${second}')`
}

export function parse_operator_relation_expression(value) {
  const match = value.match(/^op_data\.operators_work_together\('(.+)', '(.+)'\)$/)
  if (!match) return undefined
  return { first: match[1], second: match[2] }
}

export function facility_product_count_expression(product) {
  return `op_data.facility_product_count('${product}')`
}

export function parse_facility_product_count_expression(value) {
  const match = value.match(/^op_data\.facility_product_count\('(.+)'\)$/)
  if (!match || !facilityProductIds.has(match[1])) return undefined
  return match[1]
}

export const facility_product_type_count_expression = 'op_data.facility_product_type_count()'
