import {describe,it,expect} from 'vitest'
import {MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {runDefaultTradeSegment,type RunOrderPlanningState,type RunOrderPlanningSeam} from './mowerRunOrderPlanning'

describe('ideal order planning',()=>{
 it('retains nearby order wakes without staffing plans or drone conflict adjustment',()=>{
  const state:RunOrderPlanningState={
   plan:{room_1_1:[{replacement:['但书']}],room_1_2:[{replacement:['但书']}]},
   runOrderRooms:['room_1_1','room_1_2'],queue:new MowerTaskQueue(),configuredDelayMinutes:3,droneRoom:'room_1_1',
   flags:{planned:false,todoTask:false,collectNotification:false},
  }
  let clock=0
  const requests:string[]=[]
  const seam:RunOrderPlanningSeam={nowMicros:()=>clock,currentDormOccupants:()=>undefined,scheduling:{}}
  const generator=runDefaultTradeSegment(state,seam)
  let step=generator.next()
  while(!step.done){
   const request=step.value;requests.push(request.kind)
   clock+=request.kind==='return-main'?500_000:100_000
   step=generator.next({observedAtMicros:clock,...(request.kind==='read-order'?{absoluteDueMicros:request.room==='room_1_1'?900_000_000:960_000_000}:{})})
  }
  expect(step.value.tailShouldRun).toBe(true)
  expect(requests).toEqual(['enter-room','wait-interface','read-order','return-main','enter-room','wait-interface','read-order','return-main'])
  expect(state.queue.tasks).toHaveLength(2)
  expect(state.queue.tasks.map(task=>task.type)).toEqual([T.RUN_ORDER,T.RUN_ORDER])
  expect(state.queue.tasks.map(task=>task.plan)).toEqual([{},{}])
  expect(state.queue.tasks.map(task=>task.observedOrderDueMicros)).toEqual([900_000_000,960_000_000])
 })
 it.each([0, 200_000])('does not create another wake when observed completion %s has already arrived',due=>{
  const state:RunOrderPlanningState={plan:{room_1_1:[{replacement:['但书']}]},runOrderRooms:['room_1_1'],queue:new MowerTaskQueue(),configuredDelayMinutes:3,droneRoom:null,flags:{planned:false,todoTask:false,collectNotification:false}}
  let clock=0,reads=0
  for(let pass=0;pass<2;pass++){
   const generator=runDefaultTradeSegment(state,{nowMicros:()=>clock,currentDormOccupants:()=>undefined,scheduling:{}})
   let next=generator.next()
   while(!next.done){
    const request=next.value
    if(request.kind==='read-order')reads++
    if(request.kind==='return-main')clock+=500_000
    next=generator.next({observedAtMicros:clock,...(request.kind==='read-order'?{absoluteDueMicros:due}:{})})
   }
   expect(state.queue.tasks).toEqual([])
  }
  expect(reads).toBe(2)
 })
 it('keeps the native dorm observation gate before reading order deadlines',()=>{
  const state:RunOrderPlanningState={
   plan:{room_1_1:[{replacement:['但书']}],dormitory_1:[]},
   runOrderRooms:['room_1_1'],queue:new MowerTaskQueue(),configuredDelayMinutes:3,droneRoom:null,
   flags:{planned:false,todoTask:false,collectNotification:false},
  }
  const generator=runDefaultTradeSegment(state,{nowMicros:()=>0,currentDormOccupants:()=>['杜林'],scheduling:{}})
  expect(generator.next()).toEqual({done:true,value:{tailShouldRun:true}})
  expect(state.queue.tasks).toEqual([])
 })
})
