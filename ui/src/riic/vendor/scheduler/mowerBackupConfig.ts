import { effectiveMowerDormOrder, MOWER_DEFAULT_DORM_ORDER as defaultDormOrder } from '../domain/mowerDormOrder'
// PlanConfig.merge_config, Mower alpha ab0a4e5 (MIT).
import {OPERATOR_MAP} from '../domain/operators'
import {resolveOperatorCharId} from '../domain/operatorIdentifiers'

import {MOWER_OPERATOR_LIST_FIELDS, type MowerOperatorListField} from '../domain/roster'
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)

export function readMowerOperatorList(field: MowerOperatorListField, value: unknown, resolve = resolveOperatorCharId): string[] {
  const values = value == null ? [] : typeof value === 'string' ? value.replace(/，/g, ',').split(',').map(v => v.trim()).filter(Boolean) : value
  if (!Array.isArray(values)) throw new Error(`策略格式错误 ${field}`)
  return values.map(value => {
    if (typeof value !== 'string') throw new Error(`策略格式错误 ${field}`)
    const name = value.trim()
    const suffix = field === 'refresh_trading' ? name.indexOf('(') : -1
    if (suffix < 0) return resolve(name)
    const id = resolve(name.slice(0, suffix).trim())
    return (OPERATOR_MAP.get(id)?.name ?? id) + name.slice(suffix)
  })
}

export function readMowerRemovedOperators(value: unknown, resolve = resolveOperatorCharId): Partial<Record<MowerOperatorListField, string[]>> {
  if (value === undefined) return {}
  if (!record(value)) throw new Error('removed_operators 必须为策略名称到干员名单的映射')
  const result: Partial<Record<MowerOperatorListField, string[]>> = {}
  for (const [field, names] of Object.entries(value)) {
    if (!(MOWER_OPERATOR_LIST_FIELDS as readonly string[]).includes(field) || !(typeof names === 'string' || Array.isArray(names))) throw new Error(`removed_operators 策略格式错误 ${field}`)
    result[field as MowerOperatorListField] = readMowerOperatorList('rest_in_full', names, resolve)
  }
  return result
}

export function mowerBackupOverridesDormOrder(conf: Record<string, unknown>): boolean {
  if (conf.dorm_order_override != null) return conf.dorm_order_override === true
  const order = typeof conf.dorm_order === 'string' ? conf.dorm_order.replace(/，/g, ',').split(',').map(value => value.trim()).filter(Boolean) : []
  if (!order.length) return false
  const effective = effectiveMowerDormOrder(order)
  return effective.join(',') !== defaultDormOrder.join(',')
}

/** Apply one active layer; callers rebuild from the base when a layer exits. */
export function mergeMowerBackupConfig(base: Record<string, unknown>, backup: Record<string, unknown>): void {
  const removed = readMowerRemovedOperators(backup.removed_operators)
  for (const field of MOWER_OPERATOR_LIST_FIELDS) {
    const exclusions = new Set(removed[field])
    base[field] = [...new Set([...readMowerOperatorList(field, base[field]), ...readMowerOperatorList(field, backup[field])])]
      .filter(entry => !exclusions.has(resolveOperatorCharId(field === 'refresh_trading' ? entry.split('(', 1)[0]!.trim() : entry)))
  }
  if (mowerBackupOverridesDormOrder(backup)) {
    base.dorm_order = typeof backup.dorm_order === 'string' ? backup.dorm_order : ''
    base.dorm_order_override = true
  }
  if (record(backup.mood_limits)) base.mood_limits = structuredClone(backup.mood_limits)
  if (record(backup.operator_mood_limits)) {
    base.operator_mood_limits = Object.fromEntries([
      ...Object.entries(record(base.operator_mood_limits) ? base.operator_mood_limits : {}),
      ...Object.entries(backup.operator_mood_limits),
    ].map(([name, limits]) => [resolveOperatorCharId(name), structuredClone(limits)]))
  }
}
