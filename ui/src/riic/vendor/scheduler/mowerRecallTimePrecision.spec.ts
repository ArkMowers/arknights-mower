import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerRecallCanSustain} from './mowerReplacementCoordination'
import {planMowerAlphaExhaustSupport,validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(rate=4.21,endurance=6,upper=24,nowMicros=0){
 const original=new MowerSchedulingData({alpha:true,nowMicros,groupRestInFullOnMoodGap:false,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['Free','Free','Free']},operators:{
  A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'dormitory_1',currentIndex:0,operatorType:'high',mood:endurance,timeStampMicros:nowMicros,depletionRate:1,replacement:['X']}),
  B:new MowerOperatorState({name:'B',room:'room_1_2',index:0,currentRoom:'room_1_2',currentIndex:0,operatorType:'high',mood:0,timeStampMicros:nowMicros,depletionRate:1,replacement:['X'],upperLimit:upper,restMoodLimit:upper!==24,restInFull:true}),
  X:new MowerOperatorState({name:'X',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:nowMicros,depletionRate:1}),
 },dorms:[new MowerDormState(['dormitory_1',0],'A',nowMicros+Math.ceil((24-endurance)/rate*3_600_000_000)),new MowerDormState(['dormitory_1',1]),new MowerDormState(['dormitory_1',2])]})
 const rates=(data:MowerSchedulingData)=>({work:Object.fromEntries(Object.keys(data.operators).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(data.operators).map(name=>[name,rate]))})
 const admit=()=>projectMowerArrangements(original,[{room_1_1:['A'],room_1_2:['X'],dormitory_1:['Free','B','Current']}])
 return {original,rates,admit}
}

describe('ordinary recall uses one integer clock for recovery and consumption',()=>{
 it.each([0,toMowerMicros(356)+123456,Date.UTC(2026,10,8,11,17,24)*1000+685387].flatMap(now=>[{rate:4.21,endurance:6,upper:24,now},{rate:3.99,endurance:7,upper:24,now},{rate:4.21,endurance:3,upper:12,now}]))('admits a safe full-recovery handoff at $rate/h and target $upper (clock $now)',({rate,endurance,upper,now})=>{
  const {original,rates,admit}=fixture(rate,endurance,upper,now),before=JSON.stringify(original)
  const options={coordinationRates:rates},plan=planMowerAlphaExhaustSupport(original,['B'],options)
  expect(plan).toEqual({room_1_1:['A']})
  expect(validateMowerCoordinationSupport(original,plan!,['B'],options)).toBe(true)
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],options)).toBe(true)
  expect(JSON.stringify(original)).toBe(before)
 })
 it('keeps physical mood integration aligned with the forecast microsecond clock',()=>{
  const {original,admit,rates}=fixture(),start=original.nowMicros,visited:number[]=[]
  const aligned=(data:MowerSchedulingData)=>{
   const elapsed=(data.nowMicros-start)/3_600_000_000
   expect(Number.isSafeInteger(data.nowMicros)).toBe(true)
   expect(data.operators.A!.mood).toBeCloseTo(6-elapsed,12)
   expect(data.operators.B!.mood).toBeCloseTo(Math.min(24,4.21*elapsed),12)
   visited.push(data.nowMicros)
   return rates(data)
  }
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:aligned})).toBe(true)
  expect(visited.length).toBeGreaterThan(4)
 })
 it('continues through global skill and recovery-allocation boundaries',()=>{
  const {original,admit,rates}=fixture(),visited:{k:number;e:number}[]=[]
  original.plan.central=['K'];original.operators.K=new MowerOperatorState({name:'K',room:'central',index:0,currentRoom:'central',currentIndex:0,operatorType:'high',workaholic:true,mood:1,timeStampMicros:0})
  original.operators.E=new MowerOperatorState({name:'E',currentRoom:'dormitory_1',currentIndex:2,mood:21.2,timeStampMicros:0})
  original.dorms[2]=new MowerDormState(['dormitory_1',2],'E',toMowerMicros(2.8))
  const dynamic=(data:MowerSchedulingData)=>{
   const k=data.operators.K!.mood,e=data.operators.E!.mood
   visited.push({k,e})
   return {...rates(data),recovery:{...rates(data).recovery,E:1,B:k>0?4.21:e<24?3.99:4.3}}
  }
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:dynamic})).toBe(true)
  expect(visited.some(({k})=>k===0)).toBe(true)
  expect(visited.some(({e})=>e===24)).toBe(true)
 })
 it.each([{offset:-.0001,allowed:false},{offset:0,allowed:false},{offset:.0001,allowed:true}])('preserves strict work-floor safety with $offset hours of endurance margin',({offset,allowed})=>{
  const {original,admit,rates}=fixture(4.21,24/4.21+offset)
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:rates})).toBe(allowed)
 })
 it.each(['zero','negative','missing','unknown-mood'] as const)('keeps $kind recovery evidence unavailable',kind=>{
  const {original,admit,rates}=fixture()
  if(kind==='unknown-mood')original.operators.B!.timeStampMicros=undefined
  const unavailable=(data:MowerSchedulingData)=>{const result=rates(data);if(kind==='missing')delete result.recovery.B;else if(kind!=='unknown-mood')result.recovery.B=kind==='zero'?0:-1;return result}
  expect(mowerRecallCanSustain(original,admit(),new Set(['A']),['B'],{coordinationRates:unavailable})).toBe(false)
 })
})

it('dispatches the fractional-rate recall and returns its full-recovery requester before the cover reaches its floor',()=>{
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={room_1_1:[{agent:'A',group:'',replacement:['X']}],room_1_2:[{agent:'B',group:'',replacement:['X']}],dormitory_1:['K1','K2','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))}
 const config:RuntimeConfig={mowerAlpha:true,mowerDormFillers:true,mowerRunOrderEnabled:false,mowerTaskScheduling:{adjustForRunOrders:false},mowerSourcePlan:rows,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),beds:[2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===2})),initialMorale:{A:6,B:0,X:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,groupRestInFullOnMoodGap:false,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:['B'],lowPriority:[],refreshDrained:[],lingMode:0},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 state.occupants={room_1_1_0:'X',room_1_2_0:'B',dormitory_1_0:'K1',dormitory_1_1:'K2'};state.bedOccupants={dormitory_1_2:'A'}
 for(const op of Object.values(source.data.operators)){
  const position=Object.entries({...state.occupants,...state.bedOccupants}).find(([,name])=>name===op.name)?.[0],split=position?.lastIndexOf('_')??-1
  Object.assign(op,{currentRoom:position?.slice(0,split)??'',currentIndex:position?Number(position.slice(split+1)):-1,mood:state.morale[op.name]??24,timeStampMicros:0,depletionRate:position?.startsWith('dorm')?0:1})
 }
 source.data.dorms[0]!.name='A';source.data.dorms[0]!.timeMicros=Math.ceil(18/4.21*3_600_000_000)
 const request=new MowerTask({type:T.EXHAUST_OFF,metadata:'B'});request.ordinaryCoordination=true;request.coordinationRequestNames=['B'];source.queue.tasks=[request]
 const rates={workRate:()=>1,recoveryRate:()=>4.21,forecastMoods:(s:RuntimeState)=>({...s.morale}),forecastRates:(s:RuntimeState)=>({work:Object.fromEntries(Object.keys(s.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(s.morale).map(name=>[name,4.21]))})}
 settleMowerSource(state,rates)
 expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(true)
 expect(source.queue.tasks).toContain(request)
 expect(request.timeMicros).toBe(0)
 let rested=false,returned=false,minimumWorkingMood=6
 for(let step=0;step<40&&!returned;step++){
  settleRoster(state,rates)
  if(Object.values(state.bedOccupants).includes('B'))rested=true
  returned=rested&&state.occupants.room_1_2_0==='B'
  if(state.occupants.room_1_1_0==='A')minimumWorkingMood=Math.min(minimumWorkingMood,state.morale.A!)
  if(!returned)advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
 expect(returned).toBe(true)
 expect(state.morale.B).toBe(24)
 expect(minimumWorkingMood).toBeGreaterThan(0)
 expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
})
