import {describe, expect, it} from 'vitest'
import {alphaFindDormSlot, alphaRestingTier, alphaSlotTakable} from './mowerAlphaDorm'
import {mowerAlphaDormCandidates, mowerDormCandidateMood, planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {projectMowerArrangements, mowerUpdateDetail} from './mowerObservations'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState, MowerSchedulingData} from './mowerSchedulingData'
import {MowerTaskQueue, toMowerMicros} from './mowerTaskQueue'

function fixture() {
 const operators={
  owner:new MowerOperatorState({name:'owner',room:'work',index:0,operatorType:'high',restingPriority:'high',mood:0,timeStampMicros:0,replacement:['R','full']}),
  R:new MowerOperatorState({name:'R',mood:20,timeStampMicros:0}),
  idle:new MowerOperatorState({name:'idle',mood:10,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:0}),
  full:new MowerOperatorState({name:'full',mood:24,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:1}),
 }
 return new MowerSchedulingData({alpha:true,nowMicros:0,operators,plan:{work:['owner'],dormitory_1:['Free','Free']},dorms:[new MowerDormState(['dormitory_1',0],'idle'),new MowerDormState(['dormitory_1',1],'full')]})
}

describe('current Mower full dynamic resident and standby policy',()=>{
 it.each(['explicit','main','low','priority replacement','standby','replacement','idle'])('demotes a full dynamic %s resident to idle and permits a tired replacement',kind=>{
  const data=fixture(),op=data.operators.full!
  if(kind==='explicit')data.restingPriorityNames=['full']
  if(kind==='main'||kind==='low'){op.operatorType='high';op.room='work';op.restingPriority=kind==='main'?'high':'low'}
  if(kind==='priority replacement')data.priorityReplacement=['full']
  if(kind==='standby')data.standbyNames=['full']
  if(kind==='idle')data.operators.owner!.replacement=['R']
  expect(alphaRestingTier(data,'full')).toBe(6)
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(true)
 })
 it.each([false,true])('takes a measured full filler before a recovering idle resident, freeRoom=%s',freeRoom=>{
  const data=fixture();data.freeRoom=freeRoom;data.operators.R!.mood=15
  const task=planMowerAlphaDormFill(data,new MowerTaskQueue())
  expect(projectMowerArrangements(data,[task!.plan]).dorms.map(b=>b.name).sort()).toEqual(['R','idle'])
  expect(alphaFindDormSlot(data,'owner',new Set())).toBe(1)
 })
 it('allows a tired idle worker to replace an equally ranked full filler',()=>{
  const data=fixture();data.operators.owner!.replacement=['full']
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(true)
  expect(planMowerAlphaDormFill(data,new MowerTaskQueue())?.plan.dormitory_1).toEqual(['Current','R'])
 })
 it.each(['prediction','future','unknown'])('does not treat a %s full value as measured filler evidence',source=>{
  const data=fixture();data.operators.owner!.replacement=['full'];const op=data.operators.full!
  if(source==='prediction')op.moodIsPrediction=true
  if(source==='future')op.timeStampMicros=1
  if(source==='unknown')op.timeStampMicros=undefined
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(false)
 })
 it.each(['fixed','excluded','workaholic','blacklist'])('retains %s resident protection',kind=>{
  const data=fixture(),op=data.operators.full!
  if(kind==='fixed'){op.operatorType='high';op.room='dormitory_1';op.index=1;data.plan.dormitory_1![1]='full'}
  if(kind==='excluded'){data.freeRoomExclusions=['full'];data.freeRoom=true;data.restingPriorityNames=['full']}
  if(kind==='workaholic')op.workaholic=true
  if(kind==='blacklist')data.freeBlacklist=['full']
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(false)
 })
 it.each([0,8,20,24])('keeps standby identity after reading mood %s and returning to work',mood=>{
  const data=fixture(),op=data.operators.owner!;data.standbyNames=['owner'];op.restingPriority='standby'
  for(const [room,index] of [['dormitory_1',1],['work',0]] as const){
   mowerUpdateDetail(data,'owner',mood,room,index,true)
   expect(alphaRestingTier(data,'owner')).toBe(mood===24?6:4)
   expect(data.canStandby(op)).toBe(true)
  }
 })
 it.each([2,3])('allocates %s beds to mandatory members before an optional standby',count=>{
  const data=fixture(),anchor=data.operators.owner!;anchor.group='g'
  data.operators.F=new MowerOperatorState({name:'F',room:'work',index:1,group:'g',operatorType:'high',restingPriority:'high',mood:24,timeStampMicros:0})
  data.operators.S=new MowerOperatorState({name:'S',room:'work',index:2,group:'g',operatorType:'high',restingPriority:'standby',mood:0,timeStampMicros:0})
  data.standbyNames=['S'];data.plan.work=['owner','F','S'];data.plan.dormitory_1=Array(count).fill('Free')
  data.operators.idle!.currentRoom='';data.operators.full!.currentRoom='';data.dorms=Array.from({length:count},(_,index)=>new MowerDormState(['dormitory_1',index]))
  const beds=mowerAssignDormGroup(data,['S','F','owner'])
  expect(beds?.map(b=>b.name)).toEqual(count===2?['owner','F']:['owner','F','S'])
 })
})

describe('dorm scheduling chooses the newest valid observation',()=>{
 it.each(['card','prediction','future','old full'])('uses a newer card when the saved value is %s',kind=>{
  const data=fixture(),op=data.operators.R!;data.nowMicros=toMowerMicros(1);op.timeStampMicros=0;op.mood=24
  data.dormMoodEstimates.set('R',[5,toMowerMicros(.9)])
  if(kind==='prediction')op.moodIsPrediction=true
  if(kind==='future')op.timeStampMicros=toMowerMicros(2)
  expect(mowerDormCandidateMood(data,'R')).toBe(5)
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(true)
 })
 it('keeps a same-time or newer measured value above an older card',()=>{
  const data=fixture();data.dormMoodEstimates.set('R',[5,0]);data.operators.R!.mood=24
  expect(mowerDormCandidateMood(data,'R')).toBe(24)
  expect(alphaSlotTakable(data,data.dorms[1]!,'R')).toBe(false)
 })
 it('keeps card-only personal-limit candidates available without creating a measured value',()=>{
  const data=fixture(),op=data.operators.R!;op.restMoodLimit=true;op.timeStampMicros=undefined;data.dormMoodEstimates.set('R',[5,0])
  expect(mowerAlphaDormCandidates(data).estimatedRecovering).toContain('R')
  const task=planMowerAlphaDormFill(data,new MowerTaskQueue())!
  expect(projectMowerArrangements(data,[task.plan]).dorms.map(b=>b.name).sort()).toEqual(['R','idle'])
  expect(op.timeStampMicros).toBeUndefined()
 })
 it('orders full personal-cap fillers after still-recovering candidates',()=>{
  const data=fixture();data.operators.full!.currentRoom='';data.operators.full!.upperLimit=12;data.operators.full!.mood=12
  expect(mowerAlphaDormCandidates(data).filling).toEqual(['R','full'])
 })
})
