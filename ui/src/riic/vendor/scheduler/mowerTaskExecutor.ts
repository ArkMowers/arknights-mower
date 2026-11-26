// Port of default agent_arrange / infra_main arrangement handling in Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import { MOWER_RIGHT_SIDE_CAPACITY } from '../domain/mowerBackupFacilities'
import { MOWER_OUTPUT_ROOM_IDS } from '../domain/roster'
import type {BackupTiming} from './backupPlans'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {hasRestingMood, type MowerOperatorState} from './mowerOperatorState'
import {mowerSchedulingMoodObservation} from './mowerSchedulingMood'
import {MowerRoomArrangementDeferred} from './mowerNativeErrors'
import {MOWER_TASK_TYPES as T,MowerTask,fromMowerMicros,isMowerRunOrderTask,type MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
export interface MowerBackupResult {changed:boolean;generated:MowerTask[]}
interface HandoffObservations {
  data: MowerSchedulingData
  workRate: (name: string, room: string) => number
}
export interface MowerTaskExecutionHooks {
 handoff?:HandoffObservations
 currentRoom?:(name:string)=>string|undefined
 /** Enable the alpha complete-arrangement boundary in the application adapter. */
 protectShift?:boolean
 alpha?:boolean
 hasRunOrderRooms?:boolean
 adjustForRunOrders?:boolean
 /** changed is the source solver's new_task result, not any plan-condition change. */
 backup:(phase:BackupTiming,task:MowerTask,context:{appendEmptyTask:boolean;restoreOnDeactivate:boolean;customTimeMicros?:number})=>MowerBackupResult
 /** Physical I/O adapter; this core removes the successfully committed room from the task. */
 arrangeRoom:(room:string,names:string[],getTime:boolean,task:MowerTask,restoration:MowerTaskPlan)=>MowerTaskPlan|void|Generator<MowerRoomReturn,MowerTaskPlan|void,void>
 /** prepare_release_dorm validates identity/cap and clears stale plans. */
 prepareRelease?:(task:MowerTask)=>boolean
 /** A critical task may postpone the remaining dorm rooms without ending this shift. */
 deferRoom?:(room:string,task:MowerTask)=>boolean
 /** Commit the confirmed group arrangement before evaluating post-shift backups. */
 completeGroupShift?:()=>void
 completeFia?:(task:MowerTask)=>void
 metadata:()=>void
 corrections?:()=>MowerTask[]
 skip?:()=>void
}
function enqueueGenerated(queue:MowerTaskQueue,generated:MowerTask[]):void {for(const task of generated)if(!queue.tasks.includes(task))queue.tasks.push(task)}
function rosterHead(queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):MowerTask|undefined {return queue.find({ignoreRunOrders:hooks.adjustForRunOrders===false})}
function enterPhase(phase:'BEFORE_WORK'|'BEFORE_DORM',task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):boolean {
 if(task.backupShiftActive)return false
 const result=hooks.backup(phase,task,{appendEmptyTask:false,restoreOnDeactivate:true,customTimeMicros:task.timeMicros-1})
 enqueueGenerated(queue,result.generated)
 if(!result.changed)return false
 const generated=new Set(result.generated),others=queue.tasks.filter(t=>!generated.has(t)&&(hooks.adjustForRunOrders!==false||!isMowerRunOrderTask(t)))
 const anchor=others.length?Math.min(...others.map(t=>t.timeMicros)):task.timeMicros
 // Reverse enumeration gives the first generated task the earliest microsecond.
 for(const [offset,t] of [...result.generated].reverse().entries())t.timeMicros=anchor-offset-1
 if(phase==='BEFORE_WORK'){
  for(const generated of result.generated)for(const [room,names] of Object.entries(generated.plan)){
   const pending=task.plan[room];if(!pending)continue
   for(const [index,name] of names.entries())if(index<pending.length&&name!=='Current')pending[index]='Current'
  }
  for(const [room,names] of Object.entries(task.plan))if(names.every(name=>name==='Current'))delete task.plan[room]
 }else{
  for(const generated of result.generated)for(const room of Object.keys(generated.plan))if(room.startsWith('dormitory_')&&room in task.plan)delete task.plan[room]
 }
 return true
}
/** Returns false only for a deferred original task. Its identity and remaining plan survive. */
export interface MowerRoomReturn {room:string;delayMicros:number;nativeRunOrderIO?:true;returnsInfraMain?:true}
const productionRooms = new Set<string>(MOWER_OUTPUT_ROOM_IDS)
const rightRooms = new Set(Object.keys(MOWER_RIGHT_SIDE_CAPACITY))
const placeholders = new Set(['Current', 'Free', '_', ''])
const routableRooms = new Set([...productionRooms, ...rightRooms, 'central'])
routableRooms.delete('train')

function needsMapDrag(previous: string, room: string): boolean {
  if (rightRooms.has(previous)) {
    if (previous === 'meeting' && (room === 'room_1_3' || room === 'room_3_3')) return false
    return productionRooms.has(room)
  }
  return productionRooms.has(previous) && rightRooms.has(room)
}

function sameMapEntry(first: string, other: string): boolean {
  if (first === other) return true
  if (productionRooms.has(first) && productionRooms.has(other)) {
    const [, firstFloor, firstColumn] = first.split('_'), [, otherFloor, otherColumn] = other.split('_')
    return firstColumn === otherColumn && firstFloor !== '2' && otherFloor !== '2'
  }
  return ['factory', 'contact', 'recycle'].includes(first) && ['factory', 'contact', 'recycle'].includes(other)
}

function shortestMapRoute(rooms: string[], dependencies: Map<string, Set<string>>, keepLast: boolean): string[] {
  const original = rooms.slice(1).filter((room, index) => needsMapDrag(rooms[index]!, room)).length
  if (!original) return rooms
  const middle = rooms.slice(1, keepLast ? -1 : undefined)
  const bits = new Map(middle.map((room, index) => [room, 1 << index]))
  const required = middle.map(room => [...dependencies.get(room)!].reduce((mask, source) => mask | (bits.get(source) ?? 0), 0))
  const endBit = 1 << middle.length
  // The final bit includes the cost of reaching the fixed endpoint.
  const drags = (previous: string) => rooms.slice(1).reduce((mask, room, index) => needsMapDrag(previous, room) ? mask | (1 << index) : mask, 0)
  const nextDrags = middle.map(drags)
  const failed = new Set<string>()
  const path: string[] = []
  function visit(pending: number, dragMask: number, budget: number): boolean {
    if (!pending) return budget > 0 || !(dragMask & endBit)
    const key = `${pending}:${dragMask}:${budget}`
    if (failed.has(key)) return false
    for (const [index, room] of middle.entries()) {
      const bit = 1 << index
      if (!(pending & bit) || (required[index]! & pending)) continue
      const cost = (dragMask & bit) ? 1 : 0
      if (cost > budget) continue
      path.push(room)
      if (visit(pending ^ bit, nextDrags[index]!, budget - cost)) return true
      path.pop()
    }
    failed.add(key)
    return false
  }
  for (let budget = 0; budget < original; budget++) {
    if (visit(endBit - 1, drags(rooms[0]!), budget)) return [rooms[0]!, ...path, ...(keepLast ? rooms.slice(-1) : [])]
  }
  return rooms
}
function handoffHoursToLimit(op: MowerOperatorState, { data, workRate }: HandoffObservations): number | undefined {
  const now = data.nowMicros
  if (data.policy.predictiveMoodControl && op.lowerLimit === 0 && op.mood === 0 && op.exhaustTimeMicros !== undefined &&
      op.timeStampMicros !== undefined && op.timeStampMicros <= now && !op.moodIsPrediction && !op.projectedWorkPositionChanged) {
    return Math.max(0, fromMowerMicros(op.exhaustTimeMicros - now))
  }
  const observation = mowerSchedulingMoodObservation(data, op.name)
  if (!observation) return undefined
  const [mood, stamp] = observation
  if (data.policy.predictiveMoodControl) {
    if (!data.calculatedMoodSnapshot) return undefined
    if (mood <= op.lowerLimit) return 0
    const rate = workRate(op.name, op.currentRoom)
    if (!Number.isFinite(rate)) return undefined
    return rate > 0 ? (mood - op.lowerLimit) / rate : Infinity
  }
  if (op.projectedWorkPositionChanged || stamp !== op.timeStampMicros || op.moodIsPrediction || !hasRestingMood(op, now)) return undefined
  if (op.lowerLimit > 0 && op.mood <= op.lowerLimit) return 0
  if (op.exhaustTimeMicros !== undefined && op.mood !== 24) return Math.max(0, fromMowerMicros(op.exhaustTimeMicros - now))
  if (mood <= op.lowerLimit) return 0
  if (!Number.isFinite(op.depletionRate) || op.depletionRate <= 0) return undefined
  return Math.max(0, (op.mood - op.lowerLimit) / op.depletionRate - fromMowerMicros(now - stamp))
}

function plannedHandoffHours(plan: MowerTaskPlan, ordered: string[], counts: Map<string, number>, handoff: HandoffObservations): Map<string, number> {
  const workTargets = new Set(Object.entries(plan).filter(([room]) => !room.startsWith('dormitory_')).flatMap(([, names]) => names))
  const beds = new Set(Object.entries(plan).filter(([room]) => room.startsWith('dormitory_')).flatMap(([, names]) => names.filter(name => counts.get(name) === 1)))
  const occupants = new Map<string, Map<number, MowerOperatorState | undefined>>()
  for (const op of Object.values(handoff.data.operators)) {
    if (!(op.currentRoom in plan) || op.currentIndex < 0) continue
    const row = occupants.get(op.currentRoom) ?? new Map<number, MowerOperatorState | undefined>()
    row.set(op.currentIndex, row.has(op.currentIndex) ? undefined : op)
    occupants.set(op.currentRoom, row)
  }
  const departing = new Map<string, MowerOperatorState[]>()
  for (const room of ordered) {
    if (!routableRooms.has(room)) continue
    const workers: MowerOperatorState[] = []
    const row = occupants.get(room)
    if (!row) continue
    const targets = plan[room]!
    const slots = new Set([...row.keys(), ...targets.keys()])
    const confirmed = [...slots].every(index => {
      const op = row.get(index), target = targets[index]
      if (!op) return false
      if (target === 'Current') return !counts.has(op.name)
      if (target !== undefined && counts.get(target) !== 1) return false
      if (op.isHigh() && !op.workaholic && !workTargets.has(op.name) && !op.room.startsWith('dormitory_') && (op.room === room || beds.has(op.name))) workers.push(op)
      return true
    })
    if (confirmed && workers.length) departing.set(room, workers)
  }
  const hours = new Map<string, number>()
  if (departing.size < 2) return hours
  for (const [room, workers] of departing) {
    const times = workers.map(op => handoffHoursToLimit(op, handoff))
    if (times.includes(0)) hours.set(room, 0)
    else if (times.every((value): value is number => value !== undefined)) hours.set(room, Math.min(...times))
  }
  return hours
}

function workRoomOrder(work: string[], dependencies: Map<string, Set<string>>): [string[], string[]] {
  const pending = [...work], ordered: string[] = []
  while (pending.length) {
    const index = pending.findIndex(room => !pending.some(source => dependencies.get(room)!.has(source)))
    if (index < 0) break
    ordered.push(pending.splice(index, 1)[0]!)
  }
  return [ordered, pending]
}

function handoffRoomOrder(original: string[], work: string[], dependencies: Map<string, Set<string>>, hours: ReadonlyMap<string, number>): string[] {
  const choices = original.map(room => [room])
  let canImprove = false
  for (let first = 0; first < original.length;) {
    let after = first
    while (after < original.length && hours.has(original[after]!)) after++
    if (after - first > 1) {
      const preferred = original.slice(first, after).sort((a, b) => hours.get(a)! - hours.get(b)!)
      choices.fill(preferred, first, after)
      if (preferred.some((room, i) => room !== original[first + i])) canImprove = true
    }
    first = after + 1
  }
  if (!canImprove) return original
  const dorms = original.slice(work.length), stops = [...routableRooms]
  const outbound = (old: string, next: string) => Number(old !== next && stops.some(room => needsMapDrag(next, room) && !needsMapDrag(old, room)))
  const inbound = (old: string, next: string) => Number(old !== next && stops.some(room => needsMapDrag(room, next) && !needsMapDrag(room, old)))
  function resumed(pending: string[]): string[] {
    const [ready, cyclic] = workRoomOrder(work.filter(room => pending.includes(room)), dependencies)
    return [...ready, ...cyclic, ...dorms]
  }
  const returns = new Map<string, number>()
  // After the first priority task, either retained route can yield again at every handoff.
  function returnCost(pending: string[]): number {
    const index = original.length - pending.length
    if (pending.every((room, i) => room === original[index + i])) return 0
    const key = pending.join('|'), seen = returns.get(key)
    if (seen !== undefined) return seen
    const old = resumed(original.slice(index)), next = resumed(pending)
    let extra = inbound(old[0]!, next[0]!)
    for (let j = 1; j < old.length; j++) {
      const oldFrom = old[j - 1]!, oldTo = old[j]!, newFrom = next[j - 1]!, newTo = next[j]!
      const direct = Number(needsMapDrag(newFrom, newTo)) - Number(needsMapDrag(oldFrom, oldTo))
      extra += Math.max(direct, outbound(oldFrom, newFrom) + inbound(oldTo, newTo))
    }
    returns.set(key, extra)
    return extra
  }
  const failed = new Set<string>(), path: string[] = []
  function visit(pending: string[], previous: string, extra: number): boolean {
    if (!pending.length) return extra <= 0
    const index = original.length - pending.length, old = original[index]!, order = choices[index]!
    const key = `${previous}:${extra}:${pending.join('|')}`
    if (failed.has(key)) return false
    for (const room of order) {
      if (!pending.includes(room) || order.length > 1 && pending.some(source => dependencies.get(room)!.has(source))) continue
      if (index === 0 && !sameMapEntry(old, room)) continue
      const direct = extra + (index ? Number(needsMapDrag(previous, room)) - Number(needsMapDrag(original[index - 1]!, old)) : 0)
      const rest = pending.filter(other => other !== room)
      if (rest.length && index < work.length && direct + outbound(old, room) + returnCost(rest) > 0) continue
      path.push(room)
      if (visit(rest, room, direct)) return true
      path.pop()
    }
    failed.add(key)
    return false
  }
  return visit(original, '', 0) ? path : original
}

/** Refill source workplaces first and preserve stops needed after the arrangement. */
export function mowerArrangementRoomOrder(
  plan: MowerTaskPlan,
  currentRoom: (name: string) => string | undefined,
  preferVisible = true,
  allowOpenEnd = false,
  handoff?: HandoffObservations,
): string[] {
  const work = Object.keys(plan).filter(room => !room.startsWith('dormitory_'))
  const dependencies = new Map(work.map(room => [room, new Set(
    plan[room]!.map(currentRoom).filter((source): source is string => !!source && source !== room && work.includes(source)),
  )]))
  const [ordered, pending] = workRoomOrder(work, dependencies)
  const dorms = Object.keys(plan).filter(room => room.startsWith('dormitory_')).sort((a, b) => Number(a.split('_')[1]) - Number(b.split('_')[1]))
  const rooms = [...ordered, ...pending, ...dorms]
  if (!preferVisible || ordered.length < 2) return rooms
  const counts = new Map<string, number>()
  for (const names of Object.values(plan)) {
    for (const name of names) {
      if (!placeholders.has(name)) counts.set(name, (counts.get(name) ?? 0) + 1)
    }
  }
  const movable = new Set(ordered.filter(room =>
    routableRooms.has(room) &&
    plan[room]!.length > 0 && plan[room]!.every(name => counts.get(name) === 1),
  ))
  const openEnd = allowOpenEnd && movable.size === rooms.length && !movable.has('central')
  let start = 0
  for (let end = 1; end < rooms.length; end++) {
    if (end === rooms.length - 1 || !movable.has(rooms[end]!)) {
      if (end - start >= (openEnd ? 2 : 3)) rooms.splice(start, end - start + 1, ...shortestMapRoute(rooms.slice(start, end + 1), dependencies, !openEnd))
      start = end
    }
  }
  if (handoff) {
    const hours = plannedHandoffHours(plan, ordered, counts, handoff)
    if (!openEnd) hours.delete(rooms[rooms.length - 1]!)
    return handoffRoomOrder(rooms, work, dependencies, hours)
  }
  return rooms
}
/** Device back(0.5) is a source I/O boundary, including an exact Current no-op. */
export function* executeMowerTaskArrangementSteps(task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):Generator<MowerRoomReturn,boolean,void> {
 if(task.type===T.RUN_ORDER)throw new Error('理想跑单任务仅用于唤醒，不支持实体换人')
 // Native infra_main enters the arrangement branch before preview. A preview that
 // removes every physical move must still unlock the shift and rebuild metadata.
 if(!Object.keys(task.plan).length&&!task.backupShiftActive){queue.consume(task);if(rosterHead(queue,hooks)?.type===T.SHIFT_ON){const result=hooks.backup('AFTER_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)}return true}
 const protectedShift=task.backupShiftActive||!!hooks.protectShift&&Object.keys(task.plan).length>0&&task.type!==T.FIAMMETTA&&task.type!==T.RELEASE_DORM
 if(protectedShift)task.backupShiftActive=true
 let retainedLock=false
 try {
 let getTime=task.type===T.SHIFT_OFF||protectedShift&&(hooks.alpha||Object.keys(task.plan).some(room=>room.startsWith('dormitory_')))||!!hooks.alpha&&[T.SELF_CORRECTION,T.RE_ORDER,T.FILL_DORM,T.NOT_SPECIFIC].includes(task.type)
 if(task.type===T.RELEASE_DORM){if(!hooks.prepareRelease)throw new Error('Mower release requires the identity and mood-limit validation adapter');getTime=hooks.prepareRelease(task)}
 const preferVisible = !!hooks.alpha && !task.arrangementStarted && [T.SHIFT_ON, T.SHIFT_OFF, T.SELF_CORRECTION, T.NOT_SPECIFIC].includes(task.type) &&
   !task.retainsExecution && !task.strictMoodLimit && !task.arrangementRetryRoom && !task.dormRecoveryRestore.length &&
   !task.productShiftLocked && !task.exhaustSupport
 const rooms = mowerArrangementRoomOrder(task.plan, hooks.currentRoom ?? (() => undefined), preferVisible, hooks.hasRunOrderRooms === false, task.type === T.SHIFT_OFF && task.ordinaryCoordination ? hooks.handoff : undefined)
 let beforeWork=false,beforeDorm=false;const restoration:MowerTaskPlan={}
 for(const room of rooms){
  if(!room.startsWith('dormitory_')&&!beforeWork){beforeWork=true;if(enterPhase('BEFORE_WORK',task,queue,hooks)){if(!Object.keys(task.plan).length)queue.consume(task);return false}}
  if(room.startsWith('dormitory_')&&!beforeDorm){beforeDorm=true;if(enterPhase('BEFORE_DORM',task,queue,hooks)){if(!Object.keys(task.plan).length)queue.consume(task);return false}}
  const names=task.plan[room];if(!names)continue
  if(hooks.alpha&&hooks.deferRoom?.(room,task)){retainedLock=true;return false}
  task.arrangementStarted=true
  const arrangement=hooks.arrangeRoom(room,names,getTime,task,restoration)
  const additional=arrangement&&'next' in arrangement&&typeof arrangement.next==='function'?yield* (arrangement as Generator<MowerRoomReturn,MowerTaskPlan|void,void>):arrangement
  if(additional)Object.assign(restoration,additional)
  if(task.arrangementRetryRoom===room){delete task.arrangementRetryRoom;delete task.arrangementRetryCount}
  delete task.plan[room];task.dormRecoveryRestore=task.dormRecoveryRestore.filter(r=>r!==room);yield {room,delayMicros:500_000}
 }
 const restoreRooms=Object.keys(restoration)
 if(task.type===T.FIAMMETTA){
  if(restoreRooms.length){
   const restore=new MowerTask({time:rosterHead(queue,hooks)?.time??task.time,plan:restoration,type:T.FIAMMETTA})
   restore.fiaReturnTarget=task.fiaReturnTarget;restore.fiaReturnMicros=task.fiaReturnMicros;restore.fiaChargeConfirmed=task.fiaChargeConfirmed
   restore.fiaRestoration=true
   queue.tasks.push(restore);hooks.skip?.()
  }else hooks.completeFia?.(task)
 }
 task.backupShiftActive=false
 hooks.completeGroupShift?.()
 if(getTime){
  const result=hooks.backup('BEFORE_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)
  if(!result.changed)hooks.metadata()
  else if(result.generated.length){
   if(!hooks.corrections)throw new Error('Mower backup after a downshift requires the correction adapter')
   const previous=new Set(queue.tasks),created=hooks.corrections();enqueueGenerated(queue,created)
   const corrections=queue.tasks.filter(t=>!previous.has(t)&&t.type===T.SELF_CORRECTION)
   const anchor=Math.min(...result.generated.map(t=>t.timeMicros))
   for(const [offset,correction] of corrections.entries())correction.timeMicros=anchor-offset-1
  }
 }
 queue.consume(task)
 // Ideal order wakes do not hide the first retained roster task.
 if(rosterHead(queue,hooks)?.type===T.SHIFT_ON){const result=hooks.backup('AFTER_PLANNING',task,{appendEmptyTask:true,restoreOnDeactivate:false});enqueueGenerated(queue,result.generated)}
 return true
 }catch(error){if(hooks.alpha&&error instanceof MowerRoomArrangementDeferred)retainedLock=true;throw error}
 finally{if(protectedShift&&!retainedLock)task.backupShiftActive=false}
}

/** Pure decision replay: the caller owns its clock and may drain all device boundaries. */
export function executeMowerTaskArrangement(task:MowerTask,queue:MowerTaskQueue,hooks:MowerTaskExecutionHooks):boolean {
 const steps=executeMowerTaskArrangementSteps(task,queue,hooks)
 let next=steps.next();while(!next.done)next=steps.next()
 return next.value
}
