import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData} from './mowerSchedulingData'
import {mowerPendingExhaustDeparture} from './mowerExhaustPolicy'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function dataFixture(){
 const operators=Object.fromEntries(['A','B'].map((name,index)=>[name,new MowerOperatorState({name,room:'room_1_1',index,group:'G',operatorType:'high',currentRoom:'room_1_1',currentIndex:index,mood:0,timeStampMicros:0})]))
 return new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A','B'],dormitory_1:['Free','Free']}})
}
describe('concrete exhaustion departure request ownership',()=>{
 it('requires one concrete departure to cover all necessary members',()=>{
  const data=dataFixture(),partialA=new MowerTask({type:T.SHIFT_OFF,plan:{dormitory_1:['A','Current']}}),partialB=new MowerTask({type:T.SHIFT_OFF,plan:{dormitory_1:['Current','B']}})
  expect(mowerPendingExhaustDeparture(data,[partialA,partialB],['A','B'])).toBeUndefined()
  const complete=new MowerTask({time:-3,type:T.SHIFT_OFF,plan:{dormitory_1:['A','B']}});complete.executionRetained=true
  expect(mowerPendingExhaustDeparture(data,[partialA,complete],['A','B'])).toBe(complete)
  expect(complete.time).toBe(-3)
 })
 it.each(['untouched','current','same','removed','working'] as const)('accounts for actual residents and the concrete remaining plan: %s',kind=>{
  const data=dataFixture();data.operators.B!.currentRoom='dormitory_1';data.operators.B!.currentIndex=1
  const plan:Record<string,string[]>={dormitory_1:['A','Current']}
  if(kind==='untouched')delete plan.dormitory_1
  if(kind==='same')plan.dormitory_1![1]='B'
  if(kind==='removed')plan.dormitory_1![1]='Free'
  if(kind==='working')plan.room_1_1=['Current','B']
  const task=new MowerTask({type:T.SHIFT_OFF,plan})
  expect(mowerPendingExhaustDeparture(data,[task],kind==='untouched'?['B']:['A','B'])).toBe(['removed','working'].includes(kind)?undefined:task)
 })
})
function runtimeFixture(extra=false){
 const keepers=extra?['K1','K2','K3']:['K1','K2','K3','K4'],config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},...keepers.map((name,index)=>({id:'dormitory_1_'+index,roomId:'dormitory_1',primary:name,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:24,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(name=>({agent:name,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
 if(extra){config.mowerSourcePlan!.dormitory_1!.push({agent:'Free',group:'',replacement:[]});config.positions.push({id:'room_1_2_0',roomId:'room_1_2',primary:'B',candidates:['S'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15});config.mowerSourcePlan!.room_1_2=[{agent:'B',group:'',replacement:['S']}];config.beds.unshift({id:'dormitory_1_3',roomId:'dormitory_1',vip:true});Object.assign(config.initialMorale!,{B:24,S:24})}
 const state=createRosterRuntime(config),rates={workRate:()=>1,recoveryRate:()=>4};settleRoster(state,rates)
 const source=getMowerSourceRuntime(state);source.initial=false;source.firstInit=false
 state.morale.A=.1;Object.assign(source.data.operators.A!,{mood:.1,timeStampMicros:source.data.nowMicros})
 return {state,source,rates}
}
describe('metadata and exhaustion dispatch preserve an existing concrete request',()=>{
 it.each(['queued','parked'] as const)('keeps the same %s departure across repeated metadata and exhaust requests',location=>{
  const {state,source,rates}=runtimeFixture(),departure=new MowerTask({time:-1,type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['Current','Current','Current','Current','A']}})
  departure.executionRetained=true
  source.queue.tasks=[departure]
  retainMowerFailedTask(state,source.data,departure,'existing recovery dependency',['room_1_1','dormitory_1'])
  if(location==='parked'){
   source.queue.tasks=[];source.waitingRecovery=[{task:departure,reason:'backup-veto',conditionIndexes:[],observation:JSON.stringify([[],{},[],[]]),deadlines:{},names:[],rooms:[]}]
  }
  const original=structuredClone(departure)
  for(let pass=0;pass<3;pass++){
   source.queue.tasks.push(new MowerTask({time:state.time}),new MowerTask({time:state.time,type:T.EXHAUST_OFF,metadata:'A'}))
   settleRoster(state,rates)
   expect(source.queue.tasks.filter(task=>task.type===T.SHIFT_OFF)).toEqual(location==='queued'?[departure]:[])
   expect(source.queue.tasks.some(task=>task.type===T.EXHAUST_OFF&&task.metadata==='A')).toBe(false)
   expect(source.waitingRecovery?.[0]?.task).toBe(location==='parked'?departure:undefined)
   expect(departure.time).toBe(-1);expect(departure.plan).toEqual(original.plan)
  }
 })
})

import {mowerResting} from './mowerOrdinaryPlanning'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTaskQueue} from './mowerTaskQueue'
describe('ordinary planning retains the same concrete request',()=>{
 it.each(['queued','parked'] as const)('keeps the %s owner while planning an unrelated departure',location=>{
  const make=(name:string,room:string,index:number,replacement:string[]=[])=>new MowerOperatorState({name,room,index,replacement,operatorType:room?'high':'low',currentRoom:room,currentIndex:index,mood:room?.1:24,timeStampMicros:0})
  const data=new MowerSchedulingData({alpha:true,nowMicros:0,operators:{A:make('A','room_1_1',0,['X']),B:make('B','room_1_2',0,['Y']),X:make('X','',-1),Y:make('Y','',-1)},plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['Free','Free']},dorms:[new MowerDormState(['dormitory_1',0]),new MowerDormState(['dormitory_1',1])],policy:{restingThreshold:.65,rescueThreshold:.25}})
  const old=new MowerTask({time:-3,type:T.SHIFT_OFF,plan:{room_1_1:['X'],dormitory_1:['A','Current']}});old.executionRetained=true;old.ordinaryCoordination=true;old.coordinationRequestNames=['A']
  const original=structuredClone(old),queue=new MowerTaskQueue();queue.tasks=location==='queued'?[old]:[]
  const plan=mowerResting(data,queue,{tasks:location==='parked'?[old]:[]})
  expect(plan.room_1_1).toBeUndefined();expect(plan.room_1_2).toEqual(['Y']);expect(data.dorms.some(bed=>bed.name==='B')).toBe(true)
  for(let pass=0;pass<3;pass++)mowerResting(data,queue,{tasks:location==='parked'?[old]:[]})
  expect(queue.tasks.filter(task=>task.coordinationRequestNames.includes('A'))).toEqual(location==='queued'?[old]:[])
  expect(old.time).toBe(-3);expect(old.plan).toEqual(original.plan)
  queue.tasks=queue.tasks.filter(task=>task!==old)
  const next=mowerResting(data,queue)
  expect(next.room_1_1).toEqual(['X'])
  expect(queue.tasks.some(task=>task!==old&&task.coordinationRequestNames.includes('A'))).toBe(true)
 })
})

it('dispatches an unrelated ordinary departure while retaining the original failed request',()=>{
 const {state,source,rates}=runtimeFixture(true);state.config.mowerSourceRules!.exhaustRequire=[];source.data.operators.A!.exhaustRequire=false
 const old=new MowerTask({time:-1,type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['Current','Current','Current','Current','A']}})
 old.ordinaryCoordination=true;old.coordinationRequestNames=['A'];source.queue.tasks=[old]
 retainMowerFailedTask(state,source.data,old,'existing recovery dependency',['room_1_1','dormitory_1'])
 state.morale.B=.1;Object.assign(source.data.operators.B!,{mood:.1,timeStampMicros:source.data.nowMicros})
 source.queue.tasks.push(new MowerTask())
 for(let pass=0;pass<20&&!Object.values(state.bedOccupants).includes('B');pass++){
  settleRoster(state,rates)
  const hours=nextRosterActionHours(state,rates)
  if(Number.isFinite(hours)&&hours>0)advanceRoster(state,Math.min(hours,.05),rates)
 }
 expect(Object.values(state.bedOccupants)).toContain('B')
 expect(source.queue.tasks.includes(old)||Object.values(state.bedOccupants).includes('A')).toBe(true);expect(old.time).toBe(-1)
 expect(source.queue.tasks.filter(task=>task.coordinationRequestNames.includes('A')).every(task=>task===old)).toBe(true)
})
