import {describe,expect,it} from 'vitest'
import {MowerOperatorState,rescueMoodThreshold} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerRecallCanSustain,type MowerCoordinationRates} from './mowerReplacementCoordination'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerExhaustSupport} from './mowerExhaustPlanning'
import {validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'

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
 it('rejects reaching the work floor at the same instant recovery completes',()=>{
  const {original,admit}=fixture(6)
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


describe('ordinary recall rescue admission',()=>{
 it.each([false,true].flatMap(predictiveMoodControl=>['run-order','patrol','replacement'].map(recheck=>({predictiveMoodControl,recheck}))))('requires endurance to full recovery despite $recheck with saved mood mode=$predictiveMoodControl',({predictiveMoodControl,recheck})=>{
  const {original}=fixture(4);original.policy.predictiveMoodControl=predictiveMoodControl
  const task=new MowerTask({time:1})
  if(recheck==='run-order'){task.type=T.RUN_ORDER;task.metadata='room_2_1';task.observedOrderDueMicros=toMowerMicros(1.05)}
  if(recheck==='replacement')task.workingReplacementCheck={room:'room_1_1',index:0,owner:'A',cover:'X'}
  const before=JSON.stringify(original)
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed,tasks:[task]})).toBeUndefined()
  expect(JSON.stringify(original)).toBe(before)
  expect(task.timeMicros).toBe(toMowerMicros(1))
  original.operators.A!.mood=20
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed,tasks:[task]})).toEqual({room_1_1:['A']})
 })
 it('does not count a future observation as recovery when the forecast recovery rate is zero',()=>{
  const {original}=fixture(4),recheck=new MowerTask({time:1});recheck.executionRetained=true
  const zero=(data:MowerSchedulingData)=>({...fixed(data),recovery:Object.fromEntries(Object.keys(data.operators).map(name=>[name,0]))})
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:zero,tasks:[recheck]})).toBeUndefined()
 })
 it('revalidates full recovery endurance against current rates before support dispatch',()=>{
  const {original}=fixture(20),options={coordinationRates:fixed}
  const plan=planMowerExhaustSupport(original,['B'],options)!
  expect(plan).toEqual({room_1_1:['A']})
  const faster=(data:MowerSchedulingData)=>({...fixed(data),work:{...fixed(data).work,A:5}})
  expect(validateMowerCoordinationSupport(original,plan,['B'],{coordinationRates:faster})).toBe(false)
  expect(validateMowerCoordinationSupport(original,plan,['B'],options)).toBe(true)
 })
 it.each([
  {request:7.8001,target:20,expected:false},
  {request:7.8,target:20,expected:true},
  {request:7,target:7.8,expected:true},
  {request:7,target:7,expected:true},
  {request:7,target:4,expected:false},
  {request:0,target:7,expected:true},
  {request:0,target:4,expected:false},
 ])('admits requester $request and target $target only with rescue evidence and endurance',({request,target,expected})=>{
  const {original,admit}=fixture(target)
  original.policy.rescueThreshold=.5;original.operators.B!.mood=request
  expect(allowed(original,admit(),fixed)).toBe(expected)
  expect(!!planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBe(expected)
 })
 it('uses the requester personal rescue limit and the target personal endurance limit',()=>{
  const {original,admit}=fixture(20),request=original.operators.B!,target=original.operators.A!
  request.lowerLimit=12;request.upperLimit=24;request.mood=rescueMoodThreshold(request,original.policy)
  expect(allowed(original,admit(),fixed)).toBe(true)
  target.lowerLimit=12;target.mood=rescueMoodThreshold(target,original.policy)
  expect(allowed(original,admit(),fixed)).toBe(true)
  target.mood=12.5
  expect(allowed(original,admit(),fixed)).toBe(false)
  request.mood=request.lowerLimit;target.mood=16
  expect(allowed(original,admit(),fixed)).toBe(true)
 })
 it.each(['unknown','prediction','invalid'] as const)('rejects %s requesting mood as recall authorization',kind=>{
  const {original,admit}=fixture(),request=original.operators.B!
  if(kind==='unknown')request.timeStampMicros=undefined
  if(kind==='prediction')request.moodIsPrediction=true
  if(kind==='invalid')request.mood=-1
  expect(allowed(original,admit(),fixed)).toBe(false)
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBeUndefined()
 })
 it.each(['unknown','prediction','invalid','future','infinite'] as const)('rejects %s target mood even when the requester reaches its lower limit',kind=>{
  const {original,admit}=fixture(),target=original.operators.A!
  if(kind==='unknown')target.timeStampMicros=undefined
  if(kind==='prediction')target.moodIsPrediction=true
  if(kind==='invalid')target.mood=-1
  if(kind==='future')target.timeStampMicros=toMowerMicros(1)
  if(kind==='infinite')target.timeStampMicros=Infinity
  expect(allowed(original,admit(),fixed)).toBe(false)
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBeUndefined()
 })
 it('does not let a dormant, standby or shared follower authorize another group recall',()=>{
  const {original,admit}=fixture(),request=original.operators.B!
  request.currentRoom='dormitory_1'
  expect(allowed(original,admit(),fixed)).toBe(false)
  request.currentRoom=request.room;request.restingPriority='standby'
  expect(allowed(original,admit(),fixed)).toBe(false)
  request.restingPriority='high';request.groupBindings=[{group:'a',replacement:['X']},{group:'b',replacement:['X']}]
  expect(allowed(original,admit(),fixed)).toBe(false)
  request.groupBindings.push({group:'',replacement:['X']})
  expect(allowed(original,admit(),fixed)).toBe(true)
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','X'],{coordinationRates:fixed})).toBe(false)
 })
 it('checks all working primary members of the recalled group',()=>{
  const {original}=fixture(),target=original.operators.A!
  original.policy.rescueThreshold=.5;original.operators.B!.mood=7;target.group='a'
  original.plan.room_1_3=['C'];original.operators.C=new MowerOperatorState({name:'C',group:'a',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:4,timeStampMicros:0,replacement:['Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(4))
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBeUndefined()
  original.operators.C!.mood=7
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})?.room_1_3).toEqual(['C'])
 })
 it.each([{mood:4,room:'room_1_3',name:'C'},{mood:7,room:'room_1_1',name:'A'}])('selects the first complete sustainable recall with first mood $mood',({mood,room,name})=>{
  const {original}=fixture(mood)
  original.policy.rescueThreshold=.5;original.operators.B!.mood=7;original.operators.B!.replacement=['X','Y']
  original.plan.room_1_3=['C'];original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:20,timeStampMicros:0,replacement:['Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(1))
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toEqual({[room]:[name]})
 })
 it('preserves a prerequisite recall until every requesting member has a replacement',()=>{
  const {original}=fixture(20)
  original.policy.rescueThreshold=.5;original.operators.B!.mood=7;original.operators.B!.group='b'
  original.plan.room_1_3=['C'];original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:20,timeStampMicros:0,replacement:['Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(1))
  original.plan.room_1_4=['B2'];original.operators.B2=new MowerOperatorState({name:'B2',group:'b',room:'room_1_4',index:0,currentRoom:'room_1_4',currentIndex:0,operatorType:'high',mood:7,timeStampMicros:0,replacement:['Y']})
  expect(validateMowerCoordinationSupport(original,{room_1_1:['A']},['B','B2'],{coordinationRates:fixed})).toBe(false)
  expect(planMowerExhaustSupport(original,['B','B2'],{coordinationRates:fixed})).toEqual({room_1_1:['A'],room_1_3:['C']})
 })
 it('keeps alternate replacement handoff available above the rescue line',()=>{
  const {original}=fixture(4)
  original.operators.B!.mood=14;original.operators.A!.replacement=['X','Y']
  original.operators.Y=new MowerOperatorState({name:'Y',mood:24,timeStampMicros:0})
  expect(planMowerExhaustSupport(original,['B'])).toEqual({room_1_1:['Y']})
 })
 it('does not bypass explicit full recovery or missing forecast at the request lower limit',()=>{
  const {original,admit}=fixture(7)
  expect(allowed(original,admit())).toBe(false)
  original.operators.A!.restInFull=true
  expect(allowed(original,admit(),fixed)).toBe(false)
 })
 it('revalidates the rescue phase when executing a previously planned support',()=>{
  const {original}=fixture(20),options={coordinationRates:fixed}
  original.policy.rescueThreshold=.5;original.operators.B!.mood=7
  const plan=planMowerExhaustSupport(original,['B'],options)!
  expect(plan).toEqual({room_1_1:['A']})
  original.operators.B!.mood=14
  expect(validateMowerCoordinationSupport(original,plan,['B'],options)).toBe(false)
  original.operators.B!.mood=7;original.operators.A!.mood=4
  expect(validateMowerCoordinationSupport(original,plan,['B'],options)).toBe(false)
  original.operators.A!.mood=7
  expect(validateMowerCoordinationSupport(original,plan,['B'],options)).toBe(true)
  original.operators.B!.mood=0
  expect(validateMowerCoordinationSupport(original,plan,['B'],options)).toBe(true)
 })
 it('keeps genuine use-up support independent from ordinary rescue admission',()=>{
  const {original,admit}=fixture(4)
  original.operators.B!.mood=14
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{urgentExhaust:true})).toBe(true)
 })
})
