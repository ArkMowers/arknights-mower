import {describe,expect,it} from 'vitest'
import {MowerOperatorState,rescueMoodThreshold} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerRecallCanSustain,mowerRecallMoodAdmissible,mowerCoordinationRequestFulfilled,type MowerCoordinationRates} from './mowerReplacementCoordination'
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
 it('uses explicit physical simulation moods without changing room observations',()=>{
  const {original,admit}=fixture(20)
  original.plan.train=['K'];original.operators.K=new MowerOperatorState({name:'K',room:'train',index:0,currentRoom:'train',currentIndex:0,mood:24})
  const before=JSON.stringify(original),admitted=admit(),options={coordinationRates:fixed,coordinationMoods:{K:24}}
  expect(allowed(original,admitted,fixed)).toBe(false)
  expect(mowerRecallCanSustain(original,admitted,new Set(['A']),['B'],options)).toBe(true)
  expect(mowerRecallCanSustain(original,admitted,new Set(['A']),['B'],{...options,coordinationMoods:{K:NaN}})).toBe(false)
  expect(mowerRecallCanSustain(original,admitted,new Set(['A']),['B'],{...options,coordinationMoods:{K:25}})).toBe(false)
  expect(JSON.stringify(original)).toBe(before)
  expect(admitted.operators.K!.timeStampMicros).toBeUndefined()
 })
 it('advances materialized forecast moods independently of the current calculated snapshot',()=>{
  const {original,admit}=fixture(20)
  original.policy.predictiveMoodControl=true
  original.calculatedMoodSnapshot=Object.freeze({timeMicros:0,values:Object.freeze({A:20,B:0,X:24})})
  for(const op of Object.values(original.operators))op.calculatedMoodSnapshot=original.calculatedMoodSnapshot
  const before=JSON.stringify(original),admitted=admit()
  const rates=(data:MowerSchedulingData)=>{
   for(const op of Object.values(data.operators))expect(op.currentMood(data.nowMicros)).toBe(op.mood)
   expect(data.calculatedMoodSnapshot).toBeUndefined()
   return fixed(data)
  }
  expect(allowed(original,admitted,rates)).toBe(true)
  expect(JSON.stringify(original)).toBe(before)
 })
 it('clamps an exhausted cached prediction instead of reusing the old positive mood',()=>{
  const {original,admit}=fixture(4);original.nowMicros=toMowerMicros(10)
  expect(allowed(original,admit(),fixed)).toBe(false)
 })
 it('rejects reaching the work floor at the same instant the ordinary return is due',()=>{
  const {original,admit}=fixture(6-8/60)
  expect(allowed(original,admit(),fixed)).toBe(false)
 })
 it('does not require another resting group to finish before the requester can return',()=>{
  const {original}=fixture(10)
  original.plan.room_1_3=['C']
  original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:0,timeStampMicros:0,replacement:['X','Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(12))
  const admitted=projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','C']}])
  expect(allowed(original,admitted,data=>{const rates=fixed(data);return {...rates,recovery:{...rates.recovery,C:2}}})).toBe(true)
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
 it('preserves explicit full recovery while an automatic group wait yields to sustainable rescue',()=>{
  const {original,admit}=fixture()
  original.operators.A!.restInFull=true
  expect(allowed(original,admit(),fixed)).toBe(false)
  original.operators.A!.restInFull=false;original.operators.A!.group='g';original.groupRecoveryFullMembers.g=['A']
  expect(allowed(original,admit(),fixed)).toBe(true)
 })
})


describe('recall uses the recovering room operation allowance',()=>{
 it('passes room timing to both explicit full-recovery recall guards',()=>{
  const {original,admit}=fixture(23.9)
  original.dorms[0]!.timeMicros=toMowerMicros(120/3600)
  original.operators.A!.restInFull=true
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
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','X'],{coordinationRates:fixed,requestNames:['B']})).toBe(true)
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

it.each([false,true])('ordinary rescue recall includes a unique normal resting group (multi=%s)',multi=>{
 const {original}=fixture(20),requester=original.operators.B!
 requester.group='b'
 original.plan.room_1_3=['W']
 original.operators.W=new MowerOperatorState({name:'W',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,operatorType:'high',group:'w',replacement:multi?['B']:['Z'],mood:24,timeStampMicros:0})
 original.operators.Z=new MowerOperatorState({name:'Z',mood:24,timeStampMicros:0})
 if(multi)requester.groupBindings=[{group:'b',replacement:['X']},{group:'w',replacement:['Z']}]
 const data=new MowerSchedulingData({...original})
 expect(data.isGroupShiftAnchor(data.operators.B!,'b')).toBe(true)
 expect(planMowerExhaustSupport(data,['B'],{coordinationRates:fixed})).toEqual({room_1_1:['A']})
 expect(mowerCoordinationRequestFulfilled(data,['B'])).toBe(false)
 const completed=projectMowerArrangements(data,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','Free']}])
 expect(mowerCoordinationRequestFulfilled(completed,['B'])).toBe(true)
})

it('does not borrow a working follower normal group mood to authorize another group recall',()=>{
 const {original}=fixture(20)
 original.operators.B!.group='a';original.operators.B!.replacement=['X','F'];original.operators.B!.mood=15
 original.plan.room_1_3=['F'];original.operators.Y=new MowerOperatorState({name:'Y'})
 original.plan.room_2_1=['C'];original.operators.C=new MowerOperatorState({name:'C',room:'room_2_1',index:0,currentRoom:'room_2_1',currentIndex:0,group:'b',replacement:['Z'],operatorType:'high',mood:24,timeStampMicros:0});original.operators.Z=new MowerOperatorState({name:'Z'})
 original.operators.F=new MowerOperatorState({name:'F',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,operatorType:'high',group:'b',replacement:['Y'],groupBindings:[{group:'b',replacement:['Y']},{group:'a',replacement:['Y']}],mood:10,timeStampMicros:0})
 const data=new MowerSchedulingData({...original})
 expect(data.shiftRequestGroups(['B'])).toEqual(['a'])
 expect(mowerRecallMoodAdmissible(data,new Set(['A']),['B','F'],['B'])).toBe(false)
 data.operators.B!.mood=7
 expect(mowerRecallMoodAdmissible(data,new Set(['A']),['B','F'],['B'])).toBe(true)
 const completed=projectMowerArrangements(data,[{room_1_2:['F'],room_1_3:['Y'],dormitory_1:['A','B','Free']}])
 expect(completed.operators.C!.isResting()).toBe(false)
 expect(mowerCoordinationRequestFulfilled(completed,['B'])).toBe(true)
})


it.each([0,.5].flatMap(waitCap=>[4,20].map(target=>({waitCap,target}))))('ordinary rescue bypasses only automatic group wait with safe full-recovery endurance (cap=$waitCap, target=$target)',({waitCap,target})=>{
 const {original}=fixture(target)
 original.policy.rescueThreshold=.5;original.operators.B!.mood=7
 original.operators.A!.group='recovering'
 original.groupShiftState.recovering=true
 original.groupRecoveryFullMembers.recovering=['A']
 original.groupMoodGapMaxExtraWaitHours=waitCap
 const before=JSON.stringify(original)
 const plan=planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})
 if(target===20)expect(plan).toEqual({room_1_1:['A']})
 else expect(plan).toBeUndefined()
 expect(JSON.stringify(original)).toBe(before)
 if(target===20){
  original.operators.A!.restInFull=true
  expect(planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})).toBeUndefined()
 }
})


it('leaves the ordinary automatic group wait policy in place after an isolated rescue preview',()=>{
 const {original}=fixture(20)
 original.policy.rescueThreshold=.5;original.operators.B!.mood=7
 original.operators.A!.group='recovering';original.groupShiftState.recovering=true
 original.groupRecoveryFullMembers.recovering=['A']
 const plan=planMowerExhaustSupport(original,['B'],{coordinationRates:fixed})
 expect(plan).toEqual({room_1_1:['A']})
 expect(original.operators.A!.isResting()).toBe(true)
 expect(original.groupRecoveryFullMembers.recovering).toEqual(['A'])
})


function requestingGroup(){
 const {original}=fixture(3)
 original.operators.B!.group='request'
 original.groupRestInFullOnMoodGap=false
 original.plan.room_1_3=['C']
 original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,operatorType:'high',group:'request',mood:16,timeStampMicros:0,replacement:['Y']})
 original.operators.Y=new MowerOperatorState({name:'Y',mood:24,timeStampMicros:0})
 const admit=()=>projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],room_1_3:['Y'],dormitory_1:['Free','B','C']}])
 return {original,admit}
}

describe('ordinary recall waits for the executable requesting-unit return',()=>{
 it('admits a complete group that returns normally before all its members are full',()=>{
  const {original,admit}=requestingGroup(),before=JSON.stringify(original)
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','C'],{coordinationRates:fixed,requestNames:['B']})).toBe(true)
  expect(validateMowerCoordinationSupport(original,{room_1_1:['A']},['B','C'],{coordinationRates:fixed,requestNames:['B']})).toBe(true)
  expect(JSON.stringify(original)).toBe(before)
 })
 it.each(['explicit','automatic-gap','forced-rest','reserved'] as const)('preserves the requesting group %s protection',kind=>{
  const {original,admit}=requestingGroup(),options={coordinationRates:fixed,requestNames:['B'],reservedNames:new Set<string>()}
  if(kind==='explicit')original.operators.B!.restInFull=true
  if(kind==='automatic-gap'){original.groupRestInFullOnMoodGap=true;original.groupMoodGapThresholdMinutes=30}
  if(kind==='forced-rest'){original.backupGroupTasks=[[{group:'request',action:'off',mode:'forced'}]];original.planConditions=[true]}
  if(kind==='reserved')options.reservedNames.add('B')
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','C'],options)).toBe(false)
 })
 it('does not credit a partial return which leaves one requested member in the dorm',()=>{
  const {original,admit}=requestingGroup()
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','C'],{coordinationRates:fixed,requestNames:['B'],reservedNames:new Set(['C'])})).toBe(false)
 })
 it.each(['unrelated','standby'] as const)('does not wait for a slow %s resident',kind=>{
  const {original}=fixture(8)
  original.plan.room_1_3=['C']
  original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',group:kind==='standby'?'request':'other',restingPriority:kind==='standby'?'standby':'high',mood:0,timeStampMicros:0,replacement:['Y']})
  original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0})
  if(kind==='standby')original.operators.B!.group='request'
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'C',toMowerMicros(24))
  const admitted=projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','C']}])
  expect(mowerRecallCanSustain(original,admitted,new Set(['A']),['B'],{coordinationRates:data=>({...fixed(data),recovery:{...fixed(data).recovery,C:1}})})).toBe(true)
 })
 it('rejects the same group return when the recalled worker cannot reach its deadline',()=>{
  const {original,admit}=requestingGroup()
  original.operators.A!.mood=1
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','C'],{coordinationRates:fixed,requestNames:['B']})).toBe(false)
 })
})

it.each([0,8])('integrates complete requesting units with a second initial mood of %s',secondMood=>{
 const {original}=fixture(8)
 original.plan.room_1_3=['C'];original.plan.room_1_4=['D']
 original.operators.C=new MowerOperatorState({name:'C',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,operatorType:'high',mood:secondMood,timeStampMicros:0,replacement:['Y']})
 original.operators.D=new MowerOperatorState({name:'D',room:'room_1_4',index:0,currentRoom:'dormitory_1',currentIndex:2,operatorType:'high',mood:20,timeStampMicros:0,replacement:['Y']})
 original.operators.Y=new MowerOperatorState({name:'Y',currentRoom:'room_1_4',currentIndex:0,mood:24,timeStampMicros:0})
 original.plan.dormitory_1!.push('Free');original.dorms[2]=new MowerDormState(['dormitory_1',2],'D',toMowerMicros(1));original.dorms.push(new MowerDormState(['dormitory_1',3]))
 const admitted=projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],room_1_3:['Y'],room_1_4:['D'],dormitory_1:['Free','B','Free','C']}]),returned:string[]=[]
 const dynamic=(data:MowerSchedulingData)=>{
  if(data.operators.C!.currentRoom==='room_1_3')returned.push('C')
  return {...fixed(data),work:{...fixed(data).work,A:data.operators.C!.currentRoom==='room_1_3'?2:1}}
 }
 expect(mowerRecallCanSustain(original,admitted,new Set(['A','D']),['B','C'],{coordinationRates:dynamic})).toBe(true)
 if(secondMood===8)expect(returned).toContain('C')
})


it('does not materialize retained task release targets on the actual queue during a forecast',()=>{
 const {original,admit}=fixture(20),retained=new MowerTask({time:10,type:T.RELEASE_DORM,plan:{dormitory_1:['Current','Current','Free']},metadata:'E'})
 retained.executionRetained=true
 original.operators.E=new MowerOperatorState({name:'E',currentRoom:'dormitory_1',currentIndex:2,mood:24,timeStampMicros:0})
 original.dorms[2]=new MowerDormState(['dormitory_1',2],'E',0)
 const before=JSON.stringify(retained)
 mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:fixed,tasks:[retained]})
 expect(JSON.stringify(retained)).toBe(before)
 expect(retained.releaseTargets).toBeUndefined()
})

it.each(['ordinary','explicit','gap'] as const)('handles an observed zero-recovery low-priority peer under %s return rules',rule=>{
 const {original,admit}=requestingGroup()
 original.operators.A!.mood=8
 Object.assign(original.operators.C!,{mood:12,restingPriority:'low',restInFull:rule==='explicit'})
 if(rule==='gap'){original.groupRecoveryFullMembers.request=['B','C'];original.groupMoodGapMaxExtraWaitHours=0}
 const rates=(data:MowerSchedulingData)=>({...fixed(data),recovery:{...fixed(data).recovery,C:0}})
 expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B','C'],{coordinationRates:rates,requestNames:['B']})).toBe(rule==='ordinary')
})
