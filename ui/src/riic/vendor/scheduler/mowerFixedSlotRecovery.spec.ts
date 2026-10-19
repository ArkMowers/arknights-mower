import {mowerRecoveryReady} from './mowerGroupRecovery'
import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerCorrectionPlan} from './mowerCorrection'
import {projectMowerArrangements} from './mowerObservations'
import {mowerDormCandidateMood} from './mowerAlphaCandidates'
import {toMowerMicros} from './mowerTaskQueue'

describe('fixed manager slot recovery correction',()=>{
 it.each([true,false])('keeps a recovering primary in a dorm (vacancy=%s)',vacancy=>{
  const operators={A:new MowerOperatorState({name:'A',operatorType:'high',room:'room_1_1',index:0,replacement:['R'],restInFull:true,exhaustRequire:true,currentRoom:'dormitory_1',currentIndex:0,mood:12,timeStampMicros:0}),
   R:new MowerOperatorState({name:'R',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0}),
   manager:new MowerOperatorState({name:'manager',operatorType:'high',room:'dormitory_1',index:0,mood:24,timeStampMicros:0})}
  const data=new MowerSchedulingData({alpha:true,operators,nowMicros:0,plan:{room_1_1:['A'],dormitory_1:vacancy?['manager','Free']:['manager']},dorms:vacancy?[new MowerDormState(['dormitory_1',1])]:[]})
  const plan=mowerCorrectionPlan(data),projected=projectMowerArrangements(data,[plan])
  expect(projected.operators.A!.isResting()).toBe(true)
  expect(projected.operators.R!.currentRoom).toBe('room_1_1')
  expect(projected.operators.A!.currentIndex).toBe(vacancy?1:0)
  expect(operators.A.mood).toBe(12);expect(operators.A.currentIndex).toBe(0)
 })
})

describe('newest valid mood source',()=>{
 it.each([[-1,12],[0,12],[1,24]])('compares observation timestamps (%s)',(offset,expected)=>{
  const op=new MowerOperatorState({name:'A',mood:12,timeStampMicros:100,depletionRate:0})
  const data=new MowerSchedulingData({alpha:true,operators:{A:op},plan:{},dorms:[],nowMicros:200})
  data.dormMoodEstimates.set('A',[24,100+offset])
  expect(mowerDormCandidateMood(data,'A')).toBe(expected)
  expect(op.mood).toBe(12);expect(op.timeStampMicros).toBe(100)
 })
 it.each([NaN,Infinity,-1,25])('ignores invalid estimated mood %s',mood=>{
  const data=new MowerSchedulingData({alpha:true,operators:{},plan:{},dorms:[],nowMicros:toMowerMicros(1)})
  data.dormMoodEstimates.set('A',[mood,data.nowMicros])
  expect(mowerDormCandidateMood(data,'A')).toBeUndefined()
 })
})


it('does not let an old near-full countdown override newer low mood',()=>{
 const now=toMowerMicros(1),op=new MowerOperatorState({name:'A',mood:23.9,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:0})
 const data=new MowerSchedulingData({alpha:true,operators:{A:op},plan:{dormitory_1:['Free']},dorms:[new MowerDormState(['dormitory_1',0],'A',now+toMowerMicros(1/60))],nowMicros:now})
 data.dormMoodEstimates.set('A',[6,now])
 expect(mowerRecoveryReady(data,op)).toBe(false)
 expect(op.mood).toBe(23.9)
})
