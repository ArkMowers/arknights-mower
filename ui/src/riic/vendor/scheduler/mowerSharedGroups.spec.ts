import nativeOracle from './fixtures/mower-shared-groups-20261013.json'
import {describe,it,expect} from 'vitest'
import {MowerOperatorState,type MowerGroupBinding} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {normalizeMowerSharedArrangement,mowerArrangementGroupTransitions,commitMowerGroupShifts,mowerSameGroupPrimaryReplacement} from './mowerSharedGroups'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan,mowerTryReorder} from './mowerOrdinaryPlanning'
import {normalizeMowerRecoveryBeds} from './mowerRecoveryBeds'
import {generateMowerDormTasks} from './mowerDormTasks'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'
import {MowerTaskQueue,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {prepareMowerDormSelection} from './mowerSelection'

function fixture(dorm=false){
 const plan={room_1_1:['A'],room_1_2:['B'],room_1_3:dorm?[]:['F'],dormitory_1:dorm?['F','Free','Free','Free','Free']:['Free','Free','Free','Free','Free']}
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,group,replacement] of [['A','room_1_1','a',['X']],['B','room_1_2','b',['Y']],['F',dorm?'dormitory_1':'room_1_3','a',dorm?['Free']:['C','D']]] as [string,string,string,string[]][]){
  operators[name]=new MowerOperatorState({name,room,index:0,currentRoom:room,currentIndex:0,group,replacement,operatorType:'high',restingPriority:'high',mood:10,timeStampMicros:0})
 }
 operators.F!.groupBindings=[{group:'a',replacement:dorm?['Free']:['C','D']},{group:'b',replacement:dorm?['Free']:['D','E']}]
 for(const name of ['X','Y','C','D','E'])operators[name]=new MowerOperatorState({name,mood:24,timeStampMicros:0})
 return new MowerSchedulingData({alpha:true,plan,operators,dorms:plan.dormitory_1.map((_,index)=>new MowerDormState(['dormitory_1',index],'',undefined,dorm&&index===0)),nowMicros:0})
}
function apply(data:MowerSchedulingData,plan:MowerTaskPlan){expect(normalizeMowerSharedArrangement(data,plan)).toBe(true);return projectMowerArrangements(data,[plan])}
describe('October 13 shared group bindings and fixed-primary swaps',()=>{
 it('keeps a full fixed dorm cover when only its concrete shared binding is resting',()=>{
  const data=fixture(true);data.freeRoom=true
  data.operators.F!.groupBindings[1]!.replacement=['C']
  commitMowerGroupShifts(data,{a:false,b:true})
  const selected=['C','Current','Current','Current','Current']
  prepareMowerDormSelection(data,selected,'dormitory_1')
  expect(selected[0]).toBe('C')
  expect(data.dynamicDormPosition('dormitory_1',0)).toBe(false)
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(true)
  expect(data.dorms[0]!.autoFree).toBe(true)
 })
 it('switches shared dorm execution between Free and concrete replacement without changing its bed pool',()=>{
  const data=fixture(true),bed=data.dorms[0]!
  data.operators.F!.groupBindings[1]!.replacement=['C']
  commitMowerGroupShifts(data,{a:true,b:false})
  expect(data.dynamicDormPosition('dormitory_1',0)).toBe(true)
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(false)
  commitMowerGroupShifts(data,{a:false,b:true})
  expect(data.dynamicDormPosition('dormitory_1',0)).toBe(false)
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(true)
  commitMowerGroupShifts(data,{a:true,b:false})
  expect(data.dynamicDormPosition('dormitory_1',0)).toBe(true)
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(false)
  expect(data.dorms[0]).toBe(bed);expect(bed.autoFree).toBe(true)
 })
 it('uses pending shared group transitions at the dorm execution boundary',()=>{
  const data=fixture(true);data.freeRoom=true
  data.operators.F!.groupBindings[1]!.replacement=['C']
  commitMowerGroupShifts(data,{a:true,b:false})
  data.pendingGroupTransitions={a:false,b:true}
  const selected=['C','Current','Current','Current','Current']
  prepareMowerDormSelection(data,selected,'dormitory_1')
  expect(selected[0]).toBe('C')
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(true)
  expect(data.groupShiftState).toEqual({a:true,b:false})
 })
 it('protects concrete candidates from every binding while the shared dorm is fixed',()=>{
  const data=fixture(true);data.freeRoom=true
  data.operators.F!.groupBindings=[{group:'a',replacement:['C']},{group:'b',replacement:['D']}]
  commitMowerGroupShifts(data,{a:false,b:true})
  expect(data.operators.F!.replacement).toEqual(['D'])
  expect(data.dormReplacementForSlot('C','dormitory_1',0)).toBe(true)
  expect(data.dormReplacementForSlot('D','dormitory_1',0)).toBe(true)
  expect(data.dormReplacementForSlot('E','dormitory_1',0)).toBe(false)
 })
 it('does not release a completed custom recovery target from its fixed replacement post',()=>{
  const data=fixture(true);data.freeRoom=true
  data.operators.F!.groupBindings[1]!.replacement=['C']
  commitMowerGroupShifts(data,{a:false,b:true})
  data.operators.C!.restMoodLimit=true
  expect(data.restMoodComplete('C')).toBe(true)
  const selected=['C','Current','Current','Current','Current']
  prepareMowerDormSelection(data,selected,'dormitory_1')
  expect(selected[0]).toBe('C')
 })
 it('keeps the shared dorm primary and Current outside dynamic occupant recovery',()=>{
  const data=fixture(true)
  commitMowerGroupShifts(data,{a:true,b:false})
  expect(data.dynamicDormPosition('dormitory_1',0)).toBe(true)
  expect(data.dynamicDormPosition('dormitory_1',0,'C')).toBe(true)
  expect(data.dynamicDormPosition('dormitory_1',0,'F')).toBe(false)
  expect(data.dynamicDormPosition('dormitory_1',0,'Current')).toBe(false)
 })
 for(const sample of nativeOracle.freeSlots)it('native effective shared Free bed: '+sample.name,()=>{
  const data=fixture(true);data.groupShiftState=Object.fromEntries(Object.entries(sample.state).filter((entry):entry is [string,boolean]=>typeof entry[1]==='boolean'));data.dorms[0]!.name=sample.reserved
  expect(data.effectiveFreeSlot(data.dorms[0]!,new Set(sample.inactive),new Set(sample.active))).toBe(sample.effective)
 })
 it('uses each binding candidate list and retains the common cover until the last group returns',()=>{
  const data=fixture(),first={room_1_1:['X']}
  const resting=apply(data,first);expect(first).toEqual({room_1_1:['X'],room_1_3:['C']})
  expect(data.groupIsResting('a')).toBe(false);expect(resting.groupIsResting('a')).toBe(true)
  const second:MowerTaskPlan={room_1_2:['Y']},both=apply(resting,second)
  expect(second.room_1_3).toEqual(['D']);expect(both.operators.F!.group).toBe('a')
  const one:MowerTaskPlan={room_1_1:['A']},remaining=apply(both,one)
  expect(one.room_1_3).toBeUndefined();expect(remaining.currentOperator('room_1_3',0)?.name).toBe('D');expect(remaining.operators.F!.group).toBe('b')
  const last:MowerTaskPlan={room_1_2:['B']},working=apply(remaining,last)
  expect(last.room_1_3).toEqual(['F']);expect(working.currentOperator('room_1_3',0)?.name).toBe('F')
 })
 it('rejects disjoint simultaneous covers without partial plan or group state mutation',()=>{
  const data=fixture();data.operators.F!.groupBindings[1]!.replacement=['E']
  const plan={room_1_1:['X'],room_1_2:['Y']},before=structuredClone(plan)
  expect(normalizeMowerSharedArrangement(data,plan)).toBe(false);expect(plan).toEqual(before);expect(data.groupShiftState).toEqual({})
 })
 it('does not let a shared follower mood independently mark its fixed groups resting',()=>{
  const data=fixture();data.operators.F!.currentRoom='dormitory_1';data.operators.F!.currentIndex=0
  expect(data.groupIsResting('a')).toBe(false);expect(data.shiftGroupMembers('b')).toEqual(['B','F'])
 })
 it('opens a shared Free dorm once, keeps its recovering occupant, and closes only after all groups return',()=>{
  const data=fixture(true),first:MowerTaskPlan={room_1_1:['X']},resting=apply(data,first)
  expect(first.dormitory_1?.[0]).toBe('Free');expect(resting.effectiveFreeSlot(resting.dorms[0]!)).toBe(true)
  resting.operators.C!.currentRoom='dormitory_1';resting.operators.C!.currentIndex=0;resting.dorms[0]!.name='C'
  const second:MowerTaskPlan={room_1_2:['Y']},both=apply(resting,second)
  expect(second.dormitory_1).toBeUndefined();expect(both.currentOperator('dormitory_1',0)?.name).toBe('C')
  const one:MowerTaskPlan={room_1_1:['A']},remaining=apply(both,one)
  expect(remaining.effectiveFreeSlot(remaining.dorms[0]!)).toBe(true);expect(one.dormitory_1).toBeUndefined()
  const last:MowerTaskPlan={room_1_2:['B']},working=apply(remaining,last)
  expect(last.dormitory_1?.[0]).toBe('F');expect(working.effectiveFreeSlot(working.dorms[0]!)).toBe(false)
  expect(working.dorms[0]!.name).toBe('');expect(working.operators.C!.currentRoom).toBe('')
 })
 it('adds recovery capacity from an additional Free binding without duplicating physical beds',()=>{
  const config:RuntimeConfig={positions:[],beds:[],mowerAlpha:true,mowerSourcePlan:{dormitory_1:[{agent:'F',group:'a',replacement:['C'],groupBindings:[{group:'a',replacement:['C']},{group:'b',replacement:['Free']}]}]}}
  normalizeMowerRecoveryBeds(config);normalizeMowerRecoveryBeds(config)
  expect(config.beds).toEqual([{id:'dormitory_1_0',roomId:'dormitory_1',vip:false,managedRecovery:true}])
 })
 it('plans a whole group with working primary and fixed-dorm primary swapping posts',()=>{
  const data=fixture(true);delete data.operators.B;data.operators.F!.groupBindings=[];data.operators.F!.replacement=['A'];data.operators.A!.replacement=['F']
  expect(mowerSameGroupPrimaryReplacement(data,data.operators.A!,'F')).toBe(true)
  const plan:MowerTaskPlan={};expect(mowerGetRestingPlan(data,['A','F'],[],plan)).toBe(true)
  expect(plan).toEqual({room_1_1:['F'],dormitory_1:['A','Current','Current','Current','Current']})
  expect(data.dorms.every(b=>!b.name)).toBe(true)
  const projected=projectMowerArrangements(data,[plan]);expect(projected.operators.A!.currentRoom).toBe('dormitory_1');expect(projected.operators.F!.currentRoom).toBe('room_1_1')
 })
 it('allocates the working primary to an opened grouped dorm Free bed in the real downshift planner',()=>{
  const data=fixture(true);delete data.operators.B;data.operators.F!.groupBindings=[]
  const plan:MowerTaskPlan={};expect(mowerGetRestingPlan(data,['A','F'],[],plan)).toBe(true)
  const reorder=mowerTryReorder(data,plan);if(reorder)Object.assign(plan,reorder)
  expect(plan.room_1_1).toEqual(['X']);expect(plan.dormitory_1).toContain('A')
  const projected=projectMowerArrangements(data,[plan]);expect(projected.operators.F!.currentRoom).toBe('');expect(projected.operators.A!.isResting()).toBe(true)
 })
 it('retains recovery reservations in shared Free beds while the group downshift is still unconfirmed',()=>{
  const data=fixture(true);data.plan.dormitory_1=['F'];data.dorms=data.dorms.slice(0,1)
  const plan:MowerTaskPlan={};expect(mowerGetRestingPlan(data,['A','F'],[],plan)).toBe(true)
  expect(data.groupIsResting('a')).toBe(false);expect(data.dorms[0]!.name).toBe('A')
  expect(data.effectiveFreeSlot(data.dorms[0]!)).toBe(true)
  const reorder=mowerTryReorder(data,plan);expect(reorder?.dormitory_1).toEqual(['A'])
  if(reorder)Object.assign(plan,reorder)
  const projected=projectMowerArrangements(data,[plan])
  expect(projected.operators.A!.currentRoom).toBe('dormitory_1')
  expect(projected.groupIsResting('a')).toBe(true);expect(projected.groupIsResting('b')).toBe(false)
 })
 it('opens only the departing anchor group beds when a shared follower is bound to another working group',()=>{
  const data=fixture(true);data.plan.dormitory_1=['G','F']
  data.operators.F!.index=1;data.operators.F!.currentIndex=1
  data.operators.G=new MowerOperatorState({name:'G',room:'dormitory_1',index:0,currentRoom:'dormitory_1',currentIndex:0,group:'a',replacement:['Free'],operatorType:'high',mood:24,timeStampMicros:0})
  data.dorms=[0,1].map(index=>new MowerDormState(['dormitory_1',index],'',undefined,true))
  const plan:MowerTaskPlan={};expect(mowerGetRestingPlan(data,['B','F'],[],plan)).toBe(true)
  const reorder=mowerTryReorder(data,plan);if(reorder)Object.assign(plan,reorder)
  expect(plan.dormitory_1).toEqual(['Current','B'])
  const projected=projectMowerArrangements(data,[plan])
  expect(projected.currentOperator('dormitory_1',0)?.name).toBe('G')
  expect(projected.groupIsResting('a')).toBe(false);expect(projected.groupIsResting('b')).toBe(true)
 })
 it('allows a shared dorm follower to swap with a primary in its departing secondary group',()=>{
  const data=fixture(true);data.plan.dormitory_1=['F'];data.dorms=[]
  data.operators.F!.groupBindings=[{group:'a',replacement:['A']},{group:'b',replacement:['B']}]
  data.operators.F!.replacement=['A'];data.operators.B!.replacement=['F']
  const plan:MowerTaskPlan={};expect(mowerGetRestingPlan(data,['B','F'],[],plan)).toBe(true)
  expect(plan).toEqual({room_1_2:['F'],dormitory_1:['B']})
  expect(data.operators.F!.group).toBe('a')
 })
 it('matches two followers globally instead of consuming the only candidate greedily',()=>{
  const data=fixture();data.plan.room_1_3!.push('G')
  const bindings:MowerGroupBinding[]=[{group:'a',replacement:['C']},{group:'b',replacement:['C']}]
  data.operators.G=new MowerOperatorState({name:'G',room:'room_1_3',index:1,group:'a',replacement:['C'],groupBindings:bindings,operatorType:'high'})
  const plan:MowerTaskPlan={room_1_1:['X']};expect(normalizeMowerSharedArrangement(data,plan)).toBe(true);expect(plan.room_1_3).toEqual(['D','C'])
 })
 it('return generation preserves a shared follower while another anchor remains at rest',()=>{
  let data=fixture(true);data=apply(data,{room_1_1:['X'],room_1_2:['Y'],dormitory_1:['Free','A','B','Current','Current']})
  data.dorms[1]!.name='A';data.dorms[1]!.timeMicros=toMowerMicros(1);data.dorms[2]!.name='B';data.dorms[2]!.timeMicros=toMowerMicros(2)
  const tasks=generateMowerDormTasks([{timeMicros:toMowerMicros(1),dorms:[data.dorms[1]!],restInFull:false}],data)
  expect(tasks).toHaveLength(1);expect(tasks[0]!.plan.room_1_1).toEqual(['A']);expect(tasks[0]!.plan.dormitory_1?.[0]).not.toBe('F')
 })
 it('commits group state explicitly rather than mutating it during normalization',()=>{
  const data=fixture(),plan={room_1_1:['X']};normalizeMowerSharedArrangement(data,plan)
  expect(data.groupShiftState).toEqual({});commitMowerGroupShifts(data,mowerArrangementGroupTransitions(data,plan));expect(data.groupShiftState.a).toBe(true)
 })
 it('executes grouped dorm Free admission and return through the physical runtime',()=>{
  const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',group:'a',candidates:['X']},{id:'dormitory_1_0',roomId:'dormitory_1',primary:'F',group:'a',candidates:[],dormitory:true}],beds:[1,2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===1})),initialMorale:{A:10,F:24,X:24},idleOperators:['I1','I2','I3','I4'],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'a',replacement:['X']}],dormitory_1:[{agent:'F',group:'a',replacement:['Free']},...[1,2,3,4].map(()=>({agent:'Free',group:'',replacement:[]}))]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
  const state=createRosterRuntime(config),rates={workRate:()=>1,recoveryRate:()=>4}
  let down=false,returned=false
  for(let tick=0;tick<100&&state.time<6;tick++){
   settleRoster(state,rates)
   if(state.occupants.room_1_1_0==='X'&&!getMowerSourceRuntime(state).execution&&!getMowerSourceRuntime(state).queue.tasks.some(t=>t.backupShiftActive)){down=true;expect([...Object.values(state.bedOccupants),state.occupants.dormitory_1_0]).toContain('A')}
   if(down&&state.occupants.room_1_1_0==='A'){returned=true;expect(state.occupants.dormitory_1_0??state.bedOccupants.dormitory_1_0).toBe('F');break}
   const next=nextRosterActionHours(state,rates);advanceRoster(state,Math.min(Number.isFinite(next)?Math.max(next,1e-6):1,1),rates)
  }
  expect(down).toBe(true);expect(returned).toBe(true)
  expect(getMowerSourceRuntime(state).data.groupIsResting('a')).toBe(false)
 })
 it('executes overlapping group rests and restores their shared Free keeper only after the final return',()=>{
  const bindings=[{group:'a',replacement:['Free']},{group:'b',replacement:['Free']}]
  const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',group:'a',candidates:['X']},{id:'room_1_2_0',roomId:'room_1_2',primary:'B',group:'b',candidates:['Y']},{id:'dormitory_1_0',roomId:'dormitory_1',primary:'F',group:'a',candidates:[],dormitory:true}],beds:[1,2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===1})),initialMorale:{A:10,B:12,F:24,X:24,Y:24},idleOperators:['I1','I2','I3','I4','I5'],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'a',replacement:['X']}],room_1_2:[{agent:'B',group:'b',replacement:['Y']}],dormitory_1:[{agent:'F',group:'a',replacement:['Free'],groupBindings:bindings},...[1,2,3,4].map(()=>({agent:'Free',group:'',replacement:[]}))]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
  const state=createRosterRuntime(config),rates={workRate:()=>1,recoveryRate:()=>4}
  let together=false,partial=false,returned=false
  for(let tick=0;tick<200&&state.time<7;tick++){
   settleRoster(state,rates)
   const source=getMowerSourceRuntime(state),data=source.data
   if(!source.execution&&!source.queue.tasks.some(t=>t.backupShiftActive)){
    const a=data.groupIsResting('a'),b=data.groupIsResting('b')
    if(a&&b)together=true
    if(together&&a!==b){partial=true;expect(data.currentOperator('dormitory_1',0)?.name).not.toBe('F')}
    if(together&&!a&&!b){returned=true;expect(data.currentOperator('dormitory_1',0)?.name).toBe('F');break}
   }
   const next=nextRosterActionHours(state,rates);advanceRoster(state,Math.min(Number.isFinite(next)?Math.max(next,1e-6):1,1),rates)
  }
  expect({together,partial,returned,diagnostics:[...new Set(state.diagnostics.filter(d=>d.code==='mower-task-exception').map(d=>d.message))]}).toEqual({together:true,partial:true,returned:true,diagnostics:[]})
 })
 it('returns a swapped working primary from a fixed named dorm post without inventing Free capacity',()=>{
  const keepers=['K1','K2','K3','K4']
  const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',group:'a',candidates:['F']},{id:'dormitory_1_0',roomId:'dormitory_1',primary:'F',group:'a',candidates:[],dormitory:true},...keepers.map((name,i)=>({id:'dormitory_1_'+(i+1),roomId:'dormitory_1',primary:name,candidates:[],dormitory:true,permanent:true}))],beds:[],initialMorale:{A:10,F:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'a',replacement:['F']}],dormitory_1:[{agent:'F',group:'a',replacement:['A']},...keepers.map(name=>({agent:name,group:'',replacement:[]}))]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
  const state=createRosterRuntime(config),rates={workRate:()=>1,recoveryRate:()=>4}
  let down=false,returned=false
  for(let tick=0;tick<100&&state.time<6;tick++){
   settleRoster(state,rates)
   const data=getMowerSourceRuntime(state).data
   if(state.occupants.room_1_1_0==='F'){down=true;expect(state.occupants.dormitory_1_0).toBe('A');expect(data.dorms).toHaveLength(0);expect(data.groupDorms[0]!.name).toBe('A')}
   if(down&&state.occupants.room_1_1_0==='A'){returned=true;expect(state.occupants.dormitory_1_0).toBe('F');break}
   const next=nextRosterActionHours(state,rates);advanceRoster(state,Math.min(Number.isFinite(next)?Math.max(next,1e-6):1,1),rates)
  }
  expect({down,returned,errors:state.diagnostics.filter(d=>d.code==='mower-task-exception')}).toEqual({down:true,returned:true,errors:[]})
 })
 it('uses the configured 60 minute mood gap with two power plants',()=>{
  const data=fixture();data.groupMoodGapThresholdMinutes=60;delete data.operators.F;delete data.operators.B;data.plan.room_1_2=['G'];data.operators.G=new MowerOperatorState({name:'G',room:'room_1_2',index:0,group:'a',operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:1,mood:10,timeStampMicros:0})
  data.operators.A!.currentRoom='dormitory_1';data.operators.A!.currentIndex=0;data.dorms[0]!.name='A';data.dorms[0]!.timeMicros=toMowerMicros(3);data.dorms[1]!.name='G';data.dorms[1]!.timeMicros=toMowerMicros(1.75)
  const q=new MowerTaskQueue();planMowerAlphaMetadata(data,q,[])
  expect(q.tasks.find(t=>t.plan.room_1_1?.[0]==='A')?.timeMicros).toBeGreaterThan(toMowerMicros(2.5))
 })
})

describe('shared-group differential against unmodified ab0a4e5 Python methods',()=>{
 for(const scenario of nativeOracle.cases)it(scenario.name,()=>{
  let data=fixture(scenario.dorm)
  if(scenario.disjoint)data.operators.F!.groupBindings[1]!.replacement=['E']
  for(const step of scenario.steps){
   const plan=structuredClone(step.input) as MowerTaskPlan,before=JSON.stringify(data)
   expect(normalizeMowerSharedArrangement(data,plan)).toBe(step.accepted)
   expect(plan).toEqual(step.plan)
   expect(JSON.stringify(data)).toBe(before)
   if(step.accepted)data=projectMowerArrangements(data,[plan])
   expect(data.groupShiftState).toEqual(step.groups)
  }
 })
})
