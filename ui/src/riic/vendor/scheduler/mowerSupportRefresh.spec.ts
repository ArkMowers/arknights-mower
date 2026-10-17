import {afterEach,describe,expect,it,vi} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {MowerDormState} from './mowerSchedulingData'
import {retainMowerFailedTask} from './mowerTaskFailure'
import * as supportPlanning from './mowerExhaustPlanning'

const rates={workRate:()=>1,recoveryRate:()=>4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}
function generatedSupport(recall=false){
 const rows={room_1_1:[{agent:'A',group:'',replacement:['X']}],room_1_2:[{agent:'B',group:'resting',replacement:recall?['X']:['X','Y']}],room_1_3:[{agent:'C',group:'',replacement:['Z']}],contact:[{agent:'D',group:'resting',replacement:['W']}],dormitory_1:[...['K1','K2'].map(agent=>({agent,group:'',replacement:[]})),...['Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))]}
 const config:RuntimeConfig={
  mowerAlpha:true,mowerSourcePlan:rows,
  positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),
  beds:[{id:'dormitory_1_2',roomId:'dormitory_1',vip:true},{id:'dormitory_1_3',roomId:'dormitory_1',vip:false},{id:'dormitory_1_4',roomId:'dormitory_1',vip:false}],
  initialMorale:{A:0,B:4,C:4,D:4,X:24,Y:24,Z:24,W:24},idleOperators:[],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
  mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false
 for(const position of config.positions){const op=data.operators[position.primary]!;Object.assign(op,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(position.id.lastIndexOf('_')+1)),mood:state.morale[op.name]??24,timeStampMicros:0})}
 state.occupants.room_1_2_0='X';state.occupants.contact_0='W';state.bedOccupants.dormitory_1_2='B';state.bedOccupants.dormitory_1_3='D'
 Object.assign(data.operators.B!,{currentRoom:'dormitory_1',currentIndex:2,mood:4,timeStampMicros:0})
 Object.assign(data.operators.X!,{currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0})
 Object.assign(data.operators.D!,{currentRoom:'dormitory_1',currentIndex:3,mood:4,timeStampMicros:0})
 Object.assign(data.operators.W!,{currentRoom:'contact',currentIndex:0,mood:24,timeStampMicros:0})
 data.dorms=[new MowerDormState(['dormitory_1',2],'B',toMowerMicros(5)),new MowerDormState(['dormitory_1',3],'D',toMowerMicros(5)),new MowerDormState(['dormitory_1',4])]
 if(recall)for(const name of ['B','C','D']){state.morale[name]=20;Object.assign(data.operators[name]!,{mood:20,timeStampMicros:0,depletionRate:1})}
 const exhausted=new MowerTask({type:T.EXHAUST_OFF,metadata:'A'})
 source.queue.tasks=[exhausted]
 settleMowerSource(state,rates)
 expect(source.queue.tasks).toContain(exhausted)
 expect(exhausted.executionFailure).toBeDefined();expect(exhausted.timeMicros).toBe(0)
 const support=source.queue.tasks.find(task=>task.type===T.SELF_CORRECTION)!,retry=source.queue.tasks.find(task=>task.type===T.EXHAUST_OFF)!
 expect(support).toBeDefined();expect(retry).toBe(exhausted)
 expect(support.plan).toEqual(recall?{room_1_2:['B'],contact:['D']}:{room_1_2:['Y']})
 return {state,source,data:source.data,queue:source.queue,support,retry}
}

function dispatchUntilSettled(state:RuntimeState,support:MowerTask){
 const source=getMowerSourceRuntime(state)
 for(let n=0;n<30&&source.queue.tasks.includes(support)&&!support.executionFailure;n++){
  settleMowerSource(state,rates)
  if(source.queue.tasks.includes(support)&&!support.executionFailure)advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
}
afterEach(()=>vi.restoreAllMocks())
describe('runtime refreshes unstarted coordination support',()=>{
 it('replans the original request after changed replacement configuration',()=>{
  const {state,source,support,retry}=generatedSupport(),time=support.timeMicros
  retainMowerFailedTask(state,source.data,support,'previous preview')
  source.data.operators.B!.replacement=['X','Z']
  source.data.planConditions=[true]
  settleMowerSource(state,rates)
  dispatchUntilSettled(state,support)
  expect(source.trace.some(entry=>entry.type==='SELF_CORRECTION'&&entry.plan.room_1_2?.[0]==='Z')).toBe(true)
  expect(support.timeMicros).toBe(time)
  expect(support.coordinationRequestNames).toEqual(['A'])
  expect(state.occupants.room_1_2_0).toBe('Z')
  expect(retry.timeMicros).toBe(0)
 })
 it('clears an obsolete recall after new observations without committing its old group transition',()=>{
  const {state,source,support,retry}=generatedSupport(true),time=support.timeMicros
  support.backupShiftIntent=structuredClone(support.plan)
  support.groupShiftTransitions={resting:false}
  source.data.groupShiftState.resting=true
  retainMowerFailedTask(state,source.data,support,'previous preview')
  source.data.operators.A!.replacement=['X','Z']
  source.data.busyRestingNames.add('Z')
  Object.assign(source.data.operators.X!,{mood:0,timeStampMicros:1})
  state.morale.X=0
  settleMowerSource(state,rates)
  dispatchUntilSettled(state,support)
  expect(support.plan).toEqual({})
  expect(support.backupShiftIntent).toEqual({})
  expect(support.groupShiftTransitions).toEqual({})
  expect(support.timeMicros).toBe(time)
  expect(source.queue.tasks).not.toContain(support)
  expect(source.queue.tasks).toContain(retry)
  expect(source.data.groupShiftState.resting).toBe(true)
  expect(state.occupants.room_1_2_0).toBe('X')
 })
 it('does not retry an unchanged failed support or change its deadline',()=>{
  const {state,source,support}=generatedSupport(),time=support.timeMicros
  retainMowerFailedTask(state,source.data,support,'previous preview')
  const failure=support.executionFailure,plan=structuredClone(support.plan),refresh=vi.spyOn(supportPlanning,'planMowerExhaustSupport')
  for(let n=0;n<8;n++)settleMowerSource(state,rates)
  expect(refresh).not.toHaveBeenCalled()
  expect(support.executionFailure).toBe(failure)
  expect(support.plan).toEqual(plan);expect(support.timeMicros).toBe(time)
 })
 it.each(['arrangementStarted','backupShiftActive','productShiftLocked'] as const)('preserves %s support',lock=>{
  const {state,source,support}=generatedSupport(),plan=structuredClone(support.plan)
  support[lock]=true
  source.data.operators.A!.replacement=[]
  const refresh=vi.spyOn(supportPlanning,'planMowerExhaustSupport')
  dispatchUntilSettled(state,support)
  expect(refresh).not.toHaveBeenCalled()
  expect(support.plan).toEqual(plan)
  expect(support.executionFailure).toBeDefined()
 })
})
