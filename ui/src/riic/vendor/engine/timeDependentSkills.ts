import type { QualityRule } from '../domain/types'
import { operatorFor, type OperatorContext } from '../domain/operatorContext'
/** Continuous/hourly are explicit modelling choices: tooltips do not establish sub-hour ticks. */
export interface TimeContext { workHoursByOperator: ReadonlyMap<string, number>; warmupModel?: 'continuous' | 'hourly' }
const CURVES: Record<string, readonly [number,number,number]> = {
 'manu_prod_spd_addition[100]':[0,2,20],
 'manu_prod_spd_addition[030]':[20,1,25], 'manu_prod_spd_addition[031]':[20,1,25],
 'manu_prod_spd_addition[040]':[15,2,25], 'manu_prod_spd_addition[041]':[15,2,25],
 'power_rec_spd&addition[000]':[10,1,15], 'power_rec_spd&addition[001]':[15,1,20],
 'meet_spd_hast[000]':[20,2,30],
}
export function temporalSkillBonus(buffId:string, operatorId:string, context?:TimeContext):number|null {
 if (!context) return null
 const value=context.workHoursByOperator.get(operatorId)
 if(value===undefined || !Number.isFinite(value) || value<0) return null
 if(buffId==='manu_prod_cost_min[001]') return value>=12?10:0
 const curve=CURVES[buffId]; if(!curve)return null
 const [initial,slope,cap]=curve
 const hours=context.warmupModel==='hourly'?Math.floor(value):value
 return Math.min(cap,initial+slope*hours)
}
export function getTemporalSkillBoundaries(operatorId:string,context:OperatorContext={}):number[] {
 const events=new Set<number>()
 for(let hour=1;hour<=qualitySkillWarmupHours(operatorId,context);hour++)events.add(hour)
 for(const skill of operatorFor(context,operatorId)?.skills??[]) {
  if(skill.buffId==='manu_prod_cost_min[001]')events.add(12)
  const curve=CURVES[skill.buffId]
  if(curve)for(let hour=1;hour<=(curve[2]-curve[0])/curve[1];hour++)events.add(hour)
 }
 return [...events].sort((a,b)=>a-b)
}

/** PRTS verifies peak probabilities after 3/5 hours, not the intermediate curve. */
export function qualitySkillWarmupHours(operatorId:string,context:OperatorContext={}):number {
 const names=(operatorFor(context,operatorId)?.skills??[]).map(skill=>skill.name)
 if(names.some(name=>/裁缝·β|手工艺品·β|鉴定师的手段/.test(name)))return 5
 if(names.some(name=>/裁缝·α|手工艺品·α|鉴定师的眼光|懂行|千金的眼光/.test(name)))return 3
 return 0
}
/** Linear approximation; keep the strongest current effect without inventing stacking. */
export function temporalTradeQuality(ids:readonly string[],fallback:QualityRule,operators:OperatorContext,time?:TimeContext,level=3):{quality:QualityRule;qualityWarmup:number} {
 let quality:QualityRule='normal',qualityWarmup=1,best=-1
 for(const id of ids){
  const cap=qualitySkillWarmupHours(id,operators)
  if(!cap)continue
  const progress=time?Math.max(0,Math.min(1,(time.workHoursByOperator.get(id)??0)/cap)):1
  const strength=((cap===5?.85:.55)-(level===3?.2:0))*progress
  if(strength>best){best=strength;quality=cap===5?'beta':'alpha';qualityWarmup=progress}
 }
 return best<0?{quality:fallback,qualityWarmup:1}:{quality,qualityWarmup}
}
