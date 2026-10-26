import {describe,it,expect} from 'vitest'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
const rates={workRate:()=>1,recoveryRate:()=>4}
function fixture():RuntimeConfig {
 const keepers=['K1','K2','K3','K4']
 return {positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],lowerLimit:0,upperLimit:24,shiftOffThreshold:15},...keepers.map((name,i)=>({id:'dormitory_1_'+i,roomId:'dormitory_1',primary:name,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:16,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(name=>({agent:name,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
}
describe('completed full-target Fiammetta requests leave normal observations available',()=>{
 it.each([{alpha:false,named:false},{alpha:true,named:false},{alpha:false,named:true},{alpha:true,named:true}])('finishes without retrying after an unrelated room observation ($alpha, named=$named)',({alpha,named})=>{
  const config=fixture(),fia='char_300_phenxi';config.mowerAlpha=alpha
  config.positions[1]!.primary=fia;config.mowerSourcePlan!.dormitory_1![0]!.agent=fia
  config.idleOperators=['X'];config.initialMorale={A:24,R:24,X:24,[fia]:24}
  config.fiammetta={operatorId:fia,orderedTargets:['A'],fool:false,threshold:21.6}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
  expect(state.initialMorale![fia]).toBe(16);state.morale[fia]=24
  for(const [slot,name] of Object.entries(state.occupants)){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0}
  const charge=new MowerTask({type:T.FIAMMETTA,...(named?{plan:{room_1_1:['Current'],dormitory_1:['A',fia]},metadata:'A'}:{})})
  source.queue.tasks=[charge]
  settleRoster(state,rates)
  expect(source.queue.tasks).not.toContain(charge)
  expect(source.queue.tasks.some(task=>task.type===T.FIAMMETTA)).toBe(false)
  const traces=source.trace.filter(task=>task.type==='FIAMMETTA').length
  for(let attempt=0;attempt<3;attempt++)settleRoster(state,rates)
  const independent=new MowerTask({time:.01,plan:{dormitory_1:[fia,'K2','K3','K4','X']}});source.queue.tasks.push(independent)
  let phases=0
  state.time=.01;settleMowerSource(state,rates,()=>{phases++;return false})
  expect(phases).toBeGreaterThan(0)
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.trace.filter(task=>task.type==='FIAMMETTA')).toHaveLength(traces)
  expect(source.queue.tasks.some(task=>task.type===T.FIAMMETTA)).toBe(false)
  expect(state.events.filter(event=>event.type==='fiammetta')).toHaveLength(0)
  expect(state.diagnostics.filter(diagnostic=>diagnostic.code==='mower-task-exception')).toEqual([])
  state.morale.A=10
  Object.assign(source.data.operators.A!,{mood:10,timeStampMicros:36_000_000,moodIsPrediction:false})
  source.queue.tasks.push(new MowerTask({time:state.time}))
  settleRoster(state,rates)
  expect(state.events.some(event=>event.type==='fiammetta'&&event.operators[1]==='A')).toBe(true)
  expect(state.events.find(event=>event.type==='fiammetta')!.moraleAfter![1]).toBe(24)
  expect(state.occupants.dormitory_1_0).toBe(fia)
 })
})
