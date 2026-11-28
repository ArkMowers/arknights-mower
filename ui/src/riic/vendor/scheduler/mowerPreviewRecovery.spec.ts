import {describe,it,expect} from 'vitest'
import {readFileSync} from 'node:fs'
import {createRosterRuntime,settleRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {importMowerJson} from '../workbench/compat/mowerJson'
import {runScheduleSimulationBridge} from '../workbench/scheduleSimulationBridge'

const rates={workRate:()=>1,recoveryRate:()=>4}
function previewFixture(){
 const keepers=['K1','K2','K3','K4']
 const config:RuntimeConfig={mowerAlpha:true,mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],shiftOffThreshold:15},...keepers.map((primary,i)=>({id:'dormitory_1_'+i,roomId:'dormitory_1',primary,candidates:[],permanent:true,dormitory:true}))],beds:[{id:'dormitory_1_4',roomId:'dormitory_1',vip:true}],initialMorale:{A:24,R:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[...keepers.map(agent=>({agent,group:'',replacement:[]})),{agent:'Free',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state);source.initial=false
 state.mowerShiftModel={count:1,evaluate:()=>{throw new MowerShiftPreviewError('上下班副表推演出现循环，保留原任务，暂不执行换人')},swap:d=>d,transition:()=>({}),activate:()=>{}}
 const task=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['Current','Current','Current','Current','A']}})
 source.queue.tasks=[task]
 return {state,source,task}
}

describe('recoverable Mower preview failure',()=>{
 it('retains an empty-preview decision after resuming the planning I/O continuation',()=>{
  const {state,source,task}=previewFixture(),before={...state.occupants}
  source.runFlags={planned:true,todoTask:true,collectNotification:true}
  source.phaseExecution=Object.assign({steps:(function*(){})(),wakeMicros:0,skipPlanning:false},{previewNoop:true})
  const boundaryRates={...rates,thresholds:()=>[23.9]}
  settleRoster(state,boundaryRates)
  expect(nextRosterActionHours(state,boundaryRates)).toBeCloseTo(.1,8)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
  expect(state.occupants).toEqual(before)
 })

 it('ignores virtual order wakes after an empty preview and waits for a real mood boundary',()=>{
  const {state,source,task}=previewFixture(),before={...state.occupants}
  state.config.mowerTaskScheduling={...state.config.mowerTaskScheduling,adjustForRunOrders:false}
  const order=new MowerTask({type:T.RUN_ORDER,metadata:'room_1_1'})
  source.queue.tasks.push(order)
  source.runFlags={planned:true,todoTask:true,collectNotification:true}
  source.phaseExecution={steps:(function*(){})(),wakeMicros:0,skipPlanning:false,previewNoop:true}
  const boundaryRates={...rates,thresholds:()=>[23.9]}
  settleRoster(state,boundaryRates)
  expect(nextRosterActionHours(state,boundaryRates)).toBeCloseTo(.1,8)
  const traceLength=source.trace.length
  settleRoster(state,boundaryRates)
  expect(source.trace).toHaveLength(traceLength)
  expect(source.queue.tasks).toEqual(expect.arrayContaining([task,order]))
  expect(task.timeMicros).toBe(0)
  expect(order.timeMicros).toBe(0)
  expect(state.occupants).toEqual(before)
 })

 it('retains an exhausted preview at its original deadline and dispatches independent due work',()=>{
  const {state,source,task}=previewFixture()
  let calls=0
  state.mowerShiftModel!.evaluate=()=>{calls++;throw new MowerShiftPreviewError('unchanged failed preview')}
  const independent=new MowerTask({time:.01,type:T.NOT_SPECIFIC})
  source.queue.tasks.push(independent)
  settleRoster(state,rates)
  const initialCalls=calls
  expect(initialCalls).toBeGreaterThan(0)
  state.time=.01;settleRoster(state,rates)
  expect(calls).toBe(initialCalls)
  expect(source.queue.tasks).not.toContain(independent)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
  state.time=.5;settleRoster(state,rates)
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
 })

 it('allows a retained preview after a new measured observation and preserves its identity',()=>{
  const {state,source,task}=previewFixture()
  let failed=true,calls=0
  state.mowerShiftModel!.evaluate=d=>{calls++;if(failed)throw new MowerShiftPreviewError('failed preview');return d.planConditions}
  settleRoster(state,rates)
  const initialCalls=calls
  failed=false
  state.time=.01
  const observed=source.data.operators.A!
  observed.timeStampMicros=36_000_000;observed.mood=23;observed.moodIsPrediction=false
  settleRoster(state,rates)
  expect(calls).toBeGreaterThan(initialCalls)
  expect(task.timeMicros).toBe(0)
  expect(source.queue.tasks.some(t=>t===task&&t.plan.room_1_1?.includes('R'))).toBe(false)
 })

 it('finishes the original first-day roster with the September compatibility strategy and a bounded event budget',()=>{
  const json=readFileSync(new URL('./fixtures/mower-preview-recovery-roster.json',import.meta.url),'utf8')
  const workspace=importMowerJson(json)
  // The September contract includes retired phase timing fields. Current
  // imports migrate them away; this historical fixture retains its source input.
  workspace.compatibility.backupPlans=JSON.parse(json).backup_plans
  const result=runScheduleSimulationBridge(workspace,{schedulingModel:'mower-default',sampleHours:24,warmupHours:0,maxEvents:2000,warmupModel:'hourly',recordSegments:true,production:{outputMode:'potential',runOrderMode:'ideal',droneTarget:'exp',seed:42}},{fiammettaFool:false,restingThreshold:.65})
  expect(result.report?.success,JSON.stringify(result.report?.diagnostics)).toBe(true)
  expect(result.report?.production?.success).toBe(true)
  expect(result.report?.elapsedHours).toBe(24)
  expect(result.report?.assumptions.schedulingModel).toBe('mower-default')
  expect(result.report?.inputs.options.schedulingModel).toBe('mower-default')
  expect(workspace.compatibility.backupPlans).toHaveLength(9)
 },90000)

 it('keeps a rejected arrangement and physical occupants beyond ordinary stale-task cleanup',()=>{
  const {state,source,task}=previewFixture(),plan=structuredClone(task.plan),occupants={...state.occupants}
  expect(()=>settleRoster(state,rates)).not.toThrow()
  expect(source.queue.tasks).toContain(task)
  expect(task.plan).toEqual(plan)
  expect(task.backupShiftActive).toBe(false)
  expect(state.occupants).toEqual(occupants)
  expect(state.bedOccupants).toEqual({})
  expect(source.activeTask).toBeUndefined()
  expect(nextRosterActionHours(state,rates)).toBe(2.5)
  state.time=.5;settleRoster(state,rates)
  expect(source.queue.tasks).toContain(task);expect(task.timeMicros).toBe(0)
 })

 it('wakes for an earlier explicit task without changing either task deadline',()=>{
  const {state,source,task}=previewFixture(),fia=new MowerTask({time:5/60,type:T.FIAMMETTA})
  source.queue.tasks.push(fia)
  expect(()=>settleRoster(state,rates)).not.toThrow()
  expect(nextRosterActionHours(state,rates)).toBe(5/60)
  expect(task.timeMicros).toBe(0)
  expect(fia.timeMicros).toBe(300_000_000)
  expect(source.queue.tasks).toEqual(expect.arrayContaining([task,fia]))
 })

 it('keeps predicted mood from releasing a failed preview until a real room read',()=>{
  const {state,source,task}=previewFixture()
  const boundaryRates={...rates,thresholds:()=>[23.9]}
  let calls=0
  state.mowerShiftModel!.evaluate=()=>{calls++;throw new MowerShiftPreviewError('unchanged failed preview')}
  settleRoster(state,boundaryRates)
  const initialCalls=calls,plan=structuredClone(task.plan)
  expect(nextRosterActionHours(state,boundaryRates)).toBeGreaterThan(.1)
  expect(task.executionFailure).toBeDefined()
  state.time=.1;source.data.operators.A!.mood=23.9;source.data.operators.A!.moodIsPrediction=true
  expect(nextRosterActionHours(state,boundaryRates)).toBeGreaterThan(.1)
  expect(task.executionFailure).toBeDefined()
  expect(calls).toBe(initialCalls)
  // Completing the pending native phase reads actual occupants; this is new evidence.
  settleRoster(state,boundaryRates)
  expect(source.data.operators.A!.currentRoom).toBe('room_1_1')
  expect(source.data.operators.A!.moodIsPrediction).toBe(false)
  expect(source.data.operators.A!.timeStampMicros).toBe(360_000_000)
  expect(task.executionFailure).toBeUndefined()
  expect(task.executionRetained).toBe(true)
  expect(source.queue.tasks).toContain(task);expect(task.timeMicros).toBe(0)
  expect(task.plan).toEqual(plan)
 })

 it('passes both the rejected preview and a later unchanged shift without disabling backups',()=>{
  const json=readFileSync(new URL('./fixtures/mower-preview-recovery-roster.json',import.meta.url),'utf8')
  const workspace=importMowerJson(json)
  workspace.compatibility.backupPlans=JSON.parse(json).backup_plans
  const before=structuredClone(workspace)
  // This September fixture keeps its original model; current alpha decisions
  // are covered by the October 13 native oracles and shared-group runtime tests.
  // MAX minus the 100-drone reserve performs 13 sets of 100 real 0.1-second
  // decrement taps. This fixture completes in 4212 intervals (peak 227/hour),
  // versus 3049 with the old reserve bug; 1152 of the 1163 extra intervals are
  // additional decrement taps. Budget those actions while retaining the local
  // density, consecutive clock-quanta, occupancy and morale safeguards below.
  const result=runScheduleSimulationBridge(workspace,{schedulingModel:'mower-default',sampleHours:48,warmupHours:0,maxEvents:4400,warmupModel:'hourly',recordSegments:true,production:{outputMode:'potential',runOrderMode:'ideal',droneTarget:'gold',seed:42}},{fiammettaFool:true,restingThreshold:.65})
  expect(result.error).toBeUndefined()
  expect(result.report?.success,JSON.stringify(result.report?.diagnostics)).toBe(true)
  expect(result.report?.production?.success).toBe(true)
  expect(result.report?.elapsedHours).toBeCloseTo(48,7)
  expect(workspace).toEqual(before)
  expect(workspace.compatibility.backupPlans).toHaveLength(9)
  expect(result.report?.diagnostics.some(d=>d.code==='BACKUP_EXECUTION_FAILED')).toBe(false)
  const intervalsPerHour=Array<number>(48).fill(0)
  let tinyRun=0,maxTinyRun=0
  for(const segment of result.report!.segments){
   intervalsPerHour[Math.floor(segment.start)]!++
   const seconds=(segment.end-segment.start)*3600
   expect(seconds).toBeGreaterThan(0)
   tinyRun=seconds<=.000002?tinyRun+1:0;maxTinyRun=Math.max(maxTinyRun,tinyRun)
   const occupants=[...Object.values(segment.occupants),...Object.values(segment.bedOccupants)]
   expect(new Set(occupants).size).toBe(occupants.length)
   expect(Object.values(segment.morale).every(m=>Number.isFinite(m)&&m>=0&&m<=24)).toBe(true)
  }
  expect(Math.max(...intervalsPerHour)).toBeLessThanOrEqual(240)
  expect(maxTinyRun).toBeLessThanOrEqual(8)
 },90000)
})
