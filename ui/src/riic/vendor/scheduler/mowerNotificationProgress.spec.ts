import {describe,it,expect} from 'vitest'
import {MOWER_TASK_TYPES as T,MowerTask,MowerTaskQueue} from './mowerTaskQueue'
import {collectMowerInfraNotification,type MowerNotificationState} from './mowerNotification'

describe('retained failures release notification collection',()=>{
 it('retains failed work without allowing it to block collection',()=>{
  const queue=new MowerTaskQueue(),blocked=new MowerTask({time:-10,type:T.SHIFT_OFF,plan:{room_1_1:['A']}})
  blocked.executionFailure={reason:'waiting for replacement',rooms:['room_1_1'],snapshot:{intent:'unchanged',observations:{}}}
  queue.tasks=[blocked]
  const state:MowerNotificationState={queue,flags:{todoTask:true,collectNotification:false,planned:true},lastTodoMicros:null}
  const generator=collectMowerInfraNotification(state,{nowMicros:()=>0})
  expect(generator.next().value).toEqual({kind:'detect-notification'})
  expect(generator.next({kind:'detect-notification',observedAtMicros:0,value:{ready:true}}).value).toEqual({kind:'tap-notification',target:{ready:true}})
  expect(generator.next({kind:'tap-notification',observedAtMicros:0,value:null}).done).toBe(true)
  expect(queue.tasks).toEqual([blocked])
  expect(blocked.time).toBe(-10)
  expect(blocked.executionFailure).toBeDefined()
 })
})
