import {mowerArrangementGroupTransitions,commitMowerGroupShifts} from './mowerSharedGroups'
// Port of default update_detail, refresh_dorm_time, correct_dorm and project_arrangements.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {hasRestingMood,MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {toMowerMicros,fromMowerMicros,roundMowerMicros,MOWER_TASK_TYPES as T,type MowerTask,type MowerTaskPlan} from './mowerTaskQueue'
/** A confirmed ordinary departure preserves a saved observation at the personal limit.
 * Source: Mower b9ec78a822099285a2e509630fce98f27afa6580 (MIT). */
export function mowerHasMeasuredDormDeparture(data:MowerSchedulingData,op:MowerOperatorState,room:string,observed:readonly string[],task?:MowerTask,confirmedPlan?:readonly string[]):boolean {
 const planned=confirmedPlan??task?.plan[room]
 return !!task?.plan[room]&&room.startsWith('dorm')&&!!planned&&planned.length===observed.length&&planned.every((name,index)=>name===observed[index])&&
  !observed.includes(op.name)&&hasRestingMood(op,data.nowMicros)&&!op.moodIsPrediction&&(op.mood>=op.upperLimit||task.strictMoodLimit&&op.restMoodLimit&&task.metadata===op.name&&(task.moodLimit===undefined||task.moodLimit===op.upperLimit))
}
/** Actual get_agent_from_room input expansion; FIA reads only explicitly passed indexes. */
export function mowerRoomReadIndexes(data:MowerSchedulingData,room:string,task?:MowerTask,requested:number[]=[]):number[] {
 const indexes=[...requested]
 if(room.startsWith('dorm')&&task?.type!==T.FIAMMETTA)for(const [index,name] of (data.plan[room]??[]).entries())if(name==='Free'||data.operators[name]?.nativeName==='菲亚梅塔')indexes.push(index)
 return [...new Set(indexes)]
}
export function shouldMowerReadMood(data:MowerSchedulingData,name:string,room:string,index:number,indexes:number[],task?:MowerTask,firstTask?:MowerTask):boolean {
 const op=data.operators[name]!
 if(room.startsWith('dorm')&&task?.type===T.FIAMMETTA)return (op.nativeName==='菲亚梅塔'||task.metadata===name)&&indexes.includes(index)
 return op.needToRefresh(data.nowMicros,2,room)||firstTask?.type===T.SHIFT_ON||indexes.includes(index)
}
/** The native SQLite decorator discards the inner return when update_time is false. */
export function mowerUpdateDetail(data:MowerSchedulingData,name:string,mood:number,room:string,index:number,updateTime=false,trueExhaustRooms=new Set<string>(),onRoomChanged?:(op:MowerOperatorState,startedWorking:boolean)=>void):number|undefined {
 const op=data.operators[name]!
 if(data.alpha&&(updateTime||op.currentRoom!==room||op.currentIndex!==index))data.dormMoodEstimates.delete(name)
 const previousBed=data.getDormByName(name)?.[1],retained=data.alpha&&previousBed?.name===name&&previousBed.position[0]===room&&previousBed.position[1]===index?previousBed.timeMicros:undefined
 const returned=data.alpha&&(op.currentRoom!==op.room||op.currentIndex!==op.index)&&room===op.room&&index===op.index
 const working=!!op.currentRoom&&!op.isResting()
 if(updateTime){
  // Integration round-off below the simulator morale tolerance is not an observed decline.
  if(op.timeStampMicros!==undefined&&op.mood-mood>1e-8){
   const elapsed=data.nowMicros-op.timeStampMicros
   if(elapsed>toMowerMicros(29/60))op.depletionRate=(op.mood-mood)/fromMowerMicros(elapsed)
  }
  op.timeStampMicros=data.nowMicros
  if(data.alpha){op.moodIsPrediction=false;op.idleRestCheck=undefined}
 }
 if(op.isResting()&&!room.startsWith('dorm'))op.depletionRate=0
 if(op.isResting()){const previous=data.getDormByName(name)?.[1];if(previous?.name===name)previous.reset()}
 if(!trueExhaustRooms.has(room))op.exhaustTimeMicros=undefined
 if(op.currentRoom!==room){op.currentRoom=room;onRoomChanged?.(op,!working&&!!room&&!room.startsWith('dorm'))}
 op.currentIndex=index;op.mood=mood
 if(data.alpha){
  if(returned&&!room.startsWith('dorm'))for(const [group,names] of Object.entries(data.groupRecoveryFullMembers))data.groupRecoveryFullMembers[group]=names.filter(member=>member!==name)
  if(updateTime){if(room===op.dormMoodFallback&&mood>=0&&mood<=24)for(const [name,stamp] of Object.entries(op.dormMoodPeers)){const peer=data.operators[name];if(peer&&!peer.currentRoom&&peer.timeStampMicros===stamp&&mood>=peer.upperLimit)peer.idleRestCheck=[peer.upperLimit,peer.mood,peer.timeStampMicros]}op.dormMoodPeers={}}
  if(updateTime&&mood>=0&&mood<op.upperLimit)op.dormMoodFallback=''
 }
 if(room==='train'&&index===0)op.restingFromTrain=true
 else if(room&&!room.startsWith('dorm')||mood>=24)op.restingFromTrain=false
 if(mood>=24)op.clearDormRecovery()
 if(room.startsWith('dorm')){
  const bed=data.getDormByName(name)?.[1]
  if(bed){bed.name=name;if(data.alpha)bed.timeMicros=retained;if(bed.timeMicros===undefined)return updateTime?index:undefined}
 }
 if(op.nativeName==='菲亚梅塔'&&(op.timeStampMicros===undefined||op.timeStampMicros<data.nowMicros))return updateTime?index:undefined
 return undefined
}
export function invalidateMowerDormTime(data:MowerSchedulingData,room:string):void {
 for(const bed of data.allDorms())if(bed.position[0]===room)bed.timeMicros=undefined
 for(const op of Object.values(data.operators))if(op.currentRoom===room)op.dormRecoveryObservation=undefined
}
export function mowerRefreshDormTime(data:MowerSchedulingData,room:string,index:number,name:string,timeMicros:number,trueExhaustRooms=new Set<string>()):void {
 const op=data.operators[name];if(!op)return
 if(data.alpha&&room.startsWith('dorm')&&op.currentRoom===room&&op.currentIndex===index&&op.timeStampMicros!==undefined&&!op.moodIsPrediction&&op.mood>=0&&op.mood<=24&&Number.isFinite(timeMicros))op.dormRecoveryObservation=[room,index,op.timeStampMicros,timeMicros]
 const bed=data.allDorms().find(b=>b.position[0]===room&&b.position[1]===index&&data.recoveryDorm(b,name))
 if(bed){
  if(data.alpha&&bed.name===name&&bed.timeMicros!==undefined)return
  bed.name=name
  bed.timeMicros=op.mood!==24&&op.timeStampMicros!==undefined?op.timeStampMicros+roundMowerMicros((op.upperLimit-op.mood)*(timeMicros-op.timeStampMicros)/(24-op.mood)):timeMicros
 }
 if(trueExhaustRooms.has(room))op.exhaustTimeMicros=Math.max(data.nowMicros,op.mood>0&&op.lowerLimit>0?data.nowMicros+roundMowerMicros((timeMicros-data.nowMicros)*(op.mood-op.lowerLimit)/op.mood):timeMicros)
}
export function mowerCorrectDorm(data:MowerSchedulingData):void {
 for(const bed of data.allDorms()){
  const op=data.operators[bed.name];if(!bed.name||!op)continue
  if(!data.recoveryDorm(bed,bed.name)||op.currentRoom!==bed.position[0]||op.currentIndex!==bed.position[1])bed.reset()
  else if(bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros){if(data.alpha&&op.timeStampMicros!==undefined&&op.mood>=op.upperLimit){op.depletionRate=0;continue}op.mood=op.upperLimit;op.timeStampMicros=bed.timeMicros;op.depletionRate=0;if(data.alpha)op.moodIsPrediction=true}
 }
}
export function projectMowerArrangements(data:MowerSchedulingData,plans:MowerTaskPlan[]):MowerSchedulingData {
 const projected=new MowerSchedulingData({...data,pendingGroupTransitions:{},groupDorms:data.groupDorms.map(b=>new MowerDormState([...b.position],b.name,b.timeMicros)),operators:Object.fromEntries(Object.entries(data.operators).map(([n,o])=>[n,new MowerOperatorState({...o,replacement:[...o.replacement]})])),dorms:data.dorms.map(b=>new MowerDormState([...b.position],b.name,b.timeMicros,b.autoFree))})
 for(const plan of plans){
  const groupTransitions=mowerArrangementGroupTransitions(projected,plan)
  const changed=new Set(Object.entries(plan).flatMap(([room,names])=>names.flatMap((name,index)=>name!=='Current'?[room+'\0'+index]:[])))
  const timers=new Map(projected.allDorms().filter(b=>b.name).map(b=>[b.name,{position:b.position,time:b.timeMicros}]))
  for(const op of Object.values(projected.operators))if(changed.has(op.currentRoom+'\0'+op.currentIndex)){if(data.alpha)op.setProjectedPosition('',-1);else{op.currentRoom='';op.currentIndex=-1}}
  for(const [room,names] of Object.entries(plan))for(const [index,name] of names.entries()){const op=projected.operators[name];if(op){if(data.alpha){op.setProjectedPosition(room,index);op.restMoodReleaseLimit=undefined}else{op.currentRoom=room;op.currentIndex=index}}}
  if(data.alpha)commitMowerGroupShifts(projected,groupTransitions)
  if(data.alpha)for(const op of Object.values(projected.operators))if(!op.isResting())op.temporaryDormFill=false
  for(const bed of projected.allDorms()){
   const op=projected.currentOperator(...bed.position)
   if(op&&projected.recoveryDorm(bed,op.name)){bed.name=op.name;const timer=timers.get(op.name);bed.timeMicros=!data.alpha||timer?.position[0]===bed.position[0]&&timer.position[1]===bed.position[1]?timer?.time:undefined}else bed.reset()
  }
 }
 return projected
}
