import { facility_product_options } from '@/utils/base_products'
import { facility_type_names } from '@/utils/base_facilities'

const facilityProductIds = new Set(facility_product_options.map(({ value }) => value))
const facilityTypeNames = new Set(facility_type_names)

const facilityStatusMethods = {
  type: 'facility_type',
  product: 'facility_product',
  operator_count: 'facility_operator_count'
}

const facilityMethodStatuses = Object.fromEntries(
  Object.entries(facilityStatusMethods).map(([status, method]) => [method, status])
)

export function facility_expression(room, status = 'product') {
  return `op_data.${facilityStatusMethods[status]}('${room}')`
}

export function parse_facility_expression(value) {
  const match = value.match(
    /^op_data\.(facility_type|facility_product|facility_operator_count)\('(.+)'\)$/
  )
  if (!match) return undefined
  return {
    room: match[2],
    status: facilityMethodStatuses[match[1]]
  }
}

export function parse_facility_type(value) {
  const match = value.match(/^'(.+)'$/)
  return match && facilityTypeNames.has(match[1]) ? match[1] : undefined
}

export function parse_facility_product(value) {
  return facilityProductIds.has(value) ? value : undefined
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
