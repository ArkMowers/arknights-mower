import { OPERATOR_MAP, OPERATORS, type OperatorRecord } from './operators'

const OPERATOR_BY_NAME = new Map<string, OperatorRecord>()
const OPERATOR_BY_APPELLATION = new Map<string, OperatorRecord>()
const OPERATOR_BY_ID = new Map<string, OperatorRecord>()

for (const op of OPERATORS) {
  OPERATOR_BY_NAME.set(op.name, op)
  OPERATOR_BY_APPELLATION.set(op.appellation.toLowerCase(), op)
  OPERATOR_BY_ID.set(op.charId, op)
}

export function resolveOperatorCharId(identifier: string): string {
  if (OPERATOR_BY_ID.has(identifier)) return identifier
  const byName = OPERATOR_BY_NAME.get(identifier)
  if (byName) return byName.charId
  const byAppellation = OPERATOR_BY_APPELLATION.get(identifier.toLowerCase())
  if (byAppellation) return byAppellation.charId
  return identifier
}

export function restoreOperatorMowerName(charIdOrName: string): string {
  const op = OPERATOR_MAP.get(charIdOrName)
  return op ? op.name : charIdOrName
}
