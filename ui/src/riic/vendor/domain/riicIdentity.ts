import type { OperatorRecord } from './operators'
import evidence from '../data/riic-term-evidence.json'

type IdentityDimension = 'nationId' | 'groupId' | 'teamId'
// These are skill-tooltip dimensions, not interchangeable faction aliases.
const IDENTITY_TERMS: Record<string, string> = {
  'groupId:abyssal': 'cc.g.abyssal', 'groupId:rhine': 'cc.g.rh',
  'groupId:blacksteel': 'cc.g.bs', 'groupId:lgd': 'cc.g.lgd',
  'groupId:pinus': 'cc.g.psk', 'groupId:glasgow': 'cc.g.glasgow',
  'groupId:karlan': 'cc.g.karlan', 'groupId:sui': 'cc.g.sui',
  'groupId:elite': 'cc.g.elite', 'nationId:kjerag': 'cc.g.karlan',
  'nationId:siracusa': 'cc.g.siracusa', 'nationId:laterano': 'cc.g.laterano',
  'nationId:sargon': 'cc.g.sargon', 'nationId:minos': 'cc.g.minos',
  'teamId:student': 'cc.g.ussg', 'teamId:reserve1': 'cc.g.A1',
  'teamId:rainbow': 'cc.g.R6', 'teamId:lee': 'cc.g.lda',
}
const terms = evidence.terms as Record<string, { description: string }>
const termMembers = new Map<string, ReadonlySet<string>>()
for (const [id, term] of Object.entries(terms)) {
  if (term.description.startsWith('包含以下干员\n')) {
    termMembers.set(id, new Set(term.description.slice('包含以下干员\n'.length).split(/[、\n]/).map(name => name.trim()).filter(Boolean)))
  }
}

/** Identity follows raw isSpChar metadata; no name or ID-number heuristics. */
export function isRiicAlter(operator: OperatorRecord): boolean {
  return operator.isAlter === true
}

/** Preserve source affiliations on the record while exposing the user's base identity rule. */
export function effectiveRiicIdentity(operator: OperatorRecord) {
  return isRiicAlter(operator)
    ? { nationId: null, groupId: null, teamId: null, alter: true }
    : { nationId: operator.nationId, groupId: operator.groupId, teamId: operator.teamId, alter: false }
}

/** Explicit skill tooltip membership is authoritative, including any named alter exception. */
export function matchesRiicIdentity(
  operator: OperatorRecord,
  dimension: IdentityDimension,
  value: string,
): boolean {
  const termId = IDENTITY_TERMS[dimension + ':' + value]
  const members = termId ? termMembers.get(termId) : undefined
  if (members) return members.has(operator.name)
  return effectiveRiicIdentity(operator)[dimension] === value
}

/** Legacy mood rules pass one semantic group key; resolve its dimension explicitly. */
export function matchesRiicFaction(operator: OperatorRecord, ...keys: string[]): boolean {
  const dimensions: Record<string, IdentityDimension> = {
    sui: 'groupId', lgd: 'groupId', rainbow: 'teamId', kjerag: 'nationId', karlan: 'groupId',
    student: 'teamId', lee: 'teamId', sargon: 'nationId', abyssal: 'groupId',
  }
  return keys.some(key => {
    const dimension = dimensions[key]
    return dimension !== undefined && matchesRiicIdentity(operator, dimension, key)
  })
}
