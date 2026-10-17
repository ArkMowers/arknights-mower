import {parkMowerPreviewRecovery,resumeMowerPreviewRecovery} from './mowerPreviewRecoveryWait'
import {planMowerCorrection} from './mowerCorrection'
import {cloneMowerShiftTask} from './mowerShiftCycle'
import {describe,it,expect} from 'vitest'
import {createRosterRuntime} from './rosterRuntime'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import {prepareMowerRunEntry} from './mowerRunLifecycle'
import {scheduleMowerTasks} from './mowerTaskScheduling'

function fixture(){
 const state=createRosterRuntime({positions:[],beds:[],mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}]}})
 state.mowerFacilityProducts={room_1_1:'gold'}
 const data=new MowerSchedulingData({alpha:true,plan:{room_1_1:['A']},operators:{A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,mood:12,timeStampMicros:0}),R:new MowerOperatorState({name:'R',mood:24,timeStampMicros:0})},dorms:[],nowMicros:0})
 const task=new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['R']}}),queue=new MowerTaskQueue();queue.tasks=[task]
 retainMowerFailedTask(state,data,task,'failed preview')
 return {state,data,task,queue}
}

describe('native task failures retain work and release dispatch',()=>{
 it('does not resume from clock advancement or predictions and preserves the original deadline',()=>{
  const {state,data,task,queue}=fixture()
  state.time=4;data.nowMicros=toMowerMicros(4)
  data.operators.A!.moodIsPrediction=true;data.operators.A!.mood=0;data.operators.A!.timeStampMicros=data.nowMicros
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  expect(task.executionFailure).toBeDefined();expect(task.timeMicros).toBe(0)
  prepareMowerRunEntry(queue,data.nowMicros,true)
  expect(queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
 })
 it.each(['measurement','position','effective-plan','product','backup-conditions'])('resumes after a new relevant %s',change=>{
  const {state,data,task,queue}=fixture()
  if(change==='measurement')data.operators.A!.timeStampMicros=1
  if(change==='position')data.operators.A!.currentRoom='dormitory_1'
  if(change==='effective-plan')state.config.mowerSourcePlan!.room_1_1![0]!.replacement=[]
  if(change==='product')state.mowerFacilityProducts={room_1_1:'exp3'}
  if(change==='backup-conditions')data.planConditions=[true]
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(queue.tasks).toEqual([task]);expect(task.executionFailure).toBeUndefined()
  expect(task.executionRetained).toBe(true);expect(task.timeMicros).toBe(0)
  prepareMowerRunEntry(queue,toMowerMicros(2),true)
  expect(queue.tasks).toContain(task)
  queue.removeDerived();expect(queue.tasks).toContain(task)
 })
 it('ignores unrelated observations and product changes',()=>{
  const {state,data,task,queue}=fixture()
  data.operators.X=new MowerOperatorState({name:'X',currentRoom:'room_2_1',currentIndex:0,mood:3,timeStampMicros:1})
  state.mowerFacilityProducts={room_1_1:'gold',room_2_1:'exp3'}
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  expect(task.executionFailure).toBeDefined()
 })
 it('excludes suspended failures from dispatch and scheduling without rewriting remaining work',()=>{
  const {task,queue}=fixture(),other=new MowerTask({time:1,type:T.FIAMMETTA}),plan=structuredClone(task.plan)
  queue.tasks.push(other);queue.sort()
  expect(queue.find()).toBe(other)
  scheduleMowerTasks(queue.tasks,toMowerMicros(1),{alpha:true,adjustForRunOrders:false})
  expect(queue.find()).toBe(other)
  expect(queue.tasks).toContain(task);expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(0)
  queue.removeDerived();expect(queue.tasks).toContain(task)
 })
})
function derivedCorrectionFixture(){
 const {state,data,queue}=fixture()
 queue.tasks=[]
 data.operators.A!.operatorType='high';data.operators.A!.replacement=['R']
 data.operators.A!.currentRoom='';data.operators.A!.currentIndex=-1
 data.operators.R!.currentRoom='room_1_1';data.operators.R!.currentIndex=0
 const task=planMowerCorrection(data,queue,true)!
 expect(task).toBeDefined();expect(task.derivedCorrection).toBe(true)
 expect(task.plan).toEqual({room_1_1:['A']})
 retainMowerFailedTask(state,data,task,'correction blocked')
 return {state,data,queue,task}
}

describe('observation-derived correction refresh',()=>{
 it('rebuilds through the real planner and failure resume while keeping task identity and deadline',()=>{
  const {state,data,queue,task}=derivedCorrectionFixture(),originalTime=task.timeMicros
  data.nowMicros=toMowerMicros(3)
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  expect(task.plan).toEqual({room_1_1:['A']})
  data.operators.A!.currentRoom='room_1_1';data.operators.A!.currentIndex=0;data.operators.A!.timeStampMicros=data.nowMicros
  data.operators.R!.currentRoom='';data.operators.R!.currentIndex=-1
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(queue.tasks[0]).toBe(task);expect(task.timeMicros).toBe(originalTime)
  expect(task.plan).toEqual({});expect(task.executionFailure).toBeUndefined()
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  expect(cloneMowerShiftTask(task).derivedCorrection).toBe(true)
  expect(JSON.parse(JSON.stringify(task)).derivedCorrection).toBe(true)
 })
 it.each(['unknown','started','backup-active','backup-intent','backup-conditions','backup-explicit','product','support','restoration','strict','retry','metadata'])('preserves %s remaining or explicit requests',kind=>{
  const {state,data,queue,task}=derivedCorrectionFixture()
  if(kind==='unknown')task.derivedCorrection=false
  if(kind==='started')task.arrangementStarted=true
  if(kind==='backup-active')task.backupShiftActive=true
  if(kind==='backup-intent')task.backupShiftIntent=structuredClone(task.plan)
  if(kind==='backup-conditions')task.backupShiftConditions=[true]
  if(kind==='backup-explicit')task.backupExplicitSlots.add('room_1_1\0'+'0')
  if(kind==='product')task.productShiftLocked=true
  if(kind==='support')task.exhaustSupport=true
  if(kind==='restoration')task.dormRecoveryRestore=['A']
  if(kind==='strict')task.strictMoodLimit=true
  if(kind==='retry')task.arrangementRetryRoom='room_1_1'
  if(kind==='metadata')task.metadata='explicit request'
  retainMowerFailedTask(state,data,task,'blocked')
  const plan=structuredClone(task.plan)
  data.operators.A!.currentRoom='room_1_1';data.operators.A!.currentIndex=0;data.operators.A!.timeStampMicros=1
  data.operators.R!.currentRoom='';data.operators.R!.currentIndex=-1
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(0)
 })
})

function groupCorrectionFixture(){
 const {state,data,queue}=fixture();queue.tasks=[]
 Object.assign(data.operators.A!,{operatorType:'high',group:'g',replacement:['R'],currentRoom:'',currentIndex:-1,mood:24})
 Object.assign(data.operators.R!,{currentRoom:'room_1_1',currentIndex:0})
 data.groupShiftState={g:false,unrelated:false}
 const task=planMowerCorrection(data,queue,true)!
 expect(task.plan).toEqual({room_1_1:['A']})
 return {state,data,queue,task}
}
describe('derived corrections after confirmed group changes and preview waits',()=>{
 it('refreshes only after a relevant confirmed group change',()=>{
  const {state,data,queue,task}=groupCorrectionFixture()
  retainMowerFailedTask(state,data,task,'blocked')
  data.groupShiftState.unrelated=true
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  data.groupShiftState.g=true
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(task.plan).toEqual({});expect(queue.tasks[0]).toBe(task);expect(task.timeMicros).toBe(0)
 })
 it('ignores the unrelated group behind a Current slot',()=>{
  const {state,data,queue,task}=groupCorrectionFixture()
  data.plan.room_1_1!.push('B');task.plan.room_1_1!.push('Current')
  data.operators.B=new MowerOperatorState({name:'B',room:'room_1_1',index:1,currentRoom:'room_1_1',currentIndex:1,group:'unrelated',operatorType:'high',mood:24,timeStampMicros:0})
  retainMowerFailedTask(state,data,task,'blocked')
  data.groupShiftState.unrelated=true
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
 })
 it('tracks an inferred resting group when no explicit group state exists',()=>{
  const {state,data,queue,task}=groupCorrectionFixture()
  delete data.groupShiftState.g
  data.operators.P=new MowerOperatorState({name:'P',room:'room_2_1',index:0,currentRoom:'room_2_1',currentIndex:0,group:'g',operatorType:'high',mood:10,timeStampMicros:0})
  retainMowerFailedTask(state,data,task,'blocked')
  data.operators.P!.currentRoom='dormitory_1';data.operators.P!.currentIndex=0
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(task.plan).toEqual({})
 })
 it.each([false,true])('refreshes a released backup-veto wait only for known derived intent; explicit=%s',explicit=>{
  const source=groupCorrectionFixture(),{data,queue,task}=source
  if(explicit)task.derivedCorrection=false
  const original=cloneMowerShiftTask(task)
  task.plan={};task.previewReturnVeto={conditions:[0],names:['A']};data.planConditions=[true]
  expect(parkMowerPreviewRecovery(source,task,original,[task])).toBe(true)
  expect(resumeMowerPreviewRecovery(source)).toBe(false)
  expect(data.waitingRecoveryNames.has('A')).toBe(true)
  data.groupShiftState.g=true
  expect(resumeMowerPreviewRecovery(source)).toBe(true)
  expect(data.waitingRecoveryNames.has('A')).toBe(false)
  expect(task.plan).toEqual(explicit?{room_1_1:['A']}:{})
  expect(queue.tasks[0]).toBe(task);expect(task.timeMicros).toBe(0)
  expect(task.executionFailure).toBeUndefined()
 })
})
