import {afterEach,describe,expect,it,vi} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {MowerDormState} from './mowerSchedulingData'
import {mowerSupportRequestMatches,recordMowerUrgentSupport} from './mowerUrgentRecovery'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import * as supportPlanning from './mowerExhaustPlanning'

const rates={workRate:()=>1,recoveryRate:()=>4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}
function fixture(ordinary:boolean,origins=['A','C'],personal?:'ungrouped'|'shared'){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'A',group:'a',replacement:['X']},{agent:'A2',group:'a',replacement:['R']}],
  room_1_2:[{agent:'B',group:'b',replacement:['X']}],
  room_1_3:[{agent:'C',group:'c',replacement:['Z']},{agent:'C2',group:'c',replacement:['W']}],
  dormitory_1:['K1','K2','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
  dormitory_2:['K3','K4','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
 }
 if(personal){rows.room_1_1![0]!.group='';if(personal==='shared'){rows.room_1_1![0]!.groupBindings=[{group:'',replacement:['X']},{group:'a',replacement:['R']}];rows.room_1_1![1]!.replacement=['A']}}
 const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,mowerTaskScheduling:{adjustForRunOrders:false},mowerSourcePlan:rows,
  positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),
  beds:['dormitory_1','dormitory_2'].flatMap(room=>[2,3,4].map(index=>({id:room+'_'+index,roomId:room,vip:index===2}))),
  initialMorale:{A:ordinary?4:0,A2:personal?24:4,B:20,C:ordinary?4:0,C2:4,X:24,R:24,Z:24,W:24},idleOperators:['I1','I2','I3','I4','I5','I6'],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourceRules:{workaholic:[],exhaustRequire:ordinary?[]:origins,restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
  mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 for(const position of config.positions)Object.assign(data.operators[position.primary]!,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(-1)),mood:state.morale[position.primary]??24,timeStampMicros:0,depletionRate:1})
 state.occupants.room_1_2_0='X';state.bedOccupants.dormitory_1_2='B'
 Object.assign(data.operators.B!,{currentRoom:'dormitory_1',currentIndex:2,depletionRate:0})
 Object.assign(data.operators.X!,{currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
 data.dorms=config.beds.map(bed=>new MowerDormState([bed.roomId,Number(bed.id.slice(-1))],bed.id==='dormitory_1_2'?'B':'',bed.id==='dormitory_1_2'?toMowerMicros(1):undefined))
 for(const op of Object.values(data.operators))if(op.timeStampMicros===undefined)op.timeStampMicros=0
 const request=new MowerTask({type:T.EXHAUST_OFF,metadata:origins.join(',')})
 request.ordinaryCoordination=ordinary;request.coordinationRequestNames=ordinary?[...origins]:[]
 source.queue.tasks=[request]
 return {state,source,request}
}
function until(state:RuntimeState,done:()=>boolean){
 for(let attempt=0;attempt<80&&!done();attempt++){
  settleMowerSource(state,rates)
  if(!done())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
 expect(done(),JSON.stringify({time:state.time,tasks:getMowerSourceRuntime(state).queue.tasks.map(task=>({type:task.type.key,plan:task.plan,reason:task.executionFailure?.reason})),beds:state.bedOccupants,diagnostics:state.diagnostics})).toBe(true)
}
afterEach(()=>vi.restoreAllMocks())
describe('coordination request origins through the source lifecycle',()=>{
 it.each([false,true])('retains both independent triggers through support and admission, ordinary=%s',ordinary=>{
  const {state,source,request}=fixture(ordinary),time=request.timeMicros
  settleMowerSource(state,rates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)!
  expect(support).toBeDefined()
  expect(support.coordinationRequestNames).toEqual(['A','C'])
  expect(source.queue.tasks).toContain(request)
  expect(request.timeMicros).toBe(time)
  until(state,()=>source.queue.tasks.some(task=>task.type===T.SHIFT_OFF&&task.coordinationRequestNames.length===2))
  const departure=source.queue.tasks.find(task=>task.type===T.SHIFT_OFF&&task.coordinationRequestNames.length===2)!
  expect(departure.coordinationRequestNames).toEqual(['A','C'])
  expect(departure.urgentRecoveryRequestNames).toEqual(['A','A2','C','C2'])
  expect(mowerSupportRequestMatches(departure,support)).toBe(true)
  until(state,()=>['A','A2','C','C2'].every(name=>Object.values(state.bedOccupants).includes(name)))
  expect(request.timeMicros).toBe(time)
  expect(source.queue.tasks).not.toContain(request)
  expect(source.queue.tasks).not.toContain(support)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_3_0).toBe('Z')
  expect(source.data.urgentRecoverySupporters).toMatchObject({A:['B'],A2:['B'],C:['B'],C2:['B']})
  expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
 })
 it('does not give a working-swap follower ownership of its other normal group recovery',()=>{
  const {state,request}=fixture(false,['A'])
  const plan=structuredClone(state.config.mowerSourcePlan)!
  plan.room_1_1![0]!.replacement.push('F')
  plan.room_2_1=[{agent:'F',group:'a',replacement:['U'],groupBindings:[{group:'a',replacement:['U']},{group:'b',replacement:['V']}]}]
  state.config={...state.config,mowerSourcePlan:plan}
  const data=getMowerSourceRuntime(state).data
  expect(data.operators.F!.shiftGroup).toBe('b')
  const support=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_2:['B']}})
  support.exhaustSupport=true;support.coordinationRequestNames=['A']
  Object.assign(data.operators.B!,{currentRoom:'room_1_2',currentIndex:0})
  recordMowerUrgentSupport(data,support,[request],{B:['dormitory_1',2]})
  expect(request.urgentRecoveryRequestNames).toEqual(['A','A2'])
  expect(request.urgentRecoverySupportNames).toEqual(['B'])
  expect(support.coordinationRequestNames).toEqual(['A'])
 })
 it('retains an explicit individual request after its batched named group has entered recovery',()=>{
  const {state,source,request}=fixture(true),data=source.data,time=request.timeMicros
  Object.assign(data.operators.A!,{group:'',shiftGroup:undefined,groupBindings:[{group:'',replacement:['X']},{group:'a',replacement:['X']}]})
  expect(data.operators.A!.independentRest).toBe(true)
  for(const [index,name] of ['C','C2'].entries()){
   Object.assign(data.operators[name]!,{currentRoom:'dormitory_2',currentIndex:index+2})
   state.bedOccupants['dormitory_2_'+(index+2)]=name
  }
  retainMowerFailedTask(state,data,request,'等待个人恢复床位')
  for(let attempt=0;attempt<3;attempt++){
   resumeMowerFailedTasks(state,data,source.queue)
   expect(source.queue.tasks,JSON.stringify({tasks:source.queue.tasks.map(t=>({type:t.type.key,origins:t.coordinationRequestNames,plan:t.plan,reason:t.executionFailure?.reason})),beds:state.bedOccupants,diagnostics:state.diagnostics})).toContain(request)
   expect(request.timeMicros).toBe(time)
  }
  Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:3})
  state.bedOccupants.dormitory_1_3='A'
  resumeMowerFailedTasks(state,data,source.queue)
  expect(source.queue.tasks).not.toContain(request)
  expect(request.timeMicros).toBe(time)
 })
 it('keeps the original failed task and deadline until a relevant support dependency is released',()=>{
  const {state,source,request}=fixture(true,['A']),time=request.timeMicros
  settleMowerSource(state,rates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)!,supportTime=support.timeMicros
  source.data.busyRestingNames.add('B')
  retainMowerFailedTask(state,source.data,support,'替班交接等待专精结束')
  const failure=support.executionFailure,refresh=vi.spyOn(supportPlanning,'planMowerExhaustSupport')
  for(let attempt=0;attempt<8;attempt++)settleMowerSource(state,rates)
  expect(refresh).not.toHaveBeenCalled()
  expect(source.queue.tasks).toContain(request)
  expect(source.queue.tasks.filter(task=>task.exhaustSupport)).toEqual([support])
  expect(support.executionFailure).toBe(failure)
  expect(support.timeMicros).toBe(supportTime);expect(request.timeMicros).toBe(time)
  source.queue.tasks.push(new MowerTask({time:state.time}))
  until(state,()=>['C','C2'].every(name=>Object.values(state.bedOccupants).includes(name)))
  expect(source.queue.tasks).toContain(request)
  expect(request.timeMicros).toBe(time)
  expect(Object.values(state.bedOccupants)).not.toContain('A')
  source.data.busyRestingNames.delete('B')
  until(state,()=>['A','A2'].every(name=>Object.values(state.bedOccupants).includes(name)))
  expect(source.queue.tasks).not.toContain(support)
  expect(source.queue.tasks).not.toContain(request)
  expect(support.coordinationRequestNames).toEqual(['A'])
  expect(request.timeMicros).toBe(time)
 })
})


describe('resumed mixed requests retain unfinished individual departures',()=>{
 for(const personal of ['ungrouped','shared'] as const)for(const origins of [['A','C'],['C','A']])it(`keeps the individual after the named group rests (${personal}, ${origins.join(',')})`,()=>{
  const {state,source}=fixture(true,origins,personal),data=source.data
  for(const [index,name] of ['C','C2'].entries()){
   const cover=index===0?'Z':'W',bed='dormitory_2_'+(index+2)
   state.occupants['room_1_3_'+index]=cover;state.bedOccupants[bed]=name
   Object.assign(data.operators[name]!,{currentRoom:'dormitory_2',currentIndex:index+2,depletionRate:0})
   Object.assign(data.operators[cover]!,{currentRoom:'room_1_3',currentIndex:index,depletionRate:1})
   const slot=data.dorms.find(b=>b.position[0]==='dormitory_2'&&b.position[1]===index+2)!
   slot.name=name;slot.timeMicros=toMowerMicros(10)
  }
  data.groupShiftState.c=true
  const request=new MowerTask({time:-1,type:T.EXHAUST_OFF,metadata:origins.join(',')})
  request.ordinaryCoordination=true;request.coordinationRequestNames=[...origins]
  source.queue.tasks=[request];data.busyRestingNames.add('B')
  retainMowerFailedTask(state,data,request,'等待替班岗位释放',['room_1_1','room_1_2','dormitory_1'])
  const time=request.timeMicros
  advanceRoster(state,1/3600,rates)
  data.operators.A!.timeStampMicros=toMowerMicros(state.time)
  resumeMowerFailedTasks(state,data,source.queue)
  expect(request.executionFailure).toBeUndefined()
  for(let attempt=0;attempt<3;attempt++){
   settleMowerSource(state,rates)
   expect(source.queue.tasks,JSON.stringify({tasks:source.queue.tasks.map(t=>({type:t.type.key,origins:t.coordinationRequestNames,plan:t.plan,reason:t.executionFailure?.reason})),beds:state.bedOccupants,diagnostics:state.diagnostics})).toContain(request)
   expect(request.timeMicros).toBe(time)
   expect(Object.values(state.bedOccupants)).not.toContain('A')
   expect(state.bedOccupants.dormitory_2_2).toBe('C')
   expect(state.bedOccupants.dormitory_2_3).toBe('C2')
  }
  data.busyRestingNames.delete('B')
  until(state,()=>Object.values(state.bedOccupants).includes('A'))
  expect(request.timeMicros).toBe(time)
  expect(source.queue.tasks).not.toContain(request)
 })
})

describe('completed request sources remain complete after ordinary returns',()=>{
 for(const personal of ['ungrouped','shared'] as const)for(const origins of [['A','C'],['C','A']])it(`retains the original individual request after the completed group returns (${personal}, ${origins.join(',')})`,()=>{
  const slowRates={...rates,recoveryRate:(name:string)=>name==='B'?.1:4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,name==='B'?.1:4]))})}
  const {state,source,request}=fixture(true,origins,personal),time=request.timeMicros
  source.data.busyRestingNames.add('B')
  source.data.dorms.find(bed=>bed.name==='B')!.timeMicros=toMowerMicros(40)
  retainMowerFailedTask(state,source.data,request,'等待替班岗位释放',['room_1_1','room_1_2','dormitory_1'])
  source.queue.tasks.push(new MowerTask({time:state.time}))
  const settled=(done:()=>boolean)=>{
   for(let attempt=0;attempt<200&&!done();attempt++){
    settleMowerSource(state,slowRates)
    if(!done())advanceRoster(state,.05,slowRates)
   }
   expect(done(),JSON.stringify({time:state.time,beds:state.bedOccupants,tasks:source.queue.tasks.map(task=>({type:task.type.key,origins:task.coordinationRequestNames,plan:task.plan,reason:task.executionFailure?.reason}))})).toBe(true)
  }
  const departures=(name:string)=>state.events.filter(event=>event.type==='shift-off'&&event.operators.includes(name))
  settled(()=>['C','C2'].every(name=>Object.values(state.bedOccupants).includes(name)))
  expect(source.queue.tasks).toContain(request)
  expect(request.timeMicros).toBe(time)
  for(const name of ['C','C2'])expect(departures(name)).toHaveLength(1)
  expect(source.queue.tasks.some(task=>task.type===T.SHIFT_ON&&task.plan.room_1_3?.includes('C'))).toBe(true)
  settled(()=>['C','C2'].every((name,index)=>state.occupants['room_1_3_'+index]===name))
  expect(state.time).toBeGreaterThan(4)
  expect(state.morale.C).toBeGreaterThan(20)
  expect(state.events.some(event=>event.type==='shift-on'&&['C','C2'].every(name=>event.operators.includes(name)))).toBe(true)
  advanceRoster(state,.05,slowRates)
  for(let attempt=0;attempt<3;attempt++){
   settleMowerSource(state,slowRates)
   expect(source.queue.tasks).toContain(request)
   expect(request.coordinationRequestNames).toEqual(origins)
   expect(request.timeMicros).toBe(time)
   expect(state.occupants.room_1_1_0).toBe('A')
   expect(state.occupants.room_1_2_0).toBe('X')
   expect(Object.values(state.bedOccupants)).toContain('B')
   expect(Object.values(state.bedOccupants)).not.toContain('A')
  }
  source.data.busyRestingNames.delete('B')
  settled(()=>Object.values(state.bedOccupants).includes('A'))
  expect(request.timeMicros).toBe(time)
  expect(source.queue.tasks).not.toContain(request)
  for(const name of ['A','C','C2'])expect(departures(name)).toHaveLength(1)
  expect(state.diagnostics.filter(diagnostic=>/exception/.test(diagnostic.code))).toEqual([])
 })
})

describe('completed sources retain unfinished physical arrangements',()=>{
 it.each(['arrangementStarted','backupShiftActive','productShiftLocked'] as const)('keeps the original failure until a relevant observation changes with %s',flag=>{
  const {state,source,request}=fixture(true,['A','C'],'ungrouped'),data=source.data,time=request.timeMicros
  for(const name of ['C','C2']){state.morale[name]=24;data.operators[name]!.mood=24}
  const bed=data.dorms.find(value=>value.name==='B')!
  bed.name='A';bed.timeMicros=toMowerMicros(5);state.bedOccupants.dormitory_1_2='A'
  Object.assign(data.operators.B!,{currentRoom:'room_1_2',currentIndex:0});state.occupants.room_1_2_0='B'
  Object.assign(data.operators.X!,{currentRoom:'room_1_1',currentIndex:0});state.occupants.room_1_1_0='X'
  Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:2})
  request.coordinationCompletedRequestNames=['C']
  request.plan={dormitory_1:['Current','Current','A','I1','Current']}
  request[flag]=true
  retainMowerFailedTask(state,data,request,'等待剩余宿舍安排确认',['dormitory_1'])
  const failure=request.executionFailure!,snapshot=structuredClone(failure.snapshot)
  for(let attempt=0;attempt<3;attempt++){
   settleMowerSource(state,rates)
   expect(source.queue.tasks).toContain(request)
   expect(request.executionFailure).toBe(failure)
   expect(request.executionFailure!.snapshot).toEqual(snapshot)
   expect(request.coordinationRequestNames).toEqual(['A','C'])
   expect(request.timeMicros).toBe(time)
   expect(state.bedOccupants.dormitory_1_2).toBe('A')
   expect(state.bedOccupants.dormitory_1_3).toBeUndefined()
  }
  advanceRoster(state,1/3600,rates)
  source.data.operators.I1!.timeStampMicros=source.data.nowMicros
  until(state,()=>!source.queue.tasks.includes(request))
  expect(request.timeMicros).toBe(time)
  expect(state.bedOccupants.dormitory_1_2).toBe('A')
  expect(state.bedOccupants.dormitory_1_3).toBe('I1')
  expect(request.executionFailure).toBeUndefined()
  expect(state.events.filter(event=>event.type==='shift-off'&&event.operators.some(name=>['A','C','C2'].includes(name)))).toEqual([])
  expect(state.diagnostics.filter(diagnostic=>/exception/.test(diagnostic.code))).toEqual([])
 })
})
