import {describe,it,expect} from 'vitest'
import {executeMowerTodoTask,type MowerTodoTaskState,type MowerTodoTaskRequest} from './mowerTodoTask'
import {MOWER_TASK_TYPES as T,MowerTask,MowerTaskQueue,toMowerMicros} from './mowerTaskQueue'

function fixture(){
 const queue=new MowerTaskQueue(),blocked=new MowerTask({time:-10,type:T.FIAMMETTA,plan:{dormitory_1:['A','B']}})
 blocked.executionFailure={reason:'waiting for related observations',rooms:['dormitory_1'],snapshot:{intent:'unchanged',observations:{}}}
 queue.tasks=[blocked]
 const state:MowerTodoTaskState={queue,flags:{planned:true,todoTask:false,collectNotification:false},enableParty:true,lastClueMicros:null,droneRoom:'room_1_1',runOrderRooms:[],droneTimeMicros:null,droneIntervalHours:3,reloadRooms:['room_1_2'],reloadTimeMicros:null,maaGapHours:3}
 return {state,queue,blocked}
}

describe('retained failures release independent todo work',()=>{
 it('runs clue, drones and reload repeatedly without changing the failed task',()=>{
  const {state,queue,blocked}=fixture(),failure=blocked.executionFailure,plan=blocked.plan,time=blocked.timeMicros
  let now=toMowerMicros(100)
  for(let run=0;run<3;run++){
   state.flags.todoTask=false
   const generator=executeMowerTodoTask(state,{nowMicros:()=>now}),requests:MowerTodoTaskRequest[]=[]
   let next=generator.next()
   while(!next.done){
    const request=next.value
    requests.push(request)
    next=generator.next({kind:request.kind,observedAtMicros:now,value:request.kind==='reload'?{reloadTimeMicros:now}:null})
   }
   expect(requests).toEqual([{kind:'clue-new'},{kind:'drone',room:'room_1_1'},{kind:'reload',rooms:['room_1_2']}])
   expect(state.flags.todoTask).toBe(true)
   expect(state.lastClueMicros).toBe(now)
   expect(state.droneTimeMicros).toBe(now)
   expect(state.reloadTimeMicros).toBe(now)
   expect(queue.tasks).toHaveLength(1)
   expect(queue.tasks[0]).toBe(blocked)
   expect(blocked.executionFailure).toBe(failure)
   expect(blocked.plan).toBe(plan)
   expect(blocked.timeMicros).toBe(time)
   now+=toMowerMicros(4)
  }
  delete blocked.executionFailure
  expect(executeMowerTodoTask(state,{nowMicros:()=>now}).next().done).toBe(true)
  expect(queue.tasks[0]).toBe(blocked)
  expect(blocked.timeMicros).toBe(time)
 })

 it.each([0,1/60])('keeps a dispatchable task at %s hours ahead blocking todo work',ahead=>{
  const {state,queue,blocked}=fixture(),now=toMowerMicros(100),ready=new MowerTask({time:100+ahead,type:T.SHIFT_OFF,plan:{room_1_1:['C']}})
  queue.tasks.push(ready)
  expect(executeMowerTodoTask(state,{nowMicros:()=>now}).next().done).toBe(true)
  expect(state.lastClueMicros).toBeNull()
  expect(state.droneTimeMicros).toBeNull()
  expect(state.reloadTimeMicros).toBeNull()
  expect(queue.tasks).toEqual([blocked,ready])
 })
})
