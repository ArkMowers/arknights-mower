// Port of Operator observation/prediction and replacement_candidates, Mower alpha.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {toMowerMicros,fromMowerMicros} from './mowerTaskQueue'
export interface MowerGroupBinding {group:string;replacement:string[]}
export interface MowerOperatorOptions {
 groupBindings?:MowerGroupBinding[]
 alpha?:boolean;temporaryDormFill?:boolean;dormMoodFallback?:string;restMoodReleaseLimit?:number;moodIsPrediction?:boolean
 dormMoodPeers?:Record<string,unknown>
 name:string;nativeName?:string;room?:string;index?:number;group?:string;replacement?:string[];operatorType?:'high'|'low';restingPriority?:'high'|'low'|'standby'
 currentRoom?:string;currentIndex?:number;mood?:number;timeStampMicros?:number;depletionRate?:number;exhaustTimeMicros?:number
 dormPositionVersion?:number;dormRecoveryRoom?:string;dormRecoveryIndex?:number;dormRecoveryFixed?:MowerRecoveryManager[];singleRecoveryManager?:boolean;restingFromTrain?:boolean;idleRestCheck?:[number,number,number|undefined]
 lowerLimit?:number;upperLimit?:number;workaholic?:boolean;exhaustRequire?:boolean;restInFull?:boolean;restMoodLimit?:boolean;customMoodLimit?:boolean;standbyLowPriority?:boolean;workshop?:boolean
}
export type MowerRecoveryManager=[name:string,index:number,positionVersion:number]
export class MowerOperatorState {
 temporaryDormFill=false;dormMoodFallback='';restMoodReleaseLimit:number|undefined;moodIsPrediction=false
 customMoodLimit=false
 dormMoodPeers:Record<string,unknown>={}
 groupBindings:MowerGroupBinding[]=[]
 get multiGroup(){return this.groupBindings.length>1}
 replacementsForGroup(group:string):string[]{return this.multiGroup?this.groupBindings.find(binding=>binding.group===group)?.replacement??[]:this.replacement}
 alpha=false
 setProjectedPosition:(room:string,index:number)=>void
 name:string;nativeName:string;room:string;index:number;group:string;replacement:string[];operatorType:'high'|'low';restingPriority:'high'|'low'|'standby'
 currentRoom!:string;currentIndex!:number;mood:number;dormPositionVersion=0;dormRecoveryRoom='';dormRecoveryIndex=-1;dormRecoveryFixed:MowerRecoveryManager[]=[];singleRecoveryManager=false;restingFromTrain=false;idleRestCheck:[number,number,number|undefined]|undefined;timeStampMicros:number|undefined;depletionRate:number;exhaustTimeMicros:number|undefined
 refreshOrderRooms:[boolean,string[]]=[false,[]]
 lowerLimit:number;upperLimit:number;workaholic:boolean;exhaustRequire:boolean;restInFull:boolean;restMoodLimit:boolean;standbyLowPriority:boolean;workshop:boolean
 constructor(o:MowerOperatorOptions){
  let currentRoom:string|undefined,currentIndex=-1
  this.alpha=o.alpha??false
  this.groupBindings=(o.groupBindings??[]).map(binding=>({group:binding.group,replacement:[...binding.replacement]}))
  this.setProjectedPosition=(room,index)=>{currentRoom=room;this.currentIndex=index}
  this.temporaryDormFill=o.temporaryDormFill??false;this.dormMoodFallback=o.dormMoodFallback??'';this.restMoodReleaseLimit=o.restMoodReleaseLimit;this.moodIsPrediction=o.moodIsPrediction??false
  this.customMoodLimit=o.customMoodLimit??false
  this.dormMoodPeers={...o.dormMoodPeers}
  Object.defineProperties(this,{
   currentRoom:{enumerable:true,get:()=>currentRoom,set:(value:string)=>{if(currentRoom!==value){this.dormPositionVersion++;this.idleRestCheck=undefined;this.clearDormRecovery();currentRoom=value;if(this.alpha){if(value!==this.dormMoodFallback){this.dormMoodFallback='';this.dormMoodPeers={}}if(!value||!value.startsWith('dorm'))this.temporaryDormFill=false;if(value)this.restMoodReleaseLimit=undefined}}}},
   currentIndex:{enumerable:true,get:()=>currentIndex,set:(value:number)=>{if(currentIndex!==value){this.dormPositionVersion++;this.clearDormRecovery()}currentIndex=value}}
  })
 this.name=o.name;this.nativeName=o.nativeName??o.name;this.room=o.room??'';this.index=o.index??-1;this.group=o.group??'';this.replacement=o.replacement??[];this.operatorType=o.operatorType??'low';this.restingPriority=o.restingPriority??'low';this.currentRoom=o.currentRoom??'';this.currentIndex=o.currentIndex??-1;this.mood=o.mood??24;this.timeStampMicros=o.timeStampMicros;this.depletionRate=o.depletionRate??0;this.exhaustTimeMicros=o.exhaustTimeMicros;this.lowerLimit=o.lowerLimit??0;this.upperLimit=o.upperLimit??24;this.workaholic=o.workaholic??false;this.exhaustRequire=o.exhaustRequire??false;this.restInFull=o.restInFull??false;this.restMoodLimit=o.restMoodLimit??false;this.standbyLowPriority=o.standbyLowPriority??false;this.workshop=o.workshop??false;this.dormPositionVersion=o.dormPositionVersion??this.dormPositionVersion;this.dormRecoveryRoom=o.dormRecoveryRoom??'';this.dormRecoveryIndex=o.dormRecoveryIndex??-1;this.dormRecoveryFixed=o.dormRecoveryFixed?.map(m=>[...m])??[];this.singleRecoveryManager=o.singleRecoveryManager??false;this.restingFromTrain=o.restingFromTrain??false;this.idleRestCheck=o.idleRestCheck}
 clearDormRecovery(){this.dormRecoveryRoom='';this.dormRecoveryIndex=-1;this.dormRecoveryFixed=[]}
 isHigh(){return this.operatorType==='high'}
 isResting(){return this.currentRoom.startsWith('dorm')}
 /** Source returns the saved observation if an extrapolation is outside 0..24. */
 currentMood(nowMicros:number):number {const prediction=this.timeStampMicros===undefined?this.mood:this.mood-this.depletionRate*fromMowerMicros(nowMicros-this.timeStampMicros);return prediction>=0&&prediction<=24?prediction:this.mood}
 predictExhaust(nowMicros:number):number {
  if(this.workaholic||this.exhaustRequire||['factory','train'].includes(this.room))return nowMicros+toMowerMicros(24)
  const remaining=this.mood-this.lowerLimit
  if(this.timeStampMicros!==undefined&&this.depletionRate>0){const predicted=this.timeStampMicros+toMowerMicros(remaining/this.depletionRate-.5);return this.exhaustTimeMicros===undefined?predicted:Math.min(predicted,this.exhaustTimeMicros)}
  return remaining<=0?nowMicros:nowMicros+toMowerMicros(24)
 }
 needToRefresh(nowMicros:number,hours=2,room=''):boolean {if(['歌蕾蒂娅','见行者'].includes(this.nativeName))hours=.5;return this.timeStampMicros===undefined||this.timeStampMicros+toMowerMicros(hours)<nowMicros||room.startsWith('dorm')&&!this.room.startsWith('dorm')}
}
/** Ordinary dorm release shares this saved full-mood evidence with task planning. */
export function hasObservedFullMood(op:MowerOperatorState|undefined):boolean {return !!op&&op.timeStampMicros!==undefined&&op.mood>=0&&op.mood<=24&&op.mood>=op.upperLimit}
export function hasRestingMood(op:MowerOperatorState|undefined,nowMicros:number):boolean {return !!op&&op.timeStampMicros!==undefined&&op.mood>=0&&op.mood<=24&&op.currentMood(nowMicros)>=0&&op.currentMood(nowMicros)<=24}
export const restingMood=(op:MowerOperatorState|undefined,nowMicros:number)=>op&&hasRestingMood(op,nowMicros)?op.currentMood(nowMicros):24
export interface MowerMoodPolicy {restingThreshold:number;rescueThreshold:number;experimentalDormLogic?:boolean;alpha?:boolean}
export const rescueMoodThreshold=(op:MowerOperatorState,policy:MowerMoodPolicy)=>op.lowerLimit+(op.upperLimit-op.lowerLimit)*policy.restingThreshold*policy.rescueThreshold
export function mowerReplacementCandidates(op:MowerOperatorState,operators:Record<string,MowerOperatorState>,policy:MowerMoodPolicy,nowMicros:number):string[] {
 const complete=(name:string)=>{const candidate=operators[name];return !!candidate&&candidate.restMoodLimit&&hasRestingMood(candidate,nowMicros)&&restingMood(candidate,nowMicros)>=candidate.upperLimit}
 const candidates=op.replacement.filter(name=>name!=='Free'&&!(op.room.startsWith('dorm')&&complete(name)))
 const known=(candidate:MowerOperatorState|undefined):candidate is MowerOperatorState=>!!candidate&&candidate.timeStampMicros!==undefined&&candidate.mood>=0&&candidate.mood<=24
 if(!op.room.startsWith('dorm')&&op.nativeName!=='菲亚梅塔'){
  if(policy.alpha)return candidates.sort((a,b)=>Number(known(operators[a])&&operators[a]!.currentMood(nowMicros)<=operators[a]!.lowerLimit)-Number(known(operators[b])&&operators[b]!.currentMood(nowMicros)<=operators[b]!.lowerLimit))
  const rank=(name:string):[number,number]=>{const candidate=operators[name];if(!known(candidate))return [0,0];const mood=candidate.currentMood(nowMicros),below=mood<rescueMoodThreshold(candidate,policy);return [Number(below),below&&policy.experimentalDormLogic?-mood:0]}
  return candidates.sort((a,b)=>{const ra=rank(a),rb=rank(b);return ra[0]-rb[0]||ra[1]-rb[1]})
 }
 if(!op.room.startsWith('dorm')||!op.group||op.nativeName==='菲亚梅塔')return candidates
 const rank=(name:string):[number,number]=>{const candidate=operators[name];return known(candidate)?[0,candidate.currentMood(nowMicros)]:[1,0]}
 return candidates.sort((a,b)=>{const ra=rank(a),rb=rank(b);return ra[0]-rb[0]||ra[1]-rb[1]})
}
