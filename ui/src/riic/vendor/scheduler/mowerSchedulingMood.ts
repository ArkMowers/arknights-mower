import type {MowerSchedulingData} from './mowerSchedulingData'
import {hasRestingMood,restingMood} from './mowerOperatorState'
import {toMowerMicros} from './mowerTaskQueue'

/** Newest valid room or card observation; card estimates never write measured state. */
export function mowerSchedulingMoodObservation(data:MowerSchedulingData,name:string):[number,number]|undefined {
 const op=data.operators[name],now=data.nowMicros
 const measured=op&&hasRestingMood(op,now)&&!op.moodIsPrediction&&Number.isFinite(op.timeStampMicros)&&op.timeStampMicros!<=now
 const estimate=data.dormMoodEstimates.get(name),elapsed=estimate?now-estimate[1]:-1
 if(estimate&&Number.isFinite(estimate[0])&&estimate[0]>=0&&estimate[0]<=24&&elapsed>=0&&elapsed<toMowerMicros(1)&&(!measured||estimate[1]>op.timeStampMicros!))return [estimate[0],estimate[1]]
 return measured?[op.isResting()?op.mood:restingMood(op,now),op.timeStampMicros!]:undefined
}

export const mowerDormCandidateMood=(data:MowerSchedulingData,name:string)=>mowerSchedulingMoodObservation(data,name)?.[0]
