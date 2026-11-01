import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'
import {getMowerSourceRuntime,nextMowerSourceActionHours,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,toMowerMicros} from './mowerTaskQueue'

function fixture(alpha:boolean,trigger="op_data.inventory_count('赤金') >= 10"){
 const workspace=createDefaultWorkspace();workspace.compatibility.backupPlans=[{trigger}]
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule);config.mowerAlpha=alpha
 const state=createRosterRuntime(config);state.mowerInventoryCounts={'赤金':0};state.mowerFacilityProducts={room_1_1:'gold'}
 const controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 source.initial=false;source.queue.tasks=[new MowerTask({time:10})]
 controller.evaluate('END')
 return {state,controller,source,wake:()=>state.mowerBackupObservationWakeMicros?.()}
}

describe.each([false,true])('inventory observation wakes for alpha=%s',alpha=>{
 it('wakes on the condition edge, consumes evaluation, and has no one-second polling',()=>{
  const {state,controller,wake}=fixture(alpha)
  expect(wake()).toBeUndefined()
  state.mowerInventoryCounts={'赤金':9};state.time=1;expect(wake()).toBeUndefined()
  state.mowerInventoryCounts={'赤金':10};expect(wake()).toBe(toMowerMicros(1));expect(wake()).toBe(toMowerMicros(1))
  controller.evaluate('END');expect(controller.active).toEqual([true]);expect(wake()).toBeUndefined()
  state.mowerInventoryCounts={'赤金':11};expect(wake()).toBeUndefined()
  state.mowerInventoryCounts={'赤金':0};expect(wake()).toBe(toMowerMicros(1))
  controller.evaluate('END');expect(controller.active).toEqual([false]);expect(wake()).toBeUndefined()
 })
 it('wakes from actual-product changes at the same clock',()=>{
  const {state,controller,wake}=fixture(alpha,"op_data.facility_product('room_1_1') == orirock")
  expect(wake()).toBeUndefined();state.mowerFacilityProducts={room_1_1:'orirock'}
  expect(wake()).toBe(0);controller.evaluate('END');expect(controller.active).toEqual([true]);expect(wake()).toBeUndefined()
 })

 it.each([
  ["op_data.facility_product_count('gold') == 2",'gold'],
  ['op_data.facility_product_type_count() == 2','exp3'],
 ])('wakes on an observed product count edge for %s',(trigger,product)=>{
  const {state,controller,wake}=fixture(alpha,trigger)
  expect(wake()).toBeUndefined()
  state.mowerFacilityProducts={room_1_1:'gold',room_1_2:product!}
  expect(wake()).toBe(0);controller.evaluate('END')
  expect(controller.active).toEqual([true]);expect(wake()).toBeUndefined()
  state.mowerFacilityProducts={room_1_1:'gold',room_1_2:null}
  expect(wake()).toBe(0);controller.evaluate('END')
  expect(controller.active).toEqual([false]);expect(wake()).toBeUndefined()
 })
 it('does not consume an edge during a protected in-flight backup',()=>{
  const {state,controller,source,wake}=fixture(alpha),locked=new MowerTask();locked.backupShiftActive=true;source.queue.tasks.push(locked)
  state.mowerInventoryCounts={'赤金':10};expect(wake()).toBeUndefined()
  expect(controller.evaluate('END')).toBe(false);expect(controller.active).toEqual([false])
  source.queue.consume(locked);expect(wake()).toBe(0)
  controller.evaluate('END');expect(controller.active).toEqual([true]);expect(wake()).toBeUndefined()
 })
 it('schedules a same-clock wake ahead of a future task and consumes it through the runtime',()=>{
  const {state,controller,source}=fixture(alpha)
  expect(nextMowerSourceActionHours(state)).toBe(10)
  state.mowerInventoryCounts={'赤金':10}
  expect(nextMowerSourceActionHours(state)).toBe(0)
  settleMowerSource(state,{workRate:()=>0,recoveryRate:()=>0},phase=>controller.evaluate(phase))
  expect(controller.active).toEqual([true])
  expect(source.conditionWakeMicros).toBeUndefined()
  expect(nextMowerSourceActionHours(state)).toBeGreaterThan(0)
 })
 it('wakes a sleeping outer run without interrupting a physical room operation',()=>{
  const {state,controller,source}=fixture(alpha)
  source.runReturn={wakeMicros:toMowerMicros(5),finishFallback:false}
  state.mowerInventoryCounts={'赤金':10}
  expect(nextMowerSourceActionHours(state)).toBe(0)
  settleMowerSource(state,{workRate:()=>0,recoveryRate:()=>0},phase=>controller.evaluate(phase))
  expect(controller.active).toEqual([true]);expect(nextMowerSourceActionHours(state)).toBeGreaterThan(0)
 })
 it('defers observation wakes until native I/O reaches its existing boundary',()=>{
  const {state,source}=fixture(alpha)
  function* steps():Generator<never,void,void>{return}
  source.phaseExecution={steps:steps(),wakeMicros:toMowerMicros(1),skipPlanning:false}
  state.mowerInventoryCounts={'赤金':10}
  expect(nextMowerSourceActionHours(state)).toBe(1)
  delete source.phaseExecution;expect(nextMowerSourceActionHours(state)).toBe(0)
 })
})

it('keeps the wake closure non-enumerable and outside cloneable runtime data',()=>{
 const {state}=fixture(false)
 expect(Object.keys(state)).not.toContain('mowerBackupObservationWakeMicros')
 expect({...state}).not.toHaveProperty('mowerBackupObservationWakeMicros')
 delete state.mowerSource
 expect(()=>structuredClone(state)).not.toThrow()
})

it('removes an obsolete observation hook when replacing the controller',()=>{
 const {state}=fixture(false),workspace=createDefaultWorkspace()
 createBackupPlanController(compileRosterSchedule(workspace),state)
 expect(state.mowerBackupObservationWakeMicros).toBeUndefined()
})

it('does not let an ordinary maintenance condition wake interrupt an existing outer sleep',()=>{
 const {state,source,controller}=fixture(true)
 source.runReturn={wakeMicros:toMowerMicros(5),finishFallback:false};source.conditionWakeMicros=0
 settleMowerSource(state,{workRate:()=>0,recoveryRate:()=>0},phase=>controller.evaluate(phase))
 expect(source.runReturn?.wakeMicros).toBe(toMowerMicros(5))
 expect(source.conditionWakeMicros).toBe(0)
 expect(nextMowerSourceActionHours(state)).toBe(5)
})
