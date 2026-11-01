import type {MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,type MowerTaskQueue} from './mowerTaskQueue'
import {mowerArrangementGroupTransitions} from './mowerSharedGroups'
import {mowerUrgentRecallBlocked,mowerUrgentPendingSupporters} from './mowerUrgentRecovery'

export interface MowerBackupGroupTask {group:string;action:'on'|'off';mode:'once'|'while_active'|'forced'}
export interface MowerBackupGroupRequest extends MowerBackupGroupTask {backup:number}

export function readMowerBackupGroupTasks(value:unknown):MowerBackupGroupTask[] {
 if(value===undefined)return []
 if(!Array.isArray(value))throw new Error('绑组任务必须为列表')
 const groups=new Set<string>()
 return value.map(raw=>{
  if(!raw||typeof raw!=='object'||typeof raw.group!=='string'||!raw.group.trim()||raw.group!==raw.group.trim()||!['on','off'].includes(raw.action??'off')||!['once','while_active','forced'].includes(raw.mode??'once'))throw new Error('绑组任务的组名、上下班或执行方式无效')
  const task:MowerBackupGroupTask={group:raw.group,action:raw.action??'off',mode:raw.mode??'once'}
  if(task.action==='on'&&task.mode!=='once')throw new Error('上班任务只执行一次，后续沿用正常轮换')
  if(groups.has(task.group))throw new Error('同一副表不能重复安排同一绑组')
  groups.add(task.group);return task
 })
}

export function mowerHeldRestGroups(data:MowerSchedulingData,forcedOnly=false):Set<string> {
 return new Set(data.backupGroupTasks.flatMap((tasks,i)=>data.planConditions[i]?tasks.filter(t=>t.action==='off'&&(t.mode==='forced'||!forcedOnly&&t.mode==='while_active')).map(t=>t.group):[]))
}

export function mowerForcedGroupCoverReservations(data:MowerSchedulingData):{names:Set<string>;slots:Set<string>} {
 const names=new Set<string>(),slots=new Set<string>()
 for(const group of mowerHeldRestGroups(data,true))if(data.groupIsResting(group))for(const name of data.shiftGroupMembers(group)){
  const owner=data.operators[name]!,cover=data.currentOperator(owner.room,owner.index)
  if(cover&&cover.name!==name){names.add(cover.name);slots.add(owner.room+'\0'+owner.index)}
 }
 return {names,slots}
}

export function validateMowerGroupTasks(data:MowerSchedulingData):void {
 const directions=new Map<string,string>()
 data.backupGroupTasks.forEach((tasks,i)=>{if(data.planConditions[i])for(const task of tasks){
  if(directions.has(task.group)&&directions.get(task.group)!==task.action)throw new Error('生效副表对同一绑组安排了相反的上下班任务：'+task.group)
  directions.set(task.group,task.action)
  if(!data.shiftGroupMembers(task.group).some(name=>data.isGroupShiftAnchor(data.operators[name]!)))throw new Error('绑组任务找不到工作主班：'+task.group)
 }})
}
export interface MowerBackupGroupTaskState {issued:Set<string>}
/** Requests remain separate from room overlays so dependency coordination uses actual occupancy. */
export function syncMowerBackupGroupTasks(data:MowerSchedulingData,queue:MowerTaskQueue,state:MowerBackupGroupTaskState,parked:MowerTask[]=[]):void {
 const requests=data.backupGroupTasks.flatMap((tasks,backup)=>data.planConditions[backup]?tasks.map(task=>({...task,backup})):[])
 const key=(request:MowerBackupGroupRequest)=>JSON.stringify([request.backup,request.group,request.action,request.mode])
 const active=new Set(requests.map(key)),directions=new Map<string,string>()
 for(const request of requests){
  if(directions.has(request.group)&&directions.get(request.group)!==request.action)throw new Error('生效副表对同一绑组安排了相反的上下班任务：'+request.group)
  directions.set(request.group,request.action)
 }
 const keep=(task:MowerTask)=>!task.backupGroupRequest||active.has(key(task.backupGroupRequest))||task.arrangementStarted||task.backupShiftActive
 queue.tasks=queue.tasks.filter(keep)
 parked.splice(0,parked.length,...parked.filter(keep))
 for(const old of state.issued)if(!active.has(old))state.issued.delete(old)
 validateMowerGroupTasks(data)
 for(const request of requests){
  const token=key(request),members=data.shiftGroupMembers(request.group),anchors=members.filter(name=>data.isGroupShiftAnchor(data.operators[name]!))
  if(!anchors.length)throw new Error('绑组任务找不到工作主班：'+request.group)
  if([...queue.tasks,...parked].some(task=>task.backupGroupRequest?.group===request.group&&task.backupGroupRequest.action===request.action))continue
  if(request.mode==='once'&&state.issued.has(token))continue
  const resting=data.groupIsResting(request.group)
  if(resting===(request.action==='off')){state.issued.add(token);continue}
  if(request.action==='off'&&mowerUrgentRecallBlocked(data,members,mowerUrgentPendingSupporters(queue.tasks)))continue
  const task=new MowerTask({time:data.nowMicros/3_600_000_000,type:request.action==='off'?T.EXHAUST_OFF:T.SHIFT_ON,metadata:anchors[0]})
  task.backupGroupRequest={...request}
  if(request.action==='on')for(const name of members){const op=data.operators[name]!;if(data.plan[op.room])(task.plan[op.room]??=Array(data.plan[op.room]!.length).fill('Current'))[op.index]=name}
  queue.tasks.push(task);state.issued.add(token)
 }
 filterMowerHeldReturns(data,queue)
}

/** Ordinary derived returns can be rebuilt on exit; started and coordinated work retains its owner. */
export function filterMowerHeldReturns(data:MowerSchedulingData,queue:MowerTaskQueue):void {
 const held=mowerHeldRestGroups(data)
 if(!held.size)return
 for(const task of [...queue.tasks]){
  if(task.type!==T.SHIFT_ON||task.retainsExecution||task.backupGroupRequest||task.exhaustSupport||task.backupShiftActive||task.arrangementStarted||task.productShiftLocked||task.dormRecoveryRestore.length)continue
  const blocked=Object.entries(mowerArrangementGroupTransitions(data,task.plan)).filter(([group,resting])=>!resting&&held.has(group)).map(([group])=>group)
  const members=new Set(blocked.flatMap(group=>data.shiftGroupMembers(group)))
  if(!members.size)continue
  for(const [room,row] of Object.entries(task.plan)){
   row.forEach((name,index)=>{if(members.has(name)||room.startsWith('dorm')&&members.has(data.currentOperator(room,index)?.name??''))row[index]='Current'})
   if(row.every(name=>name==='Current'))delete task.plan[room]
  }
  if(!Object.keys(task.plan).length)queue.consume(task)
  else {delete task.backupShiftIntent;delete task.backupShiftConditions;task.groupShiftTransitions={}}
 }
}
