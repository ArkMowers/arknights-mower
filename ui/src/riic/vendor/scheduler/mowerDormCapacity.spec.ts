import {describe,expect,it} from 'vitest'
import {mowerDormCapacityAllows} from './mowerDormCapacity'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'

function fixture(){
 const operators={
  K:new MowerOperatorState({name:'K',room:'dormitory_1',index:0,group:'g',replacement:['Free'],operatorType:'high',mood:10,timeStampMicros:0}),
  A:new MowerOperatorState({name:'A',room:'work',index:0,group:'g',operatorType:'high',restingPriority:'high',mood:10,timeStampMicros:0}),
  B:new MowerOperatorState({name:'B',room:'work',index:1,group:'other',operatorType:'high',restingPriority:'high',mood:10,timeStampMicros:0}),
  R:new MowerOperatorState({name:'R',mood:10,timeStampMicros:0}),
 }
 return new MowerSchedulingData({alpha:true,operators,nowMicros:0,plan:{work:['A','B'],dormitory_1:['K','Free']},groupShiftState:{g:true},dorms:[new MowerDormState(['dormitory_1',0],'',undefined,true),new MowerDormState(['dormitory_1',1])]})
}
describe('group Free capacity is shared by count rather than bed identity',()=>{
 it('keeps a group capacity for its member while an unrelated primary uses the ordinary capacity',()=>{
  const data=fixture()
  expect(mowerAssignDormGroup(data,['A','B'])?.map(b=>b.name)).toEqual(['A','B'])
  const pending={dormitory_1:['B','Current']}
  expect(mowerDormCapacityAllows(data,'A',['dormitory_1',1],pending)).toBe(true)
 })
 it('rejects an unrelated protected primary when the ordinary capacity is already used',()=>{
  const data=fixture();data.operators.C=new MowerOperatorState({name:'C',room:'other',operatorType:'high',mood:10,timeStampMicros:0})
  expect(mowerDormCapacityAllows(data,'C',['dormitory_1',1],{dormitory_1:['B','Current']})).toBe(false)
 })
 it('allows lower tiers to use remaining group capacity',()=>{
  const data=fixture();data.plan.dormitory_1=['K'];data.dorms.splice(1)
  expect(mowerDormCapacityAllows(data,'R',['dormitory_1',0])).toBe(true)
  expect(mowerDormCapacityAllows(data,'B',['dormitory_1',0])).toBe(false)
 })
 it('honors group return and explicit same-round reservations',()=>{
  const data=fixture()
  expect(mowerDormCapacityAllows(data,'A',['dormitory_1',1],{work:['A','Current'],dormitory_1:['Current','B']})).toBe(true)
  expect(mowerDormCapacityAllows(data,'B',['dormitory_1',0],{work:['A','Current'],dormitory_1:['Current','A']})).toBe(false)
 })
})
