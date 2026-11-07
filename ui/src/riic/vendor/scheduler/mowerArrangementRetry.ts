// Native alpha infra_main RoomArrangementDeferred handler (Mower b2d9ac8, MIT).
import {toMowerMicros,type MowerTask,type MowerTaskQueue} from './mowerTaskQueue'
export function deferMowerArrangementRetry(task:MowerTask,queue:MowerTaskQueue,room:string,nowMicros:number):void {
 const attempts=(task.arrangementRetryRoom===room?task.arrangementRetryCount??0:0)+1
 task.arrangementRetryDueMicros??=task.timeMicros;task.arrangementRetryRoom=room;task.arrangementRetryCount=attempts
 task.timeMicros=nowMicros+toMowerMicros(Math.min(attempts,5)/60);queue.sort()
}
