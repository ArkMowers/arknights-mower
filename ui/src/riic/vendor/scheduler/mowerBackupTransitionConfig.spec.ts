import {describe,expect,it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {createBackupPlanController} from './backupPlans'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {prepareMowerShiftBackup} from './mowerShiftCycle'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function replacementOwnerFixture(explicit=true){
 const workspace=createDefaultWorkspace()
 workspace.mainPlan.facilities.dormitory_1.slots=Array.from({length:5},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))
 workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:'a',replacements:['char_240_wyvern']}]
 workspace.mainPlan.facilities.room_1_2.slots=[{occupant:{kind:'operator',operatorId:'char_502_nblade'},groupId:'a',replacements:['char_500_noirc']}]
 workspace.mainPlan.facilities.room_1_3.slots=[{occupant:{kind:'operator',operatorId:'char_208_melan'},groupId:null,replacements:['char_235_jesica']}]
 workspace.compatibility.backupPlans=[{
  name:'replace fixed owner',trigger:"op_data.operators['杰西卡'].is_working()",
  plan:{room_1_2:{plans:[{agent:'黑角',group:'',replacement:[]}]}},task:explicit?{room_1_2:['黑角']}:{},
 }]
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 source.data.groupShiftState.a=false
 return {state,controller,source}
}

describe('backup group transitions use the new fixed owner',()=>{
 it.each([false,true])('does not mark an unchanged group resting when a backup replaces one member, locked=%s',locked=>{
  const {state,controller,source}=replacementOwnerFixture()
  const task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:['char_235_jesica']}})
  task.productShiftLocked=locked
  prepareMowerShiftBackup(source.data,task,state.mowerShiftModel!)
  expect(task.backupShiftConditions).toEqual([true])
  expect(task.plan.room_1_2).toEqual(['char_500_noirc'])
  expect(task.groupShiftTransitions.a).toBeUndefined()
  expect(source.data.groupIsResting('a')).toBe(false)
  expect(controller.active).toEqual([false])
  expect(state.occupants.room_1_1_0).toBe('char_123_fang')
 })
 it('rederives a fresh intent after a plan-only backup changes its slot owner',()=>{
  const {state,source}=replacementOwnerFixture(false)
  const task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:['char_235_jesica'],room_1_2:['char_500_noirc']}})
  prepareMowerShiftBackup(source.data,task,state.mowerShiftModel!)
  expect(task.backupShiftConditions).toEqual([true])
  expect(task.backupExplicitSlots.size).toBe(0)
  expect(task.plan.room_1_2).toEqual(['char_500_noirc'])
  expect(task.groupShiftTransitions.a).toBeUndefined()
 })
 it('retains a real departure at a group slot whose owner did not change',()=>{
  const {state,source}=replacementOwnerFixture()
  const task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_3:['char_235_jesica'],room_1_1:['char_240_wyvern']}})
  prepareMowerShiftBackup(source.data,task,state.mowerShiftModel!)
  expect(task.groupShiftTransitions.a).toBe(true)
  expect(task.plan.room_1_1).toEqual(['char_240_wyvern'])
  expect(task.plan.room_1_2).toEqual(['char_500_noirc'])
 })
})
