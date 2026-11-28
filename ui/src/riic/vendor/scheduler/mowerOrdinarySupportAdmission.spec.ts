import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {planMowerOrdinarySupportAdmission} from './mowerOrdinaryPlanning'
import {validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'

function fixture(){
 const operators={
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,group:'request',replacement:['L'],operatorType:'high',mood:0,timeStampMicros:0,currentRoom:'room_1_1',currentIndex:0}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,group:'support',replacement:['X'],operatorType:'high',mood:20,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:1}),
  M:new MowerOperatorState({name:'M',room:'dormitory_1',index:0,group:'support',replacement:['L'],operatorType:'high',mood:24,timeStampMicros:0}),
  L:new MowerOperatorState({name:'L',room:'',index:-1,operatorType:'low',mood:24,timeStampMicros:0,currentRoom:'dormitory_1',currentIndex:0}),
  X:new MowerOperatorState({name:'X',room:'',index:-1,operatorType:'low',mood:24,timeStampMicros:0,currentRoom:'room_1_2',currentIndex:0}),
 }
 const data=new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['M','Free','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',1],'B',3_600_000_000),...[2,3,4].map(index=>new MowerDormState(['dormitory_1',index]))],nowMicros:0,groupShiftState:{request:false,support:true}})
 const support={room_1_2:['B'],dormitory_1:['M','Current','Current','Current','Current']}
 return {data,support}
}

describe('ordinary support admission uses its projected staffing',()=>{
 it('uses a dormitory cover released by the preceding support arrangement',()=>{
  const {data,support}=fixture()
  const options={urgentExhaust:true,isDormReplacement:(name:string)=>name==='L'}
  expect(validateMowerCoordinationSupport(data,support,['A'],options)).toBe(true)
  const projected=projectMowerArrangements(data,[support])
  expect(projected.operators.L.currentRoom).toBe('')
  const plan=planMowerOrdinarySupportAdmission(projected,['A'],options)
  expect(plan?.room_1_1).toEqual(['L'])
  expect(plan?.dormitory_1).toContain('A')
  expect(projected.operators.A.currentRoom).toBe('room_1_1')
  expect(data.operators.L.currentRoom).toBe('dormitory_1')
 })
 it('retains a cover that still occupies a configured dormitory position',()=>{
  const {data}=fixture()
  expect(planMowerOrdinarySupportAdmission(data,['A'],{isDormReplacement:()=>false})).toBeUndefined()
 })
 it('keeps independent mastery and resource reservations binding after support',()=>{
  const {data,support}=fixture(),projected=projectMowerArrangements(data,[support])
  expect(planMowerOrdinarySupportAdmission(projected,['A'],{isMasteryBusy:name=>name==='L'})).toBeUndefined()
  expect(planMowerOrdinarySupportAdmission(projected,['A'],{reservedNames:new Set(['L'])})).toBeUndefined()
 })
})
