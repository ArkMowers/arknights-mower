export type RoomType = 'manufacture' | 'trading' | 'power'
export type ManufactureProduct = 'gold' | 'exp' | 'fragment'
export type TradeStrategy = 'gold' | 'orundum'
export type QualityRule = 'normal' | 'alpha' | 'beta'
export type SpecialOrder =
  | 'none'
  | 'pepe'
  | 'closure'
  | 'uofficial'
  | 'provisoAlpha'
  | 'provisoBeta'
  | 'tequilaAlpha'
  | 'tequilaBeta'
  | 'shiftRun'

export interface OutputRoom {
  id: string
  type: RoomType
  level: 1 | 2 | 3
  operatorCount: number
  operatorIds: string[]
  skillBonus: number
  product: ManufactureProduct
  strategy: TradeStrategy
  quality: QualityRule
  specialOrder: SpecialOrder
  powerStaffed: boolean
}

export interface FacilityLevels {
  /** Omitted in legacy configs; defaults to a level-five control center. */
  central?: 0 | 1 | 2 | 3 | 4 | 5
  reception: 0 | 1 | 2 | 3
  office: 0 | 1 | 2 | 3
  training: 0 | 1 | 2 | 3
  workshop: 0 | 1 | 2 | 3
  /** Omitted in older configurations; an omitted recycle station is unbuilt. */
  recycle?: 0 | 1 | 2 | 3
  dormitories: Array<0 | 1 | 2 | 3 | 4 | 5>
}

export interface OperatorGroup {
  id: string
  name: string
  operatorIds: string[]
}

export interface EfficiencyResources {
  manufacturePerceptionInformation: number
  tradingPerceptionInformation: number
  additionalGoldProductionLines: number
  monsterCuisine: number
  worldlyFireworks: number
  suiFacilities: number
  droneCapacity: number
  extraWorkplaceOperatorIds: string[]
  trainingOperatorIds: string[]
}

export interface FacilityOperatorAssignments {
  dormitories: string[][]
  reception: string[]
  workshop: string[]
  office: string[]
  training: string[]
  recycle?: string[]
}

export interface AppConfig {
  productionWeights?: import('./productionWeights').ProductionWeights
  /** Ephemeral, actual unlocked skill snapshots for this calculation only. */
  operatorRecords?: Readonly<Record<string, import('./operators').OperatorRecord>>
  /** Force Jaye (孑) to Elite 0 state (first skill only, under shift-run / empty queue). */
  jayeElite0?: boolean
  schemaVersion: 7
  planName: string
  hours: number
  rooms: OutputRoom[]
  facilities: FacilityLevels
  dormitoryOccupantCount: number
  facilityOperatorIds: FacilityOperatorAssignments
  efficiencyResources: EfficiencyResources
  controlOperatorIds: string[]
  zeroMoraleOperatorIds: string[]
  workaholicOperatorIds: string[]
  operatorMorale: Record<string, number>
  operatorBackups: Record<string, string>
  operatorGroups: OperatorGroup[]
  droneTarget: string
}

export interface OperatorMoraleResult {
  operatorId: string
  operatorName: string
  roomId: string
  role: 'primary' | 'backup'
  replacesOperatorId: string | null
  startedAt: number | null
  initial: number
  ending: number
  initialConsumptionPerHour: number
  exhaustedAt: number | null
  leftAt: number | null
  leaveReason: 'morale-exhausted' | 'group-sync' | null
  groupName: string | null
  details: string[]
}

export interface ManufactureResult {
  roomId: string
  product: ManufactureProduct
  efficiency: number
  count: number
  value: number
  droneExtra: number
  operatorNames: string[]
  buffDetails: string[]
  unquantifiedSkills: string[]
}

export interface TradeResult {
  roomId: string
  strategy: TradeStrategy
  efficiency: number
  orders: number
  lmd: number
  goldConsumed: number
  virtualGold?: number
  virtualGoldValue?: number
  orundum: number
  fragmentsConsumed: number
  droneExtraOrders: number
  operatorNames: string[]
  buffDetails: string[]
  unquantifiedSkills: string[]
}

export interface PowerBalance {
  generation: number
  consumption: number
  margin: number
  sufficient: boolean
}

export interface CalculationReport {
  power: PowerBalance
  layoutValid: boolean
  validationMessages: string[]
  efficiencyNotes?: string[]
  manufacture: ManufactureResult[]
  trading: TradeResult[]
  drones: number
  morale: OperatorMoraleResult[]
  roomShiftDetails: Record<string, string[]>
  summary: {
    exp: number
    goldCount: number
    goldValue: number
    virtualGoldCount: number
    virtualGoldValue: number
    orderLmd: number
    fragments: number
    orundum: number
    goldConsumed: number
    fragmentsConsumed: number
    netGoldCount: number
    netGoldValue: number
    totalScore82: number
    scoreBreakdown?: import('./productionScore').ProductionScore
    totalEquivalentLmd: number
  } | null
}

export type SummaryOutput = NonNullable<CalculationReport['summary']>
