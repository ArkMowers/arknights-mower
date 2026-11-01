import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

const rates={workRate:()=>1,recoveryRate:(name:string)=>name==='A'?1:4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,name==='A'?1:4]))})}

function fixture(recall=false){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'A',group:'a',replacement:recall?['X']:['X','Y']}],
  room_1_2:[{agent:'B',group:'b',replacement:['X']},{agent:'B2',group:'b',replacement:['R2']}],
  room_1_3:[{agent:'C',group:'c',replacement:['Z']}],
  dormitory_1:['K1','K2','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
  dormitory_2:['K3','K4','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]})),
 }
 const config:RuntimeConfig={mowerAlpha:true,mowerSourcePlan:rows,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:`${room}_${index}`,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),beds:['dormitory_1','dormitory_2'].flatMap(room=>[2,3,4].map(index=>({id:`${room}_${index}`,roomId:room,vip:index===2}))),initialMorale:{A:recall?20:4,B:4,B2:12,C:24,X:24,Y:24,R2:24,Z:24},idleOperators:['Idle1','Idle2','Idle3','Idle4','Idle5','Idle6'],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:recall?['B','B2']:['A','B','B2'],lowPriority:[],refreshDrained:[],lingMode:0},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false
 for(const position of config.positions)Object.assign(data.operators[position.primary]!,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(position.id.lastIndexOf('_')+1)),mood:state.morale[position.primary]??24,timeStampMicros:0,depletionRate:1})
 state.occupants.room_1_1_0='X';state.bedOccupants.dormitory_1_2='A'
 Object.assign(data.operators.A!,{currentRoom:'dormitory_1',currentIndex:2,mood:config.initialMorale!.A,timeStampMicros:0})
 Object.assign(data.operators.X!,{currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0,depletionRate:1})
 data.dorms=config.beds.map(bed=>new MowerDormState([bed.roomId,Number(bed.id.slice(-1))],bed.id==='dormitory_1_2'?'A':undefined,bed.id==='dormitory_1_2'?toMowerMicros(recall?4:20):undefined))
 for(const op of Object.values(data.operators))if(op.timeStampMicros===undefined)op.timeStampMicros=0
 source.queue.tasks=[new MowerTask({type:T.NOT_SPECIFIC})]
 return {state,source}
}

function step(state:RuntimeState){
 settleRoster(state,rates)
 advanceRoster(state,Math.min(1/3600,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000)),rates)
}
function dispatchUntil(state:RuntimeState,done:()=>boolean){
 for(let attempt=0;attempt<80&&!done();attempt++)step(state)
 expect(done(),JSON.stringify({occupants:state.occupants,beds:state.bedOccupants,tasks:getMowerSourceRuntime(state).queue.tasks.map(task=>({type:task.type.key,metadata:task.metadata,plan:task.plan,failure:task.executionFailure?.reason})),diagnostics:state.diagnostics})).toBe(true)
 expect(state.diagnostics.filter(d=>/exception/.test(d.code))).toEqual([])
}
function useUp(state:RuntimeState,enabled:boolean){
 state.config.mowerSourceRules!.exhaustRequire=enabled?['B2']:[]
 getMowerSourceRuntime(state).data.operators.B2!.exhaustRequire=enabled
}
function setMood(state:RuntimeState,name:string,mood:number){
 state.morale[name]=mood
 const data=getMowerSourceRuntime(state).data
 Object.assign(data.operators[name]!,{mood,timeStampMicros:data.nowMicros})
}
function expectGroupWorking(state:RuntimeState){
 expect(state.occupants.room_1_2_0).toBe('B')
 expect(state.occupants.room_1_2_1).toBe('B2')
 expect(Object.values(state.bedOccupants)).not.toContain('B')
 expect(Object.values(state.bedOccupants)).not.toContain('B2')
 expect(state.events.filter(event=>event.type==='shift-off'&&event.operators.some(name=>['B','B2'].includes(name)))).toEqual([])
}

describe('ordinary coordination and use-up group interlock',()=>{
 it('rechecks a retained ordinary request after a peer enables use-up, releases other groups, and replans when disabled',()=>{
  const {state,source}=fixture()
  source.data.busyRestingNames.add('Y')
  dispatchUntil(state,()=>source.queue.tasks.some(task=>task.type===T.EXHAUST_OFF&&task.metadata.split(',').includes('B')&&!!task.executionFailure))
  const obsolete=source.queue.tasks.find(task=>task.type===T.EXHAUST_OFF&&task.metadata.split(',').includes('B'))!
  expect(obsolete.plan).toEqual({})
  expect(obsolete.arrangementStarted).toBe(false)
  const traceStart=source.trace.length
  useUp(state,true)
  source.data.busyRestingNames.delete('Y')
  setMood(state,'C',4)
  source.queue.tasks.push(new MowerTask({time:state.time}))
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('C'))
  expect(source.queue.tasks).not.toContain(obsolete)
  expect(obsolete.timeMicros).toBe(0)
  for(let attempt=0;attempt<12;attempt++)step(state)
  expect(source.trace.slice(traceStart).filter(task=>task.type==='EXHAUST_OFF'&&task.metadata==='B,B2')).toHaveLength(0)
  expectGroupWorking(state)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(Object.values(state.bedOccupants)).toContain('A')
  useUp(state,false)
  source.queue.tasks.push(new MowerTask({time:state.time}))
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('B')&&Object.values(state.bedOccupants).includes('B2'))
  expect(state.occupants.room_1_2_0).toBe('X')
 })

 it.each([false,true])('cancels queued ordinary support before rearranging or recalling another group (recall=%s)',recall=>{
  const {state,source}=fixture(recall)
  dispatchUntil(state,()=>source.queue.tasks.some(task=>task.exhaustSupport))
  const support=source.queue.tasks.find(task=>task.exhaustSupport)!
  expect(support.plan.room_1_1).toEqual([recall?'A':'Y'])
  useUp(state,true)
  for(let attempt=0;attempt<20;attempt++)step(state)
  expectGroupWorking(state)
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.events.filter(event=>event.type==='shift-on'&&event.operators.includes('A'))).toEqual([])
 })

 it('executes a genuine use-up request for the whole group despite the ordinary interlock',()=>{
  const {state,source}=fixture()
  useUp(state,true);setMood(state,'B2',0)
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('B')&&Object.values(state.bedOccupants).includes('B2'))
  expect(source.trace.some(task=>task.type==='EXHAUST_OFF'&&task.metadata.split(',').includes('B2'))).toBe(true)
  expect(state.occupants.room_1_2_0).toBe('X')
  expect(state.occupants.room_1_2_1).toBe('R2')
  expect(Object.values(state.bedOccupants)).toContain('A')
 })

 it('rechecks a concrete ordinary departure after its support has finished',()=>{
  const {state,source}=fixture()
  dispatchUntil(state,()=>source.queue.tasks.some(task=>task.type===T.SHIFT_OFF&&Object.entries(task.plan).some(([room,names])=>room.startsWith('dorm')&&names.includes('B'))))
  expect(state.occupants.room_1_1_0).toBe('Y')
  useUp(state,true)
  for(let attempt=0;attempt<20;attempt++)step(state)
  expectGroupWorking(state)
  expect(Object.values(state.bedOccupants)).toContain('A')
 })

 it('replans a batched ordinary departure when one group enables use-up',()=>{
  const {state,source}=fixture()
  source.data.operators.B!.replacement=['Y']
  state.config.mowerSourcePlan!.room_1_2![0]!.replacement=['Y']
  setMood(state,'C',4)
  dispatchUntil(state,()=>source.queue.tasks.some(task=>task.type===T.SHIFT_OFF&&task.coordinationRequestNames.includes('B')&&task.coordinationRequestNames.includes('C')))
  useUp(state,true)
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('C'))
  expectGroupWorking(state)
 })

 it('retains one failed use-up request across repeated ordinary dispatches',()=>{
  const {state,source}=fixture()
  useUp(state,true);setMood(state,'B2',0)
  source.data.busyRestingNames.add('Y')
  const original=new MowerTask({type:T.EXHAUST_OFF,metadata:'B2'})
  source.queue.tasks=[original]
  settleMowerSource(state,rates)
  expect(original.executionFailure).toBeDefined()
  for(let attempt=0;attempt<8;attempt++){
   const tick=new MowerTask({time:state.time})
   source.queue.tasks.push(tick)
   dispatchUntil(state,()=>!source.queue.tasks.includes(tick))
  }
  expect(source.queue.tasks.filter(task=>task.type===T.EXHAUST_OFF&&task.metadata.split(',').includes('B2'))).toEqual([original])
  expect(original.timeMicros).toBe(0)
  expectGroupWorking(state)
  source.data.busyRestingNames.delete('Y')
  dispatchUntil(state,()=>Object.values(state.bedOccupants).includes('B')&&Object.values(state.bedOccupants).includes('B2'))
  expect(source.queue.tasks).not.toContain(original)
 })
})
