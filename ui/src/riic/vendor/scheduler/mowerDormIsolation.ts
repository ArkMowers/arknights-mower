// Mower alpha 3de2b2ac6f1aeff6513b63faaeea4b2369cf8856 dorm isolation (MIT).
import {alphaPosition, alphaRestingTier} from './mowerAlphaDorm'
import {orderMowerAlphaDormIndices} from './mowerDormOrder'
import {projectMowerArrangements} from './mowerObservations'
import {hasRestingMood, restingMood} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTaskPlan} from './mowerTaskQueue'

const occupant = (name: string | undefined): name is string => !!name && name !== 'Free' && name !== 'Current'

/** Physical occupants, bed reservations and this pending arrangement share one view. */
export function mowerDormRoommates(data: MowerSchedulingData, room: string, index?: number, plan: MowerTaskPlan = {}): string[] {
  const moving = new Set(Object.values(plan).flat().filter(occupant))
  const beds = new Map(data.allDorms().map(bed => [alphaPosition(...bed.position), bed]))
  const row = plan[room] ?? [], names: string[] = []
  for (let position = 0; position < (data.plan[room]?.length ?? 0); position++) {
    if (position === index) continue
    let name: string | undefined
    if (position < row.length && row[position] !== 'Current') name = row[position]
    else {
      name = beds.get(alphaPosition(room, position))?.name || data.currentOperator(room, position)?.name
      if (name && moving.has(name)) continue
    }
    if (occupant(name)) names.push(name)
  }
  return names
}

/** Bed availability and takeover tier precede isolation; recovery deficit breaks remaining ties. */
export function mowerDormIsolationCost(data: MowerSchedulingData, name: string, room: string, index?: number, plan: MowerTaskPlan = {}): number {
  if (!data.dormIsolation.length) return 0
  const roommates = new Set(mowerDormRoommates(data, room, index, plan))
  roommates.delete(name)
  return data.dormIsolation.reduce((cost, group) => cost + (group.includes(name) ? new Set(group.filter(member => roommates.has(member))).size : 0), 0)
}

/** Swap dynamic beds before admission while protecting established first beds and reservations. */
export function planMowerDormIsolation(data: MowerSchedulingData, plan: MowerTaskPlan, reservedSlots: ReadonlySet<string> = new Set(), reservedNames: ReadonlySet<string> = new Set(), reallocatingNames: ReadonlySet<string> = new Set()): MowerTaskPlan {
  if (!data.dormIsolation.length || !Object.keys(plan).length && !reallocatingNames.size) return plan
  const newcomers = new Set(Object.entries(plan).filter(([room]) => room.startsWith('dorm')).flatMap(([, row]) => row).filter(name => data.operators[name] && !data.operators[name]!.isResting()))
  // 生效床序改变时，原住客也参与本批分配，可让出已有单回位置。
  for (const name of reallocatingNames) newcomers.add(name)
  if (!newcomers.size) return plan
  const projected = projectMowerArrangements(data, [plan])
  const beds = orderMowerAlphaDormIndices(projected).map(index => projected.dorms[index]!).filter(bed => projected.effectiveFreeSlot(bed))
  const first = new Map<string, number>()
  for (const bed of beds) first.set(bed.position[0], Math.min(first.get(bed.position[0]) ?? Infinity, bed.position[1]))
  const reserved = new Set([...reservedSlots, ...data.reservedProductBeds.keys()]), protectedNames = new Set(reservedNames)
  const explicitNames = new Set(Object.values(plan).flat())
  for (const bed of data.dorms) {
    const op = data.operators[bed.name]
    if (op && !explicitNames.has(bed.name) && (op.currentRoom !== bed.position[0] || op.currentIndex !== bed.position[1])) {
      reserved.add(alphaPosition(...bed.position))
      protectedNames.add(bed.name)
    }
  }
  const isFirst = (bed: typeof beds[number]) => bed.position[1] === first.get(bed.position[0])
  const movable = beds.filter(bed => !reserved.has(alphaPosition(...bed.position)) && !protectedNames.has(bed.name)
    && (!bed.name || projected.operators[bed.name] && alphaRestingTier(projected, bed.name) !== 7)
    && (!isFirst(bed) || newcomers.has(bed.name) || reallocatingNames.size && !bed.name))
  if (movable.length < 2) return plan
  const result = structuredClone(plan)
  const roomCost = (room: string) => {
    const row = projected.currentRoom(room, true) ?? []
    for (const bed of beds) if (bed.position[0] === room) row[bed.position[1]] = bed.name
    const names = new Set(row.filter(occupant))
    return data.dormIsolation.reduce((cost, group) => {const count = new Set(group.filter(name => names.has(name))).size; return cost + count * (count - 1) / 2}, 0)
  }
  const allocationGroups: typeof beds[] = []
  for (const bed of beds) {
    const previous = allocationGroups[allocationGroups.length - 1]
    if (previous && !isFirst(bed) && previous[0]!.position[0] === bed.position[0] && !isFirst(previous[0]!)) previous.push(bed)
    else allocationGroups.push([bed])
  }
  const recoveryRank = (bed: typeof beds[number]) => {
    const op = projected.operators[bed.name]
    return !op || !projected.freeRoomExcluded(bed.name) && hasRestingMood(op, projected.nowMicros) && restingMood(op, projected.nowMicros) >= op.upperLimit ? 8 : alphaRestingTier(projected, bed.name)
  }
  const recoveryScore = () => allocationGroups.flatMap(group => group.map(recoveryRank).sort((a, b) => a - b))
  type SwapKey = [gain: number, recovery: number[], targetMoves: number, residentMoves: number]
  const compare = (a: SwapKey, b: SwapKey) => {
    if (a[0] !== b[0]) return a[0] - b[0]
    for (let i = 0; i < a[1].length; i++) if (a[1][i] !== b[1][i]) return a[1][i]! - b[1][i]!
    return a[2] - b[2] || a[3] - b[3]
  }
  // Strictly improve isolation or recovery rank. Equal-speed ordinary beds never swap for morale alone.
  for (let pass = 0; pass < movable.length ** 2; pass++) {
    let best: [typeof beds[number], typeof beds[number]] | undefined
    let bestKey: SwapKey = [0, recoveryScore(), 0, 0]
    for (let i = 0; i < movable.length; i++) for (let j = i + 1; j < movable.length; j++) {
      const a = movable[i]!, b = movable[j]!, rooms = new Set([a.position[0], b.position[0]])
      const targetMoves = Number(isFirst(a)) + Number(isFirst(b))
      if (a.name === b.name || rooms.size < 2 && !targetMoves) continue
      const before = [...rooms].reduce((cost, room) => cost + roomCost(room), 0)
      ;[a.name, b.name] = [b.name, a.name]
      const gain = before - [...rooms].reduce((cost, room) => cost + roomCost(room), 0), rank = recoveryScore()
      ;[a.name, b.name] = [b.name, a.name]
      if (gain < 0 || gain === 0 && !targetMoves) continue
      const key: SwapKey = [-gain, rank, targetMoves, Number(!!a.name && !newcomers.has(a.name)) + Number(!!b.name && !newcomers.has(b.name))]
      if (compare(key, bestKey) < 0) { best = [a, b]; bestKey = key }
    }
    if (!best) break
    const [a, b] = best
    ;[a.name, b.name] = [b.name, a.name]
    for (const bed of best) (result[bed.position[0]] ??= Array(projected.plan[bed.position[0]]!.length).fill('Current'))[bed.position[1]] = bed.name || 'Free'
  }
  return result
}
