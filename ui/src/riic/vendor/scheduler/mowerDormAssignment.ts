import type {MowerTaskPlan} from './mowerTaskQueue'
// Port of default available_free / _find_dorm_slot / assign_dorm(_group).
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
import {hasRestingMood,rescueMoodThreshold,restingMood,type MowerOperatorState} from './mowerOperatorState'
import type {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {alphaRestingTier,alphaFullDynamicCandidate,alphaRestingKey,compareAlphaKeys,alphaSlotTakable,alphaFindDormSlot} from './mowerAlphaDorm'
function defaultOnly(data:MowerSchedulingData){if(data.policy.experimentalDormLogic)throw new Error('Experimental resting tiers require their source port')}
export function mowerStandbyCanYield(data:MowerSchedulingData,op:MowerOperatorState):boolean {
 return data.canStandby(op)&&hasRestingMood(op,data.nowMicros)&&restingMood(op,data.nowMicros)>=rescueMoodThreshold(op,data.policy)
}
export function mowerAvailableFree(data:MowerSchedulingData,type:'high'|'low'='high',now=data.nowMicros):number {
 if(data.alpha){const effective=data.dorms.filter(b=>data.effectiveFreeSlot(b)),count=new Set(effective.map(b=>b.position[0])).size;let high=0,low=0;for(const bed of effective)if(data.operators[bed.name]){if(alphaRestingTier(data,bed.name)<=1)high++;else low++}return type==='high'?Math.max(0,count-high):effective.length-low-Math.max(high,count)}
 defaultOnly(data)
 const effective=data.dorms.filter(b=>data.effectiveFreeSlot(b))
 const count=new Set(effective.map(b=>b.position[0])).size
 let high=0,low=0
 for(const bed of effective){
  const op=data.operators[bed.name];if(!op||op.workshop)continue
  if(bed.timeMicros!==undefined&&bed.timeMicros<now){
   if(op.isHigh()){op.mood=op.upperLimit;op.depletionRate=0;op.timeStampMicros=now}
   continue
  }
  if(op.restingPriority==='high')high++;else low++
 }
 return type==='high'?Math.max(0,count-high):effective.length-low-Math.max(high,count)
}
export function mowerActiveHighRestingCount(data:MowerSchedulingData,now=data.nowMicros):number {
 if(data.alpha)return data.dorms.filter(b=>data.effectiveFreeSlot(b)&&data.operators[b.name]?.isHigh()&&alphaRestingTier(data,b.name)!==6).length
 defaultOnly(data)
 return data.dorms.filter(b=>{
  const op=data.operators[b.name]
  return data.effectiveFreeSlot(b)&&op?.isHigh()&&!mowerStandbyCanYield(data,op)&&!op.workshop&&!(b.timeMicros!==undefined&&b.timeMicros<now)
 }).length
}
export function mowerSlotTakable(data:MowerSchedulingData,bed:MowerDormState,protectResting:boolean,requester?:string):boolean {
 if(data.alpha)return alphaSlotTakable(data,bed,requester)
 defaultOnly(data)
 if(!data.effectiveFreeSlot(bed))return false
 const op=data.operators[bed.name];if(!op)return true
 if(data.skipIdleDormRelease(op.name))return false
 if(bed.timeMicros!==undefined&&bed.timeMicros<data.nowMicros)return true
 const incoming=requester?data.operators[requester]:undefined
 if(mowerStandbyCanYield(data,op)&&incoming?.isHigh()&&incoming.restingPriority==='high'&&!incoming.workshop)return true
 if(op.workshop&&incoming)return !incoming.workshop&&(incoming.isHigh()||incoming.currentMood(data.nowMicros)<=22)
 if(!op.isHigh())return !(protectResting&&op.isResting())
 return false
}
export function mowerFindDormSlot(data:MowerSchedulingData,name:string,used:Set<number>,groupResting=false,departingNames?:ReadonlySet<string>):number|undefined {
 if(data.alpha)return alphaFindDormSlot(data,name,used,groupResting?new Set([data.operators[name]!.group]):undefined)
 defaultOnly(data)
 if(data.restMoodComplete(name))return undefined
 const op=data.operators[name]!,high=op.restingPriority==='high'&&!op.workshop
 const takeover=high||groupResting&&data.canStandby(op)
 const vip=Object.keys(data.plan).filter(room=>room.startsWith('dorm')).length
 const indices=data.dorms.map((_,i)=>i)
 const order=high?indices:[...indices.slice(vip),...indices]
 return order.find(i=>{
  if(used.has(i))return false
  const bed=data.dorms[i]!,resident=data.operators[bed.name]
  // Only low replacements can release an unfinished bed here. Resting primary
  // operators keep the existing full-rest and group protection rules.
  const departing=departingNames?.has(bed.name)&&resident&&!resident.isHigh()&&resident.currentRoom===bed.position[0]&&resident.currentIndex===bed.position[1]&&data.effectiveFreeSlot(bed)
  return departing||mowerSlotTakable(data,bed,!takeover,name)
 })
}
export function mowerStandbyCandidates(data:MowerSchedulingData,names:string[]):Set<string> {
 const anchors=new Set(names.map(n=>data.operators[n]!).filter(op=>op.group&&op.isHigh()&&(data.alpha?!data.canStandby(op):op.restingPriority==='high')&&!op.workaholic&&(data.alpha||data.policy.experimentalDormLogic||!op.workshop)&&!op.room.startsWith('dorm')&&op.mood>=0&&op.mood<op.upperLimit&&op.currentMood(data.nowMicros)<op.upperLimit).map(op=>op.group))
 const hasAnchor=data.dorms.some(b=>{const op=data.operators[b.name];return !!op&&data.effectiveFreeSlot(b)&&op.isHigh()&&(data.alpha?!data.canStandby(op)&&!data.restMoodComplete(op.name):op.restingPriority==='high')})
 return new Set(names.filter(n=>{const op=data.operators[n]!;return data.canStandby(op)&&(anchors.has(op.group)||op.independentRest&&op.groupBindings.some(binding=>!!binding.group&&anchors.has(binding.group))||!op.group&&hasAnchor)}))
}
/** Alpha group admission follows Operators.assign_dorm_group at Mower
 * 617aef56f233381426107087437262fb6a802287: keep the ordered greedy choices;
 * a required member without a bed rejects the whole reservation atomically. */
export function mowerAssignDormGroup(data:MowerSchedulingData,names:string[],activeGroups?:Set<string>,departingNames?:ReadonlySet<string>,plan:MowerTaskPlan={},reservedSlots:ReadonlySet<string>=new Set()):MowerDormState[]|undefined {
 defaultOnly(data)
 const required=names.filter(n=>!data.restMoodComplete(n)||data.freeRoomExcluded(n)),optional=new Set([...mowerStandbyCandidates(data,names)].filter(n=>!data.freeRoomExcluded(n)))
 const ordered=[...required].sort((a,b)=>{
  if(data.alpha)return Number(optional.has(a))-Number(optional.has(b))||Number(alphaFullDynamicCandidate(data,a))-Number(alphaFullDynamicCandidate(data,b))||compareAlphaKeys(alphaRestingKey(data,a),alphaRestingKey(data,b))
  const x=data.operators[a]!,y=data.operators[b]!
  return Number(x.restingPriority==='standby')-Number(y.restingPriority==='standby')||Number(x.restingPriority==='high')-Number(y.restingPriority==='high')
 })
 const pending=structuredClone(plan)
 const used=new Set<number>(),assignments:{name:string;index:number}[]=[]
 for(const name of ordered){
  const index=data.alpha?alphaFindDormSlot(data,name,used,activeGroups,pending,reservedSlots):mowerFindDormSlot(data,name,used,true,departingNames)
  if(index===undefined){if(optional.has(name))continue;return undefined}
  used.add(index);assignments.push({name,index})
  const [room,position]=data.dorms[index]!.position
  ;(pending[room]??=Array(data.plan[room]!.length).fill('Current'))[position]=name
 }
 return assignments.map(({name,index})=>{const bed=data.dorms[index]!;bed.name=name;bed.timeMicros=undefined;return bed})
}
export function mowerAssignDorm(data:MowerSchedulingData,name:string,used=new Set<number>()):MowerDormState|undefined {
 const index=mowerFindDormSlot(data,name,used);if(index===undefined)return undefined
 used.add(index);const bed=data.dorms[index]!;bed.name=name;bed.timeMicros=undefined;return bed
}
export function mowerAverageMood(data:MowerSchedulingData):number {
 let current=0,total=0
 for(const op of Object.values(data.operators)){
  if(op.isResting()||op.group&&op.room.startsWith('dorm')||!op.isHigh()||op.workaholic||op.group&&data.canStandby(op)||data.isStandby(op.name))continue
  current+=op.currentMood(data.nowMicros)-op.lowerLimit;total+=op.upperLimit-op.lowerLimit
 }
 return total?current/total:0
}
