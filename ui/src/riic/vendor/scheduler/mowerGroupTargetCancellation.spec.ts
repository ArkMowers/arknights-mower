import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {prepareMowerDormSelection} from './mowerSelection'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

describe('canceling dynamic recovery preserves working observations',()=>{
 it('keeps the depletion rate when a personal-cap admission is canceled before leaving work',()=>{
  const op=new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',mood:12,timeStampMicros:0,depletionRate:1,upperLimit:12,restMoodLimit:true})
  const data=new MowerSchedulingData({alpha:true,nowMicros:0,operators:{A:op},plan:{room_1_1:['A'],dormitory_1:['Free']},dorms:[new MowerDormState(['dormitory_1',0])]})
  const task=new MowerTask({type:T.SHIFT_OFF,plan:{dormitory_1:['A']}})
  prepareMowerDormSelection(data,task.plan.dormitory_1!,'dormitory_1',false,false,task)
  expect(task.plan.dormitory_1).toEqual(['Free'])
  expect(op.currentRoom).toBe('room_1_1')
  expect(op.depletionRate).toBe(1)
  expect(op.currentMood(toMowerMicros(1))).toBe(11)
 })
})
