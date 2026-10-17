import type {MowerFacilityType, MowerProduct} from './roster'

export function parseProduct(product: unknown): MowerProduct | undefined {
  if (typeof product !== 'string') return undefined
  if (product === 'exp3' || product === 'exp') return 'exp'
  if (product === 'orirock' || product === 'orirock_device' || product === 'fragment') return 'fragment'
  if (product === 'lmd' || product === 'money') return 'money'
  if (product === 'gold') return 'gold'
  if (product === 'orundum') return 'orundum'
  return undefined
}

export function serializeProduct(
  facilityType: MowerFacilityType,
  product: MowerProduct | undefined,
): string | undefined {
  if (facilityType === 'manufacture') {
    if (product === 'exp') return 'exp3'
    if (product === 'fragment') return 'orirock'
    if (product === 'gold') return 'gold'
    return undefined
  }
  if (facilityType === 'trading') {
    if (product === 'orundum') return 'orundum'
    if (product === 'money') return 'lmd'
    return undefined
  }
  return undefined
}
