import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'

function fixture(){
 const operators={A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,group:'G',replacement:['X'],operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:2,mood:24,timeStampMicros:0,lowerLimit:12}),B:new MowerOperatorState({name:'B',currentRoom:'dormitory_1',currentIndex:3,mood:18,timeStampMicros:0}),C:new MowerOperatorState({name:'C',room:'room_1_2',index:0,operatorType:'high',replacement:['Y'],currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0}),X:new MowerOperatorState({name:'X',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0})}
 Object.assign(operators,{K0:new MowerOperatorState({name:'K0',room:'dormitory_1',index:0,operatorType:'high',currentRoom:'dormitory_1',currentIndex:0,mood:24,timeStampMicros:0}),K1:new MowerOperatorState({name:'K1',room:'dormitory_1',index:1,operatorType:'high',currentRoom:'dormitory_1',currentIndex:1,mood:24,timeStampMicros:0}),Y:new MowerOperatorState({name:'Y',mood:24,timeStampMicros:0})})
 const data=new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A'],room_1_2:['C'],dormitory_1:['K0','K1','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',2],'A',0),new MowerDormState(['dormitory_1',3],'B',toMowerMicros(3)),new MowerDormState(['dormitory_1',4])],nowMicros:0,policy:{restingThreshold:.65,rescueThreshold:.25},groupShiftState:{G:true},planConditions:[true],groupRestInFullOnMoodGap:true,groupMoodGapThresholdMinutes:90})
 const model:MowerShiftModel={count:1,evaluate:d=>[d.operators.A!.currentRoom!=='room_1_1'],swap:(original,conditions)=>{
  const next=projectMowerArrangements(original,[])
  next.planConditions=[...conditions]
  if(conditions[0]){Object.assign(next.operators.B!,{room:'',index:-1,group:'',operatorType:'low',restingPriority:'low',lowerLimit:0,replacement:[]});Object.assign(next.operators.C!,{room:'room_1_2',index:0,group:'',operatorType:'high',replacement:['Y']});next.plan.room_1_2=['C']}
  if(!conditions[0]){Object.assign(next.operators.B!,{room:'room_1_2',index:0,group:'G',operatorType:'high',restingPriority:'high',lowerLimit:12,replacement:['C']});Object.assign(next.operators.C!,{room:'',index:-1,group:'',operatorType:'low'});next.plan.room_1_2=['B']}
  return next
 },transition:(_previous,_next,_original,conditions)=>conditions[0]?{}:{room_1_2:['B']},activate:()=>{}}
 const task=new MowerTask({time:0,type:T.SHIFT_ON,plan:{room_1_1:['A']}}),queue=new MowerTaskQueue();queue.tasks=[task]
 return {data,model,task,queue}
}

describe('normal returns account for recovery members restored by backup exit',()=>{
 it.each(['separate','same-room','shared-cover','later-coalesced','third-group','explicit-backup'] as const)('keeps independent return slots at their original time: %s',kind=>{
  const {data,model,task,queue}=fixture(),commonRoom=kind==='same-room',room=commonRoom?'room_1_1':'room_1_3',index=commonRoom?1:0
  if(kind==='explicit-backup')model.explicitSlots=(_original,conditions)=>new Set(conditions[0]?[]:['room_1_2\0'+0])
  data.operators.D=new MowerOperatorState({name:'D',room,index,group:'H',replacement:['Z'],operatorType:'high',currentRoom:'dormitory_1',currentIndex:4,mood:24,timeStampMicros:0})
  data.operators.Z=new MowerOperatorState({name:'Z',currentRoom:room,currentIndex:index,mood:24,timeStampMicros:0})
  data.plan[room]=commonRoom?['A','D']:['D'];data.groupShiftState.H=true;data.dorms[2]!.name='D';data.dorms[2]!.timeMicros=0
  task.plan[room]=commonRoom?['A','D']:['D']
  if(kind==='third-group'){
   data.operators.A!.groupBindings=[{group:'G',replacement:['X']},{group:'J',replacement:['X']}];data.operators.A!.shiftGroup='G'
   data.operators.D!.groupBindings=[{group:'H',replacement:['Z']},{group:'J',replacement:['Z']}];data.operators.D!.shiftGroup='H';data.groupShiftState.J=false
   for(const [name,index,cover] of [['J1',0,'A'],['J2',1,'D']] as const)data.operators[name]=new MowerOperatorState({name,room:'room_2_1',index,group:'J',replacement:[cover],operatorType:'high',currentRoom:'room_2_1',currentIndex:index,mood:24,timeStampMicros:0})
   data.plan.room_2_1=['J1','J2']
  }
  if(kind==='later-coalesced'){delete task.plan[room];data.groupMoodGapThresholdMinutes=30;data.nowMicros=toMowerMicros(2);queue.tasks.push(new MowerTask({time:2,type:T.SHIFT_ON,plan:{[room]:['D']}}))}
  if(kind==='shared-cover'){data.operators.X!.currentRoom='';data.operators.X!.currentIndex=-1;data.operators.D!.currentRoom='room_1_1';data.operators.D!.currentIndex=0;data.operators.A!.replacement=['D'];data.operators.D!.groupBindings=[{group:'G',replacement:['Z']},{group:'H',replacement:['Z']}];data.operators.D!.shiftGroup='H';data.dorms[2]!.reset()}
  for(let attempt=0;attempt<3;attempt++){
   prepareMowerShiftCycle(data,task,queue,model)
   const independent=queue.tasks.filter(candidate=>candidate.plan[room]?.[index]==='D')
   expect(independent).toHaveLength(1)
   expect(independent[0]!.timeMicros).toBe(toMowerMicros(kind==='shared-cover'?3:kind==='later-coalesced'?2:0))
   expect(task.timeMicros).toBe(toMowerMicros(3))
   expect(data.operators.D!.currentRoom).toBe(kind==='shared-cover'?'room_1_1':'dormitory_1')
  }
 })
 it.each([false,true])('allows an ungrouped return to release the backup before the delayed group returns; merged=%s',merged=>{
  const {data,model,task,queue}=fixture()
  data.operators.D=new MowerOperatorState({name:'D',room:'room_1_3',index:0,replacement:['Z'],operatorType:'high',currentRoom:'dormitory_1',currentIndex:4,mood:24,timeStampMicros:0})
  data.operators.Z=new MowerOperatorState({name:'Z',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0})
  data.plan.room_1_3=['D'];data.dorms[2]!.name='D';data.dorms[2]!.timeMicros=0
  task.plan.room_1_3=['D'];model.evaluate=d=>[d.operators.D!.currentRoom!=='room_1_3']
  model.transition=(_previous,_next,_original,conditions,_recovery,_pending,intent)=>conditions[0]||intent?.room_1_1?.[0]!=='A'?{}:{room_1_2:['B']}
  data.backupGroupTasks=[[{group:'G',action:'off',mode:'forced'}]];model.groupTasks=data.backupGroupTasks
  if(!merged)task.plan={room_1_3:['D']}
  prepareMowerShiftCycle(data,task,queue,model)
  expect(queue.tasks.some(candidate=>candidate.timeMicros===0&&candidate.plan.room_1_3?.[0]==='D')).toBe(true)
  expect(task.timeMicros).toBe(toMowerMicros(merged?3:0))
  if(merged){
   const sibling=queue.tasks.find(candidate=>candidate.timeMicros===0&&candidate.plan.room_1_3?.[0]==='D')!
   const observed=model.swap(projectMowerArrangements(data,[sibling.plan]),sibling.backupShiftConditions??data.planConditions)
   observed.nowMicros=toMowerMicros(3);observed.operators.B!.mood=24;observed.operators.B!.timeStampMicros=observed.nowMicros
   queue.tasks=queue.tasks.filter(candidate=>candidate!==sibling)
   prepareMowerShiftCycle(observed,task,queue,model)
   expect(task.timeMicros).toBe(toMowerMicros(3));expect(task.plan.room_1_1?.[0]).toBe('A')
   expect(queue.tasks.some(candidate=>candidate.plan.room_1_3?.[0]==='D')).toBe(false)
  }
 })
 it.each(['gap','disabled','excluded','short-gap','explicit','complete'] as const)('uses final membership without imposing a new full-recovery policy: %s',kind=>{
  const {data,model,task,queue}=fixture()
  if(kind==='disabled')data.groupRestInFullOnMoodGap=false
  if(kind==='excluded')data.groupMoodGapExclusions=['G']
  if(kind==='short-gap')data.groupMoodGapThresholdMinutes=240
  if(kind==='explicit')task.backupExplicitSlots.add('room_1_2\0'+0)
  if(kind==='complete')data.operators.B!.mood=24
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.timeMicros).toBe(toMowerMicros(kind==='gap'?3:0))
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
  expect(data.operators.B!.mood).toBe(kind==='complete'?24:18)
  expect(queue.tasks.some(queued=>queued===task)).toBe(true)
 })
 it('keeps ordinary recovery when the return activates an explicit backup arrangement',()=>{
  const {data,model,task,queue}=fixture()
  model.explicitSlots=(_original,conditions)=>new Set(conditions[0]?[]:['room_1_2\0'+0])
  for(const now of [0,.1,.2]){
   data.nowMicros=toMowerMicros(now)
   prepareMowerShiftCycle(data,task,queue,model)
   expect(task.timeMicros).toBe(toMowerMicros(3))
   expect(data.planConditions).toEqual([true])
   expect(data.operators.B!.currentRoom).toBe('dormitory_1')
   expect(queue.tasks.filter(candidate=>candidate===task)).toHaveLength(1)
  }
  data.dorms[1]!.timeMicros=toMowerMicros(4)
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.timeMicros).toBe(toMowerMicros(4))
  data.nowMicros=toMowerMicros(4);data.operators.B!.mood=24;data.operators.B!.timeStampMicros=data.nowMicros
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.timeMicros).toBe(toMowerMicros(4))
  expect(task.plan.room_1_2).toEqual(['B'])
  expect(task.backupShiftConditions).toEqual([false])
 })
 it('keeps the existing absolute extra-wait cap across repeated preparation',()=>{
  const {data,model,task,queue}=fixture();data.groupMoodGapMaxExtraWaitHours=.5
  for(const now of [0,.1,.2]){
   data.nowMicros=toMowerMicros(now)
   prepareMowerShiftCycle(data,task,queue,model)
   expect(task.timeMicros).toBe(toMowerMicros(.5))
   expect(queue.tasks.filter(queued=>queued===task)).toHaveLength(1)
  }
 })
 it.each(['started','backup','retained','product'] as const)('keeps the existing %s arrangement date',kind=>{
  const {data,model,task,queue}=fixture()
  if(kind==='started')task.arrangementStarted=true
  if(kind==='backup')task.backupShiftActive=true
  if(kind==='retained')task.executionRetained=true
  if(kind==='product')task.productShiftLocked=true
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.timeMicros).toBe(0)
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
 })
 it('retains a valid personal-cap completion while the restored member is already recovered',()=>{
  const {data,model,task,queue}=fixture(),op=data.operators.A!
  op.upperLimit=12;op.lowerLimit=0;op.restMoodLimit=true;op.currentRoom='';op.currentIndex=-1;op.mood=11.925;op.restMoodReleaseLimit=12
  data.dorms[0]!.reset();data.operators.B!.mood=24
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.timeMicros).toBe(0)
  expect(task.plan.room_1_1).toEqual(['A'])
  expect(op.mood).toBe(11.925)
 })
})
