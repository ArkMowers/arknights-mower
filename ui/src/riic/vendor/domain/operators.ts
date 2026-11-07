import data from '../../../../../arknights_mower/data/riic/operators.json'

export type GameRoomType =
  | 'MANUFACTURE'
  | 'TRADING'
  | 'POWER'
  | 'CONTROL'
  | 'DORMITORY'
  | 'MEETING'
  | 'WORKSHOP'
  | 'TRAINING'
  | 'HIRE'
  | 'RECYCLE'
  | string

export interface OperatorSkill {
  buffId: string
  name: string
  roomType: GameRoomType
  skillIcon: string
  description: string
  unlockPhase: number
  unlockLevel: number
}

export interface OperatorRecord {
  charId: string
  name: string
  appellation: string
  rarity: number
  profession: string
  isAlter: boolean
  nationId: string | null
  groupId: string | null
  teamId: string | null
  /** All versions grouped by slot; skills remains the maximum-stage snapshot. */
  skillSlots?: OperatorSkill[][]
  skills: OperatorSkill[]
}

interface OperatorPayload {
  schemaVersion: number
  sourceVersion: string
  operatorCount: number
  skillCount: number
  operators: Omit<OperatorRecord, 'skills'>[]
}

const payload = data as OperatorPayload

export const OPERATORS: OperatorRecord[] = payload.operators.map(operator => ({
  ...operator,
  skills: (operator.skillSlots ?? []).flatMap(slot => {
    const last = slot[slot.length - 1]
    return last ? [{ ...last }] : []
  }),
}))
export const OPERATOR_MAP = new Map(OPERATORS.map((operator) => [operator.charId, operator]))
export const GAME_DATA_VERSION = payload.sourceVersion
export const OPERATOR_PROFILE_COUNT = payload.operatorCount
export const OPERATOR_SKILL_COUNT = payload.skillCount

export const FACTION_LABELS: Record<string, string> = {
  abyssal: '深海猎人',
  rhine: '莱茵生命',
  pinus: '红松骑士团',
  penguin: '企鹅物流',
  glasgow: '格拉斯哥帮',
  blacksteel: '黑钢国际',
  ursus: '乌萨斯学生自治团',
  kjerag: '喀兰贸易',
  lungmen: '龙门近卫局',
}

export function factionLabel(operator: OperatorRecord): string {
  if (operator.isAlter) return '异格者'
  const id = operator.groupId ?? operator.teamId ?? operator.nationId
  return id ? (FACTION_LABELS[id] ?? id) : '未分类'
}
