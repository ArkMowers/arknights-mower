import {resolveOperatorCharId as resolve} from './operatorIdentifiers'
import {isTradeRunOrderOperator} from './shiftRunPolicy'
import {OPERATOR_MAP} from './operators'
import type {MowerRoomId, MowerSlot, RosterWorkspace} from './roster'

export interface MowerRosterRuleIssue {
  code: 'INVALID_CONFIG' | 'CONFLICTING_REPLACEMENT' | 'DUPLICATE_REPLACEMENT'
  severity: 'critical'
  roomId: MowerRoomId
  slotIndex: number
  message: string
}

function matchGroup(options: Record<string, string[]>, preferred?: Set<string>, partial = false): Record<string, string> | undefined {
  const seed = preferred?.size ? matchGroup(Object.fromEntries(Object.entries(options).map(([name, candidates]) => [name, candidates.filter(candidate => preferred.has(candidate))])), undefined, true)! : {}
  const owners = new Map(Object.entries(seed).map(([name, cover]) => [cover, name]))
  const reserve = (name: string, seen: Set<string>): boolean => {
    for (const candidate of options[name]!) if (!owners.has(candidate)) { owners.set(candidate, name); return true }
    for (const candidate of options[name]!) { if (seen.has(candidate)) continue; seen.add(candidate); if (reserve(owners.get(candidate)!, seen)) { owners.set(candidate, name); return true } }
    return false
  }
  for (const name of Object.keys(options)) if (![...owners.values()].includes(name) && !reserve(name, new Set()) && !partial) return undefined
  return Object.fromEntries([...owners].map(([candidate, name]) => [name, candidate]))
}

/** Shared static contracts for the editor and every effective runtime plan. */
export function validateMowerRosterRules(workspace: RosterWorkspace): MowerRosterRuleIssue[] {
  const issues: MowerRosterRuleIssue[] = []
  const conf = workspace.mainPlan.conf
  const names = (raw: unknown) => new Set((Array.isArray(raw) ? raw : typeof raw === 'string' ? raw.split(/[,，]/) : []).map(name => resolve(String(name).trim())))
  const workaholic = names(conf.workaholic), standby = names(conf.resting_standby), exhaust = names(conf.exhaust_require), restFull = names(conf.rest_in_full)
  const entries = Object.values(workspace.mainPlan.facilities).filter(f => f.level > 0).flatMap(f => f.slots.map((slot, slotIndex) => ({slot, slotIndex, roomId: f.roomId, dorm: f.type === 'dormitory', trading: f.type === 'trading'})))
  const bindings = (slot: MowerSlot) => [{groupId: slot.groupId, replacements: slot.replacements}, ...(slot.groupBindings ?? [])]
  const primaries = new Map(entries.flatMap(entry => entry.slot.occupant.kind === 'operator' ? [[resolve(entry.slot.occupant.operatorId), entry] as const] : []))
  const groups = new Map<string, string[]>()
  const add = (entry: typeof entries[number], message: string, code: MowerRosterRuleIssue['code'] = 'INVALID_CONFIG') => issues.push({code, severity: 'critical', roomId: entry.roomId, slotIndex: entry.slotIndex, message})
  const isStandby = (name: string) => standby.has(name) && !workaholic.has(name) && !exhaust.has(name) && !restFull.has(name) && !['年', '司霆惊蛰', '九色鹿'].includes(OPERATOR_MAP.get(name)?.name ?? name)
  for (const entry of entries) if (entry.slot.occupant.kind === 'free') {
    if (!entry.dorm) add(entry, 'Free 只能安排在宿舍。')
    if (entry.slot.groupId || entry.slot.groupBindings?.length) add(entry, 'Free 不能配置绑组。')
  }
  for (const [name, entry] of primaries) for (const binding of bindings(entry.slot)) if (binding.groupId) {const members = groups.get(binding.groupId) ?? []; if (!members.includes(name)) members.push(name); groups.set(binding.groupId, members)}
  for (const [name, entry] of primaries) {
    const {slot, dorm, trading} = entry, fiammetta = OPERATOR_MAP.get(name)?.name === '菲亚梅塔'
    const columns = bindings(slot)
    if (fiammetta && (slot.groupId || slot.groupBindings?.length)) add(entry, '菲亚梅塔不能参与绑组换班。')
    if (slot.groupBindings?.length) {
      const groupNames = columns.map(binding => binding.groupId?.trim() ?? '')
      if (groupNames.some(group => !group) || new Set(groupNames).size !== groupNames.length) add(entry, '多绑组需要互不重复的非空组名。')
    }
    for (const binding of columns) {
      const seen = new Set<string>()
      const optional = !dorm && workaholic.has(name) && (!binding.groupId || (groups.get(binding.groupId) ?? []).every(member => workaholic.has(member)))
      if (slot.groupBindings?.length && !binding.replacements.length && !optional) add(entry, '多绑组的每一列均需配置替班。')
      for (const raw of binding.replacements) {
        const candidate = resolve(raw)
        if (seen.has(candidate)) add(entry, `替补列表中存在重复干员：${OPERATOR_MAP.get(candidate)?.name ?? candidate}。`, 'DUPLICATE_REPLACEMENT')
        seen.add(candidate)
        if (candidate === 'Free') {if (!dorm || !binding.groupId || fiammetta) add(entry, 'Free 替补仅用于非菲亚梅塔的宿舍绑组席位。'); continue}
        if (dorm && fiammetta && candidate !== name) continue
        const cover = primaries.get(candidate)
        const sameGroup = candidate !== name && !!binding.groupId && cover && bindings(cover.slot).some(other => other.groupId === binding.groupId)
        if (cover && !sameGroup && !(candidate !== name && trading && isTradeRunOrderOperator(candidate))) add(entry, `替补干员 ${OPERATOR_MAP.get(candidate)?.name ?? candidate} 必须为同一非空组内的其他主力或未在岗的替补。`, 'CONFLICTING_REPLACEMENT')
      }
    }
  }
  for (const [group, members] of groups) {
    const workers = members.filter(name => !primaries.get(name)!.dorm)
    const needsAnchor = !workers.length || workers.some(name => !workaholic.has(name))
    const anchored = workers.some(name => !primaries.get(name)!.slot.groupBindings?.length && !workaholic.has(name) && !isStandby(name))
    if (needsAnchor && !anchored) add(primaries.get(members[0]!)!, `${group} 缺少决定上下班的工作主班：需要非宿舍、非零心情工作、非多绑组且非候补的主班。`)
    const zeroMood = members.every(name => workaholic.has(name)) && members.every(name => !primaries.get(name)!.dorm)
    const options = Object.fromEntries(members.flatMap(name => {
      const entry = primaries.get(name)!, candidates = bindings(entry.slot).find(binding => binding.groupId === group)!.replacements.map(resolve).filter(candidate => !isTradeRunOrderOperator(candidate))
      if (entry.dorm && candidates.includes('Free') || zeroMood && !candidates.length) return []
      return [[name, candidates]]
    }))
    const required = new Set(workers.filter(name => !workaholic.has(name) && !isStandby(name)))
    const effectiveBeds = entries.filter(entry => entry.dorm && (entry.slot.occupant.kind === 'free' || bindings(entry.slot).some(binding => binding.groupId === group && binding.replacements.includes('Free')))).length
    const assignments = [matchGroup(options), matchGroup(options, required)]
    if (assignments.every(matching => !matching)) add(primaries.get(members[0]!)!, `${group} 分组无法排班：替班名单不能覆盖所有成员。`)
    else if (!zeroMood && assignments.every(matching => !matching || [...required].filter(name => !Object.values(matching).includes(name)).length > effectiveBeds)) add(primaries.get(members[0]!)!, `${group} 分组无法排班：有效宿舍床位不足。`)

  }
  return issues
}
