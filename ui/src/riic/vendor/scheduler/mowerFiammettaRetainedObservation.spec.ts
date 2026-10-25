import {describe,it,expect} from 'vitest'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
const rates={workRate:()=>1,recoveryRate:()=>4}
function fixture():RuntimeConfig {
 const keepers=['K1','K2','K3','K4']
 return {positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},...keepers.map((name,i)=>({id:'dormitory_1_'+i,roomId:'dormitory_1',primary:name,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:16,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(name=>({agent:name,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
}
describe('retained full-to-full Fiammetta requests admit only new observations',()=>{
 it.each([{alpha:false,named:false},{alpha:true,named:false},{alpha:false,named:true},{alpha:true,named:true}])('retains a full-to-full Fiammetta charge without polling ($alpha, named=$named)',({alpha,named})=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=alpha
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.idleOperators=['X'];config.initialMorale={A:24,R:24,X:24,[fia]:24}
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  expect(state.morale[fia]).toBe(16)
  // This fixture starts after recovery; initial morale remains the common sixteen-point input.
  state.morale[fia]=24
  expect(state.initialMorale![fia]).toBe(16)
  for(const [slot,name] of Object.entries(state.occupants)){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0}
  source.queue.tasks=[new MowerTask({type:T.FIAMMETTA,...(named?{plan:{room_1_1:['Current'],dormitory_1:['A',fia]},metadata:'A'}:{})})]
  const before={...state.occupants}
  settleRoster(state,rates)
  const retained=source.queue.tasks.find(task=>task.type===T.FIAMMETTA)!
  expect(retained.executionFailure).toBeDefined();expect(retained.timeMicros).toBe(0)
  expect(retained.plan.room_1_1).toBeUndefined()
  expect(state.events.filter(e=>e.type==='fiammetta')).toHaveLength(0)
  expect(state.occupants).toEqual(before)
  // Alpha fills R's empty bed during the first settle, before the later room task.
  expect(source.data.operators.R!.currentRoom).toBe(alpha?'dormitory_1':'')
  const traceCount=source.trace.filter(t=>t.type==='FIAMMETTA').length
  for(let attempt=0;attempt<3;attempt++)settleRoster(state,rates)
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traceCount)
  expect(source.queue.tasks.find(task=>task.type===T.FIAMMETTA)).toBe(retained)
  expect(retained.timeMicros).toBe(0)
  const independent=new MowerTask({time:.01,plan:{dormitory_1:[fia,'K2','K3','K4','X']}});source.queue.tasks.push(independent)
  let independentPhases=0
  state.time=.01;settleMowerSource(state,rates,()=>{independentPhases++;return false})
  expect(independentPhases).toBeGreaterThan(0)
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.queue.tasks.find(task=>task.type===T.FIAMMETTA)).toBe(retained)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toHaveLength(1)
  // Alpha replaces R with X; normal dorm selection admits the previously idle R.
  // Either actual room change permits one retry; unchanged dispatches stay suspended.
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traceCount+1)
  expect(state.bedOccupants.dormitory_1_4).toBe(alpha?'X':'R')
  expect(source.data.operators.X!.currentRoom).toBe(alpha?'dormitory_1':'')
  expect(source.data.operators.R!.currentRoom).toBe(alpha?'':'dormitory_1')
  expect(retained.executionFailure).toBeDefined()
  for(let attempt=0;attempt<3;attempt++)settleRoster(state,rates)
  expect(source.trace.filter(t=>t.type==='FIAMMETTA')).toHaveLength(traceCount+1)
  expect(source.queue.tasks.find(task=>task.type===T.FIAMMETTA)).toBe(retained)
  expect(source.queue.tasks.filter(task=>task.type===T.FIAMMETTA)).toHaveLength(1)
  expect(state.events.filter(e=>e.type==='fiammetta')).toHaveLength(0)
  expect(retained.timeMicros).toBe(0)
  expect(state.diagnostics.some(d=>d.message.includes('五分钟'))).toBe(false)
  const target=retained.plan.dormitory_1![0]!
  state.morale[target]=10
  const op=source.data.operators[target]!;op.mood=10;op.timeStampMicros=36_000_000;op.moodIsPrediction=false
  settleRoster(state,rates)
  expect(retained.executionFailure).toBeUndefined()
  expect(state.events.some(e=>e.type==='fiammetta'&&e.operators[1]===target)).toBe(true)
  expect(source.queue.tasks).not.toContain(retained)
  expect(state.occupants.dormitory_1_0).toBe(fia)
  expect(state.occupants.room_1_1_0).toBe('A')
 })
})
