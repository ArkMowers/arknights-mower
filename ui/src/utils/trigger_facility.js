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
