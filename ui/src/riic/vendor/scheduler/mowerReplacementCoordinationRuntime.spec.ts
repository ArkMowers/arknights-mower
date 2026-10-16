import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

const rates={workRate:()=>1,recoveryRate:(name:string)=>name==='A'?1:4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,name==='A'?1:4]))})}
function fixture(alternates=['Y'],third?:'chain'|'occupied'){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={room_1_1:[{agent:'A',group:'a',replacement:['X',...alternates]}],room_1_2:[{agent:'B',group:'b',replacement:['X']}],dormitory_1:[...['K1','K2'].map(agent=>({agent,group:'',replacement:[]})),...['Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))]}
 if(third)rows.room_1_3=[{agent:'C',group:'c',replacement:third==='chain'?['Y','Z']:['Y']}]
 const config:RuntimeConfig={mowerAlpha:true,mowerSourcePlan:rows,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:`${room}_${index}`,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),beds:[2,3,4].map(index=>({id:`dormitory_1_${index}`,roomId:'dormitory_1',vip:index===2})),initialMorale:{A:4,C:4,B:0,X:24,Y:24,Z:24},idleOperators:['Idle1','Idle2','Idle3'],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:['B'],restInFull:['A','B',...(third?['C']:[])],lowPriority:[],refreshDrained:[],lingMode:0},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false
 for(const position of config.positions){const op=data.operators[position.primary]!;Object.assign(op,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(position.id.lastIndexOf('_')+1)),mood:state.morale[op.name]??24,timeStampMicros:0,depletionRate:1})}
 state.occupants.room_1_1_0='X';state.bedOccupants.dormitory_1_2='A'
 Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:2,mood:4,timeStampMicros:0})
 Object.assign(data.operators.X!,{currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
 data.dorms=[new MowerDormState(['dormitory_1',2],'A',toMowerMicros(20)),new MowerDormState(['dormitory_1',3]),new MowerDormState(['dormitory_1',4])]
 if(third){
  state.occupants.room_1_3_0='Y';state.bedOccupants.dormitory_1_3='C'
  Object.assign(data.operators.C!,{currentRoom:'dormitory_1',currentIndex:3,mood:4,timeStampMicros:0})
  Object.assign(data.operators.Y!,{currentRoom:'room_1_3',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
  data.dorms[1]=new MowerDormState(['dormitory_1',3],'C',toMowerMicros(5))
 }
 for(const op of Object.values(data.operators))if(op.timeStampMicros===undefined)op.timeStampMicros=0
 source.queue.tasks=[new MowerTask({type:T.EXHAUST_OFF,metadata:'B'}),new MowerTask({time:20,type:T.SHIFT_ON,plan:{room_1_1:['A']}})]
 return {state,source}
}
function dispatchUntil(state:RuntimeState,done:()=>boolean,maxSteps=50){
 for(let n=0;n<maxSteps&&!done();n++){
  settleRoster(state,rates)
  if(!done())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
 expect(done(),JSON.stringify({time:state.time,occupants:state.occupants,beds:state.bedOccupants,tasks:getMowerSourceRuntime(state).queue.tasks.map(task=>({type:task.type.key,plan:task.plan,time:task.timeMicros,failure:task.executionFailure?.reason})),diagnostics:state.diagnostics})).toBe(true)
 expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
}

describe('replacement coordination through source runtime',()=>{
 it.each([{mood:4,rate:1,allowed:false,ordinary:true},{mood:4,rate:1,allowed:true,ordinary:false},{mood:20,rate:1,allowed:true,ordinary:true}])('recall feasibility uses remaining work endurance: $mood mood, $rate depletion',({mood,rate,allowed,ordinary})=>{
  const {state,source}=fixture([])
  state.config.mowerSourceRules!.restInFull=['B'];source.data.operators.A!.restInFull=false
  source.queue.tasks[0]!.ordinaryCoordination=ordinary
  if(ordinary){source.data.operators.B!.exhaustRequire=false;state.config.mowerSourceRules!.exhaustRequire=[]}
  state.morale.A=mood;Object.assign(source.data.operators.A!,{mood,depletionRate:rate})
  source.data.getDormByName('A')![1].timeMicros=toMowerMicros(24-mood)
  settleMowerSource(state,rates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)
  if(allowed){
   expect(support?.plan).toEqual({room_1_1:['A']})
   dispatchUntil(state,()=>state.occupants.room_1_1_0==='A'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
   dispatchUntil(state,()=>state.occupants.room_1_2_0==='B',100)
   if(ordinary)expect(state.morale.A).toBeGreaterThan(0)
  }else{
   expect(support).toBeUndefined()
   expect(state.occupants.room_1_1_0).toBe('X')
   expect(Object.values(state.bedOccupants)).toContain('A')
  }
 })
 it('rechecks a safe recall after a projected backup makes its work endurance insufficient',()=>{
  const {state,source}=fixture([])
  state.config.mowerSourceRules!.restInFull=['B'];source.data.operators.A!.restInFull=false
  state.morale.A=20;Object.assign(source.data.operators.A!,{mood:20,depletionRate:1})
  source.data.getDormByName('A')![1].timeMicros=toMowerMicros(4)
  source.queue.tasks[0]!.ordinaryCoordination=true
  source.data.operators.B!.exhaustRequire=false;state.config.mowerSourceRules!.exhaustRequire=[]
  const changingRates={...rates,forecastRates:(projected:RuntimeState)=>{const forecast=rates.forecastRates(projected);return {...forecast,work:{...forecast.work,A:projected.mowerSource?.data.planConditions[0]?5:1}}}}
  settleMowerSource(state,changingRates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)!
  expect(support).toBeDefined()
  const activations:boolean[][]=[]
  source.data.planConditions=[false]
  state.mowerShiftModel={count:1,evaluate:data=>[data.operators.A!.currentRoom==='room_1_1'],swap:(data,conditions)=>{data.planConditions=[...conditions];return data},transition:()=>({}),activate:conditions=>{activations.push([...conditions])}}
  for(let attempt=0;attempt<20&&!support.executionFailure;attempt++){
   settleMowerSource(state,changingRates)
   if(!support.executionFailure)advanceRoster(state,Math.max(nextRosterActionHours(state,changingRates),1/3_600_000_000),changingRates)
  }
  expect(support.executionFailure).toBeDefined()
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(activations).toEqual([])
 })
 it('coordinates an ordinary blocked rest without requiring the use-up flag',()=>{
  const {state,source}=fixture()
  state.config.mowerSourceRules!.exhaustRequire=[]
  source.data.operators.B!.exhaustRequire=false
  source.queue.tasks=[new MowerTask({type:T.NOT_SPECIFIC})]
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.events.filter(event=>event.type==='shift-on'&&event.operators.includes('A'))).toEqual([])
 })
 it('moves a connected third cover before freeing the only replacement for B',()=>{
  const {state,source}=fixture(['Y'],'chain')
  settleMowerSource(state,rates)
  expect(source.queue.tasks.find(task=>task.exhaustSupport)?.plan).toEqual({room_1_3:['Z'],room_1_1:['Y']})
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&state.occupants.room_1_3_0==='Z'&&Object.values(state.bedOccupants).includes('B'))
  expect(Object.values(state.bedOccupants)).toEqual(expect.arrayContaining(['A','B','C']))
  expect(state.events.filter(event=>event.type==='shift-on'&&event.operators.some(name=>['A','C'].includes(name)))).toEqual([])
 })
 it('keeps the released preferred cover available for a third waiting group before restoring it',()=>{
  const {state,source}=fixture(['Y'],'chain')
  state.occupants.room_1_3_0='C';delete state.bedOccupants.dormitory_1_3
  Object.assign(source.data.operators.C!,{currentRoom:'room_1_3',currentIndex:0,mood:24,replacement:['X']});state.morale.C=24
  Object.assign(source.data.operators.Y!,{currentRoom:'',currentIndex:-1});source.data.dorms[1]!.reset()
  state.config.mowerSourcePlan!.room_1_3![0]!.replacement=['X']
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  state.morale.C=0;Object.assign(source.data.operators.C!,{mood:0,timeStampMicros:source.data.nowMicros})
  source.queue.tasks.push(new MowerTask({time:state.time,type:T.EXHAUST_OFF,metadata:'C'}))
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B'&&state.occupants.room_1_3_0==='X'&&Object.values(state.bedOccupants).includes('C'),100)
  expect(state.occupants.room_1_1_0).toBe('Y')
  expect(Object.values(state.bedOccupants)).toContain('A')
  dispatchUntil(state,()=>state.occupants.room_1_3_0==='C'&&state.occupants.room_1_1_0==='X',100)
  expect(state.time).toBeLessThan(20)
  expect(Object.values(state.bedOccupants)).toContain('A')
 })
 it('does not steal a third group cover when that group has no alternative or safe recall',()=>{
  const {state,source}=fixture(['Y'],'occupied')
  const original=source.queue.tasks[0]!
  settleMowerSource(state,rates)
  expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(false)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_3_0).toBe('Y')
  expect(Object.values(state.bedOccupants)).toEqual(expect.arrayContaining(['A','C']))
  expect(source.queue.tasks).toContain(original)
  expect(original.timeMicros).toBe(0)
  const dispatches=source.trace.filter(item=>item.type==='EXHAUST_OFF'&&item.metadata==='B').length
  for(let attempt=0;attempt<12;attempt++)settleMowerSource(state,rates)
  expect(source.trace.filter(item=>item.type==='EXHAUST_OFF'&&item.metadata==='B')).toHaveLength(dispatches)
  expect(source.queue.tasks).toContain(original)
  expect(original.timeMicros).toBe(0)
  // A confirmed C return releases Y, making A→Y and B→X feasible.
  state.morale.C=24;Object.assign(source.data.operators.C!,{mood:24,timeStampMicros:source.data.nowMicros})
  source.queue.tasks.push(new MowerTask({time:state.time,type:T.SHIFT_ON,plan:{room_1_3:['C']}}))
  dispatchUntil(state,()=>state.occupants.room_1_3_0==='C'&&state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  expect(source.queue.tasks).not.toContain(original)
 })
 it('retains an ordinary blocked group until a reservation releases, then restores its preferred cover',()=>{
  const {state,source}=fixture()
  state.config.mowerSourceRules!.exhaustRequire=[];source.data.operators.B!.exhaustRequire=false
  source.queue.tasks=[new MowerTask({type:T.NOT_SPECIFIC})]
  source.data.busyRestingNames.add('Y')
  dispatchUntil(state,()=>source.queue.tasks.some(task=>task.type===T.EXHAUST_OFF&&task.metadata==='B'&&!!task.executionFailure))
  const original=source.queue.tasks.find(task=>task.type===T.EXHAUST_OFF&&task.metadata==='B')!
  expect(original.executionFailure).toBeDefined()
  expect(original.coordinationDependencyWait).toBe(true)
  expect(source.data.operators.B!.exhaustRequire).toBe(false)
  expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(false)
  const timestamp=source.data.operators.Y!.timeStampMicros
  source.data.busyRestingNames.delete('Y')
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  expect(timestamp).toBe(0)
  expect(source.queue.tasks).not.toContain(original)
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B'&&state.occupants.room_1_1_0==='X',100)
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.time).toBeLessThan(20)
 })
 it('consumes a retained rest request already completed by another combined shift',()=>{
  const {state,source}=fixture([]),original=source.queue.tasks[0]!
  settleMowerSource(state,rates)
  expect(original.executionFailure).toBeDefined()
  state.morale.A=24;Object.assign(source.data.operators.A!,{mood:24,timeStampMicros:source.data.nowMicros})
  source.queue.tasks.push(new MowerTask({time:state.time,type:T.SHIFT_OFF,plan:{room_1_1:['A'],room_1_2:['X'],dormitory_1:['K1','K2','B','Free','Free']}}))
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('B')&&!source.queue.tasks.includes(original))
  expect(state.occupants.room_1_1_0).toBe('A')
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B',100)
  for(let attempt=0;attempt<8;attempt++)settleMowerSource(state,rates)
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(state.events.filter(event=>event.type==='shift-off'&&event.operators.includes('B'))).toHaveLength(1)
 })
 it('does not restore a cover after the original resting primary has already returned',()=>{
  const {state,source}=fixture()
  state.morale.A=23;source.data.operators.A!.mood=23
  source.data.getDormByName('A')![1].timeMicros=toMowerMicros(1)
  source.queue.tasks.find(task=>task.type===T.SHIFT_ON)!.timeMicros=toMowerMicros(1)
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='A')
  expect(state.occupants.room_1_2_0).toBe('X')
  const returnedAt=state.time
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B',100)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.trace.some(task=>task.timeMicros>toMowerMicros(returnedAt)&&task.plan.room_1_1?.[0]==='X')).toBe(false)
 })
 it('revalidates a queued restoration when a backup changes candidate order before dispatch',()=>{
  const {state,source}=fixture()
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B',100)
  const queued=source.queue.tasks.find(task=>task.exhaustSupport&&task.plan.room_1_1?.[0]==='X')
  expect(queued).toBeDefined()
  source.data.operators.A!.replacement=['Y','X'];state.config.mowerSourcePlan!.room_1_1![0]!.replacement=['Y','X']
  const traceStart=source.trace.length
  dispatchUntil(state,()=>!source.queue.tasks.includes(queued!))
  expect(state.occupants.room_1_1_0).toBe('Y')
  expect(source.trace.slice(traceStart).some(task=>task.plan.room_1_1?.[0]==='X')).toBe(false)
  expect(Object.values(state.bedOccupants)).toContain('A')
 })
 it.each([false,true])('restores according to the effective replacement order after B returns (backup changed=%s)',changed=>{
  const {state,source}=fixture()
  settleMowerSource(state,rates)
  expect(source.queue.tasks.find(task=>task.exhaustSupport)?.plan).toEqual({room_1_1:['Y']})
  dispatchUntil(state,()=>state.occupants.room_1_1_0==='Y'&&state.occupants.room_1_2_0==='X'&&Object.values(state.bedOccupants).includes('B'))
  const aDeadline=source.data.getDormByName('A')![1].timeMicros
  expect(aDeadline).toBe(toMowerMicros(20))
  if(changed){source.data.operators.A!.replacement=['Y','X'];state.config.mowerSourcePlan!.room_1_1![0]!.replacement=['Y','X']}
  dispatchUntil(state,()=>state.occupants.room_1_2_0==='B',100)
  const preferred=changed?'Y':'X'
  for(let n=0;n<10&&state.occupants.room_1_1_0!==preferred;n++){
   settleRoster(state,rates)
   if(state.occupants.room_1_1_0!==preferred)advanceRoster(state,Math.min(1/3600,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000)),rates)
  }
  expect(state.occupants.room_1_1_0).toBe(preferred)
  expect(state.time).toBeLessThan(20)
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.events.filter(event=>event.type==='shift-on'&&event.operators.includes('A'))).toEqual([])
  expect(source.data.getDormByName('A')![1].timeMicros).toBe(aDeadline)
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(Object.values(state.occupants)).not.toContain(changed?'X':'Y')
 })
})
