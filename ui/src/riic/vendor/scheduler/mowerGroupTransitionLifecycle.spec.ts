import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createBackupPlanController} from './backupPlans'
import {describe,expect,it,vi} from 'vitest'
import * as shiftCycle from './mowerShiftCycle'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {coalesceMowerBackupTransition,prepareMowerShiftBackup,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {projectMowerArrangements} from './mowerObservations'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

const rates={workRate:()=>1,recoveryRate:()=>4}
function fixture(){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'A',group:'a',replacement:['X']}],
  room_1_2:[{agent:'B',group:'b',replacement:['Y']}],
  room_1_3:[{agent:'F',group:'a',replacement:['C'],groupBindings:[{group:'a',replacement:['C']},{group:'b',replacement:['D']}]}],
  dormitory_1:['K0','K1','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
 }
 const config:RuntimeConfig={mowerAlpha:true,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((p,index)=>p.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:p.agent,candidates:p.replacement,group:p.group,dormitory:room.startsWith('dorm'),permanent:room.startsWith('dorm')}])),beds:[2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===2})),mowerSourcePlan:rows,mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},initialMorale:{A:4,B:24,F:10},idleOperators:['I0','I1','I2'],mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},mowerDeviceTiming:{roomReturnMicros:500_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 const task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['X'],dormitory_1:['Current','Current','A','F','Current']}})
 source.queue.tasks=[task]
 return {state,source,task}
}
function complete(state:ReturnType<typeof createRosterRuntime>,task:MowerTask){
 for(let i=0;i<30&&getMowerSourceRuntime(state).queue.tasks.includes(task);i++){
  settleRoster(state,rates)
  if(task.executionFailure)break
  if(getMowerSourceRuntime(state).queue.tasks.includes(task))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
}
describe('group transitions follow the physical arrangement lifecycle',()=>{
 it.each([false,true])('discards obsolete unexecuted group intent, explicit backup slots=%s',explicit=>{
  const {state,source,task}=fixture(),time=task.timeMicros
  task.groupShiftTransitions={a:true,b:true}
  if(explicit)task.backupExplicitSlots.add('room_1_1\0'+'0')
  complete(state,task)
  expect(source.queue.tasks).not.toContain(task)
  expect(task.timeMicros).toBe(time)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(state.occupants.room_1_3_0).toBe('C')
  expect(source.data.groupIsResting('a')).toBe(true)
  expect(source.data.groupIsResting('b')).toBe(false)
  expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
 })
 it('still retains a real simultaneous rest conflict without moving either group',()=>{
  const {state,source,task}=fixture()
  task.plan.room_1_2=['Y']
  const original=structuredClone(task.plan)
  settleRoster(state,rates)
  expect(source.queue.tasks).toContain(task)
  expect(task.executionFailure?.reason).toContain('共享替班冲突')
  expect(task.plan).toEqual(original)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(state.occupants.room_1_2_0).toBe('B')
 })
 it('checks a fresh ordinary plan after the backup cancels its conflicting departure',()=>{
  const {state,source,task}=fixture()
  task.plan.room_1_2=['Y'];task.plan.dormitory_1=['Current','Current','A','B','F']
  task.type=T.SELF_CORRECTION;task.ordinaryCoordination=true;task.coordinationRequestNames=['A','B']
  state.mowerShiftModel={count:1,evaluate:d=>[d.operators.A!.isResting()],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];next.operators.B!.exhaustRequire=!!c[0];if(c[0])next.operators.F!.groupBindings[0]!.replacement=['D'];return next},transition:()=>({}),activate:()=>{}}
  complete(state,task)
  expect(task.executionFailure).toBeUndefined()
  expect(source.queue.tasks).not.toContain(task)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(state.occupants.room_1_3_0).toBe('D')
 })
 it.each(['fresh','started','backup-active','product-locked'] as const)('preserves explicit shared slots during %s execution preflight',kind=>{
  const {state,source,task}=fixture()
  task.plan.room_1_2=['Y'];task.plan.dormitory_1=['Current','Current','A','B','F']
  if(kind!=='fresh'){task.plan.room_1_3=['D'];task.backupExplicitSlots.add('room_1_3\0'+'0')}
  if(kind==='started')task.arrangementStarted=true
  if(kind==='backup-active')task.backupShiftActive=true
  if(kind==='product-locked')task.productShiftLocked=true
  state.mowerShiftModel={count:1,evaluate:()=>[true],swap:(data,conditions)=>{const next=projectMowerArrangements(data,[]);next.planConditions=[...conditions];return next},explicitSlots:()=>new Set(['room_1_3\0'+'0']),transition:()=>({room_1_3:['D']}),activate:()=>{}}
  complete(state,task)
  expect(task.executionFailure).toBeUndefined()
  expect(state.occupants.room_1_3_0).toBe('D')
  expect(source.queue.tasks).not.toContain(task)
 })
 it('restores an unstarted task and queue after a failed preview adds projected state',()=>{
  const {state,source,task}=fixture()
  source.initial=false
  const independent=new MowerTask({time:1}),pending=[task,independent];source.queue.tasks=[...pending]
  const before=structuredClone(task),keys=Object.keys(task).sort(),fallback=source.data.operators.A!.dormMoodFallback
  const preview=vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementationOnce((_data,current,queue)=>{
   current.plan={room_1_1:['Y']};current.backupShiftIntent={room_1_2:['Y']};current.backupShiftConditions=[true];current.backupExplicitSlots.add('room_1_2\0'+'0');current.previewReturnVeto={conditions:[0],names:['B']};Reflect.set(current,'uncommittedPreviewProof',true)
   queue.tasks=[current];source.data.operators.A!.dormMoodFallback='dormitory_1'
   throw new MowerShiftPreviewError('injected final validation failure')
  })
  try{settleRoster(state,rates)}finally{preview.mockRestore()}
  expect(source.queue.tasks).toContain(task);expect(source.queue.tasks).toContain(independent)
  expect(task.plan).toEqual(before.plan);expect(task.timeMicros).toBe(before.timeMicros)
  expect(task.backupShiftIntent).toBeUndefined();expect(task.backupShiftConditions).toBeUndefined();expect(task.previewReturnVeto).toBeUndefined();expect(task.backupExplicitSlots).toEqual(before.backupExplicitSlots)
  expect(Object.keys(task).sort()).toEqual(keys)
  expect(task.groupShiftTransitions).toEqual(before.groupShiftTransitions)
  expect(Reflect.has(task,'uncommittedPreviewProof')).toBe(false)
  expect(source.data.operators.A!.dormMoodFallback).toBe(fallback)
 })
 it('resumes only remaining rooms after an interrupted physical arrangement',()=>{
  const {state,source,task}=fixture()
  settleRoster(state,rates)
  expect(source.execution?.task).toBe(task)
  expect(task.plan.room_1_1).toBeUndefined()
  expect(task.arrangementStarted).toBe(true)
  const originalTime=task.timeMicros,remaining=structuredClone(task.plan)
  // A driver error drops its generator and releases the process lock.
  delete source.execution;task.backupShiftActive=false
  source.queue.tasks=[task]
  settleRoster(state,rates)
  expect(task.groupShiftTransitions.a).toBe(true)
  expect(task.plan.room_1_1).toBeUndefined()
  expect(source.trace[source.trace.length-1]?.plan).toEqual(remaining)
  complete(state,task)
  expect(source.queue.tasks).not.toContain(task)
  expect(task.timeMicros).toBe(originalTime)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_3_0).toBe('C')
  expect(source.data.groupIsResting('a')).toBe(true)
 })
 it('does not coalesce or re-preview an interrupted physical arrangement',()=>{
  const {state,source,task}=fixture()
  settleRoster(state,rates)
  const remaining=structuredClone(task.plan),transitions={...task.groupShiftTransitions}
  delete source.execution;task.backupShiftActive=false
  const model:MowerShiftModel={count:1,evaluate:()=>{throw new Error('must not re-preview')},swap:d=>d,transition:()=>({}),activate:()=>{}}
  prepareMowerShiftCycle(source.data,task,source.queue,model)
  prepareMowerShiftBackup(source.data,task,model)
  const merged=coalesceMowerBackupTransition(source.data,{room_1_3:['F']},[task])
  expect(merged.consumed).toEqual([])
  expect(task.plan).toEqual(remaining)
  expect(task.groupShiftTransitions).toEqual(transitions)
 })
 it('rebuilds a fresh preview from its original intent rather than earlier added groups',()=>{
  const {source,task}=fixture()
  const data=source.data
  for(const op of Object.values(data.operators))if(op.isHigh())Object.assign(op,{currentRoom:op.room,currentIndex:op.index,mood:24,timeStampMicros:0})
  task.groupShiftTransitions={a:true,b:true}
  task.backupShiftIntent=structuredClone(task.plan)
  const queue=new MowerTaskQueue();queue.tasks=[task]
  const model:MowerShiftModel={count:0,evaluate:d=>d.planConditions,swap:d=>d,transition:()=>({}),activate:()=>{}}
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.groupShiftTransitions).toEqual({a:true})
  expect(task.plan.room_1_2).toBeUndefined()
 })
 it('retains confirmed group transitions across room-return boundaries',()=>{
  const {state,source,task}=fixture()
  settleRoster(state,rates)
  expect(source.execution?.task).toBe(task)
  expect(task.plan.room_1_1).toBeUndefined()
  expect(task.groupShiftTransitions.a).toBe(true)
  complete(state,task)
  expect(source.queue.tasks).not.toContain(task)
  expect(state.occupants.room_1_3_0).toBe('C')
  expect(source.data.groupIsResting('a')).toBe(true)
 })
})


describe('backup task deactivation preserves a displaced primary',()=>{
 it.each([false,true])('retains newly triggered explicit entry slots through self-deactivation and later exhaustion=%s',exhaust=>{
  const workspace=createDefaultWorkspace()
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:'a',replacements:['char_240_wyvern']}]
  workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))
  workspace.compatibility.backupPlans=[{name:'departure',trigger:"op_data.operators['芬'].is_working()",plan:{},task:{room_1_1:['香草']}}]
  if(exhaust)workspace.compatibility.backupPlans.push({name:'exhaust',trigger:"op_data.operators['芬'].is_working() != True",conf:{exhaust_require:'芬'}})
  const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule);config.mowerAlpha=true
  const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
  source.data.operators.char_123_fang!.setProjectedPosition('room_1_1',0)
  const task=new MowerTask({type:T.SELF_CORRECTION,plan:{dormitory_1:['Current','Current','Current','Current','Free']}})
  task.ordinaryCoordination=true;task.coordinationRequestNames=['char_123_fang']
  prepareMowerShiftBackup(source.data,task,state.mowerShiftModel!)
  expect(task.plan.room_1_1).toEqual(['char_240_wyvern'])
  expect([...task.backupExplicitSlots]).toEqual(['room_1_1\0'+'0','dormitory_1\0'+'0'])
  expect(task.plan.dormitory_1?.[0]).toBe('char_123_fang')
  expect(controller.active).toEqual(exhaust?[false,false]:[false])
  expect(state.occupants.room_1_1_0).toBe('char_123_fang')
 })
 it('admits an observed idle primary to rest when an explicit departure cancels its correction return',()=>{
  const workspace=createDefaultWorkspace()
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:'a',replacements:['char_240_wyvern']}]
  workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))
  workspace.mainPlan.facilities.dormitory_1.slots[4]={occupant:{kind:'operator',operatorId:'char_179_cgbird'},groupId:null,replacements:[]}
  workspace.compatibility.backupPlans=[{name:'departure',trigger:"op_data.operators['芬'].is_working()",plan:{},task:{room_1_1:['香草']}}]
  const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule);config.mowerAlpha=true
  const state=createRosterRuntime(config);createBackupPlanController(schedule,state)
  const source=getMowerSourceRuntime(state),data=source.data
  for(const op of Object.values(data.operators))Object.assign(op,{currentRoom:'',currentIndex:-1,mood:24,timeStampMicros:0,depletionRate:0})
  data.operators.char_123_fang!.mood=4
  data.operators.char_240_wyvern!.setProjectedPosition('room_1_1',0)
  data.operators.char_179_cgbird!.setProjectedPosition('dormitory_1',4)
  data.groupShiftState.a=true
  const task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['char_123_fang']}})
  source.queue.tasks=[task]
  prepareMowerShiftCycle(data,task,source.queue,state.mowerShiftModel!)
  expect(task.plan.room_1_1?.includes('char_123_fang')).not.toBe(true)
  expect(task.plan.dormitory_1).toContain('char_123_fang')
  expect(task.groupShiftTransitions.a).not.toBe(false)
 })
 it('finishes a one-shot departure whose trigger turns false before dorm admission',()=>{
  const workspace=createDefaultWorkspace()
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:'a',replacements:['char_502_nblade']}]
  workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))
  workspace.compatibility.backupPlans=[{name:'departure',trigger:"op_data.operators['芬'].is_working()",plan:{},task:{room_1_1:['香草']}}]
  const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
  config.mowerAlpha=true;config.initialMorale={...config.initialMorale,char_123_fang:4};config.idleOperators=['idle1','idle2','idle3','idle4','idle5']
  const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state)
  const source=getMowerSourceRuntime(state)
  const finished=()=>state.occupants.room_1_1_0==='char_502_nblade'&&Object.values(state.bedOccupants).includes('char_123_fang')&&!source.execution
  for(let i=0;i<30&&!finished();i++){
   settleRoster(state,rates,0,controller.evaluate)
   if(!finished()){
    const next=nextRosterActionHours(state,rates)
    if(!Number.isFinite(next))break
    advanceRoster(state,Math.max(next,1/3_600_000_000),rates)
   }
  }
  expect(finished()).toBe(true)
  expect(state.occupants.room_1_1_0).toBe('char_502_nblade')
  expect(source.queue.tasks.filter(t=>t.executionFailure)).toEqual([])
  expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
 })
})
