import type { ManufactureProduct } from '../domain/types'

// Below the scheduler's one-microsecond clock resolution; matches production boundary tolerance.
const EPSILON = 1e-8
export type ManufacturingFormulaId = 'exp-medium' | 'gold' | 'fragment-orirock' | 'fragment-device'
export type ManufacturingDiagnosticCode = 'FORMULA_CHANGE_REQUIRES_EXPLICIT_RESET'

export interface ManufacturingCost { id: string; count: number; type: 'MATERIAL' | 'GOLD' }
export interface ManufacturingFormula {
  id: ManufacturingFormulaId; product: ManufactureProduct; sourceFormulaId: string; itemId: string
  batchSize: number; baseMinutes: number; storageWeight: number; requiredRoomLevel: 1 | 3
  costs: readonly ManufacturingCost[]
}

const noCosts: readonly ManufacturingCost[] = Object.freeze([])
const orirockCosts: readonly ManufacturingCost[] = Object.freeze([{ id: '30012', count: 2, type: 'MATERIAL' }, { id: '4001', count: 1600, type: 'GOLD' }])
const deviceCosts: readonly ManufacturingCost[] = Object.freeze([{ id: '30062', count: 1, type: 'MATERIAL' }, { id: '4001', count: 1000, type: 'GOLD' }])

/** Source: building_data.manufactFormulas (v076 baseline raw GameData). */
export const MANUFACTURING_FORMULAS: Readonly<Record<ManufacturingFormulaId, ManufacturingFormula>> = Object.freeze({
  'exp-medium': Object.freeze({ id: 'exp-medium', product: 'exp', sourceFormulaId: '3', itemId: '2003', batchSize: 1, baseMinutes: 180, storageWeight: 5, requiredRoomLevel: 1, costs: noCosts }),
  gold: Object.freeze({ id: 'gold', product: 'gold', sourceFormulaId: '4', itemId: '3003', batchSize: 1, baseMinutes: 72, storageWeight: 2, requiredRoomLevel: 1, costs: noCosts }),
  'fragment-orirock': Object.freeze({ id: 'fragment-orirock', product: 'fragment', sourceFormulaId: '13', itemId: '3141', batchSize: 1, baseMinutes: 60, storageWeight: 3, requiredRoomLevel: 3, costs: orirockCosts }),
  'fragment-device': Object.freeze({ id: 'fragment-device', product: 'fragment', sourceFormulaId: '14', itemId: '3141', batchSize: 1, baseMinutes: 60, storageWeight: 3, requiredRoomLevel: 3, costs: deviceCosts }),
})

export interface ManufacturingState {
  formula: ManufacturingFormula; capacityWeight: number; storedWeight: number
  pendingBatches: number; pendingItems: number; lifetimeBatches: number; lifetimeItems: number
  remainingBaseMinutes: number; awaitingPayment: boolean; blockedByStorage: boolean
}
export interface StartManufacturingInput { formula: ManufacturingFormula | ManufacturingFormulaId; capacityWeight: number; storedWeight?: number; paymentAuthorized: boolean }
export interface BatchAuthorization { state: ManufacturingState; started: boolean; requiredCosts: readonly ManufacturingCost[] }
export interface AdvanceManufacturingResult { state: ManufacturingState; completedBatches: number; completedItems: number; consumedBaseMinutes: number; unusedBaseMinutes: number }
export interface CollectManufacturingResult { state: ManufacturingState; collectedBatches: number; collectedItems: number; freedWeight: number }
export interface FormulaChangeResult { state: ManufacturingState; diagnostics: readonly ManufacturingDiagnosticCode[] }

function resolveFormula(formula: ManufacturingFormula | ManufacturingFormulaId): ManufacturingFormula { return typeof formula === 'string' ? MANUFACTURING_FORMULAS[formula] : formula }
function validate(value: number, name: string): void { if (!Number.isFinite(value) || value < 0) throw new Error(`Invalid ${name}`) }
function canStoreBatch(state: ManufacturingState): boolean { return state.capacityWeight - state.storedWeight + EPSILON >= state.formula.storageWeight }
function assertState(state: ManufacturingState): void {
  validate(state.capacityWeight, 'capacityWeight'); validate(state.storedWeight, 'storedWeight'); validate(state.remainingBaseMinutes, 'remainingBaseMinutes')
  if (![state.pendingBatches, state.pendingItems, state.lifetimeBatches, state.lifetimeItems].every(Number.isInteger)) throw new Error('Invalid manufacturing counters')
}

/** A quote only; this module never debits materials or LMD. */
export function quoteManufacturingStart(formula: ManufacturingFormula | ManufacturingFormulaId): readonly ManufacturingCost[] { return resolveFormula(formula).costs.map(cost => ({ ...cost })) }

/** Starts exactly one externally-authorized batch. A false authorization leaves the room waiting for payment. */
export function startManufacturing(input: StartManufacturingInput): ManufacturingState {
  const formula = resolveFormula(input.formula); validate(input.capacityWeight, 'capacityWeight')
  const storedWeight = input.storedWeight ?? 0; validate(storedWeight, 'storedWeight')
  if (storedWeight > input.capacityWeight + EPSILON) throw new Error('Initial stored weight exceeds capacity')
  return { formula, capacityWeight: input.capacityWeight, storedWeight, pendingBatches: 0, pendingItems: 0, lifetimeBatches: 0, lifetimeItems: 0, remainingBaseMinutes: formula.baseMinutes, awaitingPayment: !input.paymentAuthorized, blockedByStorage: input.paymentAuthorized && storedWeight + formula.storageWeight > input.capacityWeight + EPSILON }
}

/** Requests a new batch after collection/completion. Caller must settle `requiredCosts` before authorizing it. */
export function authorizeManufacturingBatch(state: ManufacturingState, paymentAuthorized: boolean): BatchAuthorization {
  assertState(state)
  if (!state.awaitingPayment) return { state, started: false, requiredCosts: quoteManufacturingStart(state.formula) }
  const blockedByStorage = !canStoreBatch(state)
  if (!paymentAuthorized || blockedByStorage) return { state: { ...state, blockedByStorage }, started: false, requiredCosts: quoteManufacturingStart(state.formula) }
  return { state: { ...state, awaitingPayment: false, blockedByStorage: false, remainingBaseMinutes: state.formula.baseMinutes }, started: true, requiredCosts: quoteManufacturingStart(state.formula) }
}

/** Applies already-integrated base work to one authorized batch only. Excess is deliberately returned to the scheduler. */
export function advanceManufacturing(state: ManufacturingState, baseMinutes: number): AdvanceManufacturingResult {
  assertState(state); validate(baseMinutes, 'baseMinutes')
  if (state.awaitingPayment || state.blockedByStorage) return { state, completedBatches: 0, completedItems: 0, consumedBaseMinutes: 0, unusedBaseMinutes: baseMinutes }
  const consumedBaseMinutes = Math.min(baseMinutes, state.remainingBaseMinutes)
  const remainingBaseMinutes = state.remainingBaseMinutes - consumedBaseMinutes
  if (remainingBaseMinutes > EPSILON) return { state: { ...state, remainingBaseMinutes }, completedBatches: 0, completedItems: 0, consumedBaseMinutes, unusedBaseMinutes: baseMinutes - consumedBaseMinutes }
  const next: ManufacturingState = { ...state, storedWeight: state.storedWeight + state.formula.storageWeight, pendingBatches: state.pendingBatches + 1, pendingItems: state.pendingItems + state.formula.batchSize, lifetimeBatches: state.lifetimeBatches + 1, lifetimeItems: state.lifetimeItems + state.formula.batchSize, remainingBaseMinutes: state.formula.baseMinutes, awaitingPayment: true, blockedByStorage: false }
  return { state: next, completedBatches: 1, completedItems: state.formula.batchSize, consumedBaseMinutes, unusedBaseMinutes: baseMinutes - consumedBaseMinutes }
}

/** Returns the next completion distance in base minutes, or null until payment/space is available. */
export function nextManufacturingEvent(state: ManufacturingState): number | null { assertState(state); return state.awaitingPayment || state.blockedByStorage ? null : state.remainingBaseMinutes }
export function collectManufacturing(state: ManufacturingState): CollectManufacturingResult { assertState(state); return { state: { ...structuredClone(state), storedWeight: 0, pendingBatches: 0, pendingItems: 0, blockedByStorage: false }, collectedBatches: state.pendingBatches, collectedItems: state.pendingItems, freedWeight: state.storedWeight } }
/** Capacity may fall below current stock; retained products are never discarded, but no further batch can begin. */
export function updateManufacturingCapacity(state: ManufacturingState, capacityWeight: number): ManufacturingState { assertState(state); validate(capacityWeight, 'capacityWeight'); return { ...state, capacityWeight, blockedByStorage: state.awaitingPayment ? state.storedWeight + state.formula.storageWeight > capacityWeight + EPSILON : state.blockedByStorage } }
export function replaceManufacturingFormula(state: ManufacturingState, formula: ManufacturingFormula | ManufacturingFormulaId): FormulaChangeResult { assertState(state); return resolveFormula(formula).id === state.formula.id ? { state, diagnostics: [] } : { state, diagnostics: ['FORMULA_CHANGE_REQUIRES_EXPLICIT_RESET'] } }
export function droneBaseMinutes(droneCount: number): number { if (!Number.isInteger(droneCount) || droneCount < 0) throw new Error('Invalid drone count'); return droneCount * 3 }
