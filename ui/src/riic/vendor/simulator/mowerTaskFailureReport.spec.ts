import {afterEach,describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import * as shiftCycle from '../scheduler/mowerShiftCycle'
import {MowerShiftPreviewError} from '../scheduler/mowerNativeErrors'
import * as rosterRuntime from '../scheduler/rosterRuntime'
import {getMowerSourceRuntime} from '../scheduler/mowerSourceRuntime'
import {simulateSchedule} from './scheduleSimulation'

function schedule(){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
 const manufacture=workspace.mainPlan.facilities.room_1_1
 manufacture.level=3;manufacture.product='gold';manufacture.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
 workspace.mainPlan.conf.workaholic=['char_123_fang','char_240_wyvern']
 workspace.compatibility.backupPlans=[{name:'forced correction',trigger:'True',plan:{room_1_1:{plans:[{agent:'香草',group:'',replacement:['芬']}]}}}]
 return compileRosterSchedule(workspace,{idleOperators:[]})
}
afterEach(()=>vi.restoreAllMocks())

describe('unresolved native task failures in the final income report',()=>{
 it('continues the full production clock while reporting a retained unresolved task as incomplete',()=>{
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation(()=>{throw new MowerShiftPreviewError('test exhausted preview')})
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:4,maxEvents:2000,consumptionOverrides:{char_123_fang:5},production:{outputMode:'potential',droneTarget:'none',seed:42}})
  expect(report.elapsedHours).toBe(4)
  expect(report.observedHours).toBeCloseTo(4,7)
  expect(report.success).toBe(false)
  expect(report.production?.success).toBe(false)
  expect(report.production!.sample.completed.gold).toBeGreaterThan(0)
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'MOWER_PENDING_TASK_FAILURE',message:expect.stringContaining('test exhausted preview')}))
  expect(report.diagnostics.some(d=>d.code==='SIMULATION_EVENT_LIMIT'||d.code==='SIMULATION_SAME_TIME_ACTION')).toBe(false)
 })
 it('allows full success after a later observation releases and completes the retained task',()=>{
  const create=rosterRuntime.createRosterRuntime
  let runtime:rosterRuntime.RuntimeState|undefined
  vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>runtime=create(config))
  const prepare=shiftCycle.prepareMowerShiftCycle
  let failed=false
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation((...args)=>{
   if(!failed){failed=true;throw new MowerShiftPreviewError('one observed preview failure')}
   return prepare(...args)
  })
  let observed=false
  const report=simulateSchedule(schedule(),{schedulingModel:'mower-alpha',warmupHours:0,sampleHours:8,maxEvents:4000,consumptionOverrides:{char_123_fang:5},production:{outputMode:'potential',droneTarget:'none',seed:42}},progress=>{
   if(observed||!runtime||progress.elapsedHours<1)return
   // Simulate a fresh room observation, independent of the failed task's
   // prediction. The report must reflect its later successful completion.
   const op=getMowerSourceRuntime(runtime).data.operators.char_123_fang!
   op.mood=runtime.morale.char_123_fang!;op.timeStampMicros=Math.round(runtime.time*3_600_000_000);op.moodIsPrediction=false
   observed=true
  })
  expect(failed).toBe(true)
  expect(observed).toBe(true)
  expect(report.elapsedHours).toBe(8)
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production?.success).toBe(true)
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(false)
  expect(report.diagnostics).toContainEqual(expect.objectContaining({code:'mower-task-exception',message:'one observed preview failure'}))
 })
})
