import {describe,expect,it} from 'vitest'
import {createRosterRuntime,settleRoster,nextRosterActionHours,advanceRoster} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {mowerUpdateDetail} from './mowerObservations'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {syncMowerWorkingReplacementChecks,runMowerWorkingReplacementCheck} from './mowerWorkingReplacement'

const rates={workRate:()=>1,recoveryRate:()=>1}
function fixture(mood=0){
 const s=createRosterRuntime({mowerAlpha:true,mowerRunOrderEnabled:false,mowerTaskScheduling:{adjustForRunOrders:false},
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R','S'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},
   ...['K1','K2','K3','K4'].map((primary,index)=>({id:'dormitory_1_'+index,roomId:'dormitory_1',primary,candidates:[],permanent:true,dormitory:true}))],
  beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:1,R:mood,S:24},idleOperators:[],
  mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R','S']}],dormitory_1:[...['K1','K2','K3','K4'].map(agent=>({agent,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:['A'],lowPriority:[],refreshDrained:[],lingMode:0}})
 s.occupants.room_1_1_0='R';s.bedOccupants.dormitory_1_4='A'
 const source=getMowerSourceRuntime(s);source.initial=false;source.firstInit=false
 for(const op of Object.values(source.data.operators)){
  const room=op.name==='A'?'dormitory_1':op.name==='R'?'room_1_1':op.room
  const index=op.name==='A'?4:op.name==='R'?0:op.index
  mowerUpdateDetail(source.data,op.name,s.morale[op.name]??24,room,index,true)
 }
 source.data.operators.R!.depletionRate=1
 source.data.dorms[0]!.name='A';source.data.dorms[0]!.timeMicros=23*3_600_000_000
 source.queue.tasks=[new MowerTask()]
 return {s,source}
}
describe('working ordinary replacement checks',()=>{
 it('admits a cover check before a resumed phase commits its outer-run boundary',()=>{
  const {s,source}=fixture(1)
  s.config.mowerRunLoopClock={minimumClockStepMicros:1,notificationSleepMicros:1_000_000}
  source.queue.tasks=[]
  source.runFlags={planned:true,todoTask:true,collectNotification:true}
  source.phaseExecution={steps:(function*(){})(),wakeMicros:0,skipPlanning:false,previewNoop:false}
  settleRoster(s,rates)
  const check=source.queue.tasks.find(task=>task.workingReplacementCheck)!
  expect(check).toBeDefined()
  expect(check.timeMicros).toBe(0)
  expect(source.runReturn?.wakeMicros).toBe(1)
  for(let attempt=0;attempt<3;attempt++){
   expect(nextRosterActionHours(s,rates)).toBe(1/3_600_000_000)
   expect(source.queue.tasks.filter(task=>task.workingReplacementCheck)).toEqual([check])
   expect(source.runReturn?.wakeMicros).toBe(1)
  }
  advanceRoster(s,1/3_600_000_000,rates);settleRoster(s,rates)
  expect(check.time).toBeGreaterThan(s.time)
  expect(s.occupants.room_1_1_0).toBe('R')
  expect(s.bedOccupants.dormitory_1_4).toBe('A')
 })
 it('changes an exhausted cover to the next configured cover without recalling its primary',()=>{
  const {s}=fixture();settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('S')
  expect(s.bedOccupants.dormitory_1_4).toBe('A')
 })
 it('keeps the current cover until its personal floor and wakes at that observed-rate deadline',()=>{
  const {s}=fixture(1);settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('R')
  expect(nextRosterActionHours(s,rates)).toBe(1)
  advanceRoster(s,1,rates);settleRoster(s,rates)
  expect(s.occupants.room_1_1_0).toBe('S')
 })
 it('retains the original failure through repeated unchanged dispatch and resumes on a candidate observation',()=>{
  const {s,source}=fixture();source.data.operators.S!.mood=0;s.morale.S=0
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!,originalTime=task.timeMicros
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  const failure=task.executionFailure
  expect(failure).toBeDefined()
  for(let index=0;index<3;index++){
   s.time++;source.data.nowMicros=s.time*3_600_000_000
   syncMowerWorkingReplacementChecks(s,source.data,source.queue)
   expect(source.queue.tasks).toEqual([task]);expect(task.executionFailure).toBe(failure)
   expect(task.timeMicros).toBe(originalTime)
  }
  source.data.operators.S!.mood=10;source.data.operators.S!.timeStampMicros=source.data.nowMicros
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBeUndefined();expect(task.timeMicros).toBe(originalTime)
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks[0]!.plan).toEqual({room_1_1:['S']})
 })
 it('preserves a failed check when another due arrangement reserves the same slot',()=>{
  const {s,source}=fixture();source.data.operators.S!.mood=0;s.morale.S=0
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!,originalTime=task.timeMicros
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  const reservation=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['S']}})
  source.queue.tasks.push(reservation)
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(source.queue.tasks).toContain(task);expect(task.timeMicros).toBe(originalTime)
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  const failure=task.executionFailure
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBe(failure)
  source.queue.consume(reservation)
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(source.queue.tasks).toContain(task);expect(task.timeMicros).toBe(originalTime)
  expect(task.executionFailure).toBeUndefined()
 })
 it('does not release a failed check on predicted mood or a duplicate room read',()=>{
  const {s,source}=fixture();source.data.operators.S!.mood=0;s.morale.S=0
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  const failure=task.executionFailure
  source.data.operators.R!.timeStampMicros=1;source.data.nowMicros=1
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBe(failure)
  source.data.operators.S!.mood=20;source.data.operators.S!.moodIsPrediction=true
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBe(failure)
 })
 it('releases a reserved alternate only after its owning task completes',()=>{
  const {s,source}=fixture(),reservation=new MowerTask({time:5,type:T.SELF_CORRECTION,plan:{room_1_2:['S']}})
  source.queue.tasks=[reservation];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks.find(task=>task.workingReplacementCheck)!
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(task.executionFailure).toBeDefined();expect(source.queue.tasks).toContain(reservation)
  source.queue.consume(reservation);syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBeUndefined()
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(source.queue.tasks[0]!.plan).toEqual({room_1_1:['S']})
 })
 it.each(['coworker','product','refresh'])('rechecks a working deadline after a concrete %s change',kind=>{
  const {s,source}=fixture(5)
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(task.time).toBe(5)
  s.time=1;source.data.nowMicros=3_600_000_000
  if(kind==='coworker'){source.data.operators.K1!.currentRoom='room_1_1';source.data.operators.K1!.currentIndex=1}
  if(kind==='product')s.mowerFacilityProducts={room_1_1:'赤金'}
  if(kind==='refresh')s.config.mowerSourceRules!.refreshDrained=['R']
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.time).toBe(1)
 })
 it('uses a newer depleted card and resumes only when a candidate card supplies new mood evidence',()=>{
  const {s,source}=fixture();source.data.nowMicros=1;s.time=1/3_600_000_000
  source.data.dormMoodEstimates.set('S',[0,1])
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  const failure=task.executionFailure
  expect(failure).toBeDefined()
  source.data.nowMicros=2*3_600_000_000;s.time=2
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBe(failure)
  source.data.dormMoodEstimates.set('S',[10,source.data.nowMicros])
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(task.executionFailure).toBeUndefined()
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(source.queue.tasks[0]!.plan).toEqual({room_1_1:['S']})
 })
 it('waits for a usable depletion observation without requiring a working countdown',()=>{
  const {s,source}=fixture(5);source.data.operators.R!.depletionRate=0
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  const task=source.queue.tasks[0]!
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(task.executionFailure?.reason).toContain('消耗观测')
  source.data.operators.R!.depletionRate=2
  syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  runMowerWorkingReplacementCheck(s,source.data,source.queue,task,()=>{})
  expect(source.queue.tasks).not.toContain(task)
  expect(source.queue.tasks[0]!.time).toBe(2.5)
 })
 it.each(['single','workaholic','primary','training'])('does not schedule an ordinary check for %s',kind=>{
  const {s,source}=fixture()
  if(kind==='single')source.data.operators.A!.replacement=['R']
  if(kind==='workaholic')source.data.operators.R!.workaholic=true
  if(kind==='primary')source.data.operators.R!.operatorType='high'
  if(kind==='training'){
   source.data.plan.train=source.data.plan.room_1_1!;delete source.data.plan.room_1_1
   source.data.operators.R!.currentRoom='train'
  }
  source.queue.tasks=[];syncMowerWorkingReplacementChecks(s,source.data,source.queue)
  expect(source.queue.tasks).toEqual([])
 })
})
