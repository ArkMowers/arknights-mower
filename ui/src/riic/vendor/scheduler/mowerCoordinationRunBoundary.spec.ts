import {describe,expect,it} from 'vitest'
import {createRosterRuntime} from './rosterRuntime'
import {getMowerSourceRuntime,nextMowerSourceActionHours,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'

describe('coordination dependency release at native run completion',()=>{
 it('does not treat alternating failed previews as newly released physical reservations',()=>{
  const state=createRosterRuntime({mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['X']}],beds:[],mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['X']}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]}})
  const source=getMowerSourceRuntime(state),first=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['X']}}),second=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['X']}})
  first.backupExplicitSlots.add('room_1_1\0'+0);second.backupExplicitSlots.add('room_1_1\0'+0)
  source.queue.tasks=[first,second]
  retainMowerFailedTask(state,source.data,first,'shared cover blocked')
  retainMowerFailedTask(state,source.data,second,'shared cover blocked')
  expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(false)
  delete second.executionFailure;second.executionRetained=true
  expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(false)
  retainMowerFailedTask(state,source.data,second,'shared cover blocked')
  expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(false)
  expect(first.executionFailure).toBeDefined();expect(second.executionFailure).toBeDefined()
  expect(source.queue.tasks).toEqual([first,second]);expect(first.timeMicros).toBe(0);expect(second.timeMicros).toBe(0)
  // An actually active arrangement owns a reservation; completing it is new evidence.
  second.backupShiftActive=true
  retainMowerFailedTask(state,source.data,first,'active backup owns cover')
  second.backupShiftActive=false
  expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(true)
  expect(first.executionFailure).toBeUndefined()
 })
 it('readmits the original request before choosing the completed run clock',()=>{
  const state=createRosterRuntime({mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['X']}],beds:[],mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['X']}]},mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}})
  const source=getMowerSourceRuntime(state),task=new MowerTask({type:T.EXHAUST_OFF,metadata:'A'})
  source.initial=false;source.queue.tasks=[task]
  source.data.reservedProductReplacements.add('X')
  retainMowerFailedTask(state,source.data,task,'reserved replacement',['room_1_1'])
  source.runFlags={planned:true,todoTask:true,collectNotification:true}
  source.phaseExecution={steps:(function*(){source.data.reservedProductReplacements.delete('X')})(),wakeMicros:0,skipPlanning:true}
  settleMowerSource(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.queue.tasks).toContain(task)
  expect(task.timeMicros).toBe(0)
  expect(task.executionFailure).toBeUndefined()
  expect(task.executionRetained).toBe(true)
  expect(nextMowerSourceActionHours(state)).toBeGreaterThan(0)
  expect(nextMowerSourceActionHours(state)).toBe(nextMowerSourceActionHours(state))
 })
})
