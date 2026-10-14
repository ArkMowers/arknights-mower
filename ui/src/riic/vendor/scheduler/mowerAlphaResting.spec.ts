import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-alpha-resting-boundaries.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerResting} from './mowerOrdinaryPlanning'
import {MowerTaskQueue} from './mowerTaskQueue'
import {alphaRestingTier,alphaSlotTakable} from './mowerAlphaDorm'
import {mowerUpdateDetail,projectMowerArrangements} from './mowerObservations'
import {planMowerMetadata} from './mowerMetadata'
import {mowerAverageMood} from './mowerDormAssignment'

describe('alpha resting boundaries with temporary standby promotion',()=>{
 for(const c of oracle.cases)it(c.kind,()=>{
  const standby=c.kind==='standby'
  const operators={A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',mood:4,timeStampMicros:['unknown','estimated'].includes(c.kind)?undefined:0,replacement:['R'],restingPriority:standby?'standby':'high'}),R:new MowerOperatorState({name:'R',mood:10,timeStampMicros:0}),...Object.fromEntries(['K1','K2'].map((name,index)=>[name,new MowerOperatorState({name,room:'dormitory_1',index,currentRoom:'dormitory_1',currentIndex:index,operatorType:'high',mood:24,timeStampMicros:0})]))}
  const data=new MowerSchedulingData({alpha:true,plan:{room_1_1:['A'],dormitory_1:['K1','K2','Free','Free','Free']},operators,dorms:[new MowerDormState(['dormitory_1',2])],nowMicros:0,standbyNames:standby?['A']:[],dormMoodEstimates:c.kind==='estimated'?new Map([['A',[4,0]]]):undefined,reservedProductReplacements:new Set(c.kind==='reserved-primary'?['A']:c.kind==='reserved-cover'?['R']:[])})
  expect(mowerResting(data,new MowerTaskQueue())).toEqual(c.plan)
  expect(data.dorms.map(b=>b.name)).toEqual(c.bedNames)
  expect(operators.A.standbyLowPriority).toBe(c.standbyLow)
  expect(alphaRestingTier(data,'A')).toBe(standby?2:1)
 })
})

describe('temporary standby promotion preserves standby identity',()=>{
 function fixture(alpha=true){
  const operators={
   S:new MowerOperatorState({name:'S',room:'room_1_1',index:1,group:'g',replacement:['R'],operatorType:'high',restingPriority:'standby',mood:12,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:2}),
   R:new MowerOperatorState({name:'R',mood:24,timeStampMicros:0,currentRoom:'room_1_1',currentIndex:1}),
   L:new MowerOperatorState({name:'L',room:'room_1_2',index:0,operatorType:'high',restingPriority:'low',mood:4,timeStampMicros:0}),
   H:new MowerOperatorState({name:'H',room:'room_1_1',index:0,group:'g',operatorType:'high',restingPriority:'high',mood:12,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:3}),
  }
  const data=new MowerSchedulingData({alpha,operators,plan:{room_1_1:['H','S'],room_1_2:['L'],dormitory_1:['Free','Free','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',2],'S',3_600_000_000),new MowerDormState(['dormitory_1',3],'H',3_600_000_000)],nowMicros:0,standbyNames:['S']})
  return {data,operators}
 }
 it.each([4,0])('promotes to tier 2 after observing and planning with morale %s',mood=>{
  const {data}=fixture()
  mowerUpdateDetail(data,'S',mood,'dormitory_1',2,true)
  expect(alphaRestingTier(data,'S')).toBe(2)
  expect(data.operators.S!.standbyLowPriority).toBe(true)
  expect(data.canStandby(data.operators.S!)).toBe(true)
  expect(data.isGroupShiftAnchor(data.operators.S!)).toBe(false)
  mowerResting(data,new MowerTaskQueue())
  expect(alphaRestingTier(data,'S')).toBe(2)
  expect(alphaRestingTier(data,'L')).toBe(2)
  expect(data.dorms[0]!.name).toBe('S')
  expect(alphaSlotTakable(data,data.dorms[0]!,'L')).toBe(false)
 })
 it('promotes strictly below the rescue threshold and retains it until returning to the primary post',()=>{
  const {data,operators}=fixture()
  const threshold=operators.S.lowerLimit+(operators.S.upperLimit-operators.S.lowerLimit)*data.policy.restingThreshold*data.policy.rescueThreshold
  for(const mood of [threshold+1,threshold]){
   mowerUpdateDetail(data,'S',mood,'dormitory_1',2,true)
   expect(operators.S.standbyLowPriority).toBe(false)
   expect(alphaRestingTier(data,'S')).toBe(4)
  }
  mowerUpdateDetail(data,'S',threshold-.01,'dormitory_1',2,true)
  expect(operators.S.standbyLowPriority).toBe(true)
  for(const mood of [12,24]){
   mowerUpdateDetail(data,'S',mood,'dormitory_1',2,true)
   expect(operators.S.standbyLowPriority).toBe(true)
   expect(alphaRestingTier(data,'S')).toBe(2)
  }
  mowerUpdateDetail(data,'S',24,'room_1_1',1,true)
  expect(operators.S.standbyLowPriority).toBe(false)
  expect(alphaRestingTier(data,'S')).toBe(4)
  expect(data.canStandby(operators.S)).toBe(true)
  expect(data.isGroupShiftAnchor(operators.S)).toBe(false)
 })
 it.each([false,true])('keeps a zero-morale standby idle until its group returns, alpha=%s',alpha=>{
  const {data,operators}=fixture(alpha)
  mowerUpdateDetail(data,'S',0,'',-1,true)
  if(alpha)expect(operators.S.standbyLowPriority).toBe(true)
  expect(data.canStandby(operators.S)).toBe(true)
  expect(data.isStandby('S')).toBe(true)
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  const returning=queue.tasks.find(task=>task.type.key==='SHIFT_ON')!
  expect(returning.plan.room_1_1).toEqual(['H','S'])
  const projected=projectMowerArrangements(data,[returning.plan])
  expect(projected.operators.S!.currentRoom).toBe('room_1_1')
  expect(projected.operators.S!.currentIndex).toBe(1)
  expect(projected.isStandby('S')).toBe(false)
 })
 it('keeps manually configured priority above ordinary low priority at zero morale',()=>{
  const {data}=fixture()
  data.restingPriorityNames=['S']
  mowerUpdateDetail(data,'S',0,'dormitory_1',2,true)
  mowerResting(data,new MowerTaskQueue())
  expect(data.operators.S!.standbyLowPriority).toBe(true)
  expect(data.canStandby(data.operators.S!)).toBe(true)
  expect(alphaRestingTier(data,'S')).toBe(0)
  expect(alphaSlotTakable(data,data.dorms[0]!,'L')).toBe(false)
 })
})

describe('group standby morale does not drive shifts',()=>{
 function fixture(alpha=true){
  const operators={
   H:new MowerOperatorState({name:'H',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,group:'g',replacement:['R1'],operatorType:'high',mood:24,timeStampMicros:0}),
   S:new MowerOperatorState({name:'S',room:'room_1_1',index:1,currentRoom:'room_1_1',currentIndex:1,group:'g',replacement:['R2'],operatorType:'high',restingPriority:'standby',mood:0,timeStampMicros:0}),
   R1:new MowerOperatorState({name:'R1',mood:24,timeStampMicros:0}),
   R2:new MowerOperatorState({name:'R2',mood:24,timeStampMicros:0}),
  }
  const data=new MowerSchedulingData({alpha,operators,plan:{room_1_1:['H','S'],dormitory_1:['Free','Free','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',2]),new MowerDormState(['dormitory_1',3])],nowMicros:0,standbyNames:['S'],policy:{restingThreshold:.65}})
  if(alpha)mowerUpdateDetail(data,'S',0,'room_1_1',1,true)
  else operators.S.standbyLowPriority=true
  expect(operators.S.standbyLowPriority).toBe(true)
  expect(data.canStandby(operators.S)).toBe(true)
  expect(data.isGroupShiftAnchor(operators.S)).toBe(false)
  if(alpha)expect(alphaRestingTier(data,'S')).toBe(2)
  return {data,operators}
 }
 it.each([false,true])('ignores a working low/zero-morale standby as a downshift trigger, alpha=%s',alpha=>{
  for(const mood of [14,0]){
   const {data,operators}=fixture(alpha);operators.S.mood=mood
   const queue=new MowerTaskQueue()
   expect(mowerResting(data,queue)).toEqual({})
   expect(queue.tasks.some(t=>t.type.key==='SHIFT_OFF')).toBe(false)
   expect(mowerAverageMood(data)).toBe(1)
  }
 })
 it.each([false,true])('still takes standby followers off duty with their low-morale anchor, alpha=%s',alpha=>{
  const {data,operators}=fixture(alpha);operators.H.mood=10
  const queue=new MowerTaskQueue(),plan=mowerResting(data,queue)
  expect(plan.room_1_1).toEqual(['R1','R2'])
  expect(data.dorms.some(b=>b.name==='H')).toBe(true)
  expect(queue.tasks.some(t=>t.type.key==='SHIFT_OFF')).toBe(true)
 })
 it.each([false,true])('does not let an exhausted working standby advance another group return, alpha=%s',alpha=>{
  const {data,operators}=fixture(alpha)
  operators.S.group='other';operators.H.currentRoom='dormitory_1';operators.H.currentIndex=2;operators.H.mood=12
  operators.R1.currentRoom='room_1_1';operators.R1.currentIndex=0
  data.dorms[0]!.name='H';data.dorms[0]!.timeMicros=4*3_600_000_000
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  expect(queue.tasks.find(t=>t.type.key==='SHIFT_ON')!.time).toBeCloseTo(4-8/60,8)
 })
 it.each([false,true])('waits only for the anchor recovery, not the standby recovery, alpha=%s',alpha=>{
  const {data}=fixture(alpha)
  for(const [index,name] of ['H','S'].entries()){
   const op=data.operators[name]!;op.currentRoom='dormitory_1';op.currentIndex=2+index
   data.dorms[index]!.name=name;data.dorms[index]!.timeMicros=(index?12:2)*3_600_000_000
  }
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  const task=queue.tasks.find(t=>t.type.key==='SHIFT_ON')!
  expect(task.time).toBeCloseTo(2-8/60,8)
  expect(task.plan.room_1_1).toEqual(['H','S'])
 })
 it.each([false,true])('returns a capped idle anchor with its still-recovering standby, alpha=%s',alpha=>{
  const {data,operators}=fixture(alpha)
  operators.H.currentRoom='';operators.H.currentIndex=-1;operators.H.restMoodLimit=true;operators.H.upperLimit=20;operators.H.mood=20
  operators.S.currentRoom='dormitory_1';operators.S.currentIndex=3
  operators.R1.currentRoom='room_1_1';operators.R1.currentIndex=0
  operators.R2.currentRoom='room_1_1';operators.R2.currentIndex=1
  data.dorms[1]!.name='S';data.dorms[1]!.timeMicros=12*3_600_000_000
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  expect(queue.tasks.find(t=>t.type.key==='SHIFT_ON')?.plan.room_1_1).toEqual(['H','S'])
 })
 it('does not extend a recent default group return to recover standby morale',()=>{
  const {data}=fixture(false)
  for(const [index,name] of ['H','S'].entries()){
   const op=data.operators[name]!;op.currentRoom='dormitory_1';op.currentIndex=2+index
   data.dorms[index]!.name=name;data.dorms[index]!.timeMicros=(index?12:2)*3_600_000_000
  }
  data.recentShiftOnByRestUnit.set('group:g',0)
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  expect(queue.tasks.find(t=>t.type.key==='SHIFT_ON')!.time).toBeCloseTo(2-8/60,8)
 })

})
