import {MOWER_MOOD_CONTROL_VERSION} from '../scheduler/mowerPredictiveMoodControl'
import { eligibleSingleRecoveryTargets, hasSingleRecoverySkill } from '../engine/singleRecoveryEligibility'
import {createSimulationActivityMonitor, type SimulationActivity} from './simulationActivity'
import {mowerCoordinationRates} from './mowerCoordinationRates'
import {resolveInventoryProduction} from './inventorySimulation'
import { parseProduct, serializeProduct } from '../domain/mowerProducts'
import {createMowerClueIO} from './mowerNativeClueIO'
import {createMowerProductionIO} from './mowerNativeProductionIO'
import {mowerConfirmedRecoveryTargets} from '../scheduler/mowerDormRecovery'
import { createBackupPlanController } from '../scheduler/backupPlans'
import { inventoryOperatorRecords, operatorFor, hasOperatorSkill } from '../domain/operatorContext'
import {createProductionTimeline,assertRunOrderMode,type ProductionOptions,type ProductionReport,type ProductionFrame} from './productionTimeline'
import {createDefaultConfig,createRoom} from '../domain/defaults'
import { isDroneCapacity, resolveDroneCapacity } from '../domain/droneCapacity'
import {OPERATORS,OPERATOR_MAP} from '../domain/operators'
import {compileOperatorInventory,type OwnedOperatorInput} from '../domain/operatorInventory'
import {validateScheduleInventory} from '../scheduler/inventoryValidation'
import type {AppConfig,EfficiencyResources} from '../domain/types'
import {currentMoraleRates} from '../engine/morale'
import {evaluateRecycleEfficiency} from '../engine/supportFacilitySkills'
import {evaluateDormitoryRecovery} from '../engine/dormitoryRecovery'
import {evaluateOperators} from '../engine/operatorRules'
import {buildRiicGlobalContext} from '../engine/globalContext'
import {getTemporalSkillBoundaries,qualitySkillWarmupHours} from '../engine/timeDependentSkills'
import type {CompiledSchedule} from '../scheduler/types'
import {compiledScheduleToRuntimeConfig} from '../scheduler/scheduleAdapter'
import {normalizeMowerRecoveryBeds} from '../scheduler/mowerRecoveryBeds'
import {advanceRoster,createRosterRuntime,currentMoraleDerivatives,MORALE_EPSILON,nextRosterEventHours,nextRosterActionHours,settleRoster,moraleDerivative,type RuntimeState,type RuntimeRates,type RuntimeEvent} from '../scheduler/rosterRuntime'
import { MORALE_SKILL_THRESHOLDS, retainedRecoveryTarget } from '../engine/moraleThresholds'

export interface ScheduleSimulationProgress {
 phase:'warmup'|'sampling'; elapsedHours:number; totalHours:number; warmupHours:number
 activity?:SimulationActivity
}
export interface ScheduleSimulationOptions {
 /** Read-only observation of each resolved interval, including warmup. */
 observeInterval?:(config:AppConfig,start:number,end:number,workHours:ReadonlyMap<string,number>)=>void
 /** The complete-preview alpha scheduler requires an explicit opt-in. */
 schedulingModel?:'mower-default'|'mower-alpha'
 productionWeights?:import('../domain/productionWeights').ProductionWeights
 operatorInventory?:OwnedOperatorInput[]
 jayeElite0?:boolean
 production?:ProductionOptions
 /** Validation-only switch for the old ideal path that omitted order wakes. */
 experimentalDisableIdealWake?:boolean
 sampleHours?:number; warmupHours?:number; maxStepHours?:number; maxEvents?:number
 warmupModel?:'continuous'|'hourly'; recordSegments?:boolean
 consumptionOverrides?:Record<string,number>; recoveryOverrides?:Record<string,number>
 atmosphereByRoom?:Record<string,number>; recoveryTargetByProvider?:Record<string,string>
 initialWorkHours?:Record<string,number>; efficiencyResources?:Partial<EfficiencyResources>
}
export interface SimulatedOperator {
 operatorId:string; operatorName:string; mainWorkHours:number; substituteWorkHours:number
 workHours:number; exhaustedHours:number; restHours:number; idleHours:number
 /** Measured occupancy of the explicit permanent primary slot. */
 permanentPrimaryOccupancyHours?:number
 workFraction:number; workRestRatio:number|null; initialMorale:number; finalMorale:number
}
export interface SimulatedRoom {
 roomId:string; roomType:string; averageEfficiencyPercent:number; efficiencyPercentHours:number
 occupiedHours:number; teams:{operatorIds:string[]; hours:number; fraction:number}[]
}
export interface ScheduleSegment {start:number;end:number;occupants:Record<string,string>;bedOccupants:Record<string,string>;morale:Record<string,number>;efficiencyPercent:Record<string,number>}
export interface ScheduleSimulationReport {
 schemaVersion:1; engine:'mower-morale-v1'; success:boolean; elapsedHours:number; observedHours:number
 inputs:{schedule:CompiledSchedule;options:ScheduleSimulationOptions}
 assumptions:{moodControlStrategyVersion:string;predictiveMoodControl:boolean;schedulingModel?:'mower-default'|'mower-alpha';sampleHours:number;warmupHours:number;maxStepHours:number;warmupModel:'continuous'|'hourly';restingThreshold:number;operationDurationHours:0;dormAtmosphere:string;singleRecoveryTarget:string}
 production?:ProductionReport
 operators:SimulatedOperator[];rooms:SimulatedRoom[];events:RuntimeEvent[];segments:ScheduleSegment[]
 diagnostics:{code:string;message:string}[]
 shiftDeferrals?:{key:string;operatorIds:string[];blockedAt:number;resolvedAt?:number}[]
}
const EPS=MORALE_EPSILON
const numericKeys=['sampleHours','warmupHours','maxStepHours','maxEvents'] as const

/** Pure occupancy projection. Empty Free slots have no operator and create no global resources. */
export function projectScheduleState(schedule:CompiledSchedule,state:RuntimeState,actualProducts:Readonly<Record<string,string>>={}):AppConfig {
 const c=createDefaultConfig()
 const occupants=(roomId:string)=>{
  const room=schedule.rooms.find(r=>r.roomId===roomId)!
  return room.slots.map(slot=>state.occupants[`${roomId}_${slot.slotIndex}`]??state.bedOccupants[`${roomId}_${slot.slotIndex}`]??'')
 }
 c.planName=schedule.sourceWorkspace.name
 c.efficiencyResources.droneCapacity=resolveDroneCapacity(schedule.sourceWorkspace)
 c.rooms=schedule.rooms.filter(r=>['manufacture','trading','power'].includes(r.type)).map(r=>{
  const room=createRoom(r.roomId,r.type as 'manufacture'|'trading'|'power')
  room.level=r.level as 1|2|3;room.operatorIds=occupants(r.roomId).filter(Boolean);room.operatorCount=room.operatorIds.length
  const product=parseProduct(actualProducts[r.roomId])??r.product
  if(['gold','exp','fragment'].includes(product??''))room.product=product as 'gold'|'exp'|'fragment'
  room.strategy=product==='orundum'?'orundum':'gold';room.specialOrder='none';room.powerStaffed=room.operatorCount>0
  return room
 })
 const dorms=schedule.rooms.filter(r=>r.type==='dormitory')
 c.facilities.dormitories=dorms.map(r=>r.level as 1|2|3|4|5)
 c.facilityOperatorIds.dormitories=dorms.map(r=>occupants(r.roomId).filter(Boolean))
 c.dormitoryOccupantCount=c.facilityOperatorIds.dormitories.reduce((n,ids)=>n+ids.length,0)
 c.controlOperatorIds=schedule.rooms.filter(r=>r.type==='central').flatMap(r=>occupants(r.roomId).filter(Boolean))
 c.facilities.central=(schedule.rooms.find(r=>r.type==='central')?.level??0) as 0|1|2|3|4|5
 const auxiliary={meeting:'reception',contact:'office',train:'training',factory:'workshop'} as const
 for(const [type,key] of Object.entries(auxiliary)) {
  const room=schedule.rooms.find(r=>r.type===type)
  c.facilityOperatorIds[key]=room?occupants(room.roomId).filter(Boolean):[]
  c.facilities[key]=(room?.level??0) as 0|1|2|3
 }
 const recycle=schedule.rooms.find(r=>r.type==='recycle')
 if(recycle){c.facilities.recycle=recycle.level as 1|2|3;c.facilityOperatorIds.recycle=occupants(recycle.roomId).filter(Boolean)}
 c.efficiencyResources.trainingOperatorIds=[...c.facilityOperatorIds.training]
 c.operatorMorale={...state.morale}
 // Dormitory skills continue during recovery, including the instant of entering at zero.
 const working=state.config.positions.filter(p=>!p.dormitory).map(p=>state.occupants[p.id]!)
 c.zeroMoraleOperatorIds=working.filter(id=>(state.morale[id]??24)<=0)
 c.workaholicOperatorIds=[...(schedule.policies.workaholic??[])]
 return c
}

/** Integrates rates over actual joint rosters. This reports efficiency and duty, not order/resource settlement. */
export function simulateSchedule(schedule:CompiledSchedule,options:ScheduleSimulationOptions={},onProgress?:(progress:ScheduleSimulationProgress)=>void):ScheduleSimulationReport {
 const schedulingModel=options.schedulingModel??'mower-default'
 if(!['mower-default','mower-alpha'].includes(schedulingModel))throw new Error('Invalid scheduling model')
 options={...options,schedulingModel,production:resolveInventoryProduction(schedule,options.production)}
 assertRunOrderMode(options.production?.runOrderMode)
 assertRunOrderMode(schedule.assumptions.runOrderSimulationMode)
 schedule=structuredClone(schedule)
 const capacityOverride=options.efficiencyResources?.droneCapacity
 if(capacityOverride!==undefined&&!isDroneCapacity(capacityOverride))throw new RangeError('无人机上限须为0或以上的安全整数')
 const droneCapacity=capacityOverride??resolveDroneCapacity(schedule.sourceWorkspace)
 schedule.sourceWorkspace.droneCapacity=droneCapacity
 options={...options,efficiencyResources:{...options.efficiencyResources,droneCapacity}}
 schedule.assumptions.runOrderSimulationMode='ideal'
 schedule.assumptions.idealRunOrderWakeOnly=!options.experimentalDisableIdealWake
 if(options.production){
  const target=options.production.droneTarget??'gold'
  schedule.assumptions.droneRoom=target==='none'?null:options.production.droneRoomId??(target==='trading'?options.production.droneTradingRoomId??schedule.rooms.find(room=>room.type==='trading')?.roomId:schedule.rooms.find(room=>room.type==='manufacture'&&room.product===target)?.roomId)??null
 }
 const sampleHours=options.sampleHours??336,warmupHours=options.warmupHours??0,maxStepHours=options.maxStepHours??.25,maxEvents=options.maxEvents??200000
 const values={sampleHours,warmupHours,maxStepHours,maxEvents}
 for(const key of numericKeys)if(!Number.isFinite(values[key]) || (key==='warmupHours'?values[key]<0:values[key]<=0))throw new Error(`Invalid ${key}`)
 if(!Number.isSafeInteger(maxEvents)||!Number.isFinite(sampleHours+warmupHours))throw new Error('Invalid simulation horizon/event limit')
 for(const [kind,table] of Object.entries({consumption:options.consumptionOverrides,recovery:options.recoveryOverrides,initialWorkHours:options.initialWorkHours,atmosphere:options.atmosphereByRoom}))for(const value of Object.values(table??{}))if(!Number.isFinite(value)||(kind!=='consumption'&&value<0))throw new Error(`Invalid ${kind} override`)
 const warmupModel=options.warmupModel??'continuous'
 if(!['continuous','hourly'].includes(warmupModel))throw new Error('Invalid warmup model')
 const report:ScheduleSimulationReport={schemaVersion:1,engine:'mower-morale-v1',success:false,elapsedHours:0,observedHours:0,
  assumptions:{moodControlStrategyVersion:MOWER_MOOD_CONTROL_VERSION,predictiveMoodControl:schedule.assumptions.predictiveMoodControl??false,schedulingModel,sampleHours,warmupHours,maxStepHours,warmupModel,restingThreshold:schedule.assumptions.restingThreshold??.65,operationDurationHours:0,dormAtmosphere:'各宿舍默认等级上限；可逐室覆盖',singleRecoveryTarget:'先检查单回资格；禁止自身和菲亚梅塔，单回技能持有者仅在唯一待恢复候选时合格；有效普通目标保持至失效，重选按最低心情和槽位顺序'},
  inputs:{schedule:structuredClone(schedule),options:structuredClone({...options,observeInterval:undefined})},operators:[],rooms:[],events:[],segments:[],diagnostics:[]}
 const diagnostic=(code:string,message:string)=>{if(!report.diagnostics.some(d=>d.code===code&&d.message===message))report.diagnostics.push({code,message})}
 if(options.production?.inventoryMode==='finite')diagnostic('FINITE_INVENTORY_MODEL','使用预设初始库存；从预热开始连续扣料、收取和交付，采样时不重置。无外源收入或自动补货；缺料停止相应生产或交付。回收站随机材料未计入物品库存。')
 for(const d of schedule.diagnostics)diagnostic(d.code,d.message)
 diagnostic('MOWER_SCHEDULING_MODEL',schedulingModel==='mower-default'?'使用 Mower 默认兼容换班策略；按六阶段评估副表，保留完整任务保护':'使用 Mower alpha 排班模型（80c97ee60 增量适配）：副表收敛、共享绑组与宿舍隔离')
 if(schedule.diagnostics.some(d=>d.severity==='error'||d.code==='UNKNOWN_OPERATOR'))return report
 const inventory=options.operatorInventory===undefined?undefined:compileOperatorInventory(options.operatorInventory)
 const operatorRecords=inventory?inventoryOperatorRecords(inventory):undefined
 if(inventory&&!inventory.valid){for(const issue of inventory.diagnostics)diagnostic('INVENTORY_INVALID',issue.message);return report}
 if(inventory){
  // Imported inventories may contain only idle cards; staffed rooms come from the schedule.
  const admission=validateScheduleInventory(schedule,inventory,options.efficiencyResources,'efficiency-resources')
  if(!admission.valid){for(const issue of admission.diagnostics)diagnostic(issue.code,issue.message);return report}
 }
 if(schedule.assumptions.elitePhase!==2){diagnostic('SKILL_STAGE_UNSUPPORTED','当前动态模拟使用已校对的最高基建技能；较低精英阶段尚未编译');return report}
 if(schedule.assumptions.operationDurationHours!==0){diagnostic('OPERATION_DURATION_UNSUPPORTED','当前模拟仅支持忽略换人操作耗时');return report}
 if(schedule.runOrderPolicies.length&&!options.production)diagnostic('ORDER_LIFECYCLE_NOT_SIMULATED','保留跑单配置；本报告统计日常班组效率，尚未模拟每单插入干员、收单与资源结算')
 diagnostic('TIME_INTEGRATION_MODEL',`使用${warmupModel==='hourly'?'整小时':'连续'}暖机，最大步长 ${maxStepHours} h；复制取整等非线性效率采用区间中点数值积分，可缩小步长检查敏感性`)
 diagnostic('SINGLE_RECOVERY_TARGET_ASSUMPTION','单回始终排除自身和菲亚梅塔；单回技能持有者仅在唯一待恢复候选时合格，不主动锁单回；后续入住可使其资格失效，确认或显式指定不能绕过资格。普通有效目标保持至回满、离宿或宿管变化，重选按最低心情，同心情按槽位顺序')
 let state:RuntimeState
 let backups:ReturnType<typeof createBackupPlanController> | undefined
 try{
  const runtimeConfig=compiledScheduleToRuntimeConfig(schedule)
  // Supported run orders are ideal production events and reserve no roster time.
  runtimeConfig.mowerTaskScheduling={...runtimeConfig.mowerTaskScheduling,adjustForRunOrders:false}
  runtimeConfig.mowerAlpha=schedulingModel==='mower-alpha'
  runtimeConfig.mowerSingleRecoverySkillNames=OPERATORS.filter(op=>hasSingleRecoverySkill(operatorFor({operatorRecords},op.charId))).map(op=>op.charId)
  normalizeMowerRecoveryBeds(runtimeConfig)
  // Mower scans unregistered global cards too. The imported library is the idle-card pool;
  // without it, every catalog operator is eligible, subject to native task/room exclusions.
  runtimeConfig.availableIdleOperators=inventory
   ? inventory.operators.map(op=>op.charId)
   : schedule.assumptions.idleOperators??OPERATORS.map(op=>op.charId)
  if(runtimeConfig.fiammetta&&!hasOperatorSkill({operatorRecords},runtimeConfig.fiammetta.operatorId,'dorm_exchangeAp[000]'))runtimeConfig.fiammetta=undefined
  state=createRosterRuntime(runtimeConfig)
  if(runtimeConfig.mowerDeviceTiming)diagnostic('MOWER_IO_CLOCK_MODEL','Mower 每房返回 0.5 秒及无临近任务时的通知检查 1 秒已纳入时间线；识别与其他点击耗时按 0 处理。已完成 run 后仍有同刻任务时，外层单调时钟推进 1 微秒；该适配步长不改任务时刻。')
  if(runtimeConfig.mowerAlpha)diagnostic('MOWER_CONTINUOUS_MOOD_MODEL','本地心情及读取值使用连续数值，未复现游戏心情条像素与识别误差。关闭菲亚梅塔防呆时，接近满心情的微小缺额可能产生密集充能；模拟保留该策略，不添加额外冷却。')
  backups=createBackupPlanController(schedule,state,{canUseFiammetta:id=>hasOperatorSkill({operatorRecords},id,'dorm_exchangeAp[000]')})
  for(const d of backups.diagnostics)diagnostic(d.code,d.message)
 }catch(error){diagnostic('INVALID_RUNTIME',String(error));return report}
 const total=warmupHours+sampleHours,initial=state.initialMorale??{...state.morale}
 const entered=new Map<string,{position:string;revision:number;time:number}>()
 let sessionsInitialized=false
 let hasActiveTemporalSkills=false,hasActiveContinuousWarmup=false
 const checkTemporalSkills=()=>{
  hasActiveTemporalSkills=[...entered.keys()].some(id=>getTemporalSkillBoundaries(id,{operatorRecords}).length>0)
  hasActiveContinuousWarmup=hasActiveTemporalSkills&&(warmupModel==='continuous'||[...entered].some(([id,session])=>qualitySkillWarmupHours(id,{operatorRecords})>state.time-session.time))
 }
 const refreshSessions=(newEvents:RuntimeEvent[]=[])=>{
  const reset=new Set(newEvents.filter(e=>e.type==='fiammetta').map(e=>e.operators[1]))
  const working=new Map(state.config.positions.filter(p=>!p.dormitory&&state.occupants[p.id]).map(p=>[state.occupants[p.id]!,p.id]))
  for(const id of entered.keys())if(!working.has(id))entered.delete(id)
  for(const [id,position] of working){
   const revision=state.workPositionChanges?.[id]??0,previous=entered.get(id)
   if(previous?.position!==position||previous.revision!==revision||reset.has(id))entered.set(id,{position,revision,time:state.time-(!sessionsInitialized&&!reset.has(id)?(options.initialWorkHours?.[id]??0):0)})
  }
  sessionsInitialized=true
  checkTemporalSkills()
 }
 refreshSessions()
 if([...entered.keys()].some(id=>qualitySkillWarmupHours(id,{operatorRecords})>0)||Object.keys(schedule.operators).some(id=>qualitySkillWarmupHours(id,{operatorRecords})>0))diagnostic('TRADE_QUALITY_WARMUP_MODEL','裁缝类订单概率采用线性近似：α／β分别在原工位连续工作 3／5 小时达到峰值；移动工位或离岗后重新计时。同类效果不叠加，取当前四赤金概率最高者；中间曲线和叠加机制未经实测核验。')
 const stats=new Map(Object.keys(state.morale).map(id=>[id,{operatorId:id,operatorName:OPERATOR_MAP.get(id)?.name??id,mainWorkHours:0,substituteWorkHours:0,workHours:0,exhaustedHours:0,restHours:0,idleHours:0,permanentPrimaryOccupancyHours:0,workFraction:0,workRestRatio:null,initialMorale:initial[id]!,finalMorale:initial[id]!} as SimulatedOperator]))
 const roomStats=new Map(projectScheduleState(schedule,state).rooms.map(r=>[r.id,{roomId:r.id,roomType:r.type,averageEfficiencyPercent:0,efficiencyPercentHours:0,occupiedHours:0,teams:[]} as SimulatedRoom]))
 if(schedule.rooms.some(r=>r.type==='recycle'))roomStats.set('recycle',{roomId:'recycle',roomType:'recycle',averageEfficiencyPercent:0,efficiencyPercentHours:0,occupiedHours:0,teams:[]})
  // Rate formulas depend on physical occupancy and discrete morale thresholds.
  // Keep the result across native I/O ticks while every input stays in the same band.
  let production:ReturnType<typeof createProductionTimeline>|undefined
  let actualProductSignature=''
  const currentProducts=()=>production?.actualProducts()??{}
  const refreshProductRevision=()=>{const signature=JSON.stringify(currentProducts());if(signature!==actualProductSignature){actualProductSignature=signature;rateRevision++;occupancyRevision++}}
  const automaticRecoveryTargets=new Map<string,{room:string;target:string;providerPosition:string;targetPosition:string}>()
  let cachedRecoveryOrderVersion=-1
  let rateRevision=0,cachedRevision=-1,occupancyRevision=0
  let cachedWork:Record<string,number>={},cachedRecovery:Record<string,number>={}
  const rateMoodBand=(value:number|undefined)=>{
   if(value===undefined)return -1
   let band=Number(value>0)|Number(value>=24-EPS)<<1|Number(value<=12)<<2|Number(value<=18)<<3|Number(value<=20)<<4
   for(const [index,threshold] of MORALE_SKILL_THRESHOLDS.entries())if(Math.abs(value-threshold)<EPS)band|=1<<(index+5)
   return band
  }
  const trackOccupancyMap=<T extends string|number>(map:Record<string,T>):Record<string,T>=>new Proxy(map,{
    set(target,key,value){if(target[String(key)]!==value){rateRevision++;occupancyRevision++}return Reflect.set(target,key,value)},
    deleteProperty(target,key){if(Object.prototype.hasOwnProperty.call(target,key)){rateRevision++;occupancyRevision++}return Reflect.deleteProperty(target,key)},
  })
  const trackRateMap=(map:Record<string,number>):Record<string,number>=>new Proxy(map,{
   set(target,key,value){if(rateMoodBand(target[String(key)])!==rateMoodBand(value))rateRevision++;return Reflect.set(target,key,value)},
   deleteProperty(target,key){if(Object.prototype.hasOwnProperty.call(target,key))rateRevision++;return Reflect.deleteProperty(target,key)},
  })
 state.morale=trackRateMap(state.morale);state.occupants=trackOccupancyMap(state.occupants);state.bedOccupants=trackOccupancyMap(state.bedOccupants)
 let trackedMorale=state.morale,trackedOccupants=state.occupants,trackedBeds=state.bedOccupants,trackedConfig=state.config
  const updateRates=()=>{
   const recoveryOrderVersion=state.mowerSource?.data.recoveryOrderVersion??0
    if(recoveryOrderVersion!==cachedRecoveryOrderVersion){cachedRecoveryOrderVersion=recoveryOrderVersion;rateRevision++}
    if(state.config!==trackedConfig){trackedConfig=state.config;rateRevision++;occupancyRevision++}
  // Runtime replaces the bed map atomically after group reservations/reordering.
  if(state.morale!==trackedMorale){state.morale=trackedMorale=trackRateMap(state.morale);rateRevision++}
  if(state.occupants!==trackedOccupants){state.occupants=trackedOccupants=trackOccupancyMap(state.occupants);rateRevision++;occupancyRevision++}
  if(state.bedOccupants!==trackedBeds){state.bedOccupants=trackedBeds=trackOccupancyMap(state.bedOccupants);rateRevision++;occupancyRevision++}
   refreshProductRevision()
   if(cachedRevision===rateRevision)return
   cachedRevision=rateRevision
  const c=projectScheduleState(schedule,state,currentProducts());c.operatorRecords=operatorRecords;Object.assign(c.efficiencyResources,options.efficiencyResources)
  const snapshot=currentMoraleRates(c)
  for(const message of snapshot.unquantified)diagnostic('UNQUANTIFIED_WORK_RATE',message)
   let work=snapshot.rates,atBoundary=false
   const restingIds=new Set([...Object.values(state.bedOccupants),...state.config.positions.filter(p=>p.dormitory).map(p=>state.occupants[p.id]!)])
  // Strict mood thresholds use the directional limit in an evaluation copy, never alter physical mood.
  for(const [id,m] of Object.entries(c.operatorMorale)){
   const direction=restingIds.has(id)?1:-Math.sign(options.consumptionOverrides?.[id]??work[id]??0)
     if(MORALE_SKILL_THRESHOLDS.some(x=>Math.abs(m-x)<EPS)){c.operatorMorale[id]=m+direction*EPS*2;atBoundary=true}
  }
  if(atBoundary)work=currentMoraleRates(c).rates
   cachedWork={...work,...options.consumptionOverrides};cachedRecovery={}
   const dorms=schedule.rooms.filter(r=>r.type==='dormitory'),morale=new Map(Object.entries(c.operatorMorale))
   const confirmedTargets=state.mowerSource?mowerConfirmedRecoveryTargets(state.mowerSource.data):undefined
   const presentProviders=new Set<string>()
   for(const [index,room] of dorms.entries()){
   const ids=c.facilityOperatorIds.dormitories[index]??[],targets=new Map<string,string>()
   const position=(id:string)=>{
    const op=state.mowerSource?.data.operators[id]
    return op?`${op.currentRoom}:${op.currentIndex}:${op.dormPositionVersion}`:`${room.roomId}:${ids.indexOf(id)}`
   }
   for(const id of ids){
    if(!hasSingleRecoverySkill(operatorFor(c,id)))continue
    presentProviders.add(id)
    const candidates=eligibleSingleRecoveryTargets(ids.flatMap(other=>{const op=operatorFor(c,other);return op?[op]:[]}),id,other=>morale.get(other)??24).map(op=>op.charId)
    const confirmed=confirmedTargets?.get(room.roomId)?.get(id)
    const requested=options.recoveryTargetByProvider?.[id]
    let target=requested&&candidates.includes(requested)?requested:confirmed&&candidates.includes(confirmed)?confirmed:undefined
    if(target)automaticRecoveryTargets.delete(id)
    else{
     const previous=automaticRecoveryTargets.get(id)
     target=retainedRecoveryTarget(candidates,previous,room.roomId,id,position,other=>morale.get(other)!)
     if(target!==previous?.target||previous?.providerPosition!==position(id)||previous?.targetPosition!==position(target??'')){
      // Stable sorting keeps slot order only when eligible residents have equal morale.
      if(target)automaticRecoveryTargets.set(id,{room:room.roomId,target,providerPosition:position(id),targetPosition:position(target)})
      else automaticRecoveryTargets.delete(id)
     }
    }
    if(target)targets.set(id,target)
   }
   const recovery=evaluateDormitoryRecovery(c,index,morale,options.atmosphereByRoom?.[room.roomId]??(!schedule.assumptions.defaultsApplied.includes('dormAtmosphere')?schedule.assumptions.dormAtmosphere:room.level*1000),targets)
   Object.assign(cachedRecovery,Object.fromEntries(recovery.rates))
   for(const message of recovery.unquantified)diagnostic('UNQUANTIFIED_RECOVERY',`${room.roomId}: ${message}`)
  }
  for(const provider of automaticRecoveryTargets.keys())if(!presentProviders.has(provider))automaticRecoveryTargets.delete(provider)
  Object.assign(cachedRecovery,options.recoveryOverrides)
  for(const p of state.config.positions.filter(p=>!p.dormitory)){
   const id=state.occupants[p.id]
   if(!id)continue
   if(cachedWork[id]===undefined){
    cachedWork[id]=0
    const room=schedule.rooms.find(r=>r.roomId===p.roomId)
    if(room?.type==='factory'||room?.type==='train')diagnostic('PASSIVE_AUXILIARY_OCCUPANCY',`${p.roomId} / ${OPERATOR_MAP.get(id)?.name??id}：本次只模拟闲置进驻，不执行加工或训练任务，心情消耗 0/h`)
    else if((state.morale[id]??24)>0)diagnostic('UNQUANTIFIED_WORK_RATE',`${p.roomId} / ${OPERATOR_MAP.get(id)?.name??id}：尚未建模该设施的任务心情消耗；当前按未执行任务的 0/h`)
   }
  }
 }
  const rates:RuntimeRates={workRate:id=>{updateRates();return cachedWork[id]??0},recoveryRate:id=>{updateRates();return cachedRecovery[id]??0},snapshotRates:()=>{updateRates();return {work:cachedWork,recovery:cachedRecovery}},thresholds:()=>[...MORALE_SKILL_THRESHOLDS]}
  rates.forecastRates=projected=>{
   const config=projectScheduleState(schedule,projected,currentProducts())
   config.operatorRecords=operatorRecords;Object.assign(config.efficiencyResources,options.efficiencyResources)
   const atmospheres=schedule.rooms.filter(room=>room.type==='dormitory').map(room=>options.atmosphereByRoom?.[room.roomId]??(!schedule.assumptions.defaultsApplied.includes('dormAtmosphere')?schedule.assumptions.dormAtmosphere:room.level*1000))
   const forecast=mowerCoordinationRates(config,atmospheres,{work:options.consumptionOverrides,recovery:options.recoveryOverrides})
   for(const position of projected.config.positions)if(!position.dormitory){
    const id=projected.occupants[position.id]
    if(id&&forecast.work[id]===undefined&&(['factory','train'].includes(position.roomId)||projected.morale[id]===0))forecast.work[id]=0
   }
   return forecast
  }
  let derivativeRevision=-1,derivatives:Record<string,number>={}
  const derivativeRates=()=>{
   updateRates()
   if(derivativeRevision!==rateRevision){derivatives=currentMoraleDerivatives(state,rates);derivativeRevision=rateRevision}
   return derivatives
  }
 const blockedMessages=new Map<string,{code:string;message:string}>()
 const deferrals:NonNullable<ScheduleSimulationReport['shiftDeferrals']>=[]
 const pendingDeferrals=new Map<string,typeof deferrals[number]>()
 const blockedMembers=new Map<string,string[]>()
 const refreshGroups=()=>{blockedMembers.clear(); for(const p of state.config.positions.filter(p=>!p.dormitory&&!p.permanent)){
  const key=p.group?`group:${p.group}`:`slot:${p.id}`
  blockedMembers.set(key,[...(blockedMembers.get(key)??[]),p.primary])
 }
 }
 refreshGroups()
 let appliedBackupSchedule=backups!.schedule
 const synchronizeBackupSchedule=()=>{
  if(backups!.schedule===appliedBackupSchedule)return
  appliedBackupSchedule=backups!.schedule
  Object.assign(schedule,appliedBackupSchedule)
  cachedRevision=-1;derivativeRevision=-1;occupancyRevision++;refreshGroups()
 }
 let backupFailed=false
 const settleUnsafe=()=>{
  // Capture each planning pass: a deduplicated message alone cannot prove
  // whether an already recovered group blocked again later.
  state.diagnostics=state.diagnostics.filter(d=>d.code!=='group-blocked')
  const count=state.events.length
  const phase=(timing:Parameters<NonNullable<typeof backups>['evaluate']>[0])=>{
   const previousConfig=state.config,changed=backups?.evaluate(timing)??false
   if(changed||state.config!==previousConfig)synchronizeBackupSchedule()
   return changed
  }
  if(!state.config.mowerSourcePlan)phase('BEGINNING')
  settleRoster(state,rates,0,phase)
  // Complete alpha shift previews activate their effective plan inside the
  // source runtime, before the next phase callback can observe a config change.
  synchronizeBackupSchedule()
  let passes=0
  while(!state.config.mowerSourcePlan&&phase('END')){
   if(++passes>64)throw new Error('副表同刻任务链循环')
   settleRoster(state,rates,0,phase)
  }
  const events=state.events.slice(count)
  for(const [key,episode] of pendingDeferrals)if(events.some(e=>e.type==='shift-off'&&e.time>episode.blockedAt+EPS&&e.operators.length===episode.operatorIds.length&&episode.operatorIds.every(id=>e.operators.includes(id)))){
   episode.resolvedAt=state.time;pendingDeferrals.delete(key)
  }
  for(const d of state.diagnostics.filter(d=>d.code==='group-blocked')){
   blockedMessages.set(d.message,d)
   const key=[...blockedMembers.keys()].find(k=>d.message===`${k}: insufficient available candidates or beds; original occupants retained`)
   if(key&&!pendingDeferrals.has(key)){
    const episode={key,operatorIds:[...blockedMembers.get(key)!],blockedAt:state.time}
    deferrals.push(episode);pendingDeferrals.set(key,episode)
   }
  }
  // Occupancy, config, recovery order and morale bands already invalidate the
  // physical rates above. An I/O return by itself changes none of those inputs.
  refreshSessions(events)
 }
 const settle=()=>{
  if(backupFailed)return
  try{settleUnsafe()}catch(error){backupFailed=true;diagnostic('BACKUP_EXECUTION_FAILED',error instanceof Error?error.message:String(error))}
 }
 let cachedBaseConfig: ReturnType<typeof projectScheduleState> | undefined, cachedBaseConfigRevision = -1
 const getBaseConfig = () => {
  refreshProductRevision()
  if (!cachedBaseConfig || cachedBaseConfigRevision !== occupancyRevision) {
   cachedBaseConfig = projectScheduleState(schedule, state, currentProducts()); cachedBaseConfig.operatorRecords = operatorRecords; cachedBaseConfig.jayeElite0 = options.jayeElite0; Object.assign(cachedBaseConfig.efficiencyResources, options.efficiencyResources)
   cachedBaseConfigRevision = occupancyRevision
  }
  return cachedBaseConfig
 }
 let cachedEvalVersion=-1,cachedZeroMorale='',cachedMoodEfficiency='',cachedTemporalPhase=''
 let cachedEvaluations:ProductionFrame['evaluations']|undefined
 const frameAt=(offset:number):ProductionFrame=>{
  const base=getBaseConfig()
  const c={...base,operatorMorale:{...state.morale}}
  if(offset!==0){const derivative=derivativeRates();for(const id of Object.keys(c.operatorMorale))c.operatorMorale[id]=Math.max(0,Math.min(24,c.operatorMorale[id]!+(derivative[id]??0)*offset))}
  c.zeroMoraleOperatorIds=state.config.positions.filter(p=>!p.dormitory&&(c.operatorMorale[state.occupants[p.id]!]??0)<=0).map(p=>state.occupants[p.id]!)
  const zeroMoraleKey=c.zeroMoraleOperatorIds.join(',')
  // These are the mood-dependent production rules; zero-morale activity has its own key.
  // A global resource boundary must invalidate every room, including rooms without warmup.
  const totterMood=c.operatorMorale.char_4062_totter??24
  const moodEfficiencyKey=[Number((c.operatorMorale.char_2023_ling??24)>12),Number((c.operatorMorale.char_2015_dusk??24)>12),Math.floor(Math.max(0,24-totterMood)/4),Number(totterMood<12)].join(',')
  // Hourly curves advance by each operator's current session, including fractional entry/Fia times.
  const temporalPhaseKey=[...entered].filter(([id])=>getTemporalSkillBoundaries(id,{operatorRecords}).length>0).map(([id,session])=>id+':'+Math.floor(Math.max(0,state.time+offset-session.time))).join(',')
  const morale=new Map(Object.entries(c.operatorMorale)),active=new Set(Object.keys(state.morale).filter(id=>!c.zeroMoraleOperatorIds.includes(id)))
  let evaluations=cachedEvaluations
  const fullEvaluationChanged=!evaluations||occupancyRevision!==cachedEvalVersion||zeroMoraleKey!==cachedZeroMorale||moodEfficiencyKey!==cachedMoodEfficiency
  if(fullEvaluationChanged||(hasActiveTemporalSkills&&(hasActiveContinuousWarmup||temporalPhaseKey!==cachedTemporalPhase))){
   const context=buildRiicGlobalContext(c,active,morale),workHoursByOperator=new Map([...entered].map(([id,s])=>[id,Math.max(0,state.time+offset-s.time)]))
   if(fullEvaluationChanged){
    evaluations={}
    for(const room of c.rooms){const result=evaluateOperators(room,c,active,morale,context,{workHoursByOperator,warmupModel});evaluations[room.id]=result;for(const text of result.unquantifiedSkills)diagnostic('UNQUANTIFIED_EFFICIENCY',`${room.id}: ${text}`)}
   }else{
    evaluations={...evaluations}
    for(const room of c.rooms){if(room.operatorIds.some(id=>getTemporalSkillBoundaries(id,{operatorRecords}).length>0)){evaluations[room.id]=evaluateOperators(room,c,active,morale,context,{workHoursByOperator,warmupModel})}}
   }
   cachedEvalVersion=occupancyRevision;cachedZeroMorale=zeroMoraleKey;cachedMoodEfficiency=moodEfficiencyKey;cachedTemporalPhase=temporalPhaseKey;cachedEvaluations=evaluations
  }
  return {time:state.time+offset,config:c,active,morale,evaluations:evaluations!,desiredProducts:Object.fromEntries(schedule.rooms.filter(r=>r.type==='manufacture'||r.type==='trading').map(r=>{const raw=schedule.sourceWorkspace.compatibility.facilityMetadata?.[r.roomId]?.rawProduct;return [r.roomId,typeof raw==='string'&&parseProduct(raw)===r.product?raw:serializeProduct(r.type,r.product)!]}))}
 }
 const efficiencies=(frame:ProductionFrame):Record<string,number>=>({
  ...Object.fromEntries(Object.entries(frame.evaluations).map(([id,r])=>[id,r.efficiencyPercent])),
  ...(frame.config.facilities.recycle?{recycle:evaluateRecycleEfficiency(frame.config,{activeIds:frame.active}).efficiencyPercent}:{}),
 })
 production=options.production?createProductionTimeline(schedule,state,options.production,warmupHours,diagnostic,!!state.config.mowerSourcePlan):undefined
 // Real facilities exist before native scheduling first reads a countdown.
 production?.settle(()=>frameAt(0))
 if(production&&state.config.mowerSourcePlan){
  Object.assign(rates,createMowerClueIO(state))
  diagnostic('MOWER_CLUE_OBSERVATION_MODEL','线索交流固定关闭，Party Time 为空，不执行线索待办及交流任务。')
  Object.assign(rates,createMowerProductionIO(state,production,()=>frameAt(0)))
  diagnostic('MOWER_ORDER_OBSERVATION_MODEL','理想跑单在新单开始时锁定佩佩/可露希尔模式，在普通订单完成时转换但书/龙舌兰收益；保留 Mower 订单读取、任务排序与唤醒，不执行临时换人；常规换班、收取及无人机任务仍按 Mower 时间线执行。')
 }
 let steps=0,lastProgress=-1,lastPhase=''
 const activityMonitor=onProgress?createSimulationActivityMonitor():undefined
 // Production-only subdivisions preserve the independent morale clock. Inventory/product
 // conditions can change staffing at those boundaries and must recompute from live morale.
 const independentMoraleClock=!!production&&!state.mowerBackupObservationWakeMicros&&(options.production?.runOrderMode??'ideal')==='ideal'
 let moraleStep:{end:number;morale:Record<string,number>;actionAt:number}|undefined
 const reportProgress=()=>{
  if(!onProgress)return
  const percent=Math.floor(state.time/total*100),phase=state.time<warmupHours-EPS?'warmup':'sampling'
  const activity=activityMonitor?.capture(state,steps)
  if(percent!==lastProgress||phase!==lastPhase||activity){
   lastProgress=percent;lastPhase=phase
   onProgress({phase,elapsedHours:state.time,totalHours:total,warmupHours,activity:activity??activityMonitor?.latest})
  }
 }
 reportProgress()
 settle()
 if(backupFailed)return report
 production?.settle(()=>frameAt(0))
 let statsOccRevision=-1
 const cachedOccupantToPos=new Map<string,typeof state.config.positions[0]>()
 const cachedRestingSet=new Set<string>()
 const cachedRoomTeams=new Map<string,{team:SimulatedRoom['teams'][0];hasOccupants:boolean}>()
 const updateStatsIndex=()=>{
  if(statsOccRevision===occupancyRevision)return
  statsOccRevision=occupancyRevision
  cachedOccupantToPos.clear();for(const p of state.config.positions){const occ=state.occupants[p.id];if(occ)cachedOccupantToPos.set(occ,p)}
  cachedRestingSet.clear();for(const b of Object.values(state.bedOccupants))cachedRestingSet.add(b)
  for(const p of state.config.positions)if(p.dormitory){const occ=state.occupants[p.id];if(occ)cachedRestingSet.add(occ)}
  cachedRoomTeams.clear()
  for(const [id,r] of roomStats){
   const ids:string[]=[]
   for(const p of state.config.positions)if(p.roomId===id){const occ=state.occupants[p.id];if(occ)ids.push(occ)}
   ids.sort()
   const hasOccupants=ids.length>0,idKey=ids.join(',')
   let team=r.teams.find(t=>t.operatorIds.join(',')===idKey)
   if(!team){team={operatorIds:ids,hours:0,fraction:0};r.teams.push(team)}
   cachedRoomTeams.set(id,{team,hasOccupants})
  }
 }
 while(state.time<total&&!backupFailed){
  reportProgress()
  if(steps++>=maxEvents){diagnostic('SIMULATION_EVENT_LIMIT',`达到 ${maxEvents} 个积分区间，结果未完成`);break}
  let action=moraleStep?moraleStep.actionAt-state.time:nextRosterActionHours(state,rates)
  if(action<=(state.config.mowerSourcePlan?0:EPS)){settle();production?.settle(()=>frameAt(0));action=nextRosterActionHours(state,rates);if(action<=(state.config.mowerSourcePlan?0:EPS)){diagnostic('SIMULATION_SAME_TIME_ACTION','同刻调度未能稳定，结果未完成');break}}
  let dt=moraleStep?moraleStep.end-state.time:Math.min(maxStepHours,total-state.time,nextRosterEventHours(state,rates,true,derivativeRates()),state.time<warmupHours-EPS?warmupHours-state.time:Infinity)
  if(!moraleStep)for(const [id,s] of entered)for(const boundary of getTemporalSkillBoundaries(id,{operatorRecords})){const delay=boundary+s.time-state.time;if(delay>EPS)dt=Math.min(dt,delay)}
  if(independentMoraleClock&&!moraleStep){
   const derivative=derivativeRates()
   const morale=Object.fromEntries(Object.entries(state.morale).map(([id,m])=>{
    const value=Math.max(0,Math.min(24,m+(derivative[id]??0)*dt))
    return [id,value<=EPS?0:value>=24-EPS?24:value]
   }))
   moraleStep={end:state.time+dt,morale,actionAt:state.time+action}
  }
  checkTemporalSkills()
  const frames=new Map<number,ProductionFrame>()
  let zeroFrame:ProductionFrame|undefined
  const frame=(offset:number)=>{
   if(offset===0&&zeroFrame)return zeroFrame
   let value=frames.get(offset)
   if(!value){
    if(zeroFrame&&!hasActiveContinuousWarmup){
     value={time:state.time+offset,config:zeroFrame.config,active:zeroFrame.active,morale:zeroFrame.morale,evaluations:zeroFrame.evaluations}
    }else{
     value=frameAt(offset)
    }
    frames.set(offset,value)
    if(offset===0)zeroFrame=value
   }
   return value
  }
  if(production)dt=production.nextStep(dt,frame)
  if(!Number.isFinite(dt)||dt<=0||state.time+dt===state.time){diagnostic('SIMULATION_STALLED','无法确定下一个正长度区间');break}
  const observed=state.time>=warmupHours-EPS
  if(observed){
   for(const id of Object.keys(state.morale))if(!stats.has(id)){
    const initialMorale=initial[id]??state.config.initialMorale?.[id]??schedule.assumptions.initialMorale
    stats.set(id,{operatorId:id,operatorName:OPERATOR_MAP.get(id)?.name??id,mainWorkHours:0,substituteWorkHours:0,workHours:0,exhaustedHours:0,restHours:0,idleHours:report.observedHours,permanentPrimaryOccupancyHours:0,workFraction:0,workRestRatio:null,initialMorale,finalMorale:state.morale[id]!})
   }
   const eff=efficiencies(frame(dt/2))
   updateStatsIndex()
   for(const [id,s] of stats){
    const p=cachedOccupantToPos.get(id),resting=cachedRestingSet.has(id)
    if(!resting&&p?.permanent&&p.primary===id)s.permanentPrimaryOccupancyHours!+=dt
    if(resting)s.restHours+=dt
    else if(p){if((state.morale[id]??0)<=0&&moraleDerivative(state,id,rates)<=0)s.exhaustedHours+=dt;else{s.workHours+=dt;if(p.primary===id)s.mainWorkHours+=dt;else s.substituteWorkHours+=dt}}
    else s.idleHours+=dt
   }
   for(const [id,r] of roomStats){
    r.efficiencyPercentHours+=(eff[id]??0)*dt
    const cached=cachedRoomTeams.get(id)
    if(cached){if(cached.hasOccupants)r.occupiedHours+=dt;cached.team.hours+=dt}
   }
   report.observedHours+=dt
   if(options.recordSegments)report.segments.push({start:state.time,end:state.time+dt,occupants:{...state.occupants},bedOccupants:{...state.bedOccupants},morale:{...state.morale},efficiencyPercent:eff})
  }
  options.observeInterval?.(frame(dt/2).config,state.time,state.time+dt,new Map([...entered].map(([id,session])=>[id,Math.max(0,state.time-session.time)])))
  production?.advance(dt,frame(dt/2))
  advanceRoster(state,dt,rates,derivativeRates())
  if(moraleStep&&Math.abs(state.time-moraleStep.end)<=EPS){
   state.time=moraleStep.end
   Object.assign(state.morale,moraleStep.morale)
   moraleStep=undefined
  }
  production?.settle(()=>frameAt(0))
  if(state.config.mowerSourcePlan?nextRosterActionHours(state,rates)===0:Math.abs(dt-action)<=EPS){settle();production?.settle(()=>frameAt(0))}
 }
 const unresolvedFailures=state.mowerSource?.queue.tasks.filter(task=>task.executionFailure&&!task.coordinationDependencyWait)??[]
 for(const task of unresolvedFailures)diagnostic('MOWER_PENDING_TASK_FAILURE',`统计结束仍有未恢复的${task.type.displayValue}任务（${Object.keys(task.plan).join('、')}）：${task.executionFailure!.reason}；保留原任务和时间，本次收益演算未完整完成`)
 report.elapsedHours=state.time;report.success=!backupFailed&&!unresolvedFailures.length&&Math.abs(state.time-total)<EPS
 report.operators=[...stats.values()].map(s=>({...s,initialMorale:initial[s.operatorId]??s.initialMorale,finalMorale:state.morale[s.operatorId]!,workFraction:report.observedHours?s.workHours/report.observedHours:0,workRestRatio:s.restHours>EPS?s.workHours/s.restHours:null}))
 report.rooms=[...roomStats.values()].map(r=>({...r,averageEfficiencyPercent:report.observedHours?r.efficiencyPercentHours/report.observedHours:0,teams:r.teams.map(t=>({...t,fraction:report.observedHours?t.hours/report.observedHours:0}))}))
 if(production){report.production=production.report();report.production.success&&=report.success}
 report.events=state.events.filter(e=>e.time>=warmupHours-EPS)
 report.shiftDeferrals=deferrals
 for(const d of state.diagnostics.filter(d=>d.code!=='group-blocked'))diagnostic(d.code,d.message)
 for(const d of blockedMessages.values()){
  const key=[...blockedMembers.keys()].find(k=>d.message===`${k}: insufficient available candidates or beds; original occupants retained`)
  const episodes=deferrals.filter(e=>e.key===key)
  if(report.success&&episodes.length&&episodes.every(e=>e.resolvedAt!==undefined))diagnostic('SHIFT_DEFERRED_RECOVERED',`${d.message}; ${episodes.length} 次延后均已由后续完整分组下班事件确认恢复`)
  else diagnostic(d.code,d.message)
 }
 reportProgress()
 return report
}
