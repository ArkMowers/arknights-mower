// Mower b2d9ac8 PlanConfig and Operators.init_mood_limit (MIT).
import {hasRestingMood} from './mowerOperatorState'
import type {MowerSchedulingData} from './mowerSchedulingData'
import {roundMowerMicros} from './mowerTaskQueue'
export interface MowerMoodLimits {lower:number;upper:number}
export interface MowerMoodLimitConfig {all?:MowerMoodLimits;operators:Record<string,MowerMoodLimits>}
const record=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value)
export function readMowerMoodLimits(conf:Record<string,unknown>,resolve:(name:string)=>string):MowerMoodLimitConfig|undefined {
 if(conf.mood_limits==null&&conf.operator_mood_limits==null)return undefined
 const parse=(value:unknown):MowerMoodLimits=>{
  if(!record(value))throw new Error('mood limits must contain lower and upper')
  const number=(raw:unknown,fallback:number)=>raw===undefined?fallback:typeof raw==='number'||typeof raw==='boolean'||typeof raw==='string'&&/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw.trim())?Number(raw):NaN
  const lower=number(value.lower,0),upper=number(value.upper,24)
  if(!Number.isFinite(lower)||!Number.isFinite(upper)||lower<0||upper>24||lower>=upper)throw new Error('mood limits require 0 <= lower < upper <= 24')
  return {lower,upper}
 }
 const operators:Record<string,MowerMoodLimits>={}
 if(conf.operator_mood_limits!=null){if(!record(conf.operator_mood_limits))throw new Error('operator_mood_limits must be a mapping');for(const [name,value] of Object.entries(conf.operator_mood_limits))operators[resolve(name)]=parse(value)}
 return {...(conf.mood_limits==null?{}:{all:parse(conf.mood_limits)}),operators}
}
export function initializeMowerAlphaMoodLimits(data:MowerSchedulingData,mode:number,config:MowerMoodLimitConfig|undefined,previous:Record<string,number>={}):void {
 const ops=Object.values(data.operators),named=(name:string)=>ops.find(op=>op.nativeName===name)
 const planned=new Set(Object.values(data.plan).flat())
 for(const op of ops)for(const name of op.replacement)planned.add(name)
 const set=(name:string,lower=0,upper=24)=>{const op=data.operators[name];if(op&&planned.has(name)){op.lowerLimit=lower;op.upperLimit=upper}}
 const ling=()=>{
  const l=named('令'),x=named('夕')
  if(mode===1){if(l)set(l.name,0,12);if(x)set(x.name,12)}
  else if(mode===2){if(x)set(x.name,0,12);if(l)set(l.name,12)}
  else if(mode===0||mode===3){if(x)set(x.name);if(l)set(l.name)}
  const finished=new Set<string>()
  for(const op of [x,l])if(op&&!op.room.startsWith('dorm')&&op.group&&!finished.has(op.group)){
   for(const name of data.group(op.group)){const member=data.operators[name]!;if(!['令','夕'].includes(member.nativeName)&&!member.room.startsWith('dorm'))set(name,mode===1||mode===2?12:0)}
   finished.add(op.group)
  }
  for(const [name,limit] of Object.entries(config?.operators??{}))set(name,limit.lower,limit.upper)
 }
 for(const op of ops){op.lowerLimit=0;op.upperLimit=24;op.customMoodLimit=planned.has(op.name)&&!!(config?.operators[op.name]??config?.all);op.restMoodLimit=planned.has(op.name)&&(!!config?.operators[op.name]||op.nativeName===(mode===1?'令':mode===2?'夕':''))}
 ling()
 const totter=named('铅踝'),vermeil=named('红云')
 if(totter?.isHigh())set(totter.name,vermeil?.isHigh()&&vermeil.room===totter.room?8:20,vermeil?.isHigh()&&vermeil.room===totter.room?12:24)
 for(const op of ops){const limit=config?.operators[op.name]??config?.all;if(limit)set(op.name,limit.lower,limit.upper)}
 ling()
 for(const bed of data.dorms){
  const op=data.operators[bed.name];if(!op||bed.timeMicros===undefined)continue
  const old=previous[op.name]??op.upperLimit;if(old===op.upperLimit)continue
  if(!hasRestingMood(op,data.nowMicros)){bed.timeMicros=undefined;op.timeStampMicros=undefined}
  else if(op.mood>=op.upperLimit)bed.timeMicros=data.nowMicros
  else if(old>op.mood)bed.timeMicros=op.timeStampMicros!+roundMowerMicros((bed.timeMicros-op.timeStampMicros!)*(op.upperLimit-op.mood)/(old-op.mood))
  else {bed.timeMicros=undefined;op.timeStampMicros=undefined}
 }
}
