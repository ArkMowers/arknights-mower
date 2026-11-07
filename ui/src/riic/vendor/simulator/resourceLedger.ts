export type ResourceKind = 'gold' | 'lmd' | 'exp' | 'fragment' | 'orundum' | 'drone' | 'orirock' | 'device'
export type ResourceAmounts = Partial<Record<ResourceKind, number>>
export interface LedgerEntry { reason: string; delta: ResourceAmounts }
export interface ResourceLedger { initial: ResourceAmounts; balances: ResourceAmounts; inflows: ResourceAmounts; outflows: ResourceAmounts; entries: LedgerEntry[]; appliedReasons: string[] }
const validate = (values: ResourceAmounts, allowNegative: boolean) => {
  for (const [key, value] of Object.entries(values)) if (!Number.isFinite(value) || (!allowNegative && value < 0)) throw new Error(`Invalid resource ${key}`)
}
export function createLedger(initial: ResourceAmounts): ResourceLedger {
  validate(initial, false)
  return { initial: { ...initial }, balances: { ...initial }, inflows: {}, outflows: {}, entries: [], appliedReasons: [] }
}
export function transactLedger(ledger: ResourceLedger, delta: ResourceAmounts, reason: string) {
  validate(delta, true)
  if (!reason) throw new Error('Transaction reason required')
  if (ledger.appliedReasons.includes(reason)) return { applied: false, ledger }
  for (const [key, value] of Object.entries(delta) as [ResourceKind, number][]) if ((ledger.balances[key] ?? 0) + value < 0) return { applied: false, ledger }
  const next = structuredClone(ledger)
  for (const [key, value] of Object.entries(delta) as [ResourceKind, number][]) {
    next.balances[key] = (next.balances[key] ?? 0) + value
    if (value >= 0) next.inflows[key] = (next.inflows[key] ?? 0) + value
    else next.outflows[key] = (next.outflows[key] ?? 0) - value
  }
  next.entries.push({ reason, delta: { ...delta } }); next.appliedReasons.push(reason)
  return { applied: true, ledger: next }
}
export interface Storage { resource: ResourceKind; capacity: number; amount: number }
export function createStorage(resource: ResourceKind, capacity: number, amount = 0): Storage {
  if (!Number.isFinite(capacity) || !Number.isFinite(amount) || capacity < 0 || amount < 0 || amount > capacity) throw new Error('Invalid storage')
  return { resource, capacity, amount }
}
export function produceStorage(storage: Storage, requested: number) {
  if (!Number.isFinite(requested) || requested < 0) throw new Error('Invalid production')
  const produced = Math.min(requested, storage.capacity - storage.amount)
  return { storage: { ...storage, amount: storage.amount + produced }, produced, blocked: requested - produced }
}
export function collectStorage(storage: Storage, ledger: ResourceLedger, amount: number, reason: string) {
  if (!Number.isFinite(amount) || amount < 0 || amount > storage.amount) throw new Error('Invalid collection')
  const result = transactLedger(ledger, { [storage.resource]: amount }, reason)
  if (!result.applied) throw new Error('Collection transaction refused')
  return { storage: { ...storage, amount: storage.amount - amount }, ledger: result.ledger }
}
