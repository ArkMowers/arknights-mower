// Port of base_schedule task failure snapshots, Mower alpha 3ad69f15 (MIT).
import type {RuntimeState} from './rosterRuntime'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTask,MowerTaskQueue} from './mowerTaskQueue'

export interface MowerTaskFailureSnapshot {
 intent:string
 observations:Record<string,[string,number,number|null]>
}

function snapshot(state:RuntimeState,data:MowerSchedulingData,task:MowerTask,rooms:readonly string[]):MowerTaskFailureSnapshot {
 const names=new Set(Object.values(task.plan).flat())
 return {
  intent:JSON.stringify({plan:task.plan,metadata:task.metadata,
   effectivePlan:Object.fromEntries(rooms.map(room=>[room,state.config.mowerSourcePlan?.[room]])),
   products:Object.fromEntries(rooms.map(room=>[room,state.mowerFacilityProducts?.[room]??null])),
   conditions:data.planConditions,
  }),
  observations:Object.fromEntries(Object.values(data.operators).filter(op=>names.has(op.name)||rooms.includes(op.currentRoom)).map(op=>
   [op.name,[op.currentRoom,op.currentIndex,op.moodIsPrediction?null:op.timeStampMicros??null]])),
 }
}

/** Retain remaining work and its deadline; only the dispatch view is suspended. */
export function retainMowerFailedTask(state:RuntimeState,data:MowerSchedulingData,task:MowerTask,reason:string,rooms=Object.keys(task.plan)):void {
 task.executionFailure={reason,rooms:[...rooms],snapshot:snapshot(state,data,task,rooms)}
}

/** Clock/prediction changes cannot admit an exhausted failure. */
export function resumeMowerFailedTasks(state:RuntimeState,data:MowerSchedulingData,queue:MowerTaskQueue):boolean {
 let changed=false
 for(const task of queue.tasks){
  const failure=task.executionFailure
  if(!failure)continue
  // A prediction replacing a measurement does not constitute new evidence.
  for(const [name,observation] of Object.entries(failure.snapshot.observations))if(data.operators[name]?.moodIsPrediction)observation[2]=null
  if(JSON.stringify(snapshot(state,data,task,failure.rooms))===JSON.stringify(failure.snapshot))continue
  delete task.executionFailure;task.executionRetained=true;changed=true
 }
 return changed
}
