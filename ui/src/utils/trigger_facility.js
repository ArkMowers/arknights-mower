import { facility_product_options } from '@/utils/base_products'

const facilityProductIds = new Set(facility_product_options.map(({ value }) => value))

export function facility_expression(room) {
  return `op_data.facility_product('${room}')`
}

export function parse_facility_expression(value) {
  const match = value.match(/^op_data\.facility_product\('(.+)'\)$/)
  return match?.[1]
}

export function parse_facility_product(value) {
  return facilityProductIds.has(value) ? value : undefined
}
