import {mowerRecoveryMoodComplete} from './mowerGroupRecovery'
// Port of default prepare_release_dorm; mandatory full recovery rechecks measured mood.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import type {MowerSchedulingData} from './mowerSchedulingData'
import {MOWER_TASK_TYPES as T,MowerTask,type MowerTaskQueue} from './mowerTaskQueue'
import {MowerShiftPreviewError} from './mowerNativeErrors'
import {mowerGroupRecoveryDeadline,mowerRecoveryReady} from './mowerGroupRecovery'
import type {MowerTaskSchedulingOptions} from './mowerTaskScheduling'
export function prepareMowerRelease(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask,options:MowerTaskSchedulingOptions={}):boolean {
 if(data.alpha){
  // Validate all mandatory members before changing a merged release's plan.
  for(const name of mowerMandatoryReleaseNames(data,task)){
   const op=data.operators[name]!
   if(mowerRecoveryReady(data,op,options))continue
   const due=data.getDormByName(name)?.[1].timeMicros
   if(due===undefined||due<=data.nowMicros)throw new MowerShiftPreviewError('组员尚未确认回满心情，保留释放任务并等待有效恢复观察：'+op.nativeName)
  }
  return prepareAlphaRelease(data,queue,task)
 }
 let op=data.operators[task.metadata]
 if(task.strictMoodLimit&&!(op?.restMoodLimit&&(task.moodLimit===undefined||task.moodLimit===op.upperLimit))){task.plan={};return false}
 const room=Object.keys(task.plan)[0],index=room?task.plan[room]!.indexOf('Free'):-1
 if(!room||index<0){task.plan={};return false}
 if(!task.metadata&&!data.policy.experimentalDormLogic&&!task.strictMoodLimit){op=data.currentOperator(room,index);if(op)task.metadata=op.name}
 if(!op||op.currentRoom!==room||op.currentIndex!==index){task.plan={};return false}
 if(op.isHigh()&&op.mood>0){
  const dormant=data.getDormByName(op.name)
  if(dormant){
   const marker='dorm'+dormant[0],returnTask=queue.find({type:T.SHIFT_ON,metadata:marker})
   if(returnTask){const labels=returnTask.metadata.split(',');labels.splice(labels.indexOf(marker),1);returnTask.metadata=labels.join(',');op.mood=op.upperLimit;op.timeStampMicros=dormant[1].timeMicros}
  }
 }
 return true
}

/** Only mandatory recovery residents need a fresh physical observation before release. */
export function mowerMandatoryReleaseNames(data:MowerSchedulingData,task:MowerTask):string[]{
 if(!data.alpha||task.strictMoodLimit)return []
 return Object.entries(task.releaseDormTargets()).flatMap(([name,[room,index]])=>{
  const op=data.operators[name]
  if(!op||op.currentRoom!==room||op.currentIndex!==index)return []
  if(task.strictMoodLimit?!(op.restMoodLimit&&(task.moodLimit===undefined||task.moodLimit===op.upperLimit)):data.skipIdleDormRelease(name))return []
  return op.restInFull||!op.multiGroup&&Object.entries(data.groupRecoveryFullMembers).some(([group,names])=>names.includes(name)&&mowerGroupRecoveryDeadline(data,group).requiredNames.includes(name))?[name]:[]
 })
}

function prepareAlphaRelease(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask):boolean {
 if(!task.releaseTargets)return prepareAlphaMember(data,queue,task)
 const plan:Record<string,string[]>={},valid:Record<string,[string,number]>={};let ready=false
 for(const [name,[room,index]] of Object.entries(task.releaseDormTargets())){
  const row=Array(data.plan[room]!.length).fill('Current');row[index]='Free'
  const member=new MowerTask({type:T.RELEASE_DORM,plan:{[room]:row},metadata:name,strictMoodLimit:task.strictMoodLimit,moodLimit:task.moodLimit});member.timeMicros=task.timeMicros
  ready=prepareAlphaMember(data,queue,member)||ready
  if(Object.keys(member.plan).length){(plan[room]??=Array(row.length).fill('Current'))[index]='Free';valid[name]=[room,index]}
 }
 task.plan=plan;task.releaseTargets=valid;task.metadata=Object.keys(valid).join(',');return ready
}
function prepareAlphaMember(data:MowerSchedulingData,queue:MowerTaskQueue,task:MowerTask):boolean {
 const op=data.operators[task.metadata],strict=task.strictMoodLimit
 const reject=()=>{task.plan={};return false}
 if(strict&&!(op?.restMoodLimit&&(task.moodLimit===undefined||task.moodLimit===op.upperLimit))||!strict&&data.skipIdleDormRelease(task.metadata))return reject()
 const room=Object.keys(task.plan)[0],index=room?task.plan[room]!.indexOf('Free'):-1
 if(!room||index<0||!op||op.currentRoom!==room||op.currentIndex!==index)return reject()
 // A saved full dorm observation takes precedence over a retained working depletion rate.
 const mandatory=mowerMandatoryReleaseNames(data,task).includes(op.name)
 if((mandatory||!strict)&&!mowerRecoveryMoodComplete(data,op)){
  const bed=data.getDormByName(op.name)?.[1]
  if(bed?.timeMicros===undefined)return reject()
  if(bed.timeMicros>data.nowMicros){const pending=new MowerTask({type:task.type,plan:structuredClone(task.plan),metadata:task.metadata,strictMoodLimit:strict,moodLimit:task.moodLimit});pending.timeMicros=bed.timeMicros;queue.tasks.push(pending);return reject()}
 }
 if(op.isHigh()&&op.mood>0){const dormant=data.getDormByName(op.name);if(dormant){const marker='dorm'+dormant[0],returnTask=queue.find({type:T.SHIFT_ON,metadata:marker});if(returnTask){returnTask.metadata=returnTask.metadata.split(',').filter(n=>n!==marker).join(',');if(!strict){op.mood=op.upperLimit;op.timeStampMicros=dormant[1].timeMicros;op.moodIsPrediction=true}}}}
 return true
}
