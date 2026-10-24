import type {RuntimeRates,RuntimeState} from './rosterRuntime'
import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerOperatorState} from './mowerOperatorState'

export interface MowerPlanningWake {timeMicros:number;names:string[]}

/** Only a downward threshold crossing creates a wake. A blocked worker already
 * below the threshold waits for existing resource/roster tasks, without polling. */
function threshold(data:MowerSchedulingData,op:MowerOperatorState):number|undefined {
 if(!op.isHigh()||op.workaholic||op.isResting()||data.isStandby(op.name)||data.busyRestingNames.has(op.name)||!op.room||['dorm','factory','train'].some(room=>op.room.startsWith(room)))return
 if(op.exhaustRequire)return op.lowerLimit+2
 if(op.group&&data.group(op.group).some(name=>data.operators[name]!.exhaustRequire))return
 const limit=op.lowerLimit+(op.upperLimit-op.lowerLimit)*data.policy.restingThreshold
 return data.alpha&&op.customMoodLimit?limit:Math.min(Math.floor(limit),op.upperLimit-2)
}

/** Ideal production orders do not supply or suppress the roster's mood clock. */
export function nextMowerMoodPlanningWake(s:RuntimeState,data:MowerSchedulingData,rates:RuntimeRates):MowerPlanningWake|undefined {
 const rooms=new Map(Object.entries(s.occupants).map(([slot,name])=>[name,slot.slice(0,slot.lastIndexOf('_'))]))
 let result:MowerPlanningWake|undefined
 for(const op of Object.values(data.operators)){
  const room=rooms.get(op.name),limit=threshold(data,op),mood=s.morale[op.name]
  if(!room||room.startsWith('dorm')||room==='factory'||room==='train'||limit===undefined||mood===undefined||mood<=limit)continue
  const rate=rates.workRate(op.name,room,s)
  if(!Number.isFinite(rate)||rate<=0)continue
  // Round the absolute physical deadline, so integration substeps do not rebase
  // the alarm onto a differently rounded scheduler clock.
  const timeMicros=Math.max(data.nowMicros+1,Math.ceil((s.time+(mood-limit)/rate)*3_600_000_000))
  if(!result||timeMicros<result.timeMicros)result={timeMicros,names:[op.name]}
  else if(timeMicros===result.timeMicros)result.names.push(op.name)
 }
 return result
}
