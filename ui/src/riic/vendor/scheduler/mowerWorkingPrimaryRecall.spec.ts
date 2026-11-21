import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerOperatorState} from './mowerOperatorState'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {projectMowerArrangements} from './mowerObservations'
import {planMowerAlphaExhaustSupport,validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'
import {mowerReplacementRecallOwner} from './mowerReplacementCoordination'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(shared=true,twoSwaps=false){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'Request',group:'request',replacement:['Cover']}],
  room_1_2:[{agent:'Swapper',group:shared?'normal':'recovering',replacement:['Cover'],...(shared?{groupBindings:[{group:'normal',replacement:['Cover']},{group:'recovering',replacement:['Cover']}]}:{})}],
  room_1_3:[{agent:'Resting',group:'recovering',replacement:['Swapper']}],
  room_2_1:[{agent:'Peer',group:'recovering',replacement:['Other']}],
  dormitory_1:['K1','K2','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
 }
 if(twoSwaps){rows.room_1_3![0]!.replacement=['LastSwapper'];rows.room_2_2=[{agent:'LastSwapper',group:'recovering',replacement:['Swapper']}]}
 const config:RuntimeConfig={mowerAlpha:true,mowerDormFillers:true,mowerRunOrderEnabled:false,mowerTaskScheduling:{adjustForRunOrders:false},mowerSourcePlan:rows,
  positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),
  beds:[2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===2})),initialMorale:{Request:3,Swapper:20,Resting:20,Peer:20,LastSwapper:20,Cover:24,Other:24},idleOperators:[],
  mowerPolicy:{restingThreshold:.65,groupRestInFullOnMoodGap:false,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 state.occupants={room_1_1_0:'Request',room_1_2_0:'Cover',room_1_3_0:'Swapper',room_2_1_0:'Other',dormitory_1_0:'K1',dormitory_1_1:'K2'}
 if(twoSwaps){state.occupants.room_1_3_0='LastSwapper';state.occupants.room_2_2_0='Swapper'}
 state.bedOccupants={dormitory_1_2:'Resting',dormitory_1_3:'Peer'}
 for(const op of Object.values(data.operators)){
  const position=Object.entries({...state.occupants,...state.bedOccupants}).find(([,name])=>name===op.name)?.[0],split=position?.lastIndexOf('_')??-1
  Object.assign(op,{currentRoom:position?.slice(0,split)??'',currentIndex:position?Number(position.slice(split+1)):-1,mood:state.morale[op.name]??24,timeStampMicros:0,depletionRate:position?.startsWith('dorm')?0:1})
 }
 data.dorms=[new MowerDormState(['dormitory_1',2],'Resting',toMowerMicros(1)),new MowerDormState(['dormitory_1',3],'Peer',toMowerMicros(1)),new MowerDormState(['dormitory_1',4])]
 data.groupShiftState={request:false,normal:false,recovering:true}
 const task=new MowerTask({type:T.EXHAUST_OFF,metadata:'Request'})
 task.ordinaryCoordination=true;task.coordinationRequestNames=['Request'];source.queue.tasks=[task]
 return {state,source,data,task}
}
const forecast=(data:ReturnType<typeof fixture>['data'])=>({work:Object.fromEntries(Object.keys(data.operators).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(data.operators).map(name=>[name,4]))})
const rates={workRate:()=>1,recoveryRate:()=>4,forecastMoods:(state:RuntimeState)=>({...state.morale}),forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}

describe('recall follows confirmed working-primary cover dependencies',()=>{
 it.each([false,true])('returns the actual resting unit before releasing its %s shared working primary',shared=>{
  const {data}=fixture(shared),before=JSON.stringify(data)
  const plan=planMowerAlphaExhaustSupport(data,['Request'],{coordinationRates:forecast})
  expect(plan).toBeDefined()
  expect(plan!.room_1_2).toEqual(['Swapper'])
  expect(plan!.room_1_3).toEqual(['Resting'])
  expect(plan!.room_2_1).toEqual(['Peer'])
  expect(validateMowerCoordinationSupport(data,plan!,['Request'],{coordinationRates:forecast})).toBe(true)
  const returned=projectMowerArrangements(data,[plan!])
  expect(returned.operators.Cover!.currentRoom).toBe('')
  expect(returned.operators.Swapper!.currentRoom).toBe('room_1_2')
  expect(JSON.stringify(data)).toBe(before)
 })
 it.each(['middle-name','middle-slot','mastery','unrelated-working','explicit-full','unsafe','unknown-mood'] as const)('keeps the %s working chain protected',constraint=>{
  const {data}=fixture(),options={coordinationRates:forecast,reservedNames:new Set<string>(),reservedSlots:new Set<string>(),isMasteryBusy:(name:string)=>constraint==='mastery'&&name==='Swapper'}
  if(constraint==='middle-name')options.reservedNames.add('Swapper')
  if(constraint==='middle-slot')options.reservedSlots.add('room_1_3\0'+'0')
  if(constraint==='unrelated-working')data.operators.Resting!.group='other'
  if(constraint==='explicit-full')data.operators.Resting!.restInFull=true
  if(constraint==='unsafe')data.operators.Resting!.mood=1
  if(constraint==='unknown-mood')data.operators.Resting!.timeStampMicros=undefined
  const before=JSON.stringify(data)
  expect(planMowerAlphaExhaustSupport(data,['Request'],options)).toBeUndefined()
  expect(JSON.stringify(data)).toBe(before)
 })
 it('stops a cyclic or unconfigured cover chain',()=>{
  const {data}=fixture()
  data.operators.Resting!.currentRoom='room_1_2';data.operators.Resting!.currentIndex=0
  data.operators.Swapper!.groupBindings=[{group:'normal',replacement:['Cover']},{group:'recovering',replacement:['Resting','Cover']}]
  expect(mowerReplacementRecallOwner(data,'Cover')).toBeUndefined()
 })
 it('rechecks intermediate reservations before executing a previously safe handoff',()=>{
  const {data}=fixture(),options={coordinationRates:forecast}
  const plan=planMowerAlphaExhaustSupport(data,['Request'],options)!
  expect(plan).toBeDefined()
  expect(validateMowerCoordinationSupport(data,plan,['Request'],{...options,reservedSlots:new Set(['room_1_3\0'+'0'])})).toBe(false)
 })
 it('dispatches the shared-primary handoff while retaining the original requesting task',()=>{
  const {state,source,task}=fixture(),time=task.timeMicros
  settleMowerSource(state,rates)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(time)
  expect(source.queue.tasks.some(queued=>queued.exhaustSupport)).toBe(true)
  const done=()=>state.occupants.room_1_1_0==='Cover'&&state.occupants.room_1_2_0==='Swapper'&&state.occupants.room_1_3_0==='Resting'&&state.occupants.room_2_1_0==='Peer'&&Object.values(state.bedOccupants).includes('Request')
  for(let step=0;step<30&&!done();step++){
   settleRoster(state,rates)
   if(!done())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(done()).toBe(true)
  expect(state.morale.Request).toBeGreaterThan(0)
  expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
 })
 it('preserves a blocked request and deadline over unchanged dispatch',()=>{
  const {state,source,data,task}=fixture(),time=task.timeMicros
  data.busyRestingNames.add('Swapper')
  for(let attempt=0;attempt<3;attempt++)settleMowerSource(state,rates)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(time)
  expect(state.occupants.room_1_2_0).toBe('Cover')
  expect(state.occupants.room_1_3_0).toBe('Swapper')
  expect(source.queue.tasks.some(queued=>queued.exhaustSupport)).toBe(false)
 })
})


it('dispatches two consecutive configured working-primary swaps as one complete return',()=>{
 const {state,source,data,task}=fixture(true,true),time=task.timeMicros
 const plan=planMowerAlphaExhaustSupport(data,['Request'],{coordinationRates:forecast})!
 expect(plan).toBeDefined()
 expect(plan.room_1_2).toEqual(['Swapper'])
 expect(plan.room_2_2).toEqual(['LastSwapper'])
 expect(plan.room_1_3).toEqual(['Resting'])
 settleMowerSource(state,rates)
 expect(source.queue.tasks).toContain(task)
 expect(task.timeMicros).toBe(time)
 const done=()=>state.occupants.room_1_1_0==='Cover'&&state.occupants.room_1_2_0==='Swapper'&&state.occupants.room_2_2_0==='LastSwapper'&&state.occupants.room_1_3_0==='Resting'&&Object.values(state.bedOccupants).includes('Request')
 for(let step=0;step<30&&!done();step++){
  settleRoster(state,rates)
  if(!done())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
 expect(done()).toBe(true)
 expect(state.morale.Request).toBeGreaterThan(0)
 expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
})

it('does not borrow a working chain protected by another held group',()=>{
 const {data}=fixture(true,true)
 data.operators.Swapper!.groupBindings=[{group:'normal',replacement:['Cover']},{group:'middle',replacement:['Cover']}]
 data.operators.Swapper!.group='normal'
 data.operators.LastSwapper!.groupBindings=[{group:'middle',replacement:['Swapper']},{group:'recovering',replacement:['Swapper']}]
 data.operators.LastSwapper!.group='middle'
 data.groupShiftState.middle=true
 data.backupGroupTasks=[[{group:'middle',action:'off',mode:'forced'}]];data.planConditions=[true]
 const before=JSON.stringify(data)
 expect(planMowerAlphaExhaustSupport(data,['Request'],{coordinationRates:forecast})).toBeUndefined()
 expect(JSON.stringify(data)).toBe(before)
})


it('discovers the prerequisite training-primary return without directly borrowing its occupied cover',()=>{
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,groupRestInFullOnMoodGap:false,groupShiftState:{request:false,recovering:true},plan:{central:['Request','Recovering'],train:['T'],dormitory_1:['K','Manager','Free','Free','Free']},operators:{
  Request:new MowerOperatorState({name:'Request',room:'central',index:0,currentRoom:'central',currentIndex:0,group:'request',operatorType:'high',replacement:['Dusk'],mood:0,timeStampMicros:0}),
  Recovering:new MowerOperatorState({name:'Recovering',room:'central',index:1,currentRoom:'dormitory_1',currentIndex:2,group:'recovering',operatorType:'high',replacement:['Swire'],mood:20,timeStampMicros:0}),
  T:new MowerOperatorState({name:'T',room:'train',index:0,group:'recovering',operatorType:'high',replacement:['Cover'],mood:20,timeStampMicros:0}),
  Manager:new MowerOperatorState({name:'Manager',room:'dormitory_1',index:1,currentRoom:'dormitory_1',currentIndex:1,group:'request',operatorType:'high',replacement:['Cover'],mood:24,timeStampMicros:0}),
  K:new MowerOperatorState({name:'K',room:'dormitory_1',index:0,currentRoom:'dormitory_1',currentIndex:0,operatorType:'high',mood:24,timeStampMicros:0}),
  Dusk:new MowerOperatorState({name:'Dusk',mood:24,timeStampMicros:0}),
  Swire:new MowerOperatorState({name:'Swire',currentRoom:'central',currentIndex:1,mood:24,timeStampMicros:0}),
  Cover:new MowerOperatorState({name:'Cover',currentRoom:'train',currentIndex:0,mood:24,timeStampMicros:0}),
 },dorms:[new MowerDormState(['dormitory_1',2],'Recovering',toMowerMicros(1)),new MowerDormState(['dormitory_1',3]),new MowerDormState(['dormitory_1',4])]})
 const options={urgentExhaust:true},before=JSON.stringify(data)
 data.busyRestingNames.add('T')
 expect(planMowerAlphaExhaustSupport(data,['Request','Manager'],options)).toBeUndefined()
 data.busyRestingNames.delete('T')
 const support=planMowerAlphaExhaustSupport(data,['Request','Manager'],options)!
 expect(support).toBeDefined()
 expect(support.train).toEqual(['T'])
 expect(support.central?.[1]).toBe('Recovering')
 expect(JSON.stringify(data)).toBe(before)
 const after=projectMowerArrangements(data,[support]),rest={}
 expect(after.operators.Cover!.currentRoom).toBe('')
 expect(mowerGetRestingPlan(after,['Request','Manager'],[],rest,options)).toBe(true)
 expect((rest as Record<string,string[]>).dormitory_1?.[1]).toBe('Cover')
})

it.each([false,true].flatMap(shared=>[12,24,undefined].map(mood=>({shared,mood}))))('preserves explicit full recovery for the moved working primary: shared=$shared mood=$mood',({shared,mood})=>{
 const {data}=fixture(shared)
 Object.assign(data.operators.Swapper!,{restInFull:true,mood:mood??20,timeStampMicros:mood===undefined?undefined:0})
 const plan=planMowerAlphaExhaustSupport(data,['Request'],{coordinationRates:forecast})
 expect(!!plan).toBe(mood===24)
})

it('revalidates newly required full recovery before dispatching the working-primary handoff',()=>{
 const {state,source,data,task}=fixture(),time=task.timeMicros
 settleMowerSource(state,rates)
 expect(source.queue.tasks.some(queued=>queued.exhaustSupport)).toBe(true)
 state.config.mowerSourceRules!.restInFull=['Swapper']
 Object.assign(data.operators.Swapper!,{restInFull:true,mood:12,timeStampMicros:0})
 state.morale.Swapper=12
 for(let attempt=0;attempt<3;attempt++)settleRoster(state,rates)
 expect(state.occupants.room_1_1_0).toBe('Request')
 expect(state.occupants.room_1_2_0).toBe('Cover')
 expect(state.occupants.room_1_3_0).toBe('Swapper')
 expect(state.bedOccupants.dormitory_1_2).toBe('Resting')
 expect(source.queue.tasks).toContain(task)
 expect(task.timeMicros).toBe(time)
})


it('revalidates a queued full-recovery working swap through the public support validator',()=>{
 const {data}=fixture()
 Object.assign(data.operators.Swapper!,{restInFull:true,mood:24,timeStampMicros:0})
 const options={coordinationRates:forecast},plan=planMowerAlphaExhaustSupport(data,['Request'],options)!
 expect(plan).toBeDefined()
 expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(true)
 data.operators.Swapper!.mood=12
 expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(false)
 Object.assign(data.operators.Swapper!,{mood:24,timeStampMicros:undefined})
 expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(false)
 data.operators.Swapper!.timeStampMicros=0
 expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(true)
})

it.each([{marked:true,mood:8,allowed:false},{marked:true,mood:12,allowed:true},{marked:false,mood:8,allowed:true}])('applies only an explicit personal cap to the moved primary: $marked/$mood',({marked,mood,allowed})=>{
 const {data}=fixture()
 Object.assign(data.operators.Swapper!,{restMoodLimit:marked,upperLimit:12,mood,timeStampMicros:0})
 const options={coordinationRates:forecast},plan=planMowerAlphaExhaustSupport(data,['Request'],options)
 expect(!!plan).toBe(allowed)
 if(plan){
  expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(true)
  if(marked){data.operators.Swapper!.mood=8;expect(validateMowerCoordinationSupport(data,plan,['Request'],options)).toBe(false)}
 }
})
