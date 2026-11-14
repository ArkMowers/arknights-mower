// Port of PlanConfig.is_refresh_trading and refresh_run_order_time.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {MowerTask,MOWER_TASK_TYPES as T,fromMowerMicros,type MowerTaskQueue} from './mowerTaskQueue'
export function mowerRefreshTradingSpec(name:string,config:string[]):[boolean,string[]] {
 const match=config.find(entry=>entry.toLowerCase().includes(name))
 if(match===undefined)return [false,[]]
 const rooms=match.split(name).join('')
 return [true,rooms?rooms.split(','):[]]
}
/** Python list.remove removes the first equal task, even when metadata differs. */
function remove(queue:MowerTaskQueue,task:MowerTask):void {
 const index=queue.tasks.findIndex(candidate=>candidate===task||candidate.equals(task))
 if(index<0)throw new Error('Native run-order refresh task is absent')
 queue.tasks.splice(index,1)
}
export function refreshMowerRunOrderTime(queue:MowerTaskQueue,nowMicros:number,room:string):void {
 const limit=fromMowerMicros(nowMicros+900_000_000)
 const distant=queue.find({time:limit,type:T.RUN_ORDER,metadata:room,comparison:'>'})
 if(distant)remove(queue,distant)
 const near=queue.find({time:limit,type:T.RUN_ORDER,metadata:room,comparison:'<'})
 if(near&&near.timeMicros>nowMicros){
  let time=nowMicros
  if(queue.tasks.length&&queue.tasks[0]!.type!==T.FIAMMETTA)time=queue.tasks[0]!.timeMicros-1_000_000
  remove(queue,near)
  const refresh=new MowerTask({type:T.REFRESH_TIME,metadata:room});refresh.timeMicros=time;queue.tasks.push(refresh)
 }
}
