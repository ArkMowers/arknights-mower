import {describe,expect,it} from 'vitest'
import {createRosterRuntime,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {planMowerCorrection} from './mowerCorrection'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

const rates={workRate:()=>0,recoveryRate:()=>4}
function fixture(){
 const config:RuntimeConfig={mowerAlpha:true,positions:[
  {id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']},
  {id:'room_1_2_0',roomId:'room_1_2',primary:'B',candidates:['S']},
 ],beds:[],mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],room_1_2:[{agent:'B',group:'',replacement:['S']}]},
 mowerSourceRules:{workaholic:['A','B'],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},initialMorale:{A:24,B:24},mowerDeviceTiming:{roomReturnMicros:500_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false
 for(const name of ['A','B']){source.data.operators[name]!.setProjectedPosition('',-1);delete state.occupants[source.data.operators[name]!.room+'_0']}
 const retained=new MowerTask({type:T.SELF_CORRECTION,time:10,plan:{room_1_1:['A']}})
 retained.executionRetained=true;source.queue.tasks=[retained]
 return {state,source,retained}
}
describe('retained corrections own their remaining arrangements',()=>{
 it('suppresses a repeated correction and preserves independent work',()=>{
  const {source,retained}=fixture(),time=retained.timeMicros,plan=structuredClone(retained.plan)
  const first=planMowerCorrection(source.data,source.queue,true)
  expect(first?.plan).toEqual({room_1_2:['B']})
  first!.executionRetained=true
  expect(planMowerCorrection(source.data,source.queue,true)).toBeUndefined()
  expect(source.queue.tasks).toEqual([retained,first])
  expect(retained.timeMicros).toBe(time);expect(retained.plan).toEqual(plan)
 })
 it('excludes the current arrangement from its own reservation',()=>{
  const {source,retained}=fixture()
  source.data.operators.B!.setProjectedPosition('room_1_2',0)
  const correction=planMowerCorrection(source.data,source.queue,true,retained)
  expect(correction?.plan).toEqual({room_1_1:['A']})
 })
 it('protects a retained target currently occupying another correction slot',()=>{
  const {source,retained}=fixture()
  source.data.operators.A!.setProjectedPosition('room_1_2',0)
  retained.plan={room_1_1:['R']}
  expect(planMowerCorrection(source.data,source.queue,true)).toBeUndefined()
 })
 it('reserves every binding group of a retained shared member',()=>{
  const {source,retained}=fixture(),a=source.data.operators.A!,b=source.data.operators.B!
  a.group='a';a.groupBindings=[{group:'a',replacement:['R']},{group:'b',replacement:['R']}];b.group='b'
  retained.plan={room_1_1:['R']}
  const candidate=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_2:['B']}})
  expect(admitMowerDerivedTasks(source.data,[retained],[candidate])).toEqual([])
 })
 it.each(['dormitory_1',''])('admits a recovered group referenced only by an incidental preview while its member is in %s',room=>{
  const {source,retained}=fixture(),b=source.data.operators.B!
  b.group='b';b.workaholic=false;b.setProjectedPosition(room,room?0:-1)
  retained.backupShiftIntent=structuredClone(retained.plan)
  retained.plan.dormitory_1=['B']
  retained.executionFailure={reason:'incidental preview',rooms:[],snapshot:{intent:'',observations:{}}}
  const plan=structuredClone(retained.plan),time=retained.timeMicros,candidate=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_2:['B']}})
  expect(admitMowerDerivedTasks(source.data,[retained],[candidate])).toEqual([candidate])
  expect(retained.plan).toEqual(plan);expect(retained.timeMicros).toBe(time)
 })
 it('reuses an equivalent pending correction without changing its deadline',()=>{
  const {source,retained}=fixture()
  retained.executionRetained=false
  source.data.operators.B!.setProjectedPosition('room_1_2',0)
  const time=retained.timeMicros
  expect(planMowerCorrection(source.data,source.queue,true)).toBe(retained)
  expect(source.queue.tasks).toEqual([retained]);expect(retained.timeMicros).toBe(time)
 })
 it('does not duplicate or execute the retained target through real dispatch',()=>{
  const {state,source,retained}=fixture(),time=retained.timeMicros
  source.queue.tasks.unshift(new MowerTask())
  for(let i=0;i<8;i++){
   settleMowerSource(state,rates)
   const delay=nextRosterActionHours(state,rates)
   if(!Number.isFinite(delay)||state.time+delay>=1)break
   advanceRoster(state,Math.max(delay,1/3_600_000_000),rates)
  }
  expect(source.queue.tasks).toContain(retained)
  expect(retained.timeMicros).toBe(time)
  expect(state.occupants.room_1_1_0).toBeUndefined()
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(source.trace.some(entry=>entry.type==='SELF_CORRECTION'&&entry.plan.room_1_1?.includes('A'))).toBe(false)
  expect(source.queue.tasks.filter(task=>task!==retained).some(task=>Object.values(task.plan).flat().includes('A'))).toBe(false)
 })
})
