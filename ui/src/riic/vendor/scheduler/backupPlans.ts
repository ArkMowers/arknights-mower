import {mowerPrimaryJoinsRestingGroup,preserveMowerBackupRestingJoins} from './mowerBackupRestingJoin'
import {validateMowerRosterRules} from '../domain/mowerRosterRules'
import {assertMowerBackupRoomOwners, assertMowerBackupTaskRooms, mowerBackupRoomCapacity, prepareMowerBackupRoom} from '../domain/mowerBackupFacilities'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {preserveMowerBackupReplacements} from './mowerBackupReplacements'
import {captureMowerBackupRefreshRules,inheritMowerBackupRefreshRules} from './mowerBackupRefresh'
import { effectiveMowerDormOrder } from '../domain/mowerDormOrder'
import {mowerPlanEntries} from './mowerPlanOrder'
import {readMowerOperatorList, readMowerRemovedOperators, mergeMowerBackupConfig} from './mowerBackupConfig'
import {MOWER_OPERATOR_LIST_FIELDS as lists, type MowerGroupBinding, type MowerProduct} from '../domain/roster'
import {parseProduct} from '../domain/mowerProducts'
// Mower compatibility semantics: ArkMowers/arknights-mower (MIT, Copyright 2021 Nano).
// See validation/mower-backup-2026-09-22/implementation-report.md for source contracts.
import { OPERATOR_MAP } from '../domain/operators'
import {MowerTask} from './mowerTaskQueue'
import { resolveOperatorCharId as resolveId } from '../domain/operatorIdentifiers'
import type { MowerRoomId, RosterWorkspace } from '../domain/roster'
import { compileRosterSchedule } from './compileRosterSchedule'
import { compiledScheduleToRuntimeConfig } from './scheduleAdapter'
import {normalizeMowerRecoveryBeds} from './mowerRecoveryBeds'
import type { CompiledSchedule } from './types'
import type { RuntimeState } from './rosterRuntime'
import { compileBackupExpression } from './backupExpression'
import {getMowerSourceRuntime,makeMowerSchedulingData} from './mowerSourceRuntime'
import {projectMowerArrangements} from './mowerObservations'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {alphaCorrectGroupDorms,alphaRebalanceDorms,alphaPosition} from './mowerAlphaDorm'
import {mergeMowerPlanOverlay,mergeMowerShiftTransition,coalesceMowerBackupTransition,stripMowerCurrent,type MowerShiftModel} from './mowerShiftCycle'
export { actualRoom } from './backupExpression'

export const BACKUP_TIMINGS = { BEGINNING: 0, BEFORE_WORK: 100, BEFORE_DORM: 200, BEFORE_PLANNING: 300, AFTER_PLANNING: 600, END: 999 } as const
export type BackupTiming = keyof typeof BACKUP_TIMINGS
type Expression = ReturnType<typeof compileBackupExpression>['evaluate']
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)
const fail = (message: string): never => { throw new Error(`副表：${message}`) }
function operator(value: unknown): string {
  if (typeof value !== 'string' || !OPERATOR_MAP.has(resolveId(value))) return fail(`未知干员 ${String(value)}`)
  return resolveId(value)
}
export function evaluateBackupExpression(source: unknown, state: RuntimeState) {
  return compileBackupExpression(source, new Set()).evaluate(state)
}
export interface BackupDiagnostic { code: string; message: string }
interface BackupPlan {
  rooms: Partial<Record<MowerRoomId, number>>
  conf:Record<string,unknown>
  usesCurrentMood:boolean
  usesMajorMaintenance:boolean
  usesMasteryPlan:boolean
  usesInventory:boolean
  usesFacilityProduct:boolean
  name: string; timing: BackupTiming; exitTiming: BackupTiming; condition: Expression
  slots: { room: MowerRoomId; index: number; agent: string; group: string | null; replacements: string[]; groupBindings?: MowerGroupBinding[] }[]
  products: Partial<Record<MowerRoomId, {product: MowerProduct; rawProduct: unknown}>>
  task: Record<string, string[]>
}
function parsePlans(workspace: RosterWorkspace, participants: Set<string>, diagnostics: BackupDiagnostic[] = []): BackupPlan[] {
  const known = (value: unknown) => { const id = operator(value); participants.add(id); return id }
  return workspace.compatibility.backupPlans.map((raw, index) => {
    if (!record(raw)) return fail(`#${index + 1} 格式错误`)
    const name = typeof raw.name === 'string' ? raw.name : `#${index + 1}`
    try {
      const compiledCondition = compileBackupExpression(raw.trigger, participants)
      const condition = compiledCondition.evaluate
      const usesCurrentMood = compiledCondition.usesCurrentMood
      const usesMajorMaintenance = compiledCondition.usesMajorMaintenance
      const usesMasteryPlan = compiledCondition.usesMasteryPlan
      const usesInventory = compiledCondition.usesInventory
      const usesFacilityProduct = compiledCondition.usesFacilityProduct
      if (compiledCondition.skipped) {
        diagnostics.push({ code: 'BACKUP_EXTERNAL_CONDITION_SKIPPED', message: `副表 ${name}（#${index + 1}）：跳过依赖 ${compiledCondition.skipped} 的整张副表；未执行其岗位、策略与任务` })
        return { name, timing: 'AFTER_PLANNING' as const, exitTiming: 'AFTER_PLANNING' as const, condition, usesCurrentMood, usesMajorMaintenance, usesMasteryPlan, usesInventory, usesFacilityProduct, rooms: {}, slots: [], products: {}, task: {},conf:{} }
      }
      const timing = typeof raw.trigger_timing === 'string' ? raw.trigger_timing.toUpperCase() : ''
      const slots: BackupPlan['slots'] = [], task: BackupPlan['task'] = {}, products: BackupPlan['products'] = {}, rooms: BackupPlan['rooms'] = {}
      if (raw.plan !== undefined && !record(raw.plan) || raw.task !== undefined && !record(raw.task) || raw.conf !== undefined && !record(raw.conf)) fail('plan/task/conf 格式错误')
      for (const [room, data] of mowerPlanEntries(record(raw.plan) ? raw.plan : {})) {
        const facility = workspace.mainPlan.facilities[room as MowerRoomId]
        if (!facility || !record(data) || !Array.isArray(data.plans) || data.plans.length > mowerBackupRoomCapacity(workspace, room)) fail(`计划房间/槽位错误 ${room}`)
        rooms[room as MowerRoomId] = (data as {plans: unknown[]}).plans.length
        const rawProduct = (data as Record<string, unknown>).product
        if (rawProduct) {
          const product = parseProduct(rawProduct)
          if (!product) return fail(`未知副表产物 ${room}: ${String(rawProduct)}`)
          products[room as MowerRoomId] = {product, rawProduct}
        }
        ;(data as { plans: unknown[] }).plans.forEach((slot, i) => {
          if (!record(slot) || typeof slot.agent !== 'string' || !Array.isArray(slot.replacement ?? [])) return fail(`计划槽位错误 ${room}.${i}`)
          if (slot.agent === 'Current') return
          if (slot.agent === 'Free' && facility.type !== 'dormitory') fail(`Free 只能用于宿舍 ${room}`)
          if (slot.group_bindings !== undefined && !Array.isArray(slot.group_bindings)) return fail(`组合列格式错误 ${room}.${i}`)
          const groupBindings = (slot.group_bindings as unknown[] | undefined)?.map((binding, bindingIndex) => {
            if (!record(binding) || !Array.isArray(binding.replacement ?? [])) return fail(`组合列格式错误 ${room}.${i}.${bindingIndex}`)
            return {groupId: typeof binding.group === 'string' ? binding.group : null, replacements: (binding.replacement as unknown[] ?? []).map(value => value === 'Free' ? 'Free' : known(value))}
          })
          slots.push({ groupBindings, room: room as MowerRoomId, index: i, agent: slot.agent === 'Free' ? 'Free' : known(slot.agent), group: typeof slot.group === 'string' ? slot.group : null, replacements: (slot.replacement as unknown[] ?? []).map(value=>value==='Free'?'Free':known(value)) })
        })
      }
      for (const key of lists) readMowerOperatorList(key, (raw.conf as Record<string, unknown> | undefined)?.[key], known)
      readMowerRemovedOperators((raw.conf as Record<string, unknown> | undefined)?.removed_operators, known)
      for (const [room, values] of mowerPlanEntries(record(raw.task) ? raw.task : {})) {
        const facility = workspace.mainPlan.facilities[room as MowerRoomId]
        if (!facility || !Array.isArray(values) || values.length > mowerBackupRoomCapacity(workspace, room)) fail(`任务房间/槽位错误 ${room}`)
        task[room] = (values as unknown[]).map(value => value === 'Current' || value === 'Free' ? value : known(value))
        if (facility.type !== 'dormitory' && task[room]!.includes('Free')) fail(`任务 Free 只能用于宿舍 ${room}`)
      }
      const entry = timing in BACKUP_TIMINGS ? timing as BackupTiming : 'AFTER_PLANNING'
      const exit = typeof raw.exit_trigger_timing === 'string' && raw.exit_trigger_timing ? raw.exit_trigger_timing.toUpperCase() : undefined
      return { name, timing: entry, exitTiming: exit ? exit in BACKUP_TIMINGS ? exit as BackupTiming : 'AFTER_PLANNING' : entry, condition, usesCurrentMood, usesMajorMaintenance, usesMasteryPlan, usesInventory, usesFacilityProduct, rooms, slots, products, task,conf:record(raw.conf)?raw.conf:{} }
    } catch (error) { return fail(`${name}：${error instanceof Error ? error.message : String(error)}`) }
  })
}
export function backupParticipants(workspace: RosterWorkspace): string[] {
  const participants = new Set<string>(); parsePlans(workspace, participants); return [...participants]
}

/** Keeps planned roles separate from physical occupancy; no morale/production reset. */
export function createBackupPlanController(base: CompiledSchedule, state: RuntimeState, options: { virtualRunners?: boolean; canUseFiammetta?: (id: string) => boolean } = {}) {
  base = structuredClone(base)
  const recoveryBeds = new Map(compiledScheduleToRuntimeConfig(base).beds.map(bed => [bed.id,bed]))
  const diagnostics: BackupDiagnostic[] = []
  const participants = new Set<string>(), plans = parsePlans(base.sourceWorkspace, participants, diagnostics)
  if(plans.some(plan=>plan.usesMajorMaintenance)&&base.assumptions.majorMaintenanceStartHours===undefined)diagnostics.push({code:'MOWER_MAINTENANCE_ASSUMPTION',message:'未提供维护时间，本次模拟没有停服窗口'})
  if(plans.some(plan=>plan.usesMasteryPlan))diagnostics.push({code:'MOWER_MASTERY_PLAN_ASSUMPTION',message:'本次模拟固定为无未完成的训练计划，不模拟训练进度或计划完成时刻'})
  const observedPlans = plans.filter(plan=>plan.usesInventory||plan.usesFacilityProduct)
  let observedConditions: string | undefined
  const observationSignature = () => JSON.stringify(observedPlans.map(plan=>Boolean(plan.condition(state))))
  const observationBlocked = () => {
    const source=state.mowerSource
    return source?.queue.tasks.some(task=>task.backupShiftActive||task.type===T.FIAMMETTA&&task.timeMicros<=toMowerMicros(state.time))||source?.activeTask?.type===T.FIAMMETTA
  }
  if(observedPlans.length)Object.defineProperty(state,'mowerBackupObservationWakeMicros',{
    configurable:true,enumerable:false,
    value:()=>observationBlocked()||observationSignature()===observedConditions?undefined:toMowerMicros(state.time),
  })
  else delete state.mowerBackupObservationWakeMicros
  const active = plans.map(() => false)
  for (const id of participants) {
    state.morale[id] ??= base.assumptions.operatorMorale[id] ?? base.assumptions.initialMorale
    ;(state.initialMorale??={})[id] ??= state.morale[id]
  }
  const displaced = new Set<string>()
  let effective = base
  const alphaConfigs=new Map<string,{compiled:CompiledSchedule;config:RuntimeState['config']}>()
  // Keep the caller's compiled base constraints (including an intentionally empty
  // recovery pool) when a preview refreshes the unchanged base plan.
  if(!plans.length)alphaConfigs.set(JSON.stringify(active),{compiled:base,config:state.config})
  function alphaConfiguration(conditions:boolean[]){
    const key=JSON.stringify(conditions),cached=alphaConfigs.get(key);if(cached)return cached
    const workspace=structuredClone(base.sourceWorkspace);workspace.compatibility.backupPlans=[]
    let dormOrder=typeof base.rawConf.dorm_order==='string'?base.rawConf.dorm_order:base.assumptions.dormOrder??''
    conditions.forEach((enabled,i)=>{
      if(!enabled)return
      const p=plans[i]!
      for(const [room,count] of Object.entries(p.rooms))prepareMowerBackupRoom(workspace,room,count)
      for(const slot of p.slots)workspace.mainPlan.facilities[slot.room].slots[slot.index]={occupant:slot.agent==='Free'?{kind:'free'}:{kind:'operator',operatorId:slot.agent},groupId:slot.group,replacements:[...slot.replacements],groupBindings:structuredClone(slot.groupBindings)}
      for(const [room,{product,rawProduct}] of Object.entries(p.products)){
        workspace.mainPlan.facilities[room as MowerRoomId].product=product
        const metadata=workspace.compatibility.facilityMetadata??={}
        metadata[room]={...metadata[room],rawProduct}
      }
      mergeMowerBackupConfig(workspace.mainPlan.conf, p.conf)
      if(typeof workspace.mainPlan.conf.dorm_order==='string')dormOrder=workspace.mainPlan.conf.dorm_order
    })
    assertMowerBackupRoomOwners(base.sourceWorkspace,workspace)
    // A caller's legacy bed order remains the outer simulation override; otherwise use the merged native backup conf.
    if(base.assumptions.dormOrder)dormOrder=base.assumptions.dormOrder
    const roomOrder=effectiveMowerDormOrder(dormOrder.split(','))
    const ruleErrors=validateMowerRosterRules(workspace);if(ruleErrors.length)fail(ruleErrors.map(error=>error.message).join('；'))
    const compiled=compileRosterSchedule(workspace,{...base.assumptions,dormOrder:''});compiled.assumptions.defaultsApplied=[...base.assumptions.defaultsApplied]
    if(compiled.diagnostics.some(d=>d.severity==='error'||d.code==='UNKNOWN_OPERATOR'))fail(compiled.diagnostics.map(d=>d.message).join('；'))
    const config=compiledScheduleToRuntimeConfig(compiled);config.mowerAlpha=true;config.mowerDormOrder=roomOrder;config.availableIdleOperators=state.config.availableIdleOperators;config.mowerSingleRecoverySkillNames=state.config.mowerSingleRecoverySkillNames
    for(const key of ['adjustForRunOrders','maintenance','maintenanceEndMicros','firstDailyResetMicros'] as const){
      const value=state.config.mowerTaskScheduling?.[key]
      if(value!==undefined)config.mowerTaskScheduling={...config.mowerTaskScheduling,[key]:value}
    }
    if(options.virtualRunners)config.runOrderPolicies=[]
    if(config.fiammetta&&options.canUseFiammetta&&!options.canUseFiammetta(config.fiammetta.operatorId))config.fiammetta=undefined
    const primaries=config.positions.map(p=>p.primary);if(new Set(primaries).size!==primaries.length)fail('副表生效组合重复主班')
    normalizeMowerRecoveryBeds(config)
    for(const bed of config.beds)bed.managedRecovery=true
    const snapshot={compiled,config};alphaConfigs.set(key,snapshot);return snapshot
  }
  const alphaModel:MowerShiftModel={
    count:plans.length,
    explicitSlots:(original,conditions)=>new Set(plans.flatMap((plan,i)=>!original[i]&&conditions[i]?Object.entries(plan.task).flatMap(([room,row])=>row.flatMap((name,index)=>name!=='Current'?[alphaPosition(room,index)]:[])):[])),
    // This preserves the source's one-second observation capability; it does
    // not claim exact roots for arbitrary imported comparison expressions.
    nextConditionWakeMicros:data=>plans.some(plan=>plan.usesCurrentMood||plan.usesMajorMaintenance&&base.assumptions.majorMaintenanceStartHours!==undefined)?data.nowMicros+1_000_000:undefined,
    nextIdleConditionWakeMicros:data=>plans.some(plan=>plan.usesMajorMaintenance)&&base.assumptions.majorMaintenanceStartHours!==undefined&&data.nowMicros<=base.assumptions.majorMaintenanceStartHours*3_600_000_000?data.nowMicros+1_000_000:undefined,
    evaluate(data){return plans.map(p=>Boolean(p.condition({...state,time:data.nowMicros/3_600_000_000,mowerSource:{...getMowerSourceRuntime(state),data}})))},
    swap(data,conditions){const {config}=alphaConfiguration(conditions);const next=makeMowerSchedulingData({...state,config,morale:{...state.morale},initialMorale:{...state.initialMorale}},{data});next.planConditions=[...conditions];return next},
    transition(previous,next,original,conditions,recovery=previous,pendingTasks){
      const transition:Record<string,string[]>={},groupPositions=new Set<string>(),replacementPositions:[string,number][]=[],restored=new Set<string>(),joiningResting=new Set<string>()
      const protectedTraining=new Set([...previous.busyRestingNames,...next.busyRestingNames])
      plans.forEach((p,i)=>{if(original[i]&&!conditions[i])for(const [room,names] of Object.entries(p.task))names.forEach((name,index)=>{if(name!=='Current')restored.add(alphaPosition(room,index))})})
      for(const [room,names] of Object.entries(next.plan))names.forEach((name,index)=>{
        if(room.startsWith('dorm')&&name==='Free')return
        const oldName=previous.plan[room]?.[index],old=previous.operators[oldName??''],op=next.operators[name]
        if(oldName===name&&old?.group===op?.group&&JSON.stringify(old?.replacement??[])===JSON.stringify(op?.replacement??[])&&JSON.stringify(old?.groupBindings??[])===JSON.stringify(op?.groupBindings??[])&&!(restored.has(alphaPosition(room,index))&&op?.isResting()))return
        if(op&&mowerPrimaryJoinsRestingGroup(previous,next,op,protectedTraining)){replacementPositions.push([room,index]);joiningResting.add(name);return}
        const previousOwner=previous.operators[name]
        if(op&&previousOwner?.isHigh()&&(oldName===name||!op.currentRoom||op.isResting())&&(oldName===name||!room.startsWith('dorm'))&&(next.currentOperator(room,index)||op.currentRoom||op.timeStampMicros!==undefined)&&previousOwner.group===op.group&&previousOwner.room===op.room&&JSON.stringify(previousOwner.groupBindings.map(b=>b.group))===JSON.stringify(op.groupBindings.map(b=>b.group))){replacementPositions.push([room,index]);return}
        if(room.startsWith('dorm')&&op?.group){groupPositions.add(alphaPosition(room,index));return}
        const actual=next.currentOperator(room,index)
        if(actual&&(actual.name===name||op?.replacement.includes(actual.name)&&!next.excludedCandidates.has(actual.name)))return
        ;(transition[room]??=Array(names.length).fill('Current'))[index]=name
      })
      plans.forEach((p,i)=>{if(!original[i]||conditions[i])return;for(const [room,names] of Object.entries(p.task))names.forEach((name,index)=>{if(name!=='Current'&&next.plan[room]?.[index]!==undefined&&!replacementPositions.some(([r,i])=>r===room&&i===index))(transition[room]??=Array(next.plan[room]!.length).fill('Current'))[index]=next.plan[room]![index]!})})
      plans.forEach((p,i)=>{
        if(original[i]||!conditions[i])return
        // Explicit tasks run on activation; completed tasks do not constrain later overlays.
        assertMowerBackupTaskRooms(alphaConfiguration(conditions).compiled.sourceWorkspace,p.task)
        mergeMowerPlanOverlay(transition,p.task,next)
        for(const [room,names] of Object.entries(p.task))names.forEach((name,index)=>{if(name!=='Current')groupPositions.delete(alphaPosition(room,index))})
      })
      if(groupPositions.size)alphaCorrectGroupDorms(next,transition,groupPositions)
      if(joiningResting.size?!preserveMowerBackupRestingJoins(next,transition,replacementPositions,recovery.dorms,joiningResting,pendingTasks??getMowerSourceRuntime(state).queue.tasks.filter(task=>task!==getMowerSourceRuntime(state).activeTask),protectedTraining):!preserveMowerBackupReplacements(next,transition,replacementPositions,recovery.dorms))throw new MowerShiftPreviewError('副表替班或恢复床位不可用，暂缓切表')
      const signature=(data:MowerSchedulingData)=>JSON.stringify([data.dormOrder,data.dorms.map(b=>[b.position,data.plan[b.position[0]]?.[b.position[1]],data.operators[data.plan[b.position[0]]?.[b.position[1]]??'']?.group,data.effectiveFreeSlot(b),b.name])])
      if(signature(recovery)!==signature(next)){
        const migration=projectMowerArrangements(next,[transition]),reserved=new Set(Object.values(transition).flat().filter(n=>!['Current','Free',''].includes(n)))
        const slots=new Set(Object.entries(transition).flatMap(([room,names])=>names.flatMap((name,index)=>name!=='Current'?[alphaPosition(room,index)]:[])))
        const plan=alphaRebalanceDorms(migration,recovery.dorms,reserved,slots);next.dorms=migration.dorms;mergeMowerShiftTransition(transition,plan,next)
      }
      for(const [room,names] of Object.entries(transition))if(room.startsWith('dorm'))names.forEach((name,index)=>{if(!['Current','Free',''].includes(name)&&next.restMoodComplete(name)&&next.currentOperator(room,index)?.name!==name)names[index]='Current'})
      return stripMowerCurrent(transition)
    },
    activate(conditions,task){
      const previous=getMowerSourceRuntime(state).data,oldDrained=state.config.mowerSourceRules?.refreshDrained??[]
      const snapshot=alphaConfiguration(conditions)
      conditions.forEach((value,i)=>{if(value!==active[i])state.events.push({time:state.time,type:'backup-plan',operators:[],backupIndex:i,backupName:plans[i]!.name,active:value,timing:'END'});active[i]=value})
      state.config=snapshot.config;effective=snapshot.compiled;getMowerSourceRuntime(state).data.planConditions=[...active]
      captureMowerBackupRefreshRules(task,previous,getMowerSourceRuntime(state).data,oldDrained,state.config.mowerSourceRules?.refreshDrained??[])
    },
  }
  if(state.config.mowerAlpha){state.mowerShiftModel=alphaModel;getMowerSourceRuntime(state).data.planConditions=[...active]}
  function evaluateAlpha(timing:BackupTiming):boolean{
    const source=getMowerSourceRuntime(state),queue=source.queue,data=source.data
    if(queue.tasks.some(t=>t.backupShiftActive||t.type===T.FIAMMETTA&&t.timeMicros<=data.nowMicros)||source.activeTask?.type===T.FIAMMETTA)return false
    const original=[...active],seen=new Set([JSON.stringify(original)]);let current=data,conditions=alphaModel.evaluate(data)
    for(let pass=0;pass<64;pass++){
      if(conditions.every((v,i)=>v===current.planConditions[i])){
        if(conditions.every((v,i)=>v===original[i]))return false
        let transition:Record<string,string[]>
        try{transition=alphaModel.transition(data,current,original,conditions)}catch(error){if(!(error instanceof MowerShiftPreviewError))throw error;state.diagnostics.push({code:'mower-backup-deferred',message:error.message});return false}
        const merged=coalesceMowerBackupTransition(current,transition,queue.tasks)
        const generated:MowerTask[]=[]
        if(Object.keys(merged.plan).length){const task=new MowerTask({time:state.time,type:Object.keys(merged.plan).some(room=>room.startsWith('dorm'))?T.RE_ORDER:T.SELF_CORRECTION,plan:merged.plan,metadata:'副表内存收敛'});if(state.mowerBackupContext?.customTimeMicros!==undefined)task.timeMicros=state.mowerBackupContext.customTimeMicros;generated.push(task);queue.tasks.push(task);queue.tasks=queue.tasks.filter(t=>!merged.consumed.includes(t))}
        if(generated[0]){
          generated[0].coordinationRequestNames=[...new Set(merged.consumed.filter(task=>task.ordinaryCoordination).flatMap(task=>task.coordinationRequestNames))]
          generated[0].ordinaryCoordination=generated[0].coordinationRequestNames.length>0
          inheritMowerBackupRefreshRules(generated[0],merged.consumed)
          generated[0].backupExplicitSlots=new Set([...(alphaModel.explicitSlots?.(original,conditions)??[]),...merged.consumed.flatMap(task=>[...task.backupExplicitSlots].filter(slot=>{const [room,index]=slot.split('\0');return merged.plan[room!]?.[Number(index)]===task.plan[room!]?.[Number(index)]}))])
        }
        alphaModel.activate(conditions,generated[0]);getMowerSourceRuntime(state).data.dorms=current.dorms
        for(const event of state.events.slice(-plans.length))if(event.type==='backup-plan'&&event.time===state.time)event.timing=timing
        const followup=new MowerTask({time:state.time});if(state.mowerBackupContext?.customTimeMicros!==undefined)followup.timeMicros=state.mowerBackupContext.customTimeMicros;generated.push(followup)
        state.mowerBackupGenerated=generated
        return Object.keys(merged.plan).length>0
      }
      const key=JSON.stringify(conditions)
      if(seen.has(key)){state.diagnostics.push({code:'mower-backup-cycle',message:'副表条件在内存演算中出现循环，保持切换前状态'});return false}
      seen.add(key);current=alphaModel.swap(current,conditions);conditions=alphaModel.evaluate(current)
    }
    state.diagnostics.push({code:'mower-backup-cycle',message:'副表条件在 64 次演算内未收敛，保持切换前状态'});return false
  }
  const remove = (id: string, occupants: Record<string, string>, beds: Record<string, string>) => {
    for (const [key, value] of Object.entries(occupants)) if (value === id) delete occupants[key]
    for (const [key, value] of Object.entries(beds)) if (value === id) delete beds[key]
  }
  const unique = (occupants: Record<string, string>, beds: Record<string, string>) => {
    const ids = [...Object.values(occupants), ...Object.values(beds)]
    if (new Set(ids).size !== ids.length) fail('任务造成重复占岗')
  }
  function evaluate(timing: BackupTiming): boolean {
    // Only real phase evaluations consume the observation edge; alpha previews are speculative.
    if(observedPlans.length){if(observationBlocked())return false;observedConditions=observationSignature()}
    if(state.config.mowerAlpha)return evaluateAlpha(timing)
    if(state.mowerSource?.queue.tasks.some(task=>task.backupShiftActive))return false
    const next = plans.map((p, i) => {
      const enabled = Boolean(p.condition(state))
      return BACKUP_TIMINGS[enabled ? p.timing : p.exitTiming] <= BACKUP_TIMINGS[timing] ? enabled : active[i]!
    })
    if (next.every((value, i) => value === active[i])) return false
    const workspace = structuredClone(base.sourceWorkspace)
    workspace.compatibility.backupPlans = []
    next.forEach((enabled, i) => {
      if (!enabled) return
      const plan = plans[i]!
      for (const [room, count] of Object.entries(plan.rooms)) prepareMowerBackupRoom(workspace, room, count)
      for (const slot of plan.slots) workspace.mainPlan.facilities[slot.room].slots[slot.index] = {
        occupant: slot.agent === 'Free' ? { kind: 'free' } : { kind: 'operator', operatorId: slot.agent },
        groupId: slot.group, replacements: [...slot.replacements], groupBindings: structuredClone(slot.groupBindings),
      }
      for (const [room, {product, rawProduct}] of Object.entries(plan.products)) {
        workspace.mainPlan.facilities[room as MowerRoomId].product = product
        const metadata = workspace.compatibility.facilityMetadata ??= {}
        metadata[room] = {...metadata[room], rawProduct}
      }
      mergeMowerBackupConfig(workspace.mainPlan.conf, plan.conf)
    })
    assertMowerBackupRoomOwners(base.sourceWorkspace, workspace)
    next.forEach((enabled, i) => { if (enabled && !active[i]) assertMowerBackupTaskRooms(workspace, plans[i]!.task) })
    const compiled = compileRosterSchedule(workspace, base.assumptions)
    // A backup changes the roster; resolved values keep their original input provenance.
    compiled.assumptions.defaultsApplied = [...base.assumptions.defaultsApplied]
    if (compiled.diagnostics.some(d => d.severity === 'error' || d.code === 'UNKNOWN_OPERATOR')) fail(compiled.diagnostics.map(d => d.message).join('；'))
    const config = compiledScheduleToRuntimeConfig(compiled)
    for(const key of ['adjustForRunOrders','maintenance','maintenanceEndMicros','firstDailyResetMicros'] as const){
      const value=state.config.mowerTaskScheduling?.[key]
      if(value!==undefined)config.mowerTaskScheduling={...config.mowerTaskScheduling,[key]:value}
    }
    config.availableIdleOperators = state.config.availableIdleOperators
    config.mowerSingleRecoverySkillNames = state.config.mowerSingleRecoverySkillNames
    // Default alpha init_and_validate(update=True) keeps the original recovery pool.
    // Newly exposed Free slots remain real idle positions, without a group timer.
    for (const bed of config.beds) {
      const original = recoveryBeds.get(bed.id)
      bed.managedRecovery = Boolean(original)
      bed.vip = original?.vip ?? false
    }
    // Preserve exclusions applied by the simulator (virtual runners / locked skill stages).
    if (options.virtualRunners) config.runOrderPolicies = []
    if (config.fiammetta && options.canUseFiammetta && !options.canUseFiammetta(config.fiammetta.operatorId)) config.fiammetta = undefined
    const primaries = config.positions.map(p => p.primary)
    if (new Set(primaries).size !== primaries.length) fail(`激活组合 ${next.map((v, i) => v ? plans[i]!.name : '').filter(Boolean).join('、')} 重复主班`)
    // alpha init validates the full group's effective Free-bed capacity.
    const groups = new Map<string, number>()
    for (const p of config.positions) if (p.group && !p.dormitory && !p.permanent) groups.set(p.group,(groups.get(p.group) ?? 0)+1)
    for (const [group,count] of groups) if (count > config.beds.filter(b => b.managedRecovery !== false).length) fail(group+' 分组需要 '+count+' 个休息床位，副表仅提供 '+config.beds.filter(b => b.managedRecovery !== false).length+' 个')
    if(state.config.mowerSourcePlan){
      const generated:MowerTask[]=[],context=state.mowerBackupContext??{appendEmptyTask:true,restoreOnDeactivate:false}
      const restored:Record<string,Set<number>>={}
      for(const [i,plan] of plans.entries()){
        if(next[i]===active[i])continue
        if(next[i]&&Object.keys(plan.task).length){
          const task=new MowerTask({time:state.time,plan:structuredClone(plan.task)})
          if(context.customTimeMicros!==undefined)task.timeMicros=context.customTimeMicros
          generated.push(task)
        }else if(Object.keys(plan.task).length&&context.restoreOnDeactivate){
          for(const [room,names] of Object.entries(plan.task))names.forEach((name,index)=>{if(name!=='Current')(restored[room]??=new Set()).add(index)})
        }
      }
      const restore:Record<string,string[]>={}
      for(const [room,indexes] of Object.entries(restored)){
        const slots=config.mowerSourcePlan?.[room];if(!slots)continue
        const names=slots.map(()=> 'Current');for(const index of indexes)if(slots[index])names[index]=slots[index]!.agent
        if(names.some(name=>name!=='Current'))restore[room]=names
      }
      if(Object.keys(restore).length){const task=new MowerTask({time:state.time,plan:restore});if(context.customTimeMicros!==undefined)task.timeMicros=context.customTimeMicros;generated.push(task)}
      state.config=config;effective=compiled
      next.forEach((value,i)=>{
        if(value!==active[i])state.events.push({time:state.time,type:'backup-plan',operators:[],backupIndex:i,backupName:plans[i]!.name,active:value,timing})
        active[i]=value
      })
      if(state.mowerSource)state.mowerSource.data.planConditions=[...active]
      if(context.appendEmptyTask&&!generated.length)state.mowerBackupGenerated=[new MowerTask({time:state.time})]
      else state.mowerBackupGenerated=generated
      return generated.length>0
    }
    const previous = { ...state.occupants, ...state.bedOccupants }
    const resting = new Set([...Object.values(state.bedOccupants), ...state.config.positions.filter(p => p.dormitory).map(p => state.occupants[p.id]).filter(Boolean)])
    const occupants: Record<string, string> = {}, beds: Record<string, string> = {}
    for (const bed of config.beds) if (previous[bed.id]) beds[bed.id] = previous[bed.id]!
    for (const p of config.positions) {
      const old = previous[p.id]
      if (old) occupants[p.id] = old
    }
    // Reconcile the new plan for working primaries and fixed dormitory keepers.
    const assignments = config.positions.filter(p => state.config.positions.find(old => old.id === p.id)?.primary !== p.primary
      && (p.dormitory || !resting.has(p.primary) && Object.values(state.occupants).includes(p.primary)))
    for (const p of assignments) remove(p.primary, occupants, beds)
    for (const p of assignments) occupants[p.id] = p.primary
    const taskEvents: { index: number; operators: string[] }[] = []
    for (const [i, plan] of plans.entries()) {
      if (!next[i] || active[i] || !Object.keys(plan.task).length) continue
      const before = { ...occupants, ...beds }, targets: Record<string, string> = {}
      const explicit = Object.values(plan.task).flat().filter(agent => agent !== 'Current' && agent !== 'Free')
      if (new Set(explicit).size !== explicit.length) fail(`${plan.name} 任务重复干员`)
      for (const [room, slots] of Object.entries(plan.task)) slots.forEach((agent, index) => {
        const key = `${room}_${index}`
        // Moving an explicitly named operator necessarily vacates its old Current slot.
        const id = agent === 'Current' ? (before[key] && !explicit.includes(before[key]!) ? before[key] : undefined) : agent === 'Free' ? undefined : agent
        if (id) targets[key] = id
      })
      if (new Set(Object.values(targets)).size !== Object.values(targets).length) fail(`${plan.name} 任务重复干员`)
      for (const id of Object.values(targets)) remove(id, occupants, beds)
      for (const [room, slots] of Object.entries(plan.task)) slots.forEach((_, index) => {
        const key = `${room}_${index}`; delete occupants[key]; delete beds[key]
        if (!targets[key]) return
        if (config.beds.some(b => b.id === key)) beds[key] = targets[key]!
        else if (config.positions.some(p => p.id === key)) occupants[key] = targets[key]!
        else fail(`${plan.name} 任务目标没有有效岗位 ${key}`)
      })
      taskEvents.push({ index: i, operators: Object.values(targets) })
    }
    // A forced rest may vacate a work slot; reserve only an eligible real substitute.
    for (const p of config.positions.filter(p => !p.dormitory)) if (!occupants[p.id]) {
      const candidate = p.candidates.find(id => !primaries.includes(id) && !Object.values(occupants).includes(id) && !config.excludedCandidates?.includes(id))
      if (candidate) { remove(candidate, occupants, beds); occupants[p.id] = candidate }
    }
    // Tasks and plan changes may evict working or resting primaries. Preserve
    // every displaced member and queue a real bed without inventing capacity.
    const present = new Set([...Object.values(occupants), ...Object.values(beds)])
    for (const id of [...Object.values(state.occupants), ...resting, ...(state.pendingRest ?? [])]) if (id && !present.has(id)) displaced.add(id)
    for (const id of present) displaced.delete(id)
    const pendingRest = [...new Set([...(state.pendingRest ?? []), ...resting, ...displaced])].filter((id): id is string => Boolean(id) && primaries.includes(id!) && !Object.values(occupants).includes(id!) && !Object.values(beds).includes(id!))
    const activeBackupBeds = new Set<string>()
    for (const [i, plan] of plans.entries()) {
      if (next[i] && Object.keys(plan.task).length) {
        for (const [room, slots] of Object.entries(plan.task)) {
          if (room.startsWith('dormitory')) {
            slots.forEach((agent, index) => {
              if (agent !== 'Current' && agent !== 'Free') {
                activeBackupBeds.add(agent)
                const key = `${room}_${index}`
                if (config.beds.some(b => b.id === key) && !beds[key]) {
                  remove(agent, occupants, beds)
                  beds[key] = agent
                }
              }
            })
          }
        }
      }
    }
    unique(occupants, beds)
    state.backupBedOccupants = activeBackupBeds
    state.config = config; state.occupants = occupants; state.bedOccupants = beds; state.pendingRest = pendingRest
    state.returnDeadlines = {}; state.timingSignature = undefined
    effective = compiled
    next.forEach((value, i) => {
      if (value !== active[i]) state.events.push({ time: state.time, type: 'backup-plan', operators: [], backupIndex: i, backupName: plans[i]!.name, active: value, timing })
      active[i] = value
    })
    for (const task of taskEvents) state.events.push({ time: state.time, type: 'backup-task', operators: task.operators, backupIndex: task.index, backupName: plans[task.index]!.name, timing })
    return true
  }
  return { active, evaluate, diagnostics, get schedule() { return effective }, count: plans.length }
}
