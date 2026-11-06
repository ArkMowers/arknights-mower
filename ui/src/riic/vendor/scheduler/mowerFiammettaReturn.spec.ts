import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {executeMowerTaskArrangement} from './mowerTaskExecutor'
import {queueMowerFiaReturn,prepareMowerFiaReturn} from './mowerFiammetta'
import {planMowerMetadata} from './mowerMetadata'

function fixture(){
 const operators={
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,group:'G',replacement:['R'],operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:1,mood:12,timeStampMicros:0}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,group:'G',replacement:['S'],operatorType:'high',restingPriority:'low',currentRoom:'dormitory_1',currentIndex:2,mood:12,timeStampMicros:0}),
  R:new MowerOperatorState({name:'R',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0}),
  S:new MowerOperatorState({name:'S',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0}),
 }
 const data=new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['FIA','Free','Free']},dorms:[new MowerDormState(['dormitory_1',1],'A',toMowerMicros(4)),new MowerDormState(['dormitory_1',2],'B',toMowerMicros(4))],nowMicros:0,groupRestInFullOnMoodGap:false})
 const queue=new MowerTaskQueue(),charge=new MowerTask({type:T.FIAMMETTA,plan:{dormitory_1:['B','FIA']},metadata:'B'})
 charge.fiaReturnTarget='B';charge.fiaReturnMicros=1_000_000
 queue.tasks.push(charge,new MowerTask({time:4,type:T.SHIFT_ON,plan:{room_1_1:['A'],room_1_2:['B']}}))
 return {data,queue,charge}
}

describe('Fiammetta return after confirmed charge and restoration',()=>{
 it.each([false,true])('does not apply return recovery to charging or restoration, confirmed=%s',confirmed=>{
  const {data,charge}=fixture();charge.fiaChargeConfirmed=confirmed
  data.operators.A!.restInFull=true
  const original=charge.timeMicros
  prepareMowerFiaReturn(data,charge)
  expect(charge.timeMicros).toBe(original)
  data.dorms[0]!.timeMicros=undefined
  expect(()=>prepareMowerFiaReturn(data,charge)).not.toThrow()
  expect(charge.timeMicros).toBe(original)
 })
 it('carries the request through restoration and keeps one independent group return across rebuilds',()=>{
  const {data,queue,charge}=fixture()
  executeMowerTaskArrangement(charge,queue,{
   alpha:true,backup:()=>({changed:false,generated:[]}),metadata:()=>{},
   arrangeRoom:()=>{charge.fiaChargeConfirmed=true;data.operators.B!.mood=24;return {dormitory_1:['FIA','A','B'],room_1_2:['S']}},
  })
  expect(queue.tasks.some(task=>task.fiaReturnTarget&&task.type===T.SHIFT_ON)).toBe(false)
  const restore=queue.tasks.find(task=>task.type===T.FIAMMETTA)!
  expect(restore.fiaReturnTarget).toBe('B');expect(restore.fiaChargeConfirmed).toBe(true)
  executeMowerTaskArrangement(restore,queue,{
   alpha:true,backup:()=>({changed:false,generated:[]}),metadata:()=>{},arrangeRoom:()=>{},
   completeFia:task=>queueMowerFiaReturn(data,queue,task),
  })
  const requested=queue.tasks.find(task=>task.type===T.SHIFT_ON&&task.fiaReturnTarget)!
  expect(requested.plan).toEqual({room_1_1:['A'],room_1_2:['B']})
  for(let n=0;n<3;n++){
   planMowerMetadata(data,queue)
   expect(queue.tasks.filter(task=>task.type===T.SHIFT_ON)).toEqual([requested])
   expect(requested.timeMicros).toBe(1_000_000)
  }
  expect(data.operators.A!.mood).toBe(12)
  expect(data.operators.A!.currentRoom).toBe('dormitory_1')
  queueMowerFiaReturn(data,queue,restore)
  expect(queue.tasks.filter(task=>task.fiaReturnTarget)).toHaveLength(1)
 })
 it('does not force a return without a confirmed exchange',()=>{
  const {data,queue,charge}=fixture()
  queueMowerFiaReturn(data,queue,charge)
  expect(queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.fiaReturnTarget)).toBe(false)
 })
 it('retains explicit full-recovery timing and releases the same request after a new observation',()=>{
  const {data,queue,charge}=fixture();charge.fiaChargeConfirmed=true
  data.operators.B!.mood=24;data.operators.A!.restInFull=true
  queueMowerFiaReturn(data,queue,charge)
  const task=queue.tasks.find(task=>task.type===T.SHIFT_ON&&task.fiaReturnTarget)!
  prepareMowerFiaReturn(data,task)
  expect(task.timeMicros).toBe(toMowerMicros(4))
  data.operators.A!.mood=24
  prepareMowerFiaReturn(data,task)
  expect(task.timeMicros).toBe(1_000_000)
 })
 it('keeps the original request time when required recovery observations are missing',()=>{
  const {data,queue,charge}=fixture();charge.fiaChargeConfirmed=true
  data.operators.B!.mood=24;data.operators.A!.restInFull=true;data.dorms[0]!.timeMicros=undefined
  queueMowerFiaReturn(data,queue,charge)
  const task=queue.tasks.find(task=>task.type===T.SHIFT_ON&&task.fiaReturnTarget)!
  for(let n=0;n<2;n++){
   expect(()=>prepareMowerFiaReturn(data,task)).toThrow('有效恢复观测')
   expect(task.timeMicros).toBe(1_000_000)
  }
  data.operators.A!.mood=24
  expect(()=>prepareMowerFiaReturn(data,task)).not.toThrow()
 })
})
