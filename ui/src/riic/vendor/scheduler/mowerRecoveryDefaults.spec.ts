import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerOperatorState} from './mowerOperatorState'
import {mowerGroupRecoveryDeadline} from './mowerGroupRecovery'
import {toMowerMicros} from './mowerTaskQueue'

describe('power-dependent recovery spread defaults',()=>{
 it.each([2,3])('preserves unset and explicit thresholds with %s power plants',power=>{
  for(const value of [undefined,null,60,75,90]){
   const workspace=createDefaultWorkspace()
   if(power===2)workspace.mainPlan.facilities.room_3_3.type='manufacture'
   if(value!==undefined)workspace.compatibility.unrecognizedFields.advanced_settings={group_mood_gap_threshold_minutes:value}
   const schedule=compileRosterSchedule(workspace),state=createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
   expect(schedule.diagnostics.filter(d=>d.code==='INVALID_ASSUMPTION')).toEqual([])
   expect(getMowerSourceRuntime(state).data.groupMoodGapThresholdMinutes).toBe(value??(power===2?90:60))
   expect(workspace.compatibility.unrecognizedFields.advanced_settings).toEqual(value===undefined?undefined:{group_mood_gap_threshold_minutes:value})
  }
 })
 it.each([[2,90,false],[2,91,true],[3,60,false],[3,61,true]] as const)('uses the default boundary in actual group recovery: %s power, %s minute spread', (power,spread,delayed)=>{
  const operators=Object.fromEntries(['A','B'].map((name,index)=>[name,new MowerOperatorState({name,room:'room_1_1',index,group:'G',operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:index,mood:10,timeStampMicros:0})]))
  const data=new MowerSchedulingData({alpha:true,powerPlantCount:power,operators,plan:{room_1_1:['A','B'],dormitory_1:['Free','Free']},groupShiftState:{G:true},dorms:[new MowerDormState(['dormitory_1',0],'A',toMowerMicros(2)),new MowerDormState(['dormitory_1',1],'B',toMowerMicros(2+spread/60))]})
  expect(mowerGroupRecoveryDeadline(data,'G').requiredNames.length>0).toBe(delayed)
 })
})
