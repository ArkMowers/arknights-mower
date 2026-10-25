import type {AppConfig} from '../domain/types'
import {currentMoraleRates} from '../engine/morale'
import {evaluateDormitoryRecovery} from '../engine/dormitoryRecovery'
import {buildRiicGlobalContext} from '../engine/globalContext'

/** Forecast only. Positive recovery bonuses may disappear after a dormitory change. */
export function mowerCoordinationRates(config:AppConfig,atmospheres:readonly number[],overrides:{work?:Record<string,number>;recovery?:Record<string,number>}={}) {
 const snapshot=currentMoraleRates(config)
 const work:Record<string,number>=snapshot.unquantified.length?{}:{...snapshot.rates}
 const recovery:Record<string,number>={},morale=new Map(Object.entries(config.operatorMorale))
 const recoveryContext=config.facilities.dormitories.some(Boolean)?buildRiicGlobalContext(config,undefined,morale):undefined
 for(let index=0;index<config.facilities.dormitories.length;index++){
  const result=evaluateDormitoryRecovery(config,index,morale,atmospheres[index],undefined,true,recoveryContext)
  // An unselected single target is intentionally excluded from this lower bound.
  if(result.unquantified.some(message=>!message.includes('未指定单体恢复目标')))continue
  Object.assign(recovery,Object.fromEntries(result.rates))
 }
 Object.assign(work,overrides.work);Object.assign(recovery,overrides.recovery)
 return {work,recovery}
}
