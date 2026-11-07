/**
 * Derivative work based on arknights-mower (PlanEditor.vue / SlickOperatorSelect.vue)
 * Original work Copyright (c) 2021 Nano
 * Licensed under the MIT License
 */

import { match, pinyin } from 'pinyin-pro'
import { OPERATOR_MAP, OPERATORS, type OperatorRecord } from '../domain/operators'
import { isTradeRunOrderOperator } from '../domain/shiftRunPolicy'
import type { MowerFacilityType, MowerMainConf, MowerMainPlan, MowerRoomId } from '../domain/roster'
import { resolveAssetUrl } from '../utils/assets'
export { resolveAssetUrl }

export interface OperatorSearchItem extends OperatorRecord {
  fullPinyin: string
  firstLetters: string
}

const OPERATOR_BY_NAME = new Map(OPERATORS.map((op) => [op.name, op]))
const OPERATOR_BY_APPELLATION = new Map(OPERATORS.map((op) => [op.appellation.toLowerCase(), op]))

export function getOperatorName(identifier: string | null | undefined): string {
  if (!identifier) return ''
  if (identifier === 'Free' || identifier === 'free') return 'Free'
  if (identifier === 'Current' || identifier === 'current') return 'Current'
  const op =
    OPERATOR_MAP.get(identifier) ||
    OPERATOR_BY_NAME.get(identifier) ||
    OPERATOR_BY_APPELLATION.get(identifier.toLowerCase())
  return op ? op.name : identifier
}

export function isRunOrderOperator(identifier: string | null | undefined): boolean {
  if (!identifier) return false
  return isTradeRunOrderOperator(getOperatorName(identifier))
}

export function isProviso(identifier: string | null | undefined): boolean {
  if (!identifier) return false
  const name = getOperatorName(identifier)
  return name === '但书'
}

export function isFiammetta(identifier: string | null | undefined): boolean {
  if (!identifier) return false
  const name = getOperatorName(identifier)
  return name === '菲亚梅塔'
}

export function buildOperatorSearchIndex(operators: OperatorRecord[]): OperatorSearchItem[] {
  return operators.map((op) => {
    const domainOp = OPERATOR_MAP.get(op.charId) || OPERATOR_BY_NAME.get(op.name)
    const appellation = op.appellation || domainOp?.appellation || ''
    const fullPinyin = pinyin(op.name, { toneType: 'none', separator: '' }).toLowerCase()
    const firstLetters = pinyin(op.name, { pattern: 'first', toneType: 'none', separator: '' }).toLowerCase()
    return {
      ...op,
      appellation,
      fullPinyin,
      firstLetters,
    }
  })
}

export function searchOperators(
  query: string,
  index: OperatorSearchItem[],
  limit: number = 60,
): OperatorSearchItem[] {
  const rawQ = query.trim().toLowerCase()
  if (!rawQ) {
    return limit > 0 ? index.slice(0, limit) : index
  }

  const qPinyin = rawQ.replace(/v/g, 'ü')
  const rawClean = rawQ.replace(/[\s\-_'.]/g, '')

  const matched: Array<{ item: OperatorSearchItem; score: number }> = []

  for (const item of index) {
    const nameLower = item.name.toLowerCase()
    const appLower = (item.appellation || '').toLowerCase()
    const appClean = appLower.replace(/[\s\-_'.]/g, '')
    const charIdLower = item.charId.toLowerCase()
    const pinyinLower = item.fullPinyin.toLowerCase()
    const pinyinV = pinyinLower.replace(/ü/g, 'v')
    const firstLower = item.firstLetters.toLowerCase()

    let score = -1

    if (nameLower === rawQ) {
      score = 100
    } else if (nameLower.startsWith(rawQ)) {
      score = 80
    } else if (nameLower.includes(rawQ)) {
      score = 60
    } else if (firstLower === rawQ || firstLower === qPinyin) {
      score = 55
    } else if (firstLower.startsWith(rawQ) || firstLower.startsWith(qPinyin)) {
      score = 45
    } else if (firstLower.includes(rawQ) || firstLower.includes(qPinyin)) {
      score = 35
    } else if (pinyinLower === rawQ || pinyinLower === qPinyin || pinyinV === rawQ) {
      score = 50
    } else if (pinyinLower.startsWith(rawQ) || pinyinLower.startsWith(qPinyin) || pinyinV.startsWith(rawQ)) {
      score = 40
    } else if (pinyinLower.includes(rawQ) || pinyinLower.includes(qPinyin) || pinyinV.includes(rawQ)) {
      score = 30
    } else if (appLower === rawQ || (appClean.length > 0 && appClean === rawClean)) {
      score = 48
    } else if (appLower.startsWith(rawQ) || (rawClean.length >= 2 && appClean.startsWith(rawClean))) {
      score = 38
    } else if (appLower.includes(rawQ) || (rawClean.length >= 2 && appClean.includes(rawClean))) {
      score = 28
    } else if (charIdLower.includes(rawQ)) {
      score = 20
    } else {
      const pMatch = match(item.name, rawQ, { v: true }) ?? match(item.name, qPinyin)
      if (pMatch !== null && pMatch.length > 0) {
        score = 25
      }
    }

    if (score >= 0) {
      matched.push({ item, score })
    }
  }

  matched.sort((a, b) => b.score - a.score || b.item.rarity - a.item.rarity)
  const res = matched.map((m) => m.item)
  return limit > 0 ? res.slice(0, limit) : res
}

export function getOperatorAvatarUrl(identifier: string): string {
  if (!identifier) return ''
  if (identifier === 'Free') return resolveAssetUrl('avatar/Free.webp')
  if (identifier === 'Current') return resolveAssetUrl('avatar/Current.webp')
  const op = OPERATOR_MAP.get(identifier)
  const name = op ? op.name : identifier
  return resolveAssetUrl(`avatar/${encodeURI(name)}.webp`)
}

const FACILITY_TYPE_NAMES: Record<string, string> = {
  manufacture: '制造站',
  trading: '贸易站',
  power: '发电站',
  dormitory: '宿舍',
  central: '控制中枢',
  meeting: '会客室',
  factory: '加工站',
  contact: '办公室',
  train: '训练室',
  recycle: '回收站',
  gaming: '活动室',
}

export function getRoomDisplayName(roomId: string, type?: MowerFacilityType | string): string {
  if (roomId.startsWith('room_')) {
    const parts = roomId.split('_')
    const floor = parts[1]
    const col = parts[2]
    const baseCode = `B${floor}0${col}`
    if (type && FACILITY_TYPE_NAMES[type]) {
      return `${baseCode} (${FACILITY_TYPE_NAMES[type]})`
    }
    return baseCode
  }
  if (roomId === 'central') return '控制中枢'
  if (roomId.startsWith('dormitory_') || roomId.startsWith('dorm_')) {
    const num = roomId.replace(/^(dormitory_|dorm_)/, '')
    return `宿舍${num}`
  }
  if (roomId === 'meeting') return '会客室'
  if (roomId === 'factory') return '加工站'
  if (roomId === 'contact') return '办公室'
  if (roomId === 'train') return '训练室'
  if (roomId === 'recycle') return '回收站'
  if (roomId.startsWith('gaming_')) {
    const num = roomId.replace('gaming_', '')
    return `活动室${num}`
  }
  return roomId
}

export function getAssignedSummaryMap(mainPlan: MowerMainPlan): Map<string, string> {
  const map = new Map<string, string>()
  if (!mainPlan || !mainPlan.facilities) return map

  for (const roomId of Object.keys(mainPlan.facilities) as MowerRoomId[]) {
    const facility = mainPlan.facilities[roomId]
    if (!facility) continue
    const roomName = getRoomDisplayName(facility.roomId, facility.type)
    for (const slot of facility.slots) {
      if (slot.occupant.kind === 'operator' && slot.occupant.operatorId) {
        map.set(slot.occupant.operatorId, roomName)
        const op = OPERATOR_MAP.get(slot.occupant.operatorId)
        if (op) {
          map.set(op.name, roomName)
        }
      }
    }
  }

  return map
}

export interface OperatorScopeLocation {
  roomId: MowerRoomId
  roomName: string
  slotIndex: number
}

export interface ReplacementScopeResult {
  totalCount: number
  mainLocations: OperatorScopeLocation[]
  replacementLocations: OperatorScopeLocation[]
  confLocations: string[]
}

export function computeReplacementScope(
  mainPlan: MowerMainPlan,
  operatorId: string,
): ReplacementScopeResult {
  const mainLocations: OperatorScopeLocation[] = []
  const replacementLocations: OperatorScopeLocation[] = []
  const confLocations: string[] = []

  if (!mainPlan || !operatorId) {
    return { totalCount: 0, mainLocations, replacementLocations, confLocations }
  }

  const op = OPERATOR_MAP.get(operatorId)
  const targetIds = new Set<string>([operatorId])
  if (op) {
    targetIds.add(op.name)
    targetIds.add(op.charId)
  }

  if (mainPlan.facilities) {
    for (const roomId of Object.keys(mainPlan.facilities) as MowerRoomId[]) {
      const facility = mainPlan.facilities[roomId]
      if (!facility) continue
      const roomName = getRoomDisplayName(facility.roomId, facility.type)

      facility.slots.forEach((slot, slotIndex) => {
        if (slot.occupant.kind === 'operator' && targetIds.has(slot.occupant.operatorId)) {
          mainLocations.push({ roomId, roomName, slotIndex })
        }
        if (slot.replacements.some((rep) => targetIds.has(rep))) {
          replacementLocations.push({ roomId, roomName, slotIndex })
        }
      })
    }
  }

  if (mainPlan.conf) {
    const policyKeys: Array<keyof MowerMainConf> = [
      'exhaust_require',
      'rest_in_full',
      'resting_priority',
      'workaholic',
      'refresh_trading',
      'refresh_drained',
      'ope_resting_priority',
    ]
    for (const key of policyKeys) {
      if (typeof key !== 'string') continue
      const list = mainPlan.conf[key]
      if (Array.isArray(list) && list.some((id: string) => targetIds.has(id))) {
        confLocations.push(key)
      }
    }
  }

  const totalCount = mainLocations.length + replacementLocations.length + confLocations.length
  return {
    totalCount,
    mainLocations,
    replacementLocations,
    confLocations,
  }
}
