import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,makeMowerSchedulingData,settleMowerSource} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerAlphaExhaustSupport,validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {mowerReplacementReservations} from './mowerReplacementCoordination'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'
import {projectMowerArrangements} from './mowerObservations'
import {cloneMowerShiftTask,coalesceMowerBackupTransition} from './mowerShiftCycle'
import {reconcileMowerUrgentRecovery,mowerUrgentRecallBlocked,recordMowerUrgentRecovery} from './mowerUrgentRecovery'

const rates={workRate:()=>1,recoveryRate:()=>4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}
function fixture(two=false,fixed=false){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'A',group:'a',replacement:[fixed?'L':'X']}],
  room_1_2:[{agent:'B',group:'b',replacement:['Y']}],
  ...(two?{room_1_3:[{agent:'C',group:'c',replacement:['Z']}]}:{}),
  ...(!fixed?{meeting:[{agent:'S',group:'',replacement:['V'],groupBindings:[{group:'',replacement:['V']},{group:'a',replacement:['V']},{group:'b',replacement:['U']}]}]}:{}),
  ...(two?{contact:[{agent:'S2',group:'',replacement:['V2'],groupBindings:[{group:'',replacement:['V2']},{group:'a',replacement:['V2']},{group:'c',replacement:['U2']}]}]}:{}),
  dormitory_1:[{agent:fixed?'M':'K1',group:fixed?'b':'',replacement:fixed?['L']:[]},{agent:'K2',group:'',replacement:[]},...['Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))],
  dormitory_2:['K3','K4','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
 }
 const config:RuntimeConfig={mowerAlpha:true,mowerSourcePlan:rows,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),beds:['dormitory_1','dormitory_2'].flatMap(room=>[2,3,4].map(index=>({id:room+'_'+index,roomId:room,vip:index===2}))),initialMorale:{A:0,B:1,C:1,S:23,S2:23,M:10},idleOperators:Array.from({length:12},(_,i)=>'Idle'+i),mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:['A','B','C'],restInFull:[],lowPriority:[],standby:['S','S2'],refreshDrained:[],lingMode:0},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false
 for(const position of config.positions)Object.assign(data.operators[position.primary]!,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(-1)),mood:state.morale[position.primary]??24,timeStampMicros:0,depletionRate:1})
 const place=(name:string,room:string,index:number)=>{
  const op=data.operators[name]!;Object.assign(op,{currentRoom:room,currentIndex:index,mood:state.morale[name]??24,timeStampMicros:0,depletionRate:room.startsWith('dorm')?0:1})
  if(room.startsWith('dorm')&&index>=2){state.bedOccupants[room+'_'+index]=name;data.dorms.find(b=>b.position[0]===room&&b.position[1]===index)!.name=name}
  else if(room)state.occupants[room+'_'+index]=name
 }
 data.dorms=config.beds.map(b=>new MowerDormState([b.roomId,Number(b.id.slice(-1))]))
 place('B','dormitory_1',2);place('Y','room_1_2',0)
 if(two){place('C','dormitory_1',3);place('Z','room_1_3',0);place('S2','',-1);place('U2','contact',0)}
 if(fixed){place('M','dormitory_1',3);place('L','dormitory_1',0)}else{place('S','',-1);place('U','meeting',0)}
 for(const op of Object.values(data.operators))if(op.timeStampMicros===undefined)Object.assign(op,{mood:state.morale[op.name]??24,timeStampMicros:0,depletionRate:0})
 for(const bed of data.dorms)if(bed.name)bed.timeMicros=toMowerMicros((24-(state.morale[bed.name]??24))/4)
 data.groupShiftState={a:false,b:true,...(two?{c:true}:{})}
 const request=new MowerTask({type:T.EXHAUST_OFF,metadata:'A'});source.queue.tasks=[request]
 return {state,source,request}
}
function drive(state:RuntimeState,done:()=>boolean,max=120){
 for(let i=0;i<max&&!done();i++){
  settleMowerSource(state,rates)
  if(!done())advanceRoster(state,Math.min(1/3600,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000)),rates)
 }
 expect(done(),JSON.stringify({time:state.time,occupants:state.occupants,beds:state.bedOccupants,queue:getMowerSourceRuntime(state).queue.tasks.map(t=>({type:t.type.key,plan:t.plan,metadata:t.metadata,reason:t.executionFailure?.reason})),diagnostics:state.diagnostics})).toBe(true)
}

describe('urgent dependency recall and observed recovery ownership',()=>{
 it.each([false,true])('recalls all shared binding dependencies in one admission (two=%s)',two=>{
  const {state,source,request}=fixture(two),before=JSON.stringify(source.data)
  const candidates=source.data.shiftGroupMembers('a'),plan=planMowerAlphaExhaustSupport(source.data,candidates,{urgentExhaust:true})
  expect(plan?.room_1_2).toEqual(['B'])
  if(two)expect(plan?.room_1_3).toEqual(['C'])
  expect(validateMowerCoordinationSupport(source.data,plan!,candidates,{urgentExhaust:true})).toBe(true)
  expect(JSON.stringify(source.data)).toBe(before)
  drive(state,()=>Object.values(state.bedOccupants).includes('A'))
  expect(state.occupants.room_1_2_0).toBe('B')
  if(two)expect(state.occupants.room_1_3_0).toBe('C')
  expect(source.data.urgentRecoverySupporters.A).toEqual(expect.arrayContaining(two?['B','C']:['B']))
  expect(request.timeMicros).toBe(0)
  expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
 })
 it('recalls the fixed dorm manager owner instead of stealing its active cover',()=>{
  const {state,source}=fixture(false,true)
  expect(source.data.dormReplacementForSlot('L','dormitory_1',0)).toBe(true)
  const plan=planMowerAlphaExhaustSupport(source.data,['A'],{urgentExhaust:true})
  expect(plan?.room_1_2).toEqual(['B'])
  expect(plan?.dormitory_1?.[0]).toBe('M')
  drive(state,()=>Object.values(state.bedOccupants).includes('A'))
  expect(state.occupants.room_1_1_0).toBe('L')
  expect(state.occupants.dormitory_1_0).toBe('M')
  expect(source.data.urgentRecoverySupporters.A).toContain('B')
 })
 it('retains real support resources until the original request enters its dorm',()=>{
  const {state,source,request}=fixture()
  drive(state,()=>request.urgentRecoverySupportNames.length>0)
  expect(Object.values(state.bedOccupants)).not.toContain('A')
  expect(request.urgentRecoveryReservedNames).toContain('Y')
  const reservations=mowerReplacementReservations(source.data,[request]),beds=mowerDormTaskReservations(source.data,[request])
  expect(reservations.reservedNames.has('Y')).toBe(true)
  expect(reservations.reservedSlots.has('dormitory_1\0'+'2')).toBe(true)
  expect(beds.slots).toEqual(reservations.reservedSlots)
  expect(request.timeMicros).toBe(0)
  drive(state,()=>Object.values(state.bedOccupants).includes('A'))
  expect(source.data.urgentRecoverySupporters.A).toContain('B')
 })
 it('allows low recalled workers to wait without reversing the completed rescue',()=>{
  const {state,source}=fixture()
  drive(state,()=>Object.values(state.bedOccupants).includes('A'))
  state.morale.B=0;Object.assign(source.data.operators.B!,{mood:0,timeStampMicros:source.data.nowMicros,moodIsPrediction:false})
  const reverse=new MowerTask({time:state.time,type:T.EXHAUST_OFF,metadata:'B'});source.queue.tasks.push(reverse)
  drive(state,()=>!!reverse.executionFailure)
  const failure=reverse.executionFailure,time=reverse.timeMicros
  for(let i=0;i<12;i++)settleMowerSource(state,rates)
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(source.data.urgentRecoverySupporters.A).toContain('B')
  expect(reverse.executionFailure).toBe(failure)
  expect(reverse.timeMicros).toBe(time)
  expect(source.queue.tasks.filter(t=>t.exhaustSupport)).toHaveLength(0)
  expect(mowerUrgentRecallBlocked(source.data,['B'])).toBe(true)
  state.morale.A=24;Object.assign(source.data.operators.A!,{mood:24,timeStampMicros:source.data.nowMicros,moodIsPrediction:false})
  reconcileMowerUrgentRecovery(source.data)
  expect(source.data.urgentRecoverySupporters).toEqual({})
  drive(state,()=>Object.values(state.bedOccupants).includes('B'))
 })
 it('isolates projections and preserves supporters until the last beneficiary returns',()=>{
  const {state,source}=fixture(true)
  source.data.urgentRecoverySupporters={B:['A'],C:['A']}
  const projected=projectMowerArrangements(source.data,[])
  projected.urgentRecoverySupporters.B!.push('Other');delete projected.urgentRecoverySupporters.C
  expect(source.data.urgentRecoverySupporters).toEqual({B:['A'],C:['A']})
  const rebuilt=makeMowerSchedulingData(state,source)
  expect(rebuilt.urgentRecoverySupporters).toEqual(source.data.urgentRecoverySupporters)
  Object.assign(source.data.operators.B!,{mood:24,moodIsPrediction:false})
  reconcileMowerUrgentRecovery(source.data)
  expect(mowerUrgentRecallBlocked(source.data,['A'])).toBe(true)
  Object.assign(source.data.operators.C!,{currentRoom:'room_1_3',currentIndex:0,moodIsPrediction:false})
  reconcileMowerUrgentRecovery(source.data)
  expect(mowerUrgentRecallBlocked(source.data,['A'])).toBe(false)
 })
 it('keeps an admitted recovery departure out of unrelated backup coalescing',()=>{
  const {source}=fixture(),departure=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['X']}})
  departure.urgentRecoveryRequestNames=['A'];departure.urgentRecoverySupportNames=['B'];departure.urgentRecoveryReservedNames=['Y'];departure.urgentRecoveryReservedSlots=['dormitory_1\0'+'2']
  const copy=cloneMowerShiftTask(departure);copy.urgentRecoverySupportNames.push('C')
  expect(departure.urgentRecoverySupportNames).toEqual(['B'])
  expect(coalesceMowerBackupTransition(source.data,{room_1_1:['A']},[departure]).consumed).toEqual([])
 })
 it('keeps explicit recovery and ordinary coordination outside urgent fallback',()=>{
  const {source}=fixture()
  expect(planMowerAlphaExhaustSupport(source.data,source.data.shiftGroupMembers('a'),{})).toBeUndefined()
  source.data.operators.B!.restInFull=true
  expect(planMowerAlphaExhaustSupport(source.data,source.data.shiftGroupMembers('a'),{urgentExhaust:true})).toBeUndefined()
  expect(source.data.urgentRecoverySupporters).toEqual({})
 })
 it('does not let a direct departure steal the released cover before admission',()=>{
  const {state,source,request}=fixture()
  drive(state,()=>request.urgentRecoverySupportNames.length>0)
  const reserved=mowerReplacementReservations(source.data,[request]),trial=projectMowerArrangements(source.data,[]),plan={}
  expect(mowerGetRestingPlan(trial,['B'],[],plan,reserved)).toBe(false)
  expect(plan).toEqual({})
 })
 it('exempts only its own resource reservation and retains other task locks',()=>{
  const {source}=fixture(),owner=new MowerTask()
  owner.urgentRecoveryRequestNames=['A','Shared'];owner.urgentRecoveryReservedNames=['Y'];owner.urgentRecoveryReservedSlots=['dormitory_1\0'+'2']
  owner.productShiftLocked=true;owner.productLockNames.add('X');owner.productLockSlots.add('room_1_1\0'+'0')
  const own=mowerReplacementReservations(source.data,[owner],['Shared','A'])
  expect(own.reservedNames.has('Y')).toBe(false);expect(own.reservedSlots.has('dormitory_1\0'+'2')).toBe(false)
  expect(own.reservedNames.has('X')).toBe(true);expect(own.reservedSlots.has('room_1_1\0'+'0')).toBe(true)
  const other=mowerReplacementReservations(source.data,[owner],['Shared','B'])
  expect(other.reservedNames.has('Y')).toBe(true);expect(other.reservedSlots.has('dormitory_1\0'+'2')).toBe(true)
 })
 it('records observed admissions from idle without protecting unobserved or shared followers',()=>{
  const {source}=fixture(),request=new MowerTask({metadata:'A'})
  request.urgentRecoveryRequestNames=['A'];request.urgentRecoverySupportNames=['B']
  Object.assign(source.data.operators.A!,{currentRoom:'dormitory_2',currentIndex:2,moodIsPrediction:true})
  recordMowerUrgentRecovery(source.data,new MowerTask(),[request])
  expect(source.data.urgentRecoverySupporters).toEqual({})
  source.data.operators.A!.moodIsPrediction=false
  recordMowerUrgentRecovery(source.data,new MowerTask(),[request])
  expect(source.data.urgentRecoverySupporters).toEqual({A:['B']})
  source.data.operators.A!.mood=24;source.data.operators.A!.moodIsPrediction=true
  reconcileMowerUrgentRecovery(source.data)
  expect(mowerUrgentRecallBlocked(source.data,['B'])).toBe(true)
 })
 it('blocks a supporter from forcing a third group but still permits a free handoff',()=>{
  const {source}=fixture(true)
  // B is also recovering here; use A's request to demonstrate the same supporter gate.
  source.data.urgentRecoverySupporters.B=['A']
  expect(planMowerAlphaExhaustSupport(source.data,source.data.shiftGroupMembers('a'),{urgentExhaust:true})).toBeUndefined()
  source.data.groupShiftState.b=false;source.data.groupShiftState.c=false
  const direct=planMowerAlphaExhaustSupport(source.data,['A'],{urgentExhaust:true})
  expect(direct).toEqual({})
 })

 it('reserves a confirmed partial return before the remaining support rooms execute',()=>{
  const {state,source,request}=fixture(true)
  state.config.mowerDeviceTiming={roomReturnMicros:500_000}
  drive(state,()=>request.urgentRecoverySupportNames.length>0)
  expect(source.execution?.task.exhaustSupport).toBe(true)
  expect(source.execution?.task.urgentRecoveryRequestNames).toEqual(request.urgentRecoveryRequestNames)
  expect(source.queue.tasks).toContain(request)
  expect(source.data.urgentRecoverySupporters).toEqual({})
  expect(mowerReplacementReservations(source.data,[request]).reservedNames.has('Y')).toBe(true)
  drive(state,()=>Object.values(state.bedOccupants).includes('A'))
  expect(source.data.urgentRecoverySupporters.A).toEqual(expect.arrayContaining(['B','C']))
 })

})
