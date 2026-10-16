import {describe,it,expect} from 'vitest'
import {MowerOperatorState,type MowerOperatorOptions} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'
import {MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {projectMowerArrangements} from './mowerObservations'
import {commitMowerGroupShifts} from './mowerSharedGroups'
import {mowerGroupRecoveryDeadline,mowerGroupRecoveryWorkers} from './mowerGroupRecovery'

type Resident={name:string;hours?:number;options?:Partial<MowerOperatorOptions>}
function fixture(rows:Resident[],gap=false,maxWait=0){
 const operators=Object.fromEntries(rows.map(({name,options},index)=>[name,new MowerOperatorState({name,room:'room_1_1',index,group:'G',operatorType:'high',restingPriority:'high',mood:12,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:index,...options})]))
 return new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:rows.map(row=>row.name),dormitory_1:rows.map(()=> 'Free')},dorms:rows.map(({name,hours},index)=>new MowerDormState(['dormitory_1',index],name,hours===undefined?undefined:toMowerMicros(hours))),nowMicros:0,groupShiftState:{G:true},groupRestInFullOnMoodGap:gap,groupMoodGapThresholdMinutes:60,groupMoodGapMaxExtraWaitHours:maxWait})
}
function returnTask(data:MowerSchedulingData){const queue=new MowerTaskQueue();planMowerAlphaMetadata(data,queue,[]);return queue.tasks.find(task=>task.type===T.SHIFT_ON)}
function releaseFull(data:MowerSchedulingData,name:string){const op=data.operators[name]!;data.dorms.find(b=>b.name===name)!.reset();op.currentRoom='';op.currentIndex=-1;op.mood=op.upperLimit;op.timeStampMicros=data.nowMicros;op.depletionRate=0}

describe('strict grouped recovery in the alpha simulator',()=>{
 it('waits for every explicitly full-rest member without either lead time',()=>{
  const data=fixture([{name:'迷迭香',hours:1},{name:'黑键',hours:2,options:{restInFull:true}},{name:'绮良',hours:4,options:{restInFull:true}}])
  const task=returnTask(data)!
  expect(task.timeMicros).toBe(toMowerMicros(4));expect(task.plan.room_1_1).toEqual(['迷迭香','黑键','绮良'])
 })
 it('includes low-priority explicit full-rest workers when high-priority residents exist',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:5,options:{restInFull:true,restingPriority:'low'}}])
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(5))
 })
 it('combines explicit full recovery with the gap rule and includes low-priority workers',()=>{
  const data=fixture([{name:'A',hours:1,options:{restInFull:true}},{name:'B',hours:3},{name:'C',hours:6,options:{restingPriority:'low'}}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(6))
 })
 it('uses only non-standby work primaries for the gap and full-recovery membership',()=>{
  const data=fixture([
   {name:'A',hours:1},{name:'B',hours:4,options:{restingPriority:'low'}},
   {name:'S',hours:30,options:{restingPriority:'standby'}},
   {name:'R',hours:40,options:{operatorType:'low',room:''}},
   {name:'K',hours:50,options:{room:'dormitory_1'}},
   {name:'W',hours:60,options:{workaholic:true}}
  ],true)
  expect(mowerGroupRecoveryWorkers(data,'G').map(op=>op.name)).toEqual(['A','B'])
  expect(mowerGroupRecoveryDeadline(data,'G')).toEqual({requiredNames:['A','B'],timeMicros:toMowerMicros(4)})
 })
 it('does not shorten full recovery using the extra-wait cap',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:6}],true,1)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(6))
 })
 it('keeps waiting when one required member has already recovered and left its bed',()=>{
  const data=fixture([{name:'A',hours:1,options:{restInFull:true}},{name:'B',hours:4,options:{restInFull:true}},{name:'C',hours:2}])
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('does not silently omit a required resident whose completion time is unknown',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',options:{restInFull:true}}])
  expect(returnTask(data)).toBeUndefined()
 })
 it('preserves ordinary earliest return and its existing lead when no full rule applies',()=>{
  const data=fixture([{name:'A',hours:3},{name:'B',hours:3.5}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(3-8/60))
 })
 it('keeps an activated full-group wait after the first member leaves and metadata repeats',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'C',hours:4.5}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4.5))
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4.5))
  data.nowMicros=toMowerMicros(4);releaseFull(data,'B')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4.5))
 })
 it('excludes fixed dorm managers and workaholics from the group full deadline',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'K',hours:20,options:{room:'dormitory_1',restInFull:true}},{name:'W',hours:30,options:{workaholic:true,restInFull:true}}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('refreshes a latched full deadline after recovery speed changes',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  data.dorms.find(b=>b.name==='B')!.timeMicros=toMowerMicros(7)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(7))
 })
 it('waits for an unknown released full-rest member instead of recalling the group',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4,options:{restInFull:true}}])
  data.dorms.find(b=>b.name==='B')!.reset();data.operators.B!.currentRoom='';data.operators.B!.currentIndex=-1
  expect(returnTask(data)).toBeUndefined()
 })
 it('applies an already triggered group wait to newly joined primary members',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'C',hours:7,options:{group:'other'}}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
  data.operators.C!.group='G'
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(7))
 })
 it('drops obsolete requirements after a backup moves members out of the group',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'C',hours:7}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(7))
  data.operators.C!.group='other';data.dorms.find(b=>b.name==='C')!.timeMicros=undefined
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('excludes a standby member from an activated group wait even if its bed becomes unavailable',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'C',hours:7,options:{restingPriority:'standby'}}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
  expect(data.groupRecoveryFullMembers.G).toEqual(['A','B'])
  data.dorms.find(b=>b.name==='C')!.reset();data.operators.C!.currentRoom='';data.operators.C!.currentIndex=-1
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('does not trigger a gap wait from a standby recovery deadline',()=>{
  const data=fixture([{name:'A',hours:1,options:{restMoodLimit:true}},{name:'B',hours:4,options:{restingPriority:'standby'}}],true)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(1-8/60))
  expect(data.groupRecoveryFullMembers.G).toBeUndefined()
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(1))
 })
 it('clears stale standby obligations without blocking an off-bed primary return',()=>{
  const data=fixture([{name:'A',hours:1,options:{restMoodLimit:true}},{name:'B',hours:4,options:{restingPriority:'standby'}}],true)
  data.groupRecoveryFullMembers.G=['A','B']
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  data.dorms.find(b=>b.name==='B')!.timeMicros=undefined
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(1))
  expect(data.groupRecoveryFullMembers.G).toEqual(['A'])
 })
 it.each(['restInFull','exhaustRequire'] as const)('preserves primary recovery when %s overrides standby priority',rule=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4,options:{restingPriority:'standby',[rule]:true}}],rule==='exhaustRequire')
  expect(data.canStandby(data.operators.B!)).toBe(false)
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('preserves ordinary off-bed group recall when no standby full obligation was activated',()=>{
  const data=fixture([{name:'A',hours:1,options:{restMoodLimit:true}},{name:'B',hours:4,options:{restingPriority:'standby'}}])
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(1))
 })
 it.each([false,true])('ignores shared recovery before and after its primary leaves without changing another group: %s',otherResting=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4,options:{groupBindings:[{group:'G',replacement:['Y']},{group:'H',replacement:['Y']}],replacement:['Y']}}],true)
  data.groupShiftState.H=otherResting
  data.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_1',currentIndex:1,mood:24,timeStampMicros:0})
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(1-8/60))
  expect(data.groupRecoveryFullMembers.G).toBeUndefined()
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  const task=returnTask(data)!
  expect(task.timeMicros).toBe(toMowerMicros(1))
  expect(task.plan.room_1_1).toEqual(['A',otherResting?'Current':'B'])
  expect(data.groupShiftState).toEqual({G:true,H:otherResting})
 })
 it.each([false,true])('keeps explicit full recovery for a shared last resident with gap=%s',gap=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4,options:{restInFull:true,groupBindings:[{group:'G',replacement:['Y']},{group:'H',replacement:['Y']}],replacement:['Y']}}],gap)
  data.groupShiftState.H=false
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it('does not extend an activated primary gap wait to a shared member and removes its stale latch',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'Shared',hours:10,options:{groupBindings:[{group:'G',replacement:['Y']},{group:'H',replacement:['Y']}],replacement:['Y']}}],true)
  data.groupRecoveryFullMembers.G=['A','B','Shared']
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
  expect(data.groupRecoveryFullMembers.G).toEqual(['A','B'])
  data.dorms.find(b=>b.name==='Shared')!.timeMicros=undefined
  data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4))
 })
 it.each([{last:2,expected:1},{last:2.25,expected:1},{last:3,expected:3}])('combines explicit full recovery with the 75-minute primary gap: $last hours',({last,expected})=>{
  const data=fixture([{name:'Required',hours:1,options:{restInFull:true}},{name:'A',hours:1.5},{name:'B',hours:last}],true)
  data.groupMoodGapThresholdMinutes=75
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(expected))
  data.nowMicros=toMowerMicros(1);releaseFull(data,'Required')
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(expected))
 })
 it('isolates projected cycle transitions and resets only on a new actual group cycle',()=>{
  const data=fixture([{name:'A',hours:1},{name:'B',hours:4},{name:'C',hours:4.5}],true)
  returnTask(data);data.nowMicros=toMowerMicros(1);releaseFull(data,'A')
  const projected=projectMowerArrangements(data,[]);commitMowerGroupShifts(projected,{G:false})
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4.5))
  commitMowerGroupShifts(data,{G:false});commitMowerGroupShifts(data,{G:true})
  data.operators.A!.currentRoom='room_1_1';data.operators.A!.currentIndex=0
  expect(returnTask(data)!.timeMicros).toBe(toMowerMicros(4-8/60))
 })
})
