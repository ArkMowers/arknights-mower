import {MowerBackupRecoveryBlocked} from './mowerBackupDepartureRecovery'
import {parkMowerBackupDepartureRecovery,parkMowerPreviewRecovery,resumeMowerPreviewRecovery,nextMowerPreviewRecoveryObservation,type MowerPreviewRecoveryWait} from './mowerPreviewRecoveryWait'
import {mowerVerifiedRecoveryDependencyReturn} from './mowerRecoveryDependency'
import {mowerOrdinaryCoordinationNeeded,mowerPendingExhaust} from './mowerExhaustPolicy'
import {hasSingleRecoverySkill} from '../engine/singleRecoveryEligibility'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import {mowerArrangementGroupTransitions,normalizeMowerSharedArrangement,commitMowerGroupShifts} from './mowerSharedGroups'
import {mergeMowerBackupRefreshRule} from './mowerBackupRefresh'
import {executeMowerReload} from './mowerReload'
import {MowerExitError,MowerRecognizeError,MowerShiftPreviewError,MowerRoomArrangementDeferred,rethrowMowerInfraFatal} from './mowerNativeErrors'
import {executeMowerTodoTask,type MowerTodoTaskState} from './mowerTodoTask'
import {executeMowerClueNew,runMowerClueFlow,setMowerPartyTime,type MowerClueLifecycleState} from './mowerClueLifecycle'
import {collectMowerInfraNotification,collectMowerTodoList} from './mowerNotification'
import {bridgeMowerNativeIO,type MowerNativeIOYield} from './mowerRunOrderBridge'
import {runDefaultTradeSegment,dispatchDefaultRefreshTime,type RunOrderPlanningState,type RunOrderPlanningSeam} from './mowerRunOrderPlanning'
// Headless adapter for pinned default Mower task decisions.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
// Physical room reads come from the RIIC simulation; reservations and observations stay separate.
// Trade runner recognition extends the pinned source list with U-Official for this app.
import {mowerPlanEntries} from './mowerPlanOrder'
import {initializeMowerAlphaMoodLimits} from './mowerMoodLimits'
import {scheduleMowerTasks,protectMowerSupportSwaps} from './mowerTaskScheduling'
import {deferMowerAlphaDorm} from './mowerAlphaTaskProtection'
import {mowerAlphaDormCandidates,planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {fillMowerAlphaEmptyDorms} from './mowerAlphaDormPlanning'
import {deferMowerArrangementRetry} from './mowerArrangementRetry'
import {mowerRefreshTradingSpec,refreshMowerRunOrderTime} from './mowerRunOrderRefresh'
import {MowerArrangementError} from './mowerArrangementError'
import {OPERATOR_MAP} from '../domain/operators'
import {isTradeRunOrderOperator} from '../domain/shiftRunPolicy'
import type {BackupTiming} from './backupPlans'
import type {RuntimeState,RuntimeRates,RuntimeConfig} from './rosterRuntime'
import {nextRosterEventHours} from './rosterRuntime'
import {hasObservedFullMood,MowerOperatorState,type MowerGroupBinding} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,fromMowerMicros,isMowerRunOrderTask,type MowerTaskPlan} from './mowerTaskQueue'
import {executeMowerTaskArrangementSteps,type MowerRoomReturn,type MowerBackupResult} from './mowerTaskExecutor'
import {projectMowerArrangements,invalidateMowerDormTime,mowerUpdateDetail,mowerRefreshDormTime,mowerCorrectDorm,mowerRoomReadIndexes,shouldMowerReadMood,mowerHasMeasuredDormDeparture} from './mowerObservations'
import {mowerIsDormReplacement,planMowerCorrection} from './mowerCorrection'
import {planMowerOrdinary,mowerGetRestingPlan,mowerTryReorder,mowerPlanningHasNearTask} from './mowerOrdinaryPlanning'
import {planMowerMetadata,mowerRestUnitKey} from './mowerMetadata'
import {mowerReplacementDependencyNames,mowerReplacementReservations,planMowerPreferredReplacementRestore,mowerCoordinationRequestFulfilled} from './mowerReplacementCoordination'
import {reconcileMowerUrgentRecovery,mowerUrgentPendingSupporters,recordMowerUrgentSupport,recordMowerUrgentRecovery,inheritMowerUrgentRecovery} from './mowerUrgentRecovery'
import {validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'
import {planMowerExhaustSupport} from './mowerExhaustPlanning'
import {selectMowerFiaTarget,mowerFiaReadyMicros} from './mowerFiammetta'
import {prepareMowerDormSelection,mowerArrangementReadIndexes} from './mowerSelection'
import {cloneMowerShiftTask,prepareMowerShiftCycle,recordMowerDormAdmissions,type MowerShiftModel} from './mowerShiftCycle'
import {prepareMowerRunEntry,nextMowerRunRecoveryMicros} from './mowerRunLifecycle'
import {ensureMowerDormRecovery} from './mowerDormRecovery'
import {normalizeMowerRecoveryBeds} from './mowerRecoveryBeds'
import {mowerGroupRecoveryDeadline,mowerGroupRecoveryWorkers,mowerRecoveryMoodComplete,mowerObservedRecoveryDeadline,mowerRecoveryReady,mowerUnfinishedReturnMembers,splitMowerRecoveryTask} from './mowerGroupRecovery'
import {mowerMandatoryReleaseNames,prepareMowerRelease} from './mowerRelease'
import {nextMowerMoodPlanningWake,type MowerPlanningWake} from './mowerPlanningWake'
import {mowerProtectedShift,prepareMowerShiftBeds} from './mowerShiftProtection'
export interface MowerBackupContext {appendEmptyTask:boolean;restoreOnDeactivate:boolean;customTimeMicros?:number}
export interface MowerSourceRuntime {
 waitingRecovery?:MowerPreviewRecoveryWait[]
 data:MowerSchedulingData;queue:MowerTaskQueue;config:RuntimeConfig;initial:boolean;firstInit:boolean;error?:boolean
 activeTask?:MowerTask;lastTodoMicros?:number|null;lastClueMicros?:number|null;partyTimeMicros?:number|null;droneTimeMicros?:number|null;reloadTimeMicros?:number|null;baseRunAborted?:boolean
 runFlags?:{planned:boolean;todoTask:boolean;collectNotification:boolean}
 execution?:{task:MowerTask;steps:Generator<MowerRoomReturn,boolean,void>;wakeMicros:number;intent:MowerTaskPlan;data:MowerSchedulingData;lastBoundary?:MowerRoomReturn;positions?:Record<string,[string,number]>}
 phaseExecution?:{steps:Generator<MowerRoomReturn,void,void>;wakeMicros:number;skipPlanning:boolean;previewNoop?:boolean}
 runReturn?:{wakeMicros:number;finishFallback:boolean}
 conditionWakeMicros?:number
 planningWake?:MowerPlanningWake;planningMoodRefreshNames?:string[]
 lastTrainMoodReadMicros?:number;lastWakeMicros?:number;trace:{timeMicros:number;type:string;plan:MowerTaskPlan;metadata:string}[]
}
const slotIndex=(id:string)=>Number(id.slice(id.lastIndexOf('_')+1))
const isConfiguredTradeRoom=(config:RuntimeConfig,room:string)=>config.runOrderPolicies?.some(policy=>policy.roomId===room)??false
export function makeMowerSchedulingData(s:RuntimeState,previous?:{data:MowerSchedulingData}):MowerSchedulingData {
 const config=s.config,source=Object.fromEntries(mowerPlanEntries(config.mowerSourcePlan!)),rules=config.mowerSourceRules!,operators:Record<string,MowerOperatorState>={}
 const primary=new Set(Object.values(source).flatMap(slots=>slots.map(p=>p.agent)).filter(n=>!['Free','Current',''].includes(n)))
 const create=(name:string,room='',index=-1,group='',replacement:string[]=[],groupBindings:MowerGroupBinding[]=[])=>{
  if(['Free','Current',''].includes(name)||operators[name])return
  s.morale[name]??=config.initialMorale?.[name]??24
  ;(s.initialMorale??={})[name]??=s.morale[name]
  const old=previous?.data.operators[name],position=config.positions.find(p=>p.primary===name)
  const op=new MowerOperatorState({name,nativeName:OPERATOR_MAP.get(name)?.name??name,room,index,group,replacement,groupBindings,operatorType:primary.has(name)&&!!room?'high':'low',restingPriority:rules.lowPriority.includes(name)||!room?'low':'high',workaholic:rules.workaholic.includes(name),exhaustRequire:rules.exhaustRequire.includes(name),restInFull:rules.restInFull.includes(name),lowerLimit:position?.lowerLimit??0,upperLimit:position?.upperLimit??config.mowerPolicy?.restMoodLimits?.[name]??24,restMoodLimit:!!config.mowerPolicy?.restMoodLimits?.[name],mood:old?.mood??24,timeStampMicros:old?.timeStampMicros,depletionRate:old?.depletionRate,currentRoom:old?.currentRoom??'',currentIndex:old?.currentIndex??-1,dormPositionVersion:old?.dormPositionVersion,dormRecoveryRoom:old?.dormRecoveryRoom,dormRecoveryIndex:old?.dormRecoveryIndex,dormRecoveryFixed:old?.dormRecoveryFixed,restingFromTrain:old?.restingFromTrain,idleRestCheck:old?.idleRestCheck})
  op.refreshOrderRooms=mowerRefreshTradingSpec(op.nativeName,(rules.refreshTrading??[]).map(entry=>OPERATOR_MAP.get(entry)?.name??entry))
  op.workshop=['年','司霆惊蛰','九色鹿'].includes(op.nativeName)
  if(old){op.temporaryDormFill=old.temporaryDormFill;op.dormMoodFallback=old.dormMoodFallback;op.dormMoodPeers={...old.dormMoodPeers};op.restMoodReleaseLimit=old.restMoodReleaseLimit;op.moodIsPrediction=old.moodIsPrediction;op.standbyLowPriority=old.standbyLowPriority}
  // operators.py:add applies standby only after group and mandatory-rest flags.
  if(rules.standby?.includes(name)&&op.isHigh()&&(config.mowerAlpha||op.group)&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.exhaustRequire&&!op.restInFull&&(config.mowerAlpha||!op.workshop))op.restingPriority='standby'
  operators[name]=op
 }
 for(const [room,slots] of Object.entries(source))slots.forEach((p,index)=>create(p.agent,room,index,p.group,[...p.replacement],p.groupBindings))
 for(const slots of Object.values(source))for(const p of slots)if(OPERATOR_MAP.get(p.agent)?.name!=='菲亚梅塔')[...p.replacement,...(p.groupBindings??[]).flatMap(binding=>binding.replacement)].forEach(name=>create(name))
 config.idleOperators?.forEach(name=>create(name))
 if(previous)Object.keys(previous.data.operators).forEach(name=>create(name))
 const singleRecoveryNames=config.mowerSingleRecoverySkillNames===undefined?undefined:new Set(config.mowerSingleRecoverySkillNames)
 for(const op of Object.values(operators))op.singleRecoveryManager=singleRecoveryNames?.has(op.name)??hasSingleRecoverySkill(OPERATOR_MAP.get(op.name))
 const runOrderRooms=config.mowerRunOrderEnabled===false?{}:{...previous?.data.runOrderRooms}
 if(config.mowerRunOrderEnabled!==false)for(const [room,slots] of Object.entries(source))if(room.startsWith('room')&&slots.some(slot=>slot.replacement.some(id=>isTradeRunOrderOperator(id)&&((OPERATOR_MAP.get(id)?.name??id)!=='U-Official'||isConfiguredTradeRoom(config,room)))))runOrderRooms[room]={}
 const oldBeds=new Map(previous?.data.dorms.map(b=>[b.position[0]+'_'+b.position[1],b]))
 normalizeMowerRecoveryBeds(config)
 const configuredBeds=[...config.beds]
 const roomOrder=(config.mowerDormOrder??['dormitory_1','dormitory_2','dormitory_3','dormitory_4']).filter(option=>!option.endsWith('_low'))
 const dorms=config.mowerAlpha?configuredBeds.filter(b=>b.managedRecovery!==false).sort((a,b)=>roomOrder.indexOf(a.roomId)-roomOrder.indexOf(b.roomId)||slotIndex(a.id)-slotIndex(b.id)).map(b=>{const old=oldBeds.get(b.id);return new MowerDormState([b.roomId,slotIndex(b.id)],old?.name??'',old?.timeMicros,[source[b.roomId]?.[slotIndex(b.id)]?.replacement??[],...(source[b.roomId]?.[slotIndex(b.id)]?.groupBindings??[]).map(binding=>binding.replacement)].some(replacements=>replacements.includes('Free')))}):previous?.data.dorms??config.beds.filter(b=>b.managedRecovery!==false).sort((a,b)=>Number(b.vip)-Number(a.vip)).map(b=>new MowerDormState([b.roomId,slotIndex(b.id)]))
 const data=new MowerSchedulingData({backupExplicitTasks:s.mowerShiftModel?.explicitTasks??previous?.data.backupExplicitTasks,dormIsolation:config.mowerDormIsolation,alpha:config.mowerAlpha,priorityReplacement:rules.priorityReplacement,freeRoomExclusions:rules.freeRoomExclusions,standbyNames:rules.standby,dormOrder:config.mowerDormOrder,plan:Object.fromEntries(Object.entries(source).map(([room,slots])=>[room,slots.map(p=>p.agent)])),operators,dorms,runOrderRooms,nowMicros:toMowerMicros(s.time),policy:{restingThreshold:config.mowerPolicy!.restingThreshold,rescueThreshold:config.mowerPolicy?.rescueThreshold??.75},freeRoom:config.mowerPolicy?.freeRoom,groupRestInFullOnMoodGap:config.mowerPolicy?.groupRestInFullOnMoodGap,groupMoodGapMaxExtraWaitHours:config.mowerPolicy?.groupMoodGapMaxExtraWaitHours,groupMoodGapExclusions:config.mowerPolicy?.groupMoodGapExclusions,groupMoodGapThresholdMinutes:config.mowerPolicy?.groupMoodGapThresholdMinutes,groupShiftState:previous?.data.groupShiftState,groupRecoveryFullMembers:previous?.data.groupRecoveryFullMembers,urgentRecoverySupporters:previous?.data.urgentRecoverySupporters,groupRecoveryReturnMicros:previous?.data.groupRecoveryReturnMicros,mergeIntervalMinutes:config.mowerPolicy?.mergeIntervalMinutes,powerPlantCount:config.mowerPolicy?.powerPlantCount,planConditions:previous?.data.planConditions,backupGroup:previous?.data.backupGroup,partyTime:config.mowerServices?.enableParty===false?undefined:previous?.data.partyTime,restingPriorityNames:config.mowerPolicy?.opeRestingPriority,freeBlacklist:config.freeBlacklist,excludedCandidates:new Set(config.excludedCandidates),recentShiftOnByRestUnit:previous?.data.recentShiftOnByRestUnit})
 if(data.alpha)initializeMowerAlphaMoodLimits(data,rules.lingMode,config.mowerMoodLimits,Object.fromEntries(Object.values(previous?.data.operators??{}).map(o=>[o.name,o.upperLimit])))
 if(data.alpha&&config.mowerInitialMorale?.fromUpperLimit){
  const explicit=new Set(config.mowerInitialMorale.explicitOperators)
  for(const op of Object.values(operators))if(!previous?.data.operators[op.name]&&!explicit.has(op.name)){
   s.morale[op.name]=op.upperLimit
   op.mood=op.upperLimit
   ;(s.initialMorale??={})[op.name]=op.upperLimit
  }
 }
 for(const bed of data.groupDorms){const old=previous?.data.groupDorms.find(previous=>previous.position[0]===bed.position[0]&&previous.position[1]===bed.position[1]);if(old){bed.name=old.name;bed.timeMicros=old.timeMicros}}
 if(data.alpha&&previous)commitMowerGroupShifts(data,{})
 data.adjustForRunOrders=config.mowerTaskScheduling?.adjustForRunOrders
 data.unregisteredIdleNames=config.availableIdleOperators??[]
 data.waitingRecoveryNames=new Set(previous?.data.waitingRecoveryNames)
 data.dormMoodEstimates=new Map(previous?.data.dormMoodEstimates);data.idleDormSearchExhausted=previous?.data.idleDormSearchExhausted??false;data.idleDormSearchStoppedAtMicros=previous?.data.idleDormSearchStoppedAtMicros
 data.reservedProductReplacements=previous?.data.reservedProductReplacements??new Set();data.reservedProductBeds=previous?.data.reservedProductBeds??new Map();data.emergencyDormAgents=previous?.data.emergencyDormAgents??new Set()
 return data
}
export function getMowerSourceRuntime(s:RuntimeState):MowerSourceRuntime {
 if(!s.mowerSource){const data=makeMowerSchedulingData(s);s.mowerSource={data,queue:new MowerTaskQueue(),config:s.config,initial:true,firstInit:true,trace:[]};s.mowerSource.queue.tasks.push(new MowerTask({time:s.time}))}
 const source=s.mowerSource
 if(source.config!==s.config){
  source.data=makeMowerSchedulingData(s,source);source.config=s.config;source.firstInit=false
  if(s.config.mowerServices?.enableParty===false){
   source.partyTimeMicros=null
   source.queue.tasks=source.queue.tasks.filter(task=>![T.CLUE,T.CLUE_PARTY].includes(task.type))
  }
 }
 source.data.nowMicros=toMowerMicros(s.time);return source
}
/** Numerical event wake for a run whose preview cannot commit a physical move.
 * Retain task identities/deadlines, and stop at morale boundaries as well as the
 * next explicit task or native stale-task rebuild instead of polling at 1 us.
 */
function nextMowerDecisionMicros(s:RuntimeState,rates:RuntimeRates):number {
 const {data,queue}=getMowerSourceRuntime(s),queued=nextMowerRunRecoveryMicros(queue,data.nowMicros,data.alpha,s.config.mowerTaskScheduling)
 const moraleHours=nextRosterEventHours(s,rates,false)
 const conditionWake=Math.min(s.mowerShiftModel?.nextConditionWakeMicros?.(data)??Infinity,s.mowerBackupObservationWakeMicros?.()??Infinity)
 return Math.min(queued,conditionWake,Number.isFinite(moraleHours)?data.nowMicros+Math.max(1,toMowerMicros(moraleHours)):Infinity)
}
function physicalRoom(s:RuntimeState,room:string,length:number):string[] {
 const names=Array(length).fill('')
 for(const [slot,name] of Object.entries({...s.occupants,...s.bedOccupants}))if(slot.startsWith(room+'_')){const index=slotIndex(slot);if(index<length)names[index]=name}
 return names
}
function physicalRate(s:RuntimeState,rates:RuntimeRates,name:string,room:string):number {
 if(room.startsWith('dorm'))return name===s.config.fiammetta?.operatorId?2:rates.recoveryRate(name,room,s)
 return -rates.workRate(name,room,s)
}
/** Operator.current_room setter calls this before index/mood assignment, also on cleanup. */
function currentRoomChanged(s:RuntimeState,op:MowerOperatorState,startedWorking=false):void {
 const source=getMowerSourceRuntime(s),{data,queue}=source
 if(source.firstInit||data.operators[op.name]!==op)return
 if(data.alpha&&startedWorking)for(const task of [...queue.tasks]){
  if(task===source.activeTask||task.type!==T.SHIFT_ON||![task.plan,task.backupShiftIntent??{}].some(plan=>Object.values(plan).some(row=>row.includes(op.name))))continue
  if(task.backupShiftIntent&&!task.backupShiftActive){task.plan=structuredClone(task.backupShiftIntent);delete task.backupShiftIntent;delete task.backupShiftConditions;delete task.backupGroup}
  task.plan=Object.fromEntries(Object.entries(task.plan).filter(([,row])=>row.some(name=>name!==op.name&&name!=='Current')).map(([room,row])=>[room,row.map(name=>name===op.name?'Current':name)]))
  if(!Object.values(task.plan).flat().some(name=>!['Current','Free',''].includes(name)))queue.consume(task)
 }
 const current={drained:s.config.mowerSourceRules!.refreshDrained.includes(op.name),trading:op.refreshOrderRooms},previous=source.activeTask?.backupRefreshRules?.[op.name]
 const refresh=previous?mergeMowerBackupRefreshRule(previous,current):current
 if(s.config.mowerRunOrderEnabled!==false&&refresh.trading[0])for(const room of refresh.trading[1].length?refresh.trading[1]:Object.keys(data.runOrderRooms))refreshMowerRunOrderTime(queue,data.nowMicros,room)
 if(!refresh.drained)return
 const solved=new Set<string>()
 const invalidateExhaust=(member:MowerOperatorState)=>{
  if(data.alpha&&!member.currentRoom&&member.depletionRate===0&&hasObservedFullMood(member)&&!member.moodIsPrediction)return
  member.timeStampMicros=undefined
 }
 for(const exhaust of Object.values(data.operators).filter(o=>o.exhaustRequire)){
  if(solved.has(exhaust.name))continue
  const queued=queue.find({time:s.time+1/60,type:T.EXHAUST_OFF,metadata:exhaust.name,comparison:'>'})
  if(queued){queue.consume(queued);queued.metadata.split(',').forEach(n=>{solved.add(n);if(data.operators[n])invalidateExhaust(data.operators[n]!)})}
  else invalidateExhaust(exhaust)
 }
 if(solved.size)queue.tasks.push(new MowerTask({time:s.time}))
}
function observeRoom(s:RuntimeState,rates:RuntimeRates,room:string,task?:MowerTask,readTimes:number[]=[],departingPlan?:readonly string[],confirmedPlan?:readonly string[],observedWorkDepartures:ReadonlySet<string>=new Set()):Set<string> {
 const measuredWorkDepartures=new Set<string>()
 const {data,queue}=getMowerSourceRuntime(s),names=physicalRoom(s,room,data.plan[room]?.length??5),recognized=new Set(names.filter(Boolean))
 readTimes=mowerRoomReadIndexes(data,room,task,readTimes)
 const trueExhaustRooms=new Set(['central'])
 for(const [index,name] of names.entries()){
  let op=data.operators[name]
  if(!op&&s.config.availableIdleOperators?.includes(name)&&OPERATOR_MAP.has(name)){
   const rules=s.config.mowerSourceRules!
   s.morale[name]??=s.config.initialMorale?.[name]??24
   op=new MowerOperatorState({name,nativeName:OPERATOR_MAP.get(name)!.name,room:'',index:-1,operatorType:'low',restingPriority:'low',mood:24,lowerLimit:0,upperLimit:s.config.mowerPolicy?.restMoodLimits?.[name]??24,restMoodLimit:s.config.mowerPolicy?.restMoodLimits?.[name]!==undefined,workaholic:rules.workaholic.includes(name),exhaustRequire:rules.exhaustRequire.includes(name),restInFull:rules.restInFull.includes(name)})
   op.refreshOrderRooms=mowerRefreshTradingSpec(op.nativeName,(rules.refreshTrading??[]).map(entry=>OPERATOR_MAP.get(entry)?.name??entry))
   op.workshop=['年','司霆惊蛰','九色鹿'].includes(op.nativeName)
   data.operators[name]=op
   op.alpha=data.alpha
  }
  if(!op)continue
  const departing=departingPlan!==undefined&&index<departingPlan.length&&departingPlan[index]!=='Current'&&!departingPlan.includes(name)
  const read=departing&&task?.type!==T.FIAMMETTA||shouldMowerReadMood(data,name,room,index,readTimes,task,queue.find({ignoreRunOrders:data.adjustForRunOrders===false}))
  const previousPosition:[string,number]=[op.currentRoom,op.currentIndex]
  const displayedMood=read?s.morale[name]!:op.currentMood(data.nowMicros)
  const missing=mowerUpdateDetail(data,name,read?s.morale[name]!:op.mood,room,index,read,trueExhaustRooms,(changed,started)=>currentRoomChanged(s,changed,started))
  if(read&&departing&&!room.startsWith('dorm'))measuredWorkDepartures.add(name)
  if(data.alpha&&task)recordMowerDormAdmissions(data,task,new Map([[name,previousPosition]]))
  if(data.alpha&&read&&task?.idleDormSearchNames[room]?.includes(name)){task.idleDormSearchNames[room]=task.idleDormSearchNames[room]!.filter(n=>n!==name);if(s.morale[name]!>=op.upperLimit)data.stopIdleDormSearch()}
  if(missing!==undefined&&!readTimes.includes(missing))readTimes.push(missing)
  if(readTimes.includes(index)){
   const mood=s.morale[name]!,rate=physicalRate(s,rates,name,room),remaining=room.startsWith('dorm')?24-mood:mood
   const due=displayedMood===24||['meeting','factory'].includes(room)&&!read?data.nowMicros:rate!==0?data.nowMicros+toMowerMicros(Math.max(0,remaining/Math.abs(rate))):data.nowMicros
   mowerRefreshDormTime(data,room,index,name,due,trueExhaustRooms)
  }
 }
 for(const op of Object.values(data.operators))if(op.currentRoom===room&&!recognized.has(op.name)){
  const measuredDeparture=data.alpha&&(mowerHasMeasuredDormDeparture(data,op,room,names,task,confirmedPlan)||!room.startsWith('dorm')&&observedWorkDepartures.has(op.name)&&op.timeStampMicros===data.nowMicros&&!op.moodIsPrediction)
  const bed=data.getDormByName(op.name)?.[1];if(bed?.name===op.name)bed.reset()
  if(measuredDeparture)op.depletionRate=0
  op.currentRoom='';currentRoomChanged(s,op);op.currentIndex=-1
  if(data.alpha&&!measuredDeparture)op.timeStampMicros=undefined
  if(data.alpha&&room.startsWith('dorm')&&task?.strictMoodLimit&&task.metadata===op.name)op.restMoodReleaseLimit=op.upperLimit
  if(data.freeRoom&&task&&task.type!==T.SHIFT_OFF){const release=queue.find({type:T.RELEASE_DORM,metadata:op.name});if(release&&release!==task){if(data.alpha){release.removeReleaseDormOperator(op.name);if(!Object.keys(release.plan).length)queue.consume(release)}else queue.consume(release)}}
 }
 if(data.alpha&&task?.idleDormShiftGroups)for(const [group,members] of Object.entries(task.idleDormShiftGroups))if(members.every(n=>data.operators[n]?.isResting())){data.refreshIdleDormSearch('成组下班已完成',new Set(members));delete task.idleDormShiftGroups[group]}
 return measuredWorkDepartures
}
/** Missing dorm observations must be read before a projected return can erase its intent. */
function readMissingMowerReturnRecovery(s:RuntimeState,rates:RuntimeRates,task:MowerTask):void {
 if(task.arrangementStarted||task.backupShiftActive||task.productShiftLocked||![T.SHIFT_ON,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type))return
 const {data}=getMowerSourceRuntime(s),requested=new Set(Object.entries(task.plan).flatMap(([room,row])=>room.startsWith('dorm')?[]:row.filter((name,index)=>data.operators[name]?.room===room&&data.operators[name]?.index===index)))
 const groups=new Set([...requested].map(name=>data.operators[name]?.group).filter(Boolean)),rooms=new Map<string,number[]>()
 for(const op of Object.values(data.operators))if(op.isResting()&&(requested.has(op.name)||groups.has(op.group))){
  const bed=data.getDormByName(op.name)?.[1]
  if(op.timeStampMicros!==undefined&&!op.moodIsPrediction&&(!bed||bed.timeMicros!==undefined))continue
  const indexes=rooms.get(op.currentRoom)??[];indexes.push(op.currentIndex);rooms.set(op.currentRoom,indexes)
 }
 for(const [room,indexes] of rooms)observeRoom(s,rates,room,task,indexes)
}
/** Recheck mandatory group recovery when a saved return task reaches dispatch. */
function confirmMowerGroupReturn(s:RuntimeState,rates:RuntimeRates,task:MowerTask):number|undefined {
 const {data}=getMowerSourceRuntime(s)
 const groups=Object.entries(mowerArrangementGroupTransitions(data,task.plan)).filter(([group,resting])=>!resting&&data.groupIsResting(group)).map(([group])=>group)
 const explicitGroups=new Set(groups.filter(group=>data.shiftGroupMembers(group).some(name=>{
  const op=data.operators[name]!
  return !op.room.startsWith('dorm')&&task.plan[op.room]?.[op.index]===name&&task.backupExplicitSlots.has(op.room+'\0'+op.index)
 })))
 const relevant=groups.filter(group=>!explicitGroups.has(group)&&(!data.groupMoodGapExclusions.includes(group)&&(data.groupRestInFullOnMoodGap||data.groupRecoveryFullMembers[group]?.length)||mowerGroupRecoveryWorkers(data,group).some(op=>op.restInFull)))
 if(!relevant.length)return undefined
 const rooms=new Map<string,number[]>()
 for(const group of relevant)for(const op of mowerGroupRecoveryWorkers(data,group))if(op.isResting()&&!mowerRecoveryMoodComplete(data,op)){
  const indexes=rooms.get(op.currentRoom)??[];indexes.push(op.currentIndex);rooms.set(op.currentRoom,indexes)
 }
 // Recovery targets may have changed since the task was generated. Re-read the
 // actual room and its displayed recovery deadline instead of trusting old timers.
 for(const [room,indexes] of rooms){
  invalidateMowerDormTime(data,room)
  observeRoom(s,rates,room,task,indexes)
 }
 let deadline=data.nowMicros
 for(const group of relevant){
  const recovery=mowerGroupRecoveryDeadline(data,group)
  const required=recovery.requiredNames.filter(name=>!task.exhaustSupport||task.ordinaryCoordination||data.operators[name]!.restInFull)
  for(const name of required){
   const op=data.operators[name]
   if(mowerRecoveryReady(data,op,s.config.mowerTaskScheduling))continue
   const due=op?.isResting()?mowerObservedRecoveryDeadline(data,op):undefined
   if(due===undefined||due<=data.nowMicros){
    if(!op?.restInFull&&recovery.timeMicros!==undefined&&recovery.timeMicros>data.nowMicros){deadline=Math.max(deadline,recovery.timeMicros);continue}
    throw new MowerShiftPreviewError('组员尚未确认回满心情，保留回班任务并等待有效恢复观察：'+(op?.nativeName??name))
   }
   deadline=Math.max(deadline,Math.min(due,recovery.timeMicros??due))
  }
 }
 return deadline>data.nowMicros?deadline:undefined
}
function readAgentMood(s:RuntimeState,rates:RuntimeRates):void {
 const {data}=getMowerSourceRuntime(s)
 const rooms=new Set(Object.values(data.operators).filter(o=>o.room&&o.needToRefresh(data.nowMicros)).map(o=>o.room))
 if(data.plan.train)rooms.add('train')
 for(const room of rooms){
  if(room==='train'){const last=getMowerSourceRuntime(s).lastTrainMoodReadMicros;if(last!==undefined&&data.nowMicros-last<toMowerMicros(2.5))continue}
  const current=Object.values(data.operators).filter(o=>o.currentRoom===room)
  if(current.length&&current.every(o=>o.timeStampMicros!==undefined&&o.timeStampMicros>data.nowMicros-toMowerMicros(['歌蕾蒂娅','见行者'].includes(o.nativeName)?.5:2.5)))continue
  if(room==='train')getMowerSourceRuntime(s).lastTrainMoodReadMicros=data.nowMicros
  observeRoom(s,rates,room,undefined,room==='central'?data.plan[room]!.map((_,i)=>i):[])
 }
}
function projectPublicState(s:RuntimeState):void {
 const {data,queue}=getMowerSourceRuntime(s)
 const resting=new Set(Object.values(s.bedOccupants)),present=new Set(Object.values(s.occupants))
 s.completedRest=Object.values(data.operators).filter(o=>o.isHigh()&&!o.currentRoom&&!o.workaholic&&o.timeStampMicros!==undefined&&o.mood>=o.upperLimit).map(o=>o.name)
 s.standbyWorkaholics=Object.values(data.operators).filter(o=>o.isHigh()&&o.workaholic&&!o.currentRoom).map(o=>o.name)
 s.pendingRest=Object.values(data.operators).filter(o=>o.isHigh()&&!o.room.startsWith('dorm')&&!o.workaholic&&!present.has(o.name)&&!resting.has(o.name)&&!s.completedRest!.includes(o.name)&&!data.isStandby(o.name)).map(o=>o.name)
 s.returnDeadlines={}
 for(const task of queue.tasks)if(task.type===T.SHIFT_ON)for(const name of Object.values(task.plan).flat()){
  const op=data.operators[name];if(op&&op.room&&!op.room.startsWith('dorm'))s.returnDeadlines[op.group?'group:'+op.group:'slot:'+op.room+'_'+op.index]=task.time
 }
 s.nextPlanningTime=queue.tasks.filter(t=>t.type===T.NOT_SPECIFIC&&!Object.keys(t.plan).length).reduce((t,task)=>Math.min(t,task.time),Infinity)
 s.nextFiammettaCheckTime=queue.tasks.filter(t=>t.type===T.FIAMMETTA).reduce((t,task)=>Math.min(t,task.time),Infinity)
}
/** Concrete game confirmation seam: a partial list leaves trailing slots empty. */
function confirmPhysicalRoom(s:RuntimeState,room:string,names:string[]):void {
 const previousPositions=new Map(Object.entries(s.occupants).filter(([slot])=>s.config.positions.some(p=>p.id===slot&&!p.dormitory)).map(([slot,name])=>[name,slot]))
 const explicit=new Set(names.filter(n=>!['Free','Current',''].includes(n)))
 for(const [slot,name] of Object.entries(s.occupants))if(explicit.has(name))delete s.occupants[slot]
 for(const [slot,name] of Object.entries(s.bedOccupants))if(explicit.has(name))delete s.bedOccupants[slot]
 for(const slot of Object.keys(s.occupants))if(slot.startsWith(room+'_'))delete s.occupants[slot]
 for(const slot of Object.keys(s.bedOccupants))if(slot.startsWith(room+'_'))delete s.bedOccupants[slot]
 for(const [index,name] of names.entries()){
  const slot=room+'_'+index;delete s.occupants[slot];delete s.bedOccupants[slot]
  if(name!=='Free'){
   if(s.config.beds.some(b=>b.id===slot)||s.config.mowerAlpha&&getMowerSourceRuntime(s).data.dynamicDormPosition(room,index))s.bedOccupants[slot]=name
   else s.occupants[slot]=name
  }
 }
 const currentPositions=new Map(Object.entries(s.occupants).filter(([slot])=>s.config.positions.some(p=>p.id===slot&&!p.dormitory)).map(([slot,name])=>[name,slot]))
 for(const [name,slot] of previousPositions)if(currentPositions.get(name)!==slot){
  s.workPositionChanges??={}
  s.workPositionChanges[name]=(s.workPositionChanges[name]??0)+1
 }
}
/** Native get_free_list includes both registered idle operators and unregistered catalog cards. */
function freeCandidateNames(s:RuntimeState,data:MowerSchedulingData,forbidden:Set<string>):string[]{
 let known=Object.values(data.operators).filter(op=>!forbidden.has(op.name)&&!op.workaholic&&!data.freeBlacklist.includes(op.name)&&(!op.isHigh()||data.isStandby(op.name))&&!op.currentRoom&&!data.restMoodComplete(op.name))
 if(known.some(op=>!op.workshop&&op.currentMood(data.nowMicros)<=22))known=known.filter(op=>!op.workshop)
 const unseen=(s.config.availableIdleOperators??[]).filter(name=>OPERATOR_MAP.has(name)&&!data.operators[name]&&!forbidden.has(name))
 return [...known.map(op=>op.name),...unseen].sort((a,b)=>(s.morale[a]??24)-(s.morale[b]??24))
}
function recordMowerAlphaDormCard(s:RuntimeState,data:MowerSchedulingData,task:MowerTask,room:string,name:string):void {
 if(!data.alpha||!room.startsWith('dorm'))return
 const peers=mowerAlphaDormCandidates(data).filling
 s.morale[name]??=s.config.initialMorale?.[name]??24
 const op=data.operators[name]??=new MowerOperatorState({alpha:true,name,nativeName:OPERATOR_MAP.get(name)?.name??name})
 op.dormMoodFallback=room;op.dormMoodPeers=Object.fromEntries(peers.filter(n=>n!==name&&data.operators[n]).map(n=>[n,data.operators[n]!.timeStampMicros]))
 ;(task.idleDormSearchNames[room]??=[]).push(name)
}
function selectConcreteNames(s:RuntimeState,room:string,names:string[],task:MowerTask,preserve=false):string[] {
 const {data}=getMowerSourceRuntime(s),selected=[...names]
 prepareMowerDormSelection(data,selected,room,preserve,false,task)
 const forbidden=new Set([...selected,...Object.values(task.plan).flat(),...(s.config.freeBlacklist??[])])
 const trainee=data.currentOperator('train',0)?.name;if(trainee)forbidden.add(trainee)
 const free=freeCandidateNames(s,data,forbidden)
 for(const [index,name] of selected.entries())if(name==='Free'){
  const card=free.shift();if(!card)throw new MowerArrangementError('Mower Free selection needs an owned idle operator: '+room+'_'+index)
  selected[index]=card
 }
 return selected
}
function* arrangeRoom(s:RuntimeState,rates:RuntimeRates,room:string,names:string[],getTime:boolean,task:MowerTask,chooseError=0,sharedRestoration:MowerTaskPlan={}):Generator<MowerRoomReturn,MowerTaskPlan|void,void> {
 const {data}=getMowerSourceRuntime(s)
 // refresh_current_room uses cached positions when all requested slots are known.
 const requested=names.flatMap((name,index)=>name==='Current'?[index]:[])
 const cached=()=>data.currentRoom(room,true)!
 if(data.currentRoom(room,false,requested)===undefined)observeRoom(s,rates,room,task)
 const current=cached(),resolved=names.map((name,index)=>name==='Current'?current[index]||'Free':name||'Free'),fia=s.config.fiammetta?.operatorId
 // Moving an explicit operator vacates their old Current slot before dorm recovery ordering.
 const explicit=new Set(names.filter(name=>name!=='Current'&&name!=='Free'&&name!==''))
 for(const [index,name] of names.entries())if(name==='Current'&&explicit.has(resolved[index]!))resolved[index]='Free'
 const seen=new Set<string>()
 for(const [index,name] of resolved.entries())if(name!=='Free'&&name!==''){if(seen.has(name))resolved[index]='Free';else seen.add(name)}
 names.splice(0,names.length,...resolved)
 // Restoration is reserved for Fiammetta; ideal runners never enter a trade room.
 let restoration:MowerTaskPlan|undefined,fiammettaCharge=false
 if(room in getMowerSourceRuntime(s).data.runOrderRooms&&task.type!==T.RUN_ORDER&&
   (resolved.length!==current.length||resolved.some((name,index)=>name!==current[index])))
  refreshMowerRunOrderTime(getMowerSourceRuntime(s).queue,data.nowMicros,room)
 // Native captures both Fia restoration rooms before exact-noop detection (7525-7533).
 if(fia&&resolved.length===2&&resolved.includes(fia)&&chooseError===0){
  const target=data.operators[resolved[0]!]!
  restoration={[room]:[...current],[target.room]:data.currentRoom(target.room,true)!}
  Object.assign(sharedRestoration,restoration)
 }
 // Native final dorm confirmation invalidates every timer because co-residents change recovery rates.
 const fiaArrangement=task.type===T.FIAMMETTA&&!!fia&&resolved.includes(fia)
 const refreshDormIndexes=()=>{
  const beds=data.allDorms().filter(bed=>bed.position[0]===room)
  invalidateMowerDormTime(data,room)
  return beds.filter(bed=>{const name=resolved[bed.position[1]];return !!name&&data.recoveryDorm(bed,name)}).map(bed=>bed.position[1])
 }
 // Native admission resolves the final roster before recovery ordering and no-op detection.
 if(room.startsWith('dorm')){prepareMowerDormSelection(data,resolved,room,false,false,task);names.splice(0,names.length,...resolved)}
 const resumingRecovery=task.dormRecoveryRestore.includes(room)
 const ensureRecovery=()=>ensureMowerDormRecovery(data,getMowerSourceRuntime(s).queue,task,room,resolved,{
  arrangeTemporary:retained=>{
   const selected=selectConcreteNames(s,room,retained,task,true)
   retained.splice(0,retained.length,...selected)
   const confirmed=[...selected,...Array(data.plan[room]!.length-selected.length).fill('')]
   // Observe departures before temporary single-target ordering removes them.
   // Completion is valid only after observing this exact intermediate roster.
   observeRoom(s,rates,room,task,[],confirmed)
   confirmPhysicalRoom(s,room,selected)
   observeRoom(s,rates,room,task,[],undefined,confirmed)
  }
 })
 let recoveryOrdered=ensureRecovery()
 const afterRecovery=cached()
 if(resolved.length===afterRecovery.length&&resolved.every((name,index)=>name===afterRecovery[index])){
  if(data.alpha&&room.startsWith('dorm')&&!fiaArrangement&&getTime)observeRoom(s,rates,room,task,refreshDormIndexes())
  return restoration
 }
 // Native get_agent_from_room(departing_plan) reads departures before selection.
 const observedWorkDepartures=data.alpha&&task.type!==T.RUN_ORDER&&task.type!==T.FIAMMETTA&&room!=='train'?observeRoom(s,rates,room,task,[],resolved):new Set<string>()
 if(task.type===T.FIAMMETTA&&fia&&resolved.length===2&&resolved.includes(fia)){
  fiammettaCharge=true
  restoration=sharedRestoration

 }
 let readTimes=recoveryOrdered?data.plan[room]!.flatMap((name,index)=>name==='Free'?[index]:[]):mowerArrangementReadIndexes(data,room,resolved,getTime,task)
 // Default get_free_list; the UI chooses eligible idle cards in ascending physical mood.
 // Account-specific tie order is the provided roster registration order.
 const forbidden=new Set([...resolved,...Object.values(task.plan).flat(),...(s.config.freeBlacklist??[])])
 const trainee=data.currentOperator('train',0)?.name;if(trainee)forbidden.add(trainee)
 let free=freeCandidateNames(s,data,forbidden)
 if(room.startsWith('dorm')){
  const ordinary=free.map(name=>data.operators[name]).filter((op):op is MowerOperatorState=>!!op&&!op.workshop&&op.currentMood(data.nowMicros)<=22).sort((a,b)=>a.currentMood(data.nowMicros)-b.currentMood(data.nowMicros))
  for(const [index,name] of resolved.entries())if(name==='Free'){
   const current=data.currentOperator(room,index)
   if(current?.workshop&&current.currentMood(data.nowMicros)<current.upperLimit&&!resolved.includes(current.name)){
    const next=ordinary.shift()??current;resolved[index]=next.name;free=free.filter(name=>name!==next.name)
   }
  }
 }
 // choose_agent mutates the list shared with task.plan after no-op detection.
 prepareMowerDormSelection(data,resolved,room,recoveryOrdered,false,task)
 names.splice(0,names.length,...resolved)
 const refreshedForbidden=new Set([...resolved,...Object.values(task.plan).flat(),...(s.config.freeBlacklist??[])])
 if(trainee)refreshedForbidden.add(trainee)
 free=freeCandidateNames(s,data,refreshedForbidden)
 for(const [index,name] of resolved.entries())if(name==='Free'){
  const card=free.shift()
  if(!card)throw new MowerArrangementError('Mower Free selection needs an owned idle operator: '+room+'_'+index)
  recordMowerAlphaDormCard(s,data,task,room,card)
  resolved[index]=card
 }
 names.splice(0,names.length,...resolved)
 // Ideal selection knows the concrete Free cards before confirmation. Establish
 // their real recovery order now, so an identical following backup can reuse it.
 if(data.adjustForRunOrders===false&&!resumingRecovery&&room.startsWith('dorm')){
  recoveryOrdered=ensureRecovery()
  // A temporary observation may prove a card has already reached its custom
  // recovery limit. Such completed cards are excluded from subsequent picks.
  while(recoveryOrdered){
   const prepared=[...resolved];prepareMowerDormSelection(data,prepared,room,true,false,task)
   if(prepared.every((name,index)=>name===resolved[index]))break
   const selected=selectConcreteNames(s,room,prepared,task,true)
   for(const [index,name] of prepared.entries())if(name==='Free')recordMowerAlphaDormCard(s,data,task,room,selected[index]!)
   resolved.splice(0,resolved.length,...selected);names.splice(0,names.length,...resolved)
   recoveryOrdered=ensureRecovery()
  }
  if(recoveryOrdered)readTimes=data.plan[room]!.flatMap((name,index)=>name==='Free'?[index]:[])
 }
 if(fiammettaCharge&&fia){
  const target=resolved[0]!,old=s.morale[target]!
  if(old>=24-1e-8&&s.morale[fia]!>=24-1e-8)throw new MowerShiftPreviewError('菲亚梅塔与实际充能目标均已满心情，保留充能任务，等待相关实测或安排更新')
  s.morale[target]=24;s.morale[fia]=old;s.lastFiammettaTime=s.time
  s.events.push({time:s.time,type:'fiammetta',operators:[fia,target],moraleBefore:[24,old],moraleAfter:[old,24]})
  data.operators[fia]!.timeStampMicros=undefined;data.operators[target]!.timeStampMicros=undefined
 }
 confirmPhysicalRoom(s,room,resolved)

 observeRoom(s,rates,room,task,data.alpha&&room.startsWith('dorm')&&!fiaArrangement?refreshDormIndexes():readTimes,undefined,undefined,observedWorkDepartures)
 return restoration
}
/** Actual agent_arrange_room: four attempts, three back(0.5) retry boundaries. */
function* arrangeRoomSteps(s:RuntimeState,rates:RuntimeRates,room:string,names:string[],getTime:boolean,task:MowerTask,restoration:MowerTaskPlan={}):Generator<MowerRoomReturn,MowerTaskPlan|void,void>{
 for(let attempt=getMowerSourceRuntime(s).data.alpha&&task.arrangementRetryRoom===room?1:0;;attempt++){
  try {
   if(attempt){
    // Reconcile a successfully confirmed selection before attempting another arrangement.
    observeRoom(s,rates,room,task)
    const actual=getMowerSourceRuntime(s).data.currentRoom(room,true)!
    if(actual.length===names.length&&actual.every((name,index)=>name===names[index]||names[index]==='Free'))return restoration
   }
   return yield* arrangeRoom(s,rates,room,names,getTime,task,attempt,restoration)
  }catch(error){
   rethrowMowerInfraFatal(error)
   if(error instanceof MowerShiftPreviewError)throw error
   const {data,queue}=getMowerSourceRuntime(s),queued=data.alpha&&![T.RUN_ORDER,T.FIAMMETTA,T.SKILL_UPGRADE,T.SWAP_SUPPORT].includes(task.type)&&queue.tasks.includes(task)
   const urgent=queued&&!task.dormRecoveryRestore.length&&queue.tasks.some(t=>t!==task&&[T.FIAMMETTA,T.RUN_ORDER,T.SWAP_SUPPORT,T.SKILL_UPGRADE].includes(t.type)&&(t.type!==T.RUN_ORDER||s.config.mowerTaskScheduling?.adjustForRunOrders!==false)&&t.timeMicros<=data.nowMicros+toMowerMicros(1/60))
   if(queued&&(attempt>=3||urgent))throw new MowerRoomArrangementDeferred(room,error)
   if(attempt>=3)throw error
   yield {room,delayMicros:500_000}
  }
 }
}
function scheduleFiaAndExhaust(s:RuntimeState,rates:RuntimeRates):void {
 const source=getMowerSourceRuntime(s),{data,queue}=source,fia=s.config.fiammetta
 if(fia&&!queue.tasks.some(task=>task.type===T.FIAMMETTA)){
  const op=data.operators[fia.operatorId]
  if(op?.room.startsWith('dorm')){
   const ready=mowerFiaReadyMicros(op,data.nowMicros,()=>{
    const index=op.currentIndex===-1?op.index:op.currentIndex
    observeRoom(s,rates,op.room,undefined,[index])
    return data.nowMicros+toMowerMicros(Math.max(0,(24-s.morale[fia.operatorId]!)/2))
   })
   const task=new MowerTask({type:T.FIAMMETTA});task.timeMicros=ready;queue.tasks.push(task)
  }
 }
 for(const op of Object.values(data.operators)){
  if(!op.exhaustRequire||op.isResting()||!op.isHigh()||!data.plan[op.currentRoom]||op.currentMood(data.nowMicros)>op.lowerLimit+2||mowerPendingExhaust(queue.tasks,op.name))continue
  observeRoom(s,rates,op.currentRoom,undefined,[op.currentIndex])
  const rate=-physicalRate(s,rates,op.name,op.currentRoom),mood=s.morale[op.name]!,group=op.group?data.group(op.group).map(n=>data.operators[n]!):[]
  const fullGroups=new Set(Object.values(data.operators).filter(p=>p.restInFull&&p.group&&!p.room.startsWith('dorm')).map(p=>p.group))
  const margin=fullGroups.has(op.name)?10:30
  let due=data.nowMicros
  if(rate>0&&mood>0)due=data.nowMicros+toMowerMicros(mood/rate-margin/60)
  else if(op.currentMood(data.nowMicros)>op.lowerLimit+.25&&op.depletionRate!==0)due=data.nowMicros+toMowerMicros((op.currentMood(data.nowMicros)-op.lowerLimit-.25)/op.depletionRate-margin/60)
  const exhaustedTime=due<data.nowMicros
  due=Math.max(data.nowMicros,due)
  let shared=false
  if(op.group)for(const peer of group.filter(p=>p.exhaustRequire)){const old=mowerPendingExhaust(queue.tasks,peer.name);if(old){if(!old.retainsExecution){old.timeMicros=Math.min(old.timeMicros,due);if(!old.metadata.split(',').includes(op.name))old.metadata+=','+op.name}shared=true}}
  if(!shared){const task=new MowerTask({type:T.EXHAUST_OFF,metadata:op.name});task.timeMicros=due;queue.tasks.push(task)}
  if(exhaustedTime)break
 }
}
/** Read live native room data; primary-only data.plan loses replacement lists. */
export function mowerRunOrderContext(s:RuntimeState):[RunOrderPlanningState,RunOrderPlanningSeam]{
 const source=getMowerSourceRuntime(s)
 const state:RunOrderPlanningState={
  plan:Object.fromEntries(mowerPlanEntries(s.config.mowerSourcePlan!)),
  runOrderRooms:Object.keys(source.data.runOrderRooms),queue:source.queue,
  configuredDelayMinutes:s.config.mowerTaskScheduling?.configuredDelayMinutes??3,
  droneRoom:s.config.mowerDroneRoom??null,flags:source.runFlags!,
 }
 const seam:RunOrderPlanningSeam={
  nowMicros:()=>toMowerMicros(s.time),
  currentDormOccupants:room=>getMowerSourceRuntime(s).data.currentRoom(room),
  scheduling:{...s.config.mowerTaskScheduling,alpha:source.data.alpha},
 }
 return [state,seam]
}
function mowerClueState(s:RuntimeState):MowerClueLifecycleState {
 const source=getMowerSourceRuntime(s)
 return {
  queue:source.queue,flags:source.runFlags!,
  get partyTimeMicros(){return source.partyTimeMicros??null},
  set partyTimeMicros(value){source.partyTimeMicros=value},
  get dataPartyTime(){const value=getMowerSourceRuntime(s).data.partyTime;return typeof value==='boolean'?value:value?.timeMicros??null},
  set dataPartyTime(value){getMowerSourceRuntime(s).data.partyTime=typeof value==='number'?{timeMicros:value}:value},
  get lastClueMicros(){return source.lastClueMicros??null},
  set lastClueMicros(value){source.lastClueMicros=value},
  leifengMode:s.config.mowerServices?.leifengMode??true,clueCount:s.config.mowerClueObservations?.clueCount??0,clueCountLimit:9,
  mall:{maaMallEnable:true,maaMallMode:'maa'},waitingScenes:[],
 }
}
export function settleMowerSource(s:RuntimeState,rates:RuntimeRates,onPhase?:(phase:BackupTiming)=>boolean):void {
 const source=getMowerSourceRuntime(s),queue=source.queue
 reconcileMowerUrgentRecovery(source.data)
 for(const task of [...queue.tasks])if(task!==source.execution?.task&&task.type===T.EXHAUST_OFF&&mowerCoordinationRequestFulfilled(source.data,task.metadata.split(',')))queue.consume(task)
 for(const task of [...queue.tasks])if(task!==source.execution?.task&&task.exhaustSupport&&task.coordinationRequestNames.length&&!queue.tasks.some(request=>request.type===T.EXHAUST_OFF&&request.metadata.split(',').some(name=>task.coordinationRequestNames.includes(name))))queue.consume(task)
 if(resumeMowerFailedTasks(s,source.data,queue)&&!source.execution&&!source.phaseExecution)delete source.runReturn
 if(!source.execution&&!source.phaseExecution&&!source.runReturn&&source.planningWake&&source.planningWake.timeMicros<=source.data.nowMicros){
  source.planningMoodRefreshNames=[...new Set([...(source.planningMoodRefreshNames??[]),...source.planningWake.names])]
  if(!queue.tasks.some(task=>task.type===T.NOT_SPECIFIC&&!Object.keys(task.plan).length&&task.timeMicros<=source.data.nowMicros))queue.tasks.push(new MowerTask({time:s.time}))
  delete source.planningWake;queue.sort()
 }
 const skip=()=>{Object.assign(source.runFlags??={planned:false,todoTask:false,collectNotification:false}, {planned:true,todoTask:true,collectNotification:true})}
 const dependencyReturn=(data:MowerSchedulingData,retained:MowerTask,candidate:MowerTask,pending:readonly MowerTask[])=>!!s.mowerShiftModel&&mowerVerifiedRecoveryDependencyReturn(data,retained,candidate,pending,s.mowerShiftModel)
 const options=()=>({dependencyReturn,urgentRecoveryPendingSupporters:mowerUrgentPendingSupporters(queue.tasks),urgentExhaust:!!source.activeTask&&!source.activeTask.ordinaryCoordination&&(source.activeTask.type===T.EXHAUST_OFF||source.activeTask.exhaustSupport),...mowerReplacementReservations(getMowerSourceRuntime(s).data,queue.tasks.filter(task=>task!==source.activeTask),source.activeTask?.urgentRecoveryRequestNames),coordinationRates:(projected:MowerSchedulingData)=>{
  if(!rates.forecastRates)return undefined
  const occupants:Record<string,string>={},bedOccupants:Record<string,string>={},bedSlots=new Set(projected.allDorms().map(bed=>bed.position[0]+'_'+bed.position[1]))
  for(const op of Object.values(projected.operators))if(op.currentRoom)(bedSlots.has(op.currentRoom+'_'+op.currentIndex)?bedOccupants:occupants)[op.currentRoom+'_'+op.currentIndex]=op.name
  return rates.forecastRates({...s,time:fromMowerMicros(projected.nowMicros),occupants,bedOccupants,morale:Object.fromEntries(Object.values(projected.operators).map(op=>[op.name,op.mood])),mowerSource:{...source,data:projected}})
 },priorityScheduling:s.config.mowerTaskScheduling,onException:(error:unknown)=>s.diagnostics.push({code:'mower-plan-solver-exception',message:error instanceof Error?error.message:String(error)}),fiaTargets:s.config.fiammetta?.orderedTargets??[],isDormReplacement:(n:string)=>mowerIsDormReplacement(getMowerSourceRuntime(s).data,n),isMasteryBusy:(n:string)=>getMowerSourceRuntime(s).data.busyRestingNames.has(n),onBlocked:(names:string[])=>{
  const op=getMowerSourceRuntime(s).data.operators[names[0]!]!,key=op.group?'group:'+op.group:'slot:'+op.room+'_'+op.index,message=key+': insufficient available candidates or beds; original occupants retained'
  if(!s.diagnostics.some(d=>d.code==='group-blocked'&&d.message===message))s.diagnostics.push({code:'group-blocked',message})
 }})
  const backup=(phase:BackupTiming,_task?:MowerTask,context:MowerBackupContext={appendEmptyTask:true,restoreOnDeactivate:false}):MowerBackupResult=>{
   if(queue.tasks.some(task=>task.backupShiftActive))return {changed:false,generated:[]}
  if(_task?.type===T.FIAMMETTA||queue.tasks.some(t=>t.type===T.FIAMMETTA&&t.timeMicros<=toMowerMicros(s.time)))return {changed:false,generated:[]}
  const previousConfig=s.config
  s.mowerBackupContext=context;s.mowerBackupGenerated=[]
  const changed=onPhase?.(phase)??false
  const generated=s.mowerBackupGenerated??[];delete s.mowerBackupContext;getMowerSourceRuntime(s)
  for(const task of generated)if(!queue.tasks.includes(task))queue.tasks.push(task)
  if(previousConfig!==s.config&&queue.tasks.some(t=>t.type===T.SHIFT_ON||t.type===T.RELEASE_DORM))planMowerMetadata(getMowerSourceRuntime(s).data,queue,dependencyReturn)
  if(getMowerSourceRuntime(s).config!==source.config)throw new Error('Mower source config identity lost')
  return {changed,generated}
 }

 const observedWake=!source.execution&&!source.phaseExecution&&source.runReturn?s.mowerBackupObservationWakeMicros?.():undefined
 if(!source.execution&&!source.phaseExecution&&(!source.runReturn||observedWake!==undefined&&observedWake<=source.data.nowMicros)&&source.conditionWakeMicros!==undefined&&source.conditionWakeMicros<=source.data.nowMicros){
  delete source.conditionWakeMicros
  if(observedWake!==undefined)delete source.runReturn
  backup('END')
 }

 function* clueSteps(flow:boolean):Generator<MowerNativeIOYield,null,void>{
  if(!rates.mowerClueIO)throw new Error('Native clue lifecycle requires explicit observations')
  const generator=(flow?runMowerClueFlow:executeMowerClueNew)(mowerClueState(s),{nowMicros:()=>toMowerMicros(s.time)})
  return yield* bridgeMowerNativeIO(generator,request=>{
   if(request.kind!=='backup-plan')return rates.mowerClueIO!(request,s)
   return {delayMicros:0,observe:()=>({kind:request.kind,observedAtMicros:toMowerMicros(s.time),value:backup('END')})}
  },()=> 'meeting')
 }
 if(!source.execution&&!source.phaseExecution){
  if(nextMowerPreviewRecoveryObservation(source)<=source.data.nowMicros){
   const rooms=new Set(source.waitingRecovery?.flatMap(wait=>Object.entries(wait.deadlines).filter(([,due])=>due<=source.data.nowMicros).map(([room])=>room)))
   for(const room of rooms){invalidateMowerDormTime(source.data,room);observeRoom(s,rates,room,undefined,source.data.plan[room]?.map((_,i)=>i)??[])}
  }
  if(resumeMowerPreviewRecovery(source)){delete source.runReturn;source.queue.sort()}
 }
 if(source.initial){for(const room of Object.keys(source.data.plan))observeRoom(s,rates,room,undefined,room==='central'?source.data.plan[room]!.map((_,i)=>i):[]);source.initial=false}
 // Recovery reads can release a retained dependency in this same run.
 // Admit it before dispatch so a next-action query cannot reveal overdue work.
 if(!source.execution&&!source.phaseExecution&&resumeMowerFailedTasks(s,source.data,queue))delete source.runReturn
 const clock=s.config.mowerRunLoopClock
 if(clock&&(!Number.isSafeInteger(clock.minimumClockStepMicros)||clock.minimumClockStepMicros<1||!Number.isSafeInteger(clock.notificationSleepMicros)||clock.notificationSleepMicros<0))throw new Error('Invalid Mower outer clock')
 if(source.runReturn){
  if(source.runReturn.wakeMicros>source.data.nowMicros){projectPublicState(s);return}
  if(source.runReturn.finishFallback){source.runFlags!.collectNotification=true;queue.ensureFallback(s.time,s.config.mowerTaskScheduling)}
  delete source.runReturn;queue.sort()
  if(!queue.find()||queue.find()!.timeMicros>source.data.nowMicros){projectPublicState(s);return}
 }
 if(!source.execution&&!source.phaseExecution){
  source.runFlags={planned:false,todoTask:false,collectNotification:false};source.error=false
  if(source.partyTimeMicros!==undefined&&source.partyTimeMicros!==null&&source.partyTimeMicros<source.data.nowMicros)setMowerPartyTime(mowerClueState(s),null,{nowMicros:()=>toMowerMicros(s.time)})
  if(clock)prepareMowerRunEntry(queue,source.data.nowMicros,source.data.alpha,s.config.mowerTaskScheduling)
 }
 let pass=0
 for(;pass<256;pass++){
  const running=source.execution,runningPhase=source.phaseExecution
  if(runningPhase&&runningPhase.wakeMicros>getMowerSourceRuntime(s).data.nowMicros)break
  if(running&&running.wakeMicros>getMowerSourceRuntime(s).data.nowMicros)break
  if(!running&&!runningPhase){
   if(getMowerSourceRuntime(s).data.alpha)fillMowerAlphaEmptyDorms(getMowerSourceRuntime(s).data,queue,options())
   const scheduling={...s.config.mowerTaskScheduling,alpha:getMowerSourceRuntime(s).data.alpha,mergeIntervalMinutes:getMowerSourceRuntime(s).data.mergeIntervalMinutes,experimental:getMowerSourceRuntime(s).data.policy.experimentalDormLogic}
   scheduleMowerTasks(queue.tasks,getMowerSourceRuntime(s).data.nowMicros,scheduling)
   protectMowerSupportSwaps(queue.tasks,getMowerSourceRuntime(s).data.nowMicros,scheduling)
  }
  const selected=runningPhase?undefined:running?.task??queue.find()
  const task=selected&&(running||selected.timeMicros<=getMowerSourceRuntime(s).data.nowMicros)?selected:undefined
  if(!task&&!runningPhase)break
  if(!running&&!runningPhase){mowerCorrectDorm(getMowerSourceRuntime(s).data);backup('BEGINNING',task)}
  let data=getMowerSourceRuntime(s).data
  // infra_main must not execute a task removed by entry metadata rebuilding.
  if(task&&!running&&(!queue.tasks.includes(task)||task.timeMicros>data.nowMicros)){skip();break}
  let skipPlanning=runningPhase?.skipPlanning??false,previewNoop=runningPhase?.previewNoop??false
  if(task){
   try {
    source.activeTask=task
    if(!running&&!task.backupShiftActive&&!task.productShiftLocked&&!task.backupExplicitSlots.size&&task.ordinaryCoordination&&(task.exhaustSupport||[T.SHIFT_OFF,T.EXHAUST_OFF].includes(task.type))&&!mowerOrdinaryCoordinationNeeded(data,task.coordinationRequestNames.length?task.coordinationRequestNames:task.metadata.split(','))){queue.consume(task);delete source.activeTask;continue}
    if(!running&&data.alpha&&task.exhaustSupport&&!task.arrangementStarted&&!task.backupShiftActive&&!task.productShiftLocked){
     const names=task.coordinationRequestNames.filter(name=>data.operators[name])
     task.plan=names.length?planMowerExhaustSupport(data,names,options())??{}:{}
     if(task.backupShiftIntent)task.backupShiftIntent=structuredClone(task.plan)
     task.groupShiftTransitions=mowerArrangementGroupTransitions(data,task.plan)
    }
    if(!running&&task.preferredReplacementRestore){
     const reservations=mowerReplacementReservations(data,queue.tasks.filter(other=>other!==task))
     for(const pending of queue.tasks)if(pending!==task&&pending.type===T.EXHAUST_OFF&&pending.timeMicros<=data.nowMicros)mowerReplacementDependencyNames(data,pending.metadata.split(',')).forEach(name=>reservations.reservedNames.add(name))
     task.plan=planMowerPreferredReplacementRestore(data,reservations.reservedNames,reservations.reservedSlots)
     if(!Object.keys(task.plan).length){queue.consume(task);delete source.activeTask;continue}
    }
    if(!running&&data.alpha&&[T.SHIFT_ON,T.SHIFT_OFF,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type)&&Object.keys(task.plan).length){
     const model:MowerShiftModel=s.mowerShiftModel??{count:0,evaluate:d=>d.planConditions,swap:d=>d,transition:()=>({}),activate:()=>{}}
     readMissingMowerReturnRecovery(s,rates,task)
     const independentTasks:MowerTask[]=[]
     splitMowerRecoveryTask(data,task,independentTasks,mowerUnfinishedReturnMembers(data,task,s.config.mowerTaskScheduling))
     const originalKeys=new Set(Object.keys(task)),original=cloneMowerShiftTask(task),pending=[...queue.tasks],fallbacks=new Map(Object.values(data.operators).map(op=>[op.name,op.dormMoodFallback]))
     try {
     commitMowerGroupShifts(data,{})
     const transitions=mowerArrangementGroupTransitions(data,task.plan)
     task.groupShiftTransitions=task.arrangementStarted||task.backupShiftActive||task.productShiftLocked?{...task.groupShiftTransitions,...transitions}:transitions
     if((task.arrangementStarted||task.backupShiftActive||task.productShiftLocked)&&!normalizeMowerSharedArrangement(data,task.plan,task.groupShiftTransitions,task.backupExplicitSlots))throw new MowerShiftPreviewError('绑组共享替班冲突，保留原任务并等待岗位释放')
     prepareMowerShiftCycle(data,task,queue,model,{...options(),priorityScheduling:s.config.mowerTaskScheduling})
     const previewRules=task.backupShiftConditions?model.swap(projectMowerArrangements(data,[]),task.backupShiftConditions,task.backupGroup):data
     if(!normalizeMowerSharedArrangement(previewRules,task.plan,task.groupShiftTransitions,task.backupExplicitSlots))throw new MowerShiftPreviewError('绑组共享替班冲突，保留原任务并等待岗位释放')
     previewNoop=!Object.keys(task.plan).length
     if(previewNoop&&parkMowerPreviewRecovery(source,task,original,pending,model.observationNames)){delete source.activeTask;continue}
     // A projected return must not switch the effective backup configuration
     // until its physical recovery prerequisites are ready.
     if([T.SHIFT_ON,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type)){
      const readyAt=confirmMowerGroupReturn(s,rates,task)
      if(readyAt!==undefined){task.timeMicros=readyAt;queue.sort();delete source.activeTask;continue}
     }
     if(task.exhaustSupport&&task.coordinationRequestNames.length){
      const effective=task.backupShiftConditions?model.swap(projectMowerArrangements(data,[]),task.backupShiftConditions,task.backupGroup):data
      const projected=projectMowerArrangements(data,[task.plan]),recalls=Object.values(data.operators).some(op=>op.isHigh()&&op.isResting()&&projected.operators[op.name]?.currentRoom===op.room&&!op.room.startsWith('dorm'))
      if(recalls&&task.ordinaryCoordination&&task.backupShiftConditions&&JSON.stringify(task.backupShiftConditions)!==JSON.stringify(data.planConditions))throw new MowerShiftPreviewError('副表改变召回条件，保留任务等待实际配置确认')
      if(!validateMowerCoordinationSupport(effective,task.plan,task.coordinationRequestNames,options()))throw new MowerShiftPreviewError('替班交接条件已变化，保留原任务等待依赖释放')
     }
     if(task.preferredReplacementRestore&&task.backupShiftConditions){
      const effective=model.swap(projectMowerArrangements(data,[]),task.backupShiftConditions,task.backupGroup),reserved=mowerReplacementReservations(effective,queue.tasks.filter(other=>other!==task)),current=planMowerPreferredReplacementRestore(effective,reserved.reservedNames,reserved.reservedSlots)
      if(Object.entries(task.plan).some(([room,row])=>row.some((name,index)=>name!=='Current'&&!task.backupExplicitSlots.has(room+'\0'+index)&&current[room]?.[index]!==name)))throw new MowerShiftPreviewError('副表改变首选替班，等待实际配置后重新协调')
     }
     }catch(error){
      if(!original.arrangementStarted&&!original.backupShiftActive&&!original.productShiftLocked){
       for(const key of Object.keys(task))if(!originalKeys.has(key))Reflect.deleteProperty(task,key)
       Object.assign(task,Object.fromEntries(Object.entries(original).filter(([key])=>originalKeys.has(key))))
       queue.tasks=pending
       for(const [name,fallback] of fallbacks)if(data.operators[name])data.operators[name]!.dormMoodFallback=fallback
      }
      throw error
     }finally{queue.tasks.push(...independentTasks)}
     if(task.backupShiftConditions){model.activate(task.backupShiftConditions,task);data=getMowerSourceRuntime(s).data;task.backupShiftActive=true}
    }
    if(!running&&mowerProtectedShift(task)){
     const prepared=prepareMowerShiftBeds(data,task,queue.tasks)
     if(!prepared.ready){
      task.timeMicros=prepared.retryAtMicros;queue.sort()
      const message=prepared.names.map(name=>data.operators[name]!.nativeName).join('、')+': forced dorm task waits for valid recovery beds'
      if(!s.diagnostics.some(d=>d.code==='mower-shift-bed-conflict'&&d.message===message))s.diagnostics.push({code:'mower-shift-bed-conflict',message})
      delete source.activeTask;skip();break
     }
     task.plan=prepared.plan
    }
   if(!running){source.trace.push({timeMicros:data.nowMicros,type:task.type.key,plan:structuredClone(task.plan),metadata:task.metadata});if(source.trace.length>300)source.trace.shift()}
   if([T.CLUE,T.CLUE_PARTY].includes(task.type)){
    const steps=running?.steps??(function*():Generator<MowerRoomReturn,boolean,void>{
     yield* clueSteps(true);queue.consume(task);return true
    })()
    let next=steps.next()
    while(!next.done&&next.value.delayMicros===0)next=steps.next()
    if(!next.done){source.execution={task,steps,wakeMicros:data.nowMicros+next.value.delayMicros,intent:running?.intent??{},data:running?.data??data};break}
    delete source.execution
   }else if(task.type===T.REFRESH_TIME&&rates.mowerRunOrderIO){
    const [state,seam]=mowerRunOrderContext(s)
    const steps=running?.steps??(function*():Generator<MowerRoomReturn,boolean,void>{
     yield* bridgeMowerNativeIO(dispatchDefaultRefreshTime(state,seam,task),request=>rates.mowerRunOrderIO!(request,s))
     return true
    })()
    let next=steps.next()
    while(!next.done&&next.value.delayMicros===0)next=steps.next()
    if(!next.done){source.execution={task,steps,wakeMicros:data.nowMicros+next.value.delayMicros,intent:running?.intent??{},data:running?.data??data};break}
    delete source.execution
   }else if(!running&&task.type===T.RUN_ORDER){
    // Keep the native pre-order wake, then recheck at the observed completion time.
    // The queued task suppresses repeated reads of this still-pending order.
    if(task.wakeOnlyCompletion)queue.consume(task)
    else {
     if(task.observedOrderDueMicros===undefined)throw new Error('Wake-only order has no observed completion deadline')
     task.wakeOnlyCompletion=true;task.plan={}
     task.timeMicros=Math.max(data.nowMicros+1,task.observedOrderDueMicros)
     queue.sort()
    }
   }else if(!running&&task.type===T.FIAMMETTA&&!Object.keys(task.plan).length){
    const fia=s.config.fiammetta,target=fia?selectMowerFiaTarget(data,fia.orderedTargets,fia.fool??true,(fia.threshold??21.6)/24):undefined
    if(target&&fia){
     queue.tasks.push(new MowerTask({time:task.time,type:T.FIAMMETTA,plan:{[data.operators[fia.operatorId]!.room]:[target,fia.operatorId]},metadata:target}));for(const old of queue.tasks)if(old.type===T.SHIFT_ON&&Object.values(old.plan).flat().includes(target)){old.time=task.time+1/3600;queue.sort();break}
    }else if(fia)queue.tasks.push(new MowerTask({time:task.time+(24-(fia.threshold??21.6))/2,type:T.FIAMMETTA}))
    queue.consume(task)
   }else if(!running&&task.type===T.EXHAUST_OFF&&!Object.keys(task.plan).length){
    const first=data.operators[task.metadata.split(',')[0]!],members=first?.group?data.shiftGroupMembers(first.group):first?[first.name]:[],plan:MowerTaskPlan={}
    const pendingSupport=queue.tasks.find(other=>other!==task&&other.exhaustSupport&&other.coordinationRequestNames.some(name=>members.includes(name)))
    if(pendingSupport){
     const dependencies=mowerReplacementDependencyNames(data,members),rooms=[...new Set([...dependencies].flatMap(name=>{const op=data.operators[name];return op?[op.room,op.currentRoom].filter(Boolean):[]}).concat(data.allDorms().map(bed=>bed.position[0])))]
     retainMowerFailedTask(s,data,task,'等待已排定的替班交接',rooms);task.coordinationDependencyWait=true;delete source.activeTask;continue
    }
    mowerGetRestingPlan(data,[...members],[],plan,options())
    if(Object.keys(plan).length){
     const reorder=mowerTryReorder(data,plan);if(reorder)Object.assign(plan,reorder)
     const departure=new MowerTask({time:s.time,type:T.SHIFT_OFF,plan});inheritMowerUrgentRecovery(departure,task);departure.ordinaryCoordination=task.ordinaryCoordination;departure.coordinationRequestNames=task.ordinaryCoordination?[...members]:[];queue.tasks.push(departure)
    }else{
     const support=planMowerExhaustSupport(data,members,options())
     if(support&&Object.keys(support).length){
      const supportTask=new MowerTask({time:s.time,type:T.SELF_CORRECTION,plan:support});supportTask.exhaustSupport=true;supportTask.ordinaryCoordination=task.ordinaryCoordination;supportTask.coordinationRequestNames=[...members]
      queue.tasks.push(supportTask);skipPlanning=true
      const dependencies=mowerReplacementDependencyNames(data,members),rooms=[...new Set([...dependencies].flatMap(name=>{const op=data.operators[name];return op?[op.room,op.currentRoom].filter(Boolean):[]}).concat(data.allDorms().map(bed=>bed.position[0])))]
      retainMowerFailedTask(s,data,task,'等待替班交接完成',rooms);task.coordinationDependencyWait=true
     }
     else {
      options().onBlocked(members);skipPlanning=true
      const dependencies=mowerReplacementDependencyNames(data,members),rooms=[...new Set([...dependencies].flatMap(name=>{const op=data.operators[name];return op?[op.room,op.currentRoom].filter(Boolean):[]}).concat(data.allDorms().map(bed=>bed.position[0])))]
      retainMowerFailedTask(s,data,task,'替班或床位依赖尚未释放',rooms);task.coordinationDependencyWait=true
     }
    }
    if(!task.executionFailure)queue.consume(task)
    if(queue.find({ignoreRunOrders:s.config.mowerTaskScheduling?.adjustForRunOrders===false})?.type===T.SHIFT_ON)backup('AFTER_PLANNING',task)
   }else{
     data.pendingGroupTransitions={...mowerArrangementGroupTransitions(data,running?.intent??task.plan),...task.groupShiftTransitions}
     const intent=running?.intent??structuredClone(task.plan),positions=running?.positions??Object.fromEntries(Object.values(data.operators).map(op=>[op.name,[op.currentRoom,op.currentIndex] as [string,number]])),steps=running?.steps??executeMowerTaskArrangementSteps(task,queue,{
      protectShift:mowerProtectedShift(task),alpha:data.alpha,adjustForRunOrders:s.config.mowerTaskScheduling?.adjustForRunOrders,
     backup,
     arrangeRoom:(room,names,getTime,current,restoration)=>arrangeRoomSteps(s,rates,room,names,getTime,current,restoration),
     metadata:()=>{const actual=getMowerSourceRuntime(s).data;if(actual.alpha)commitMowerGroupShifts(actual,{...mowerArrangementGroupTransitions(actual,intent),...task.groupShiftTransitions});planMowerMetadata(actual,queue,dependencyReturn)},
     corrections:()=>{readAgentMood(s,rates);const correction=planMowerCorrection(getMowerSourceRuntime(s).data,queue,true,task,false,skip,s.config.mowerTaskScheduling);return correction?[correction]:[]},
     prepareRelease:current=>{
      const actual=getMowerSourceRuntime(s).data,rooms=new Map<string,number[]>()
      for(const name of mowerMandatoryReleaseNames(actual,current)){
       const op=actual.operators[name]!,bed=actual.getDormByName(name)?.[1]
       if(bed)bed.timeMicros=undefined
       const indexes=rooms.get(op.currentRoom)??[];indexes.push(op.currentIndex);rooms.set(op.currentRoom,indexes)
      }
      for(const [room,indexes] of rooms)observeRoom(s,rates,room,current,indexes)
      return prepareMowerRelease(actual,queue,current,s.config.mowerTaskScheduling)
     },
     deferRoom:(room,current)=>deferMowerAlphaDorm(current,queue.tasks,room,getMowerSourceRuntime(s).data.nowMicros,s.config.mowerTaskScheduling),
     skip
    })
    if(data.alpha&&!task.idleDormShiftGroups&&[T.SHIFT_OFF,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER].includes(task.type)){
     const groups:Record<string,string[]>={}
     for(const [room,row] of Object.entries(intent))if(room.startsWith('dorm'))for(const name of row){const op=data.operators[name];if(op?.isHigh()&&op.group&&!op.room.startsWith('dorm')&&!op.workaholic&&!op.isResting())(groups[op.group]??=[]).push(name)}
     task.idleDormShiftGroups=Object.fromEntries(Object.entries(groups).filter(([,names])=>names.length>=2))
    }
    let lastBoundary=running?.lastBoundary
    const resume=()=>{
     if(lastBoundary&&(!lastBoundary.nativeRunOrderIO||lastBoundary.returnsInfraMain)&&s.mowerUI)s.mowerUI.scene='INFRA_MAIN'
     const next=steps.next();lastBoundary=next.done?undefined:next.value
     const observed=getMowerSourceRuntime(s).data
     if(observed.alpha){
      recordMowerUrgentSupport(observed,task,queue.tasks,positions)
      recordMowerUrgentRecovery(observed,task,queue.tasks)
      reconcileMowerUrgentRecovery(observed)
     }
     return next
    }
    let next=resume()
    const boundaryDelay=()=>next.done?0:next.value.nativeRunOrderIO?next.value.delayMicros:s.config.mowerDeviceTiming?.roomReturnMicros??0
    let delay=boundaryDelay()
    if(!Number.isSafeInteger(delay)||delay<0)throw new Error('Invalid Mower device clock')
    while(!next.done&&delay===0){next=resume();delay=boundaryDelay()}
    if(!next.done){source.execution={task,steps,wakeMicros:data.nowMicros+delay,intent,data:running?.data??data,lastBoundary:next.value,positions};break}
    delete source.execution
    data.pendingGroupTransitions={}
    const success=next.value,eventData=running?.data??data
    skipPlanning=!success||task.type===T.RE_ORDER
    if(success&&data.alpha){
     commitMowerGroupShifts(getMowerSourceRuntime(s).data,{...mowerArrangementGroupTransitions(data,intent),...task.groupShiftTransitions})
     const actual=getMowerSourceRuntime(s).data,off:string[]=[],on:string[]=[]
     for(const op of Object.values(actual.operators))if(op.isHigh()&&!op.room.startsWith('dorm')){
      const old=positions[op.name];if(!old)continue
      if(old[0]&&!old[0].startsWith('dorm')&&op.isResting())off.push(op.name)
      if((old[0]!==op.room||old[1]!==op.index)&&op.currentRoom===op.room&&op.currentIndex===op.index)on.push(op.name)
     }
     recordMowerUrgentSupport(actual,task,queue.tasks,positions)
     recordMowerUrgentRecovery(actual,task,queue.tasks)
     reconcileMowerUrgentRecovery(actual)
     if(off.length)s.events.push({time:s.time,type:'shift-off',operators:off})
     if(on.length)s.events.push({time:s.time,type:'shift-on',operators:on,...(task.type===T.SELF_CORRECTION?{reason:'position-correction' as const}:{})})
    }else if(success&&[T.SHIFT_OFF,T.SHIFT_ON,T.SELF_CORRECTION].includes(task.type)){
     const names=task.type===T.SHIFT_OFF?Object.values(eventData.operators).filter(op=>op.isHigh()&&!op.room.startsWith('dorm')&&Object.entries(intent).some(([room,slots])=>op.room===room&&slots[op.index]!=='Current'&&slots[op.index]!==op.name)).map(o=>o.name):Object.values(intent).flat().filter(n=>eventData.operators[n]?.isHigh()&&!eventData.operators[n]!.room.startsWith('dorm'))
      if(task.type===T.SHIFT_ON||task.type===T.SELF_CORRECTION)for(const name of names){
      const op=eventData.operators[name]!
      if(op.currentRoom===op.room&&op.currentIndex===op.index)eventData.recentShiftOnByRestUnit.set(mowerRestUnitKey(op),eventData.nowMicros)
     }
     if(names.length)s.events.push({time:s.time,type:task.type===T.SHIFT_OFF?'shift-off':'shift-on',operators:names,...(task.type===T.SELF_CORRECTION?{reason:'position-correction' as const}:{})})
    }
   }
   }catch(error){
    // The driver can fail after a yield, outside the executor's try/finally.
    if(!(data.alpha&&error instanceof MowerRoomArrangementDeferred))task.backupShiftActive=false
    rethrowMowerInfraFatal(error)
    if(error instanceof MowerBackupRecoveryBlocked&&parkMowerBackupDepartureRecovery(source,task,error,s.mowerShiftModel?.observationNames)){delete source.execution;delete source.activeTask;source.error=false;continue}
    s.diagnostics.push({code:'mower-task-exception',message:error instanceof Error?error.message:String(error)})
    delete source.execution
    if(data.alpha&&error instanceof MowerRoomArrangementDeferred){
     deferMowerArrangementRetry(task,queue,error.room,data.nowMicros);skip();skipPlanning=true
     if(s.mowerUI){s.mowerUI.scene='INFRA_MAIN';s.mowerUI.lastRoom=''}
    }else{
    source.error=true;skip();skipPlanning=true
    if(error instanceof MowerShiftPreviewError){
     retainMowerFailedTask(s,data,task,error.message)
     source.error=false
     delete source.activeTask
     continue
    }
    }
   }
  }
  delete source.activeTask // Native infra_main clears self.task before planning (1169).
  // Native planning stays in the same run through real order I/O continuations.
  function* returnToInfraMain():Generator<MowerRoomReturn,void,void>{
   if(!s.mowerUI||['INFRA_MAIN','INFRA_TODOLIST'].includes(s.mowerUI.scene))return
   if(s.mowerUI.scene!=='INFRA_DETAILS')throw new Error('Native scene graph input is unavailable for '+s.mowerUI.scene)
   // graph.py infra_back directly calls BaseSolver.back(), whose default sleep is one second.
   yield {room:s.mowerUI.lastRoom,delayMicros:1_000_000,nativeRunOrderIO:true}
   s.mowerUI.scene='INFRA_MAIN';s.mowerUI.lastRoom=''
  }
  function* planningSteps():Generator<MowerRoomReturn,void,void>{
   yield* returnToInfraMain()
   if(skipPlanning||queue.find({time:s.time+1/60,ignoreRunOrders:s.config.mowerTaskScheduling?.adjustForRunOrders===false}))skip()
   if(!source.runFlags!.planned){
    try {
    if(source.planningMoodRefreshNames){
     const current=getMowerSourceRuntime(s).data,rooms=new Map<string,number[]>()
     for(const name of source.planningMoodRefreshNames){
      const op=current.operators[name];if(!op?.currentRoom)continue
      const indexes=rooms.get(op.currentRoom)??[]
      indexes.push(op.currentIndex);rooms.set(op.currentRoom,indexes)
     }
     delete source.planningMoodRefreshNames
     for(const [room,indexes] of rooms)observeRoom(s,rates,room,undefined,indexes)
    }
    readAgentMood(s,rates)
    if(!planMowerCorrection(getMowerSourceRuntime(s).data,queue,false,undefined,true,skip,s.config.mowerTaskScheduling)){
     let tailShouldRun=true
     if(rates.mowerRunOrderIO){
      const [state,seam]=mowerRunOrderContext(s)
      const result=yield* bridgeMowerNativeIO(runDefaultTradeSegment(state,seam),request=>rates.mowerRunOrderIO!(request,s))
      tailShouldRun=result.tailShouldRun
     }else if(Object.keys(getMowerSourceRuntime(s).data.runOrderRooms).length&&!s.diagnostics.some(d=>d.code==='mower-run-order-io-unavailable')){
      s.diagnostics.push({code:'mower-run-order-io-unavailable',message:'Native run-order lifecycle observations are absent; full Mower parity is unavailable'})
     }
     if(tailShouldRun)scheduleFiaAndExhaust(s,rates)
     planMowerOrdinary(getMowerSourceRuntime(s).data,queue,options())
     if(getMowerSourceRuntime(s).data.alpha){
      const current=getMowerSourceRuntime(s).data;fillMowerAlphaEmptyDorms(current,queue,options(),true)
      if(current.freeRoom||!queue.find({time:s.time+5/60,ignoreRunOrders:s.config.mowerTaskScheduling?.adjustForRunOrders===false}))planMowerAlphaDormFill(current,queue,false,s.config.mowerTaskScheduling)
     }
     if(!mowerPlanningHasNearTask(getMowerSourceRuntime(s).data,queue,s.config.mowerTaskScheduling)){
      readAgentMood(s,rates);if(!planMowerCorrection(getMowerSourceRuntime(s).data,queue,false,undefined,false,skip,s.config.mowerTaskScheduling))backup('END')
     }
    }else skip()
    }catch(error){
     rethrowMowerInfraFatal(error)
     s.diagnostics.push({code:'mower-planning-exception',message:error instanceof Error?error.message:String(error)})
     source.error=true
    }
    source.runFlags!.planned=true
   }
   yield* returnToInfraMain()
   let retryTimes=3
   while(!source.runFlags!.todoTask){
    try {
    if(rates.mowerTodoTaskIO&&rates.mowerClueIO){
     const settings=s.config.mowerServices
     const todoState:MowerTodoTaskState={
      queue,flags:source.runFlags!,enableParty:settings?.enableParty??true,
      get lastClueMicros(){return source.lastClueMicros??null},set lastClueMicros(value){source.lastClueMicros=value},
      get droneRoom(){return s.config.mowerDroneRoom??null},get runOrderRooms(){return []},
      get droneTimeMicros(){return source.droneTimeMicros??null},set droneTimeMicros(value){source.droneTimeMicros=value},
      droneIntervalHours:settings?.droneIntervalHours??3,reloadRooms:settings?.reloadRooms??null,
      get reloadTimeMicros(){return source.reloadTimeMicros??null},set reloadTimeMicros(value){source.reloadTimeMicros=value},
      maaGapHours:settings?.maaGapHours??3,
     }
     yield* bridgeMowerNativeIO(executeMowerTodoTask(todoState,{nowMicros:()=>toMowerMicros(s.time)}),request=>{
      if(request.kind==='reload')return (function*(){
       const reloadState={rooms:request.rooms,reloadTimeMicros:source.reloadTimeMicros??null,width:1920,height:1080,waitingScenes:[]}
       const value=yield* bridgeMowerNativeIO(executeMowerReload(reloadState,{nowMicros:()=>toMowerMicros(s.time),isMowerExit:error=>error instanceof MowerExitError}),step=>{
        if(!rates.mowerReloadIO)throw new Error('Native nonempty reload lifecycle observations are unavailable')
        return rates.mowerReloadIO(step,s)
       })
       return {kind:request.kind,observedAtMicros:toMowerMicros(s.time),value:{result:value,reloadTimeMicros:reloadState.reloadTimeMicros}}
      })()
      if(request.kind!=='clue-new')return rates.mowerTodoTaskIO!(request,s)
      return (function*(){const value=yield* clueSteps(false);return {kind:request.kind,observedAtMicros:toMowerMicros(s.time),value}})()
     })
    }else{
     if(!s.diagnostics.some(d=>d.code==='mower-todo-io-unavailable'))s.diagnostics.push({code:'mower-todo-io-unavailable',message:'Native clue/drone/reload lifecycle input is unavailable in this decision-only run'})
     source.runFlags!.todoTask=true
    }
    }catch(error){
     if(!(error instanceof MowerRecognizeError))throw error
     s.diagnostics.push({code:'mower-todo-recognize-retry',message:error.message})
     --retryTimes
     yield {room:'',delayMicros:3_000_000,nativeRunOrderIO:true}
     if(retryTimes===0){source.baseRunAborted=true;return}
    }
   }
   if(rates.mowerNotificationIO){
    const notificationState={queue,flags:source.runFlags!,
     get collectRecycle(){return s.config.mowerRecycleBuilt||Object.prototype.hasOwnProperty.call(s.config.mowerSourcePlan??{},'recycle')},
     get lastTodoMicros(){return source.lastTodoMicros??null},set lastTodoMicros(value:number|null){source.lastTodoMicros=value}}
    retryTimes=3
    while(!source.runFlags!.collectNotification||rates.mowerTodoListVisible?.()){
    try {
    const seam={nowMicros:()=>toMowerMicros(s.time)}
    yield* returnToInfraMain()
    if(!source.runFlags!.collectNotification){
     yield* bridgeMowerNativeIO(collectMowerInfraNotification(notificationState,seam),request=>rates.mowerNotificationIO!(request,s),()=> '')
     // BaseSolver.run resets its budget after each successful transition.
     retryTimes=3
    }
    while(rates.mowerTodoListVisible?.()){
     yield* bridgeMowerNativeIO(collectMowerTodoList(notificationState,seam),request=>rates.mowerNotificationIO!(request,s),()=> '')
     retryTimes=3
    }
    break
    }catch(error){
     if(!(error instanceof MowerRecognizeError))throw error
     s.diagnostics.push({code:'mower-notification-recognize-retry',message:error.message})
     --retryTimes
     yield {room:'',delayMicros:3_000_000,nativeRunOrderIO:true}
     if(retryTimes===0){source.baseRunAborted=true;return}
    }
    }
   }
  }
  const phaseSteps=runningPhase?.steps??planningSteps()
  let phaseNext=phaseSteps.next()
  while(!phaseNext.done&&phaseNext.value.delayMicros===0)phaseNext=phaseSteps.next()
  if(!phaseNext.done){
   // Planning may yield for native order/notification I/O after an empty preview.
   // Retain that decision until the whole run finishes, including repeated yields.
   source.phaseExecution={steps:phaseSteps,wakeMicros:toMowerMicros(s.time)+phaseNext.value.delayMicros,skipPlanning,previewNoop}
   break
  }
  delete source.phaseExecution
  // A completed native phase may release a real reservation. Admit that work before
  // the existing outer-run clock is selected; a next-action query must not discover it late.
  resumeMowerFailedTasks(s,getMowerSourceRuntime(s).data,queue)
  if(source.baseRunAborted){
   delete source.baseRunAborted
   source.runReturn={wakeMicros:toMowerMicros(s.time)+(clock?.minimumClockStepMicros??1),finishFallback:false}
   break
  }
  if(clock){
   // Source notification branch with no notification detected advances one second.
   // Recognition/transport are separate zero-time seams; near tasks skip this branch.
   if(source.error)prepareMowerRunEntry(queue,data.nowMicros,data.alpha,s.config.mowerTaskScheduling)
   const notification=!source.runFlags?.collectNotification&&!skipPlanning&&!queue.find({time:s.time+1/60,ignoreRunOrders:s.config.mowerTaskScheduling?.adjustForRunOrders===false})?clock.notificationSleepMicros:0
   const due=queue.tasks.filter(t=>!t.executionFailure&&t.timeMicros<=data.nowMicros&&(s.config.mowerTaskScheduling?.adjustForRunOrders!==false||!isMowerRunOrderTask(t)))
   if(previewNoop&&due.length&&due.every(t=>[T.SHIFT_ON,T.SHIFT_OFF,T.EXHAUST_OFF,T.SELF_CORRECTION,T.RE_ORDER,T.FILL_DORM,T.NOT_SPECIFIC].includes(t.type))){
    source.runReturn={wakeMicros:nextMowerDecisionMicros(s,rates),finishFallback:false}
   }else if(notification>0)source.runReturn={wakeMicros:data.nowMicros+notification,finishFallback:true}
   else {
    source.runFlags!.collectNotification=true
    queue.ensureFallback(s.time,s.config.mowerTaskScheduling)
    if(queue.tasks.some(t=>!t.executionFailure&&t.timeMicros<=data.nowMicros))source.runReturn={wakeMicros:data.nowMicros+clock.minimumClockStepMicros,finishFallback:false}
   }
   break
  }
  source.runFlags!.collectNotification=true
  if(source.error)prepareMowerRunEntry(queue,data.nowMicros,false,s.config.mowerTaskScheduling)
  else queue.ensureFallback(s.time,s.config.mowerTaskScheduling)
 }
 if(pass===256)throw new Error('Mower source task chain did not converge '+JSON.stringify({queue:queue.tasks.slice(0,4).map(t=>({type:t.type.key,plan:t.plan,time:t.time})),trace:source.trace.slice(-5)}))
 queue.sort();projectPublicState(s);source.lastWakeMicros=toMowerMicros(s.time)
}
export function nextMowerSourceActionHours(s:RuntimeState,rates?:RuntimeRates):number {
 const source=getMowerSourceRuntime(s)
 if(!source.execution&&!source.phaseExecution&&resumeMowerPreviewRecovery(source))delete source.runReturn
 if(resumeMowerFailedTasks(s,source.data,source.queue)&&!source.execution&&!source.phaseExecution)delete source.runReturn
 source.queue.sort()
 const running=source.execution?.wakeMicros??source.phaseExecution?.wakeMicros??source.runReturn?.wakeMicros
 if(running===undefined&&rates&&s.config.mowerTaskScheduling?.adjustForRunOrders===false){
  // Physical integration can reach the threshold before its ceil deadline,
  // while the rounded scheduler clock is still one microsecond behind.
  if(!source.planningWake||source.planningWake.timeMicros>source.data.nowMicros+1)source.planningWake=nextMowerMoodPlanningWake(s,source.data,rates)
 }
 if(running===undefined)source.conditionWakeMicros??=s.mowerShiftModel?.nextIdleConditionWakeMicros?.(source.data)
 // New ledger or product observations may wake an idle/sleeping outer run, never an in-flight room operation.
 const observationWake=!source.execution&&!source.phaseExecution?s.mowerBackupObservationWakeMicros?.():undefined
 if(observationWake!==undefined)source.conditionWakeMicros=Math.min(source.conditionWakeMicros??Infinity,observationWake)
 const dispatch=running??Math.min(source.queue.find()?.timeMicros??Infinity,source.planningWake?.timeMicros??Infinity,source.conditionWakeMicros??Infinity)
 const next=Math.min(dispatch,observationWake??Infinity,!source.execution&&!source.phaseExecution?nextMowerPreviewRecoveryObservation(source):Infinity)
 return Math.max(0,(next-source.data.nowMicros)/3_600_000_000)
}
