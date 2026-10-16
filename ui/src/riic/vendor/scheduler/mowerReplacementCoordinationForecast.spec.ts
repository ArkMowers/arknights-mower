import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerRecallCanSustain,type MowerCoordinationRates} from './mowerReplacementCoordination'
import {toMowerMicros} from './mowerTaskQueue'
import {planMowerExhaustSupport} from './mowerExhaustPlanning'

function fixture(mood=20){
 const original=new MowerSchedulingData({alpha:true,nowMicros:0,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['Free','Free','Free']},operators:{
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'dormitory_1',currentIndex:0,operatorType:'high',mood,timeStampMicros:0,depletionRate:1,replacement:['X']}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,currentRoom:'room_1_2',currentIndex:0,operatorType:'high',mood:0,timeStampMicros:0,depletionRate:1,replacement:['X']}),
  X:new MowerOperatorState({name:'X',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1}),
 },dorms:[new MowerDormState(['dormitory_1',0],'A',toMowerMicros(24-mood)),new MowerDormState(['dormitory_1',1]),new MowerDormState(['dormitory_1',2])]})
 const admit=()=>projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','Free']}])
 return {original,admit}
}
function fixed(data:MowerSchedulingData):MowerCoordinationRates {
 return {work:Object.fromEntries(Object.keys(data.operators).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(data.operators).map(name=>[name,4]))}
}
function allowed(original:MowerSchedulingData,admitted:MowerSchedulingData,coordinationRates?: (data:MowerSchedulingData)=>MowerCoordinationRates|undefined){
 return mowerRecallCanSustain(original,admitted,new Set(['A']),['B'],{coordinationRates})
}

describe('replacement recall forecast covers the connected recovery cycle',()=>{
 it.each([{mood:4,result:false},{mood:20,result:true}])('checks actual sustainable work for $mood mood',({mood,result})=>{
  const {original,admit}=fixture(mood),before=JSON.stringify(original)
  expect(allowed(original,admit(),fixed)).toBe(result)
  expect(JSON.stringify(original)).toBe(before)
 })
 it('rejects missing forecast evidence and accepts explicitly observed zero consumption',()=>{
  const {original,admit}=fixture(1)
  expect(allowed(original,admit())).toBe(false)
  expect(allowed(original,admit(),data=>{const rates=fixed(data);return {...rates,work:{X:1}}})).toBe(false)
  expect(allowed(original,admit(),data=>{const rates=fixed(data);return {...rates,work:{...rates.work,A:0}}})).toBe(true)
 })
 it('clamps an exhausted cached prediction instead of reusing the old positive mood',()=>{
  const {original,admit}=fixture(4);original.nowMicros=toMowerMicros(10)
  expect(allowed(original,admit(),fixed)).toBe(false)
 })
 it('includes a third resting group sharing replacements and beds',()=>{
  const {original}=fixture(10)
  original.plan.room_1_3=['C']
  original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:0,timeStampMicros:0,replacement:['X','Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(12))
  const admitted=projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','C']}])
  expect(allowed(original,admitted,data=>{const rates=fixed(data);return {...rates,recovery:{...rates.recovery,C:2}}})).toBe(false)
  expect(allowed(original,admitted,fixed)).toBe(true)
 })
 it('recomputes rates when a global operator reaches zero mood',()=>{
  const {original,admit}=fixture(10)
  original.plan.central=['K'];original.operators.K=new MowerOperatorState({name:'K',room:'central',index:0,currentRoom:'central',currentIndex:0,operatorType:'high',workaholic:true,mood:1,timeStampMicros:0,depletionRate:1})
  const visited:number[]=[]
  expect(allowed(original,admit(),data=>{visited.push(data.operators.K!.mood);const rates=fixed(data);return {...rates,work:{...rates.work,A:data.operators.K!.mood>0?1:2}}})).toBe(false)
  expect(visited).toContain(0)
  expect(allowed(original,admit(),fixed)).toBe(true)
 })
 it('recomputes recovery when another resident reaches full mood and changes the recovery allocation',()=>{
  const {original}=fixture(10)
  original.operators.E=new MowerOperatorState({name:'E',currentRoom:'dormitory_1',currentIndex:2,mood:21,timeStampMicros:0})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'E',toMowerMicros(1))
  const admitted=projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','E']}]),visited:number[]=[]
  expect(allowed(original,admitted,data=>{visited.push(data.operators.E!.mood);const rates=fixed(data);return {...rates,recovery:{...rates.recovery,E:3,B:data.operators.E!.mood<24?4:1}}})).toBe(false)
  expect(visited).toContain(24)
  expect(allowed(original,admitted,fixed)).toBe(true)
 })
 it('does not recall a group protected by explicit full recovery or a triggered group wait',()=>{
  const {original,admit}=fixture()
  original.operators.A!.restInFull=true
  expect(allowed(original,admit(),fixed)).toBe(false)
  original.operators.A!.restInFull=false;original.operators.A!.group='g';original.groupRecoveryFullMembers.g=['A']
  expect(allowed(original,admit(),fixed)).toBe(false)
 })
})


describe('recall uses the recovering room operation allowance',()=>{
 it.each(['personal','group'] as const)('passes room timing to both recall guards for %s recovery',mode=>{
  const {original,admit}=fixture(23.9)
  original.dorms[0]!.timeMicros=toMowerMicros(120/3600)
  if(mode==='personal')original.operators.A!.restInFull=true
  else {original.operators.A!.group='g';original.groupRecoveryFullMembers.g=['A']}
  const options={coordinationRates:fixed,priorityScheduling:{dormDurations:{dormitory_1:[100]}}}
  const before=JSON.stringify(original)
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:fixed})).toBe(false)
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBeUndefined()
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],options)).toBe(true)
  expect(planMowerExhaustSupport(original,['B'],options)?.room_1_1).toEqual(['A'])
  expect(JSON.stringify(original)).toBe(before)
 })
})
