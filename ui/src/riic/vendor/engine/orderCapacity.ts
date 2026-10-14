import { operatorFor, hasOperatorSkill } from '../domain/operatorContext'
import type {AppConfig,OutputRoom} from '../domain/types'
import {type OperatorRecord} from '../domain/operators'
import {matchesRiicIdentity} from '../domain/riicIdentity'
import {evaluateHighestPhaseJaye,TRADING_BASE_ORDER_LIMIT} from './jayeRules'
import type {OperatorEfficiencyResult} from './operatorRules'
export interface TradeOrderCapacityResult {limit:number|null;unquantified:string[]}
/** Highest phase only. Live capacity never rewrites or deletes already captured orders. */
export function evaluateTradeOrderCapacity(room:OutputRoom,config:AppConfig,activeIds:ReadonlySet<string>,evaluation:Pick<OperatorEfficiencyResult,'operatorContributions'>):TradeOrderCapacityResult {
 if(room.type!=='trading'||![1,2,3].includes(room.level))throw new Error('Trading capacity requires a valid trading room')
 const operators=room.operatorIds.filter(id=>activeIds.has(id)).map(id=>operatorFor(config, id)).filter((op):op is OperatorRecord=>Boolean(op))
 const presentNames=new Set(room.operatorIds.map(id=>operatorFor(config, id)?.name))
 const control=new Set(config.controlOperatorIds.filter(id=>activeIds.has(id)).map(id=>operatorFor(config, id)?.name))
 const delta=(op:OperatorRecord)=>{
  let value=0
  for(const skill of op.skills.filter(s=>s.roomType==='TRADING')){
   if(['trade_ord_limit&trade&lv[000]','trade_ord_limit&trade&lv[001]'].includes(skill.buffId)){value+=room.level;continue}
   if(skill.buffId==='trade_ord_limit&cost_P[020]'){if(presentNames.has('伺夜'))value+=2;continue}
   if(skill.buffId==='trade_ord_limit&cost_P[001]'){if(presentNames.has('德克萨斯'))value+=4;continue}
   const direct=skill.description.match(/订单上限([+-])(\d+)/)
   if(direct)value+=Number(direct[2])*(direct[1]==='-'?-1:1)
  }
  if(control.has('灵知')&&hasOperatorSkill(config,'char_206_gnosis','control_tra_limit&spd[000]')&&matchesRiicIdentity(op,'nationId','kjerag'))value+=6
  if(control.has('维什戴尔')&&op.name==='赫德雷')value+=2
  return value
 }
 const jaye=operators.find(op=>op.skills.some(s=>s.buffId==='trade_ord_limit_diff[000]'))
 if(!jaye)return {limit:Math.max(1,TRADING_BASE_ORDER_LIMIT[room.level-1]!+operators.reduce((sum,op)=>sum+delta(op),0)),unquantified:[]}
 const snow=operators.find(op=>op.skills.some(s=>/^trade_ord_spd_variable2\[(000|001)\]$/.test(s.buffId)))
 const partners=operators.filter(op=>op!==jaye&&op!==snow)
 if(partners.some(op=>!evaluation.operatorContributions.some(c=>c.operatorId===op.charId)))return {limit:null,unquantified:['JAYE_PARTNER_CONTRIBUTION_MISSING']}
 const snowSkill=snow?.skills.find(s=>/^trade_ord_spd_variable2\[(000|001)\]$/.test(s.buffId))
 const hasCountSkill=jaye.skills.some(s=>s.buffId==='trade_ord_limit_count[000]')
 const isElite0=Boolean(config.jayeElite0||!hasCountSkill)
 const result=evaluateHighestPhaseJaye({roomLevel:room.level,hasBothJayeSkills:hasCountSkill&&!config.jayeElite0,isElite0,clearedByShamare:operators.some(op=>op.name==='巫恋'),snowsant:snow&&snowSkill?{operatorId:snow.charId,cap:snowSkill.buffId.endsWith('[001]')?35:25}:undefined,
   partners:partners.map(op=>{
    const contribution=evaluation.operatorContributions.find(c=>c.operatorId===op.charId)!
    const efficiency=contribution.skillBonus
    const orderLimitSkills=op.skills.filter(s=>['trade_ord_spd_variable[000]','trade_ord_spd_variable3[000]'].includes(s.buffId))
    const orderLimitDerivedEfficiency=orderLimitSkills.reduce((sum,skill)=>{
      const item=contribution.items.find(i=>i.name===op.name+'·'+skill.name||i.name===skill.name)
      return sum+(item?item.value:0)
    },0)
    return {operatorId:op.charId,efficiency,snowsantCopyableEfficiency:efficiency,orderLimitDelta:delta(op),dependsOnOrderLimit:orderLimitSkills.length>0,orderLimitDerivedEfficiency}
   })})
 if(!result.supported)return {limit:null,unquantified:[result.reason]}
 return result.effectiveOrderLimit===null?{limit:null,unquantified:['JAYE_SHAMARE_CAPACITY_UNVERIFIED']}:{limit:result.effectiveOrderLimit,unquantified:[]}
}
