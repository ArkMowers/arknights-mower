import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerResting,mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {commitMowerGroupShifts,normalizeMowerSharedArrangement,mowerRestingBindingGroups} from './mowerSharedGroups'
import {generateMowerDormTasks} from './mowerDormTasks'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'
import {alphaDormResidents,alphaRestoreDisplaced} from './mowerAlphaDorm'
import {projectMowerArrangements} from './mowerObservations'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {planMowerAlphaExhaustSupport} from './mowerAlphaExhaustSupport'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'

function fixture(){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,group,replacement] of [['A','room_1_1','a',['X']],['B','room_1_2','b',['Y']],['F','room_1_3','a',['C','D']]] as [string,string,string,string[]][]){
  operators[name]=new MowerOperatorState({name,room,index:0,currentRoom:room,currentIndex:0,group,replacement,operatorType:'high',restingPriority:'high',mood:name==='F'?5:24,timeStampMicros:0,...(name==='F'?{groupBindings:[{group:'a',replacement:['C','D']},{group:'b',replacement:['D','E']},{group:'',replacement:['P']}]}:{})})
 }
 for(const name of ['X','Y','C','D','E','P'])operators[name]=new MowerOperatorState({name,mood:24,timeStampMicros:0})
 return new MowerSchedulingData({alpha:true,plan:{room_1_1:['A'],room_1_2:['B'],room_1_3:['F'],dormitory_1:['Free','Free','Free']},operators,dorms:[0,1,2].map(i=>new MowerDormState(['dormitory_1',i])),nowMicros:0,groupShiftState:{a:false,b:false}})
}
function resting(data:MowerSchedulingData,name:string,index:number,hours:number){
 const op=data.operators[name]!,bed=data.dorms[index]!
 op.currentRoom='dormitory_1';op.currentIndex=index;bed.name=name;bed.timeMicros=toMowerMicros(hours)
 return bed
}
describe('shared working primary with one empty binding',()=>{
 it('rests independently using its empty column without shifting either named group',()=>{
  const data=fixture(),queue=new MowerTaskQueue()
  expect(data.operators.F!.group).toBe('');expect(data.operators.F!.replacement).toEqual(['P'])
  expect(mowerResting(data,queue)).toEqual({room_1_3:['P']})
  expect(data.dorms.filter(b=>b.name).map(b=>b.name)).toEqual(['F'])
  expect(data.groupShiftState).toEqual({a:false,b:false})
 })
 it('uses a departing primary from the same named group as the shared replacement',()=>{
  const data=fixture(),plan:MowerTaskPlan={};data.operators.F!.groupBindings[0]!.replacement=['A']
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(true)
  expect(plan).toEqual({room_1_1:['X'],room_1_3:['A']})
  expect(data.dorms.filter(b=>b.name).map(b=>b.name)).toEqual(['F'])
 })
 it.each(['X','P'])('replaces a personal downshift with a named downshift in the same pass, including reuse of superseded cover %s',cover=>{
  const data=fixture();data.operators.F!.mood=1;data.operators.A!.mood=5;data.operators.A!.replacement=[cover]
  const plan=mowerResting(data,new MowerTaskQueue())
  expect(data.dorms.filter(b=>b.name==='F')).toHaveLength(1)
  expect(data.dorms.filter(b=>b.name==='A')).toHaveLength(1)
  expect(plan).toEqual({room_1_3:['C'],room_1_1:[cover]})
 })
 it('prioritizes named group intersections while preserving the existing recovery bed and deadline',()=>{
  const data=fixture(),bed=resting(data,'F',0,8),plan:MowerTaskPlan={}
  data.operators.P!.currentRoom='room_1_3';data.operators.P!.currentIndex=0
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(true)
  expect(plan).toEqual({room_1_1:['X'],room_1_3:['C']})
  expect(bed.name).toBe('F');expect(bed.timeMicros).toBe(toMowerMicros(8))
  expect(data.operators.F!.currentRoom).toBe('dormitory_1')
  commitMowerGroupShifts(data,{a:true,b:true})
  const both:MowerTaskPlan={room_1_2:['Y']}
  expect(normalizeMowerSharedArrangement(data,both)).toBe(true);expect(both.room_1_3).toEqual(['D'])
  expect(mowerRestingBindingGroups(data,data.operators.F!)).toEqual(['a','b'])
  expect(data.operators.F!.group).toBe('');expect(data.operators.F!.replacement).toEqual(['P'])
 })
 it('waits for disjoint named covers without considering the personal replacement',()=>{
  const data=fixture();data.operators.F!.groupBindings[1]!.replacement=['E']
  const plan:MowerTaskPlan={room_1_1:['X'],room_1_2:['Y']},before=structuredClone(plan)
  expect(normalizeMowerSharedArrangement(data,plan)).toBe(false);expect(plan).toEqual(before)
 })
 it('uses the personal replacement after the last group returns, then returns the primary at its own deadline',()=>{
  const data=fixture(),a=resting(data,'A',1,2),f=resting(data,'F',0,8)
  data.operators.C!.currentRoom='room_1_3';data.operators.C!.currentIndex=0
  commitMowerGroupShifts(data,{a:true})
  const tasks=generateMowerDormTasks([{timeMicros:a.timeMicros!,dorms:[a],restInFull:false},{timeMicros:f.timeMicros!,dorms:[f],restInFull:false}],data)
  expect(tasks).toHaveLength(2)
  expect(tasks[0]!.plan).toEqual({room_1_1:['A'],room_1_3:['P']})
  expect(tasks[1]!.plan).toEqual({room_1_3:['F']})
  expect(tasks[1]!.timeMicros).toBe(toMowerMicros(8-8/60))
  expect(f.name).toBe('F');expect(f.timeMicros).toBe(toMowerMicros(8))
 })
 it('does not let personal return overwrite a resting named group cover',()=>{
  const data=fixture(),f=resting(data,'F',0,1)
  commitMowerGroupShifts(data,{a:true})
  expect(generateMowerDormTasks([{timeMicros:f.timeMicros!,dorms:[f],restInFull:false}],data)).toEqual([])
 })
 it.each(['normalize','prepare'])('preserves personal recovery when an old group return explicitly recalls the shared primary: %s',entry=>{
  const data=fixture(),f=resting(data,'F',0,8);resting(data,'A',1,2)
  data.operators.C!.currentRoom='room_1_3';data.operators.C!.currentIndex=0
  data.operators.X!.currentRoom='room_1_1';data.operators.X!.currentIndex=0
  commitMowerGroupShifts(data,{a:true})
  const task=new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['A'],room_1_3:['F']}})
  if(entry==='normalize')expect(normalizeMowerSharedArrangement(data,task.plan)).toBe(true)
  else {
   const queue=new MowerTaskQueue();queue.tasks=[task]
   const model:MowerShiftModel={count:0,evaluate:()=>[],swap:d=>d,transition:()=>({}),activate:()=>{}}
   expect(()=>prepareMowerShiftCycle(data,task,queue,model)).not.toThrow()
  }
  expect(task.plan.room_1_3).toEqual(['P']);expect(task.plan.room_1_1).toEqual(['A'])
  expect(data.operators.F!.isResting()).toBe(true);expect(f.name).toBe('F');expect(f.timeMicros).toBe(toMowerMicros(8))
 })
 it('includes independent recovery in metadata without using it as a named group anchor',()=>{
  const data=fixture(),f=resting(data,'F',0,8),queue=new MowerTaskQueue()
  planMowerAlphaMetadata(data,queue,[])
  expect(queue.tasks.some(t=>t.plan.room_1_3?.[0]==='F')).toBe(true)
  expect(data.groupIsResting('a')).toBe(false);expect(data.isGroupShiftAnchor(data.operators.F!)).toBe(false)
  expect(f.timeMicros).toBe(toMowerMicros(8))
 })
 it('does not shorten a named group return deadline when the independent worker becomes exhausted',()=>{
  const deadline=(mood:number)=>{
   const data=fixture();resting(data,'A',0,6);data.operators.F!.mood=mood
   const queue=new MowerTaskQueue();planMowerAlphaMetadata(data,queue,[])
   return queue.tasks.find(t=>t.plan.room_1_1?.[0]==='A')!.timeMicros
  }
  expect(deadline(0)).toBe(deadline(24))
 })
 it.each([{workaholic:true},{exhaustRequire:true}])('retains ordinary rest exclusions %j',policy=>{
  const data=fixture();Object.assign(data.operators.F!,policy)
  expect(mowerResting(data,new MowerTaskQueue())).toEqual({})
 })
 it('uses named candidates for exhausted group support even when the personal cover is unavailable',()=>{
  const data=fixture();data.operators.P!.currentRoom='train';data.operators.P!.currentIndex=1
  expect(planMowerAlphaExhaustSupport(data,data.shiftGroupMembers('a'))).toEqual({})
 })
 it('returns a completed personal recovery after dorm release only when named groups have returned',()=>{
  const data=fixture(),op=data.operators.F!;op.currentRoom='';op.currentIndex=-1;op.mood=24
  commitMowerGroupShifts(data,{a:true})
  const blocked=new MowerTaskQueue();planMowerAlphaMetadata(data,blocked,[])
  expect(blocked.tasks.some(t=>t.plan.room_1_3?.[0]==='F')).toBe(false)
  commitMowerGroupShifts(data,{a:false})
  const ready=new MowerTaskQueue();planMowerAlphaMetadata(data,ready,[])
  expect(ready.tasks.find(t=>t.plan.room_1_3?.[0]==='F')?.plan).toEqual({room_1_3:['F']})
 })
 it('allows a shared standby to yield its only bed to a named group anchor without recalling any group',()=>{
  const data=fixture();data.dorms=data.dorms.slice(0,1);data.plan.dormitory_1=['Free'];data.operators.F!.restingPriority='standby'
  resting(data,'F',0,8);data.operators.A!.mood=5
  data.operators.P!.currentRoom='room_1_3';data.operators.P!.currentIndex=0
  const previous=alphaDormResidents(data),plan:MowerTaskPlan={}
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(true)
  expect(data.dorms[0]!.name).toBe('A');expect(plan).toEqual({room_1_1:['X'],room_1_3:['C']})
  expect(alphaRestoreDisplaced(data,previous,plan,[])).toEqual(new Set())
  const projected=projectMowerArrangements(data,[{...plan,dormitory_1:['A']}])
  expect(projected.operators.F!.currentRoom).toBe('');expect(projected.groupIsResting('a')).toBe(true)
 })
 it('lets a not-yet-resting shared standby leave without a bed when its anchor takes the only bed',()=>{
  const data=fixture();data.dorms=data.dorms.slice(0,1);data.plan.dormitory_1=['Free'];data.operators.F!.restingPriority='standby'
  data.operators.A!.mood=5
  const plan:MowerTaskPlan={}
  expect(mowerGetRestingPlan(data,data.shiftGroupMembers('a'),[],plan)).toBe(true)
  expect(data.dorms[0]!.name).toBe('A');expect(plan).toEqual({room_1_1:['X'],room_1_3:['C']})
 })
 it.each(['standby','low'] as const)('does not recall a displaced %s shared primary or its named groups while a binding remains resting',priority=>{
  const data=fixture();data.operators.F!.restingPriority=priority;resting(data,'F',0,8)
  const previous=alphaDormResidents(data);data.dorms[0]!.name='A'
  commitMowerGroupShifts(data,{a:true})
  const plan:MowerTaskPlan={dormitory_1:['A','Current','Current']}
  expect(alphaRestoreDisplaced(data,previous,plan,[])).toEqual(new Set())
  expect(plan).toEqual({dormitory_1:['A','Current','Current']})
  expect(data.groupShiftState).toEqual({a:true,b:false})
 })
 it('executes personal rest, named group takeover and personal cover restoration in the event runtime',()=>{
  const bindings=[{group:'a',replacement:['C']},{group:'',replacement:['P']}]
  const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',group:'a',candidates:['X']},{id:'room_1_3_0',roomId:'room_1_3',primary:'F',group:'a',candidates:['C']}],beds:[0,1,2].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===0})),initialMorale:{A:18,F:5,X:24,C:24,P:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'a',replacement:['X']}],room_1_3:[{agent:'F',group:'a',replacement:['C'],groupBindings:bindings}],dormitory_1:[0,1,2].map(()=>({agent:'Free',group:'',replacement:[]}))},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:['F'],lowPriority:[],refreshDrained:[],lingMode:0}}
  const state=createRosterRuntime(config),rates={workRate:(name:string)=>name==='A'||name==='F'?1:0,recoveryRate:(name:string)=>name==='F'?1:4}
  let personal=false,takeover=false,restored=false
  for(let tick=0;tick<300&&state.time<10;tick++){
   settleRoster(state,rates)
   const source=getMowerSourceRuntime(state),data=source.data
   if(!source.execution&&!source.queue.tasks.some(t=>t.backupShiftActive)){
    if(state.occupants.room_1_3_0==='P'&&!data.groupIsResting('a')){if(takeover)restored=true;else personal=true}
    if(personal&&state.occupants.room_1_3_0==='C'&&data.groupIsResting('a'))takeover=true
    if(personal)expect(data.operators.F!.isResting()).toBe(true)
    if(restored)break
   }
   const next=nextRosterActionHours(state,rates);advanceRoster(state,Math.min(Number.isFinite(next)?Math.max(next,1e-6):1,1),rates)
  }
  expect({personal,takeover,restored,errors:state.diagnostics.filter(d=>d.code==='mower-task-exception')}).toEqual({personal:true,takeover:true,restored:true,errors:[]})
 })
})
