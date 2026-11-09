import {afterEach,describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import * as shiftCycle from '../scheduler/mowerShiftCycle'
import {MowerResourceWaitError,MowerShiftPreviewError} from '../scheduler/mowerNativeErrors'
import * as rosterRuntime from '../scheduler/rosterRuntime'
import {getMowerSourceRuntime} from '../scheduler/mowerSourceRuntime'
import {simulateSchedule} from './scheduleSimulation'
import {OPERATORS} from '../domain/operators'
import {MowerTask,MOWER_TASK_TYPES as T} from '../scheduler/mowerTaskQueue'
import * as productionTimeline from './productionTimeline'

function schedule(){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
 const manufacture=workspace.mainPlan.facilities.room_1_1
 manufacture.level=3;manufacture.product='gold';manufacture.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
 workspace.mainPlan.conf.workaholic=['char_123_fang','char_240_wyvern']
 workspace.compatibility.backupPlans=[{name:'forced correction',trigger:'True',plan:{room_1_1:{plans:[{agent:'香草',group:'',replacement:['芬']}]}}}]
 return compileRosterSchedule(workspace,{idleOperators:[]})
}
afterEach(()=>vi.restoreAllMocks())

function mandatoryRecoverySchedule(automatic=false){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
 const manufacture=workspace.mainPlan.facilities.room_1_1
 manufacture.level=3;manufacture.product='gold'
 manufacture.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:'recovery',replacements:['char_240_wyvern']}]
 workspace.mainPlan.conf.rest_in_full=automatic?[]:['char_123_fang']
 const dorm=workspace.mainPlan.facilities.dormitory_1;dorm.level=5
 dorm.slots=[{occupant:{kind:'operator',operatorId:'char_501_durin'},groupId:null,replacements:[]},{occupant:{kind:'free'},groupId:null,replacements:[]}]
 return compileRosterSchedule(workspace,{idleOperators:[]})
}

function captureMandatoryReturn(kind:'return'|'release',automatic:boolean){
 const create=rosterRuntime.createRosterRuntime
 let runtime:rosterRuntime.RuntimeState|undefined
 const task=new MowerTask(kind==='return'?{type:T.SHIFT_ON,time:0,plan:{room_1_1:['char_123_fang']}}:{type:T.RELEASE_DORM,time:0,plan:{dormitory_1:['Current','Free']},metadata:'char_123_fang'})
 // A started return must preserve its remaining workplace instead of being rebuilt.
 task.arrangementStarted=kind==='return'
 vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>{
  const state=runtime=create(config),source=getMowerSourceRuntime(state),data=source.data
  source.initial=false;source.firstInit=false
  state.occupants.room_1_1_0='char_240_wyvern'
  const bed=state.config.beds[0]!
  state.bedOccupants[bed.id]='char_123_fang';state.morale.char_123_fang=10
  Object.assign(data.operators.char_123_fang!,{currentRoom:bed.roomId,currentIndex:Number(bed.id.split('_').at(-1)),mood:10,timeStampMicros:0})
  Object.assign(data.operators.char_240_wyvern!,{currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0})
  data.dorms[0]!.name='char_123_fang';data.dorms[0]!.timeMicros=undefined
  data.groupShiftState.recovery=true
  if(automatic){data.groupRecoveryFullMembers.recovery=['char_123_fang'];data.groupRecoveryReturnMicros.recovery=0}
  source.queue.tasks=[task]
  return state
 })
 return {task,runtime:()=>runtime!}
}

const mandatoryWaits=[['return',false],['release',false],['return',true],['release',true]] as const

describe('unresolved native task failures in the final income report',()=>{
 it.each(mandatoryWaits)('completes the sampling horizon while the real %s check waits for recovery, automatic=%s',(kind,automatic)=>{
  const captured=captureMandatoryReturn(kind,automatic),originalPlan=structuredClone(captured.task.plan)
  const create=productionTimeline.createProductionTimeline
  let controller:ReturnType<typeof create>|undefined
  vi.spyOn(productionTimeline,'createProductionTimeline').mockImplementation((...args)=>{
   controller=create(...args);vi.spyOn(controller,'finalize');return controller
  })
  const report=simulateSchedule(mandatoryRecoverySchedule(automatic),{schedulingModel:'mower-alpha',sampleHours:2,maxEvents:2000,consumptionOverrides:{char_240_wyvern:0},recoveryOverrides:{char_123_fang:0},production:{outputMode:'potential',droneTarget:'none',expectationMode:true,theoreticalMode:true}})
  const state=captured.runtime(),source=getMowerSourceRuntime(state)
  expect(report.elapsedHours,JSON.stringify(report.diagnostics)).toBe(2)
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production?.success).toBe(true)
  expect(report.production!.sample.completed.gold).toBeGreaterThan(0)
  expect(controller!.finalize).toHaveBeenCalledOnce()
  expect(source.queue.tasks).toContain(captured.task)
  expect(source.queue.tasks.filter(task=>task===captured.task)).toHaveLength(1)
  expect(captured.task.timeMicros).toBe(0)
  expect(captured.task.plan).toEqual(originalPlan)
  expect(captured.task.executionFailure?.kind).toBe('resource-wait')
  expect(captured.task.executionFailure?.reason).toContain('组员尚未确认回满心情')
  expect(state.occupants.room_1_1_0).toBe('char_240_wyvern')
  expect(Object.values(state.bedOccupants)).toContain('char_123_fang')
  expect(source.data.operators.char_123_fang!.timeStampMicros).toBe(0)
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'MOWER_PENDING_RESOURCE_WAIT'}))
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(false)
 })
 it.each(mandatoryWaits)('resumes the same real %s after a new full recovery observation, automatic=%s',(kind,automatic)=>{
  const captured=captureMandatoryReturn(kind,automatic),originalTime=captured.task.timeMicros
  let observed=false,failure:unknown
  const report=simulateSchedule(mandatoryRecoverySchedule(automatic),{schedulingModel:'mower-alpha',sampleHours:4,maxEvents:2000,consumptionOverrides:{char_123_fang:0,char_240_wyvern:0},recoveryOverrides:{char_123_fang:0},production:{outputMode:'potential',droneTarget:'none',expectationMode:true,theoreticalMode:true}},progress=>{
   if(observed||progress.elapsedHours<1||!captured.task.executionFailure)return
   observed=true;failure=captured.task.executionFailure
   const state=captured.runtime(),data=getMowerSourceRuntime(state).data
   expect(data.operators.char_123_fang!.timeStampMicros).toBe(0)
   expect(captured.task.timeMicros).toBe(originalTime)
   state.morale.char_123_fang=24
   Object.assign(data.operators.char_123_fang!,{mood:24,timeStampMicros:Math.round(state.time*3_600_000_000),moodIsPrediction:false})
   data.dorms[0]!.timeMicros=Math.round(state.time*3_600_000_000)
  })
  const state=captured.runtime(),source=getMowerSourceRuntime(state)
  expect(observed).toBe(true)
  expect(failure).toBeDefined()
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.observedHours).toBeCloseTo(4,7)
  expect(report.production?.success).toBe(true)
  expect(state.occupants.room_1_1_0).toBe('char_123_fang')
  expect(source.queue.tasks).not.toContain(captured.task)
  expect(captured.task.timeMicros).toBe(originalTime)
  expect(captured.task.executionFailure).toBeUndefined()
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE'||d.code==='MOWER_PENDING_RESOURCE_WAIT')).toBe(false)
 })
 it('completes ordinary replacement contention without creating a failed placeholder task',()=>{
  const id=(name:string)=>OPERATORS.find(op=>op.name===name)!.charId
  const workspace=createDefaultWorkspace()
  for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
  for(const [roomId,name] of [['room_1_1','芬'],['room_1_2','香草']] as const){
   const room=workspace.mainPlan.facilities[roomId];room.level=1;room.product='gold'
   room.slots=[{occupant:{kind:'operator',operatorId:id(name)},groupId:null,replacements:[id('克洛丝')]}]
  }
  const dorm=workspace.mainPlan.facilities.dormitory_1;dorm.level=5
  dorm.slots=[...['杜林','闪灵'].map(name=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:null,replacements:[]})),...Array.from({length:3},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))]
  workspace.mainPlan.conf.rest_in_full=['芬','香草'].map(id)
  const input=compileRosterSchedule(workspace,{idleOperators:['安德切尔','梓兰','史都华德'].map(id)})
  const create=rosterRuntime.createRosterRuntime
  let runtime:rosterRuntime.RuntimeState|undefined
  vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>runtime=create(config))
  const report=simulateSchedule(input,{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:2,maxEvents:2000,consumptionOverrides:{[id('芬')]:10,[id('香草')]:5,[id('克洛丝')]:1},recoveryOverrides:{[id('芬')]:1,[id('香草')]:1},production:{outputMode:'potential',droneTarget:'none',seed:42}})
  expect(report.elapsedHours).toBe(2)
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production?.success).toBe(true)
  expect(report.production!.sample.completed.gold).toBeGreaterThan(0)
  expect(runtime!.occupants.room_1_2_0).toBe(id('香草'))
  expect(getMowerSourceRuntime(runtime!).queue.tasks.some(task=>task.type.key==='EXHAUST_OFF'&&task.ordinaryCoordination)).toBe(false)
  expect(getMowerSourceRuntime(runtime!).queue.tasks.some(task=>task.executionFailure)).toBe(false)
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(false)
 })
 it('completes actual production with a warning while preserving an expected resource wait',()=>{
  const create=rosterRuntime.createRosterRuntime
  let runtime:rosterRuntime.RuntimeState|undefined
  vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>runtime=create(config))
  let retained:Parameters<typeof shiftCycle.prepareMowerShiftCycle>[1]|undefined
  let originalPlan:unknown,originalTime:number|undefined,calls=0
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation((_data,task)=>{
   calls++;retained=task;originalPlan=structuredClone(task.plan);originalTime=task.timeMicros
   throw new MowerResourceWaitError('shared replacement remains occupied')
  })
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:4,maxEvents:2000,consumptionOverrides:{char_123_fang:5},production:{outputMode:'potential',droneTarget:'none',seed:42}})
  expect(report.elapsedHours).toBe(4)
  expect(report.observedHours).toBeCloseTo(4,7)
  expect(report.success).toBe(true)
  expect(report.production?.success).toBe(true)
  expect(report.production!.sample.completed.gold).toBeGreaterThan(0)
  expect(calls).toBe(1)
  expect(getMowerSourceRuntime(runtime!).queue.tasks).toContain(retained)
  expect(retained!.timeMicros).toBe(originalTime)
  expect(retained!.plan).toEqual(originalPlan)
  expect(retained!.executionFailure?.kind).toBe('resource-wait')
  expect(runtime!.occupants.room_1_1_0).toBe('char_123_fang')
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'MOWER_PENDING_RESOURCE_WAIT',message:expect.stringContaining('收益按实际在岗情况计算')}))
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(false)
 })
 it('does not turn an exhausted event allowance into a complete result for a resource wait',()=>{
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation(()=>{throw new MowerResourceWaitError('shared replacement remains occupied')})
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:4,maxEvents:1,production:{outputMode:'potential',droneTarget:'none',seed:42}})
  expect(report.elapsedHours).toBeLessThan(4)
  expect(report.success).toBe(false)
  expect(report.production?.success).toBe(false)
  expect(report.diagnostics.some(d=>d.code==='SIMULATION_EVENT_LIMIT')).toBe(true)
 })
 it('continues the full production clock while reporting a retained unresolved task as incomplete',()=>{
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation(()=>{throw new MowerShiftPreviewError('test exhausted preview')})
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:4,maxEvents:2000,consumptionOverrides:{char_123_fang:5},production:{outputMode:'potential',droneTarget:'none',seed:42}})
  expect(report.elapsedHours).toBe(4)
  expect(report.observedHours).toBeCloseTo(4,7)
  expect(report.success).toBe(false)
  expect(report.production?.success).toBe(false)
  expect(report.production!.sample.completed.gold).toBeGreaterThan(0)
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'MOWER_PENDING_TASK_FAILURE',message:expect.stringContaining('test exhausted preview')}))
  expect(report.diagnostics.some(d=>d.code==='SIMULATION_EVENT_LIMIT'||d.code==='SIMULATION_SAME_TIME_ACTION')).toBe(false)
 })
 it('allows full success after a later observation releases and completes the retained task',()=>{
  const create=rosterRuntime.createRosterRuntime
  let runtime:rosterRuntime.RuntimeState|undefined
  vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>runtime=create(config))
  const prepare=shiftCycle.prepareMowerShiftCycle
  let failed=false
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation((...args)=>{
   if(!failed){failed=true;throw new MowerShiftPreviewError('one observed preview failure')}
   return prepare(...args)
  })
  let observed=false
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:8,maxEvents:4000,consumptionOverrides:{char_123_fang:5},production:{outputMode:'potential',droneTarget:'none',seed:42}},progress=>{
   if(observed||!runtime||progress.elapsedHours<1)return
   // Simulate a fresh room observation, independent of the failed task's
   // prediction. The report must reflect its later successful completion.
   const op=getMowerSourceRuntime(runtime).data.operators.char_123_fang!
   op.mood=runtime.morale.char_123_fang!;op.timeStampMicros=Math.round(runtime.time*3_600_000_000);op.moodIsPrediction=false
   observed=true
  })
  expect(failed).toBe(true)
  expect(observed).toBe(true)
  expect(report.elapsedHours).toBe(8)
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production?.success).toBe(true)
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(false)
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'mower-task-exception',message:'one observed preview failure'}))
 })
})
