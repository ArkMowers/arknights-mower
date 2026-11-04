import {describe,expect,it} from 'vitest'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerOperatorState} from './mowerOperatorState'
import {mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
import {preserveMowerBackupReplacements} from './mowerBackupReplacements'

function fixture(){
 const operators={
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,group:'a',replacement:['B'],groupBindings:[{group:'a',replacement:['B']},{group:'b',replacement:['B']}],operatorType:'high',currentRoom:'dormitory_1',currentIndex:2,mood:1,timeStampMicros:0}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,group:'b',replacement:['D'],operatorType:'high',currentRoom:'dormitory_1',currentIndex:3,mood:24,timeStampMicros:0}),
  C:new MowerOperatorState({name:'C',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0}),
  D:new MowerOperatorState({name:'D',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0}),
 }
 const data=new MowerSchedulingData({alpha:true,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['K1','K2','Free','Free','Free']},operators,dorms:[new MowerDormState(['dormitory_1',2],'A'),new MowerDormState(['dormitory_1',3],'B'),new MowerDormState(['dormitory_1',4])],groupShiftState:{a:true,b:true},nowMicros:0})
 return {data,operators}
}
describe('shared-primary replacements across active resting bindings',()=>{
 it('preserves low-mood recovery using a legal primary cover from another active binding',()=>{
  const {data,operators}=fixture(),plan={}
  expect(operators.A.group).toBe('a')
  expect(mowerSameGroupPrimaryReplacement(data,operators.A,'B')).toBe(true)
  expect(mowerSameGroupPrimaryReplacement(data,operators.A,'B','a')).toBe(false)
  expect(mowerSameGroupPrimaryReplacement(data,operators.A,'B','b')).toBe(true)
  expect(preserveMowerBackupReplacements(data,plan,[['room_1_1',0]],data.dorms)).toBe(true)
  expect(plan).toEqual({room_1_1:['B']})
  expect(operators.A.currentRoom).toBe('dormitory_1');expect(operators.A.mood).toBe(1)
 })
 it.each(['inactive-binding','working-cover','unfinished-cover','reserved-cover'] as const)('keeps %s protected',kind=>{
  const {data,operators}=fixture(),plan={}
  if(kind==='inactive-binding')data.groupShiftState.b=false
  if(kind==='working-cover'){operators.B.currentRoom='room_1_2';operators.B.currentIndex=0}
  if(kind==='unfinished-cover'){operators.B.mood=1;operators.B.restInFull=true}
  if(kind==='reserved-cover')data.reservedProductReplacements.add('B')
  expect(preserveMowerBackupReplacements(data,plan,[['room_1_1',0]],data.dorms)).toBe(false)
  expect(plan).toEqual({});expect(operators.A.currentRoom).toBe('dormitory_1')
 })
})
