import type { MowerFacilityType, MowerMainConf, MowerOccupant, MowerProduct, RosterWorkspace } from '../domain/roster'

export interface CompileDiagnostic {
  code: string
  severity: 'error' | 'warning' | 'info'
  message: string
  path?: string
}
export interface SimulationAssumptions {
  schemaVersion: 1
  initialMorale: number
  /** Hours from simulation start until major maintenance; omitted means no scheduled window. */
  majorMaintenanceStartHours?: number
  /** Total stopping hours; zero or omitted does not match duration comparisons. */
  majorMaintenanceDurationHours?: number
  /** Mower global configuration; absent from the plan JSON. */
  predictiveMoodControl?: boolean
  restingThreshold?: number
  rescueThreshold?: number
  /** Mower global free_room: release recovered ordinary dorm residents. */
  freeRoom?: boolean
  /** Native global config.conf.dorm_order: every concrete recovery bed. */
  dormOrder?: string
  dormIsolation?: string[][]
  groupRestInFullOnMoodGap?: boolean
  groupMoodGapThresholdMinutes?: number
  groupMoodGapMaxExtraWaitHours?: number
  groupMoodGapExclusions?: string[]
  mergeIntervalMinutes?: number
  enableMastery?: boolean
  enableParty?: boolean
  leifengMode?: boolean
  droneRoom?: string | null
  droneIntervalHours?: number
  droneCountLimit?: number
  reloadRooms?: string[] | null
  maaGapHours?: number
  /** Simulation-only choice; preserved when backup plans recompile the runtime. */
  runOrderSimulationMode?: 'ideal'
  /** Ideal mode retains order task scheduling; false reproduces the old no-wake comparison. */
  idealRunOrderWakeOnly?: boolean
  idleOperators?: string[]
  fiammettaFool?: boolean
  fiammettaThreshold?: number
  operatorMorale: Record<string, number>
  dormAtmosphere: number
  initialGold: number
  initialFragments: number
  initialDrones: number
  collectionIntervalHours: number
  operationDurationHours: number
  horizonHours: number
  elitePhase: 0 | 1 | 2
  currentOccupants: Record<string, string[]>
}
export interface CompiledSlot {
  roomId: string
  slotIndex: number
  occupant: MowerOccupant
  primaryOperatorId: string | null
  orderedCandidates: string[]
  groupId: string | null
  groupBindings?: { group: string; replacement: string[] }[]
  role: 'work' | 'dorm-keeper' | 'free-rest' | 'fiammetta'
  metadata?: Record<string, unknown>
}
export interface CompiledRoom {
  roomId: string
  type: MowerFacilityType
  level: number
  product?: MowerProduct
  capacity: number
  slots: CompiledSlot[]
}
export interface OperatorRuntimeState {
  operatorId: string
  morale: number
  roomId: string | null
  slotIndex: number | null
}
export interface RestPool { roomId: string; capacity: number; freeSlotIndices: number[] }
export type MainRosterPolicies = MowerMainConf
export interface RunOrderPolicy { roomId: string; orderedOperatorIds: string[] }
export interface FiammettaPolicy { roomId: string; slotIndex: number; operatorId: string; orderedTargets: string[] }
export interface CompiledSchedule {
  schemaVersion: 1
  rooms: CompiledRoom[]
  operators: Record<string, OperatorRuntimeState>
  restPools: RestPool[]
  policies: MainRosterPolicies
  rawConf: MowerMainConf
  runOrderPolicies: RunOrderPolicy[]
  fiammettaPolicies: FiammettaPolicy[]
  assumptions: SimulationAssumptions & {
    dataVersion: string
    compilerVersion: string
    levelSource: string
    importSource: string
    defaultsApplied: string[]
  }
  diagnostics: CompileDiagnostic[]
  sourceWorkspace: RosterWorkspace
}
