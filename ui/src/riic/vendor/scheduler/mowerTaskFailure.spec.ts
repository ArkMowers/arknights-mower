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
