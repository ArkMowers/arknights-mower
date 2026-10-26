import { normalizeProductionWeights, type ProductionWeights } from './productionWeights'

export interface ProductionScore {exp:number;goldValue:number;orderValue:number;weightedExp:number;weightedGold:number;weightedOrders:number;weightedFragments:number;weightedOrundum:number;total:number}
export interface CompletedProduction {exp:number;gold:number;orderLmd:number;virtualGold?:number;fragments?:number;orundum?:number}
/** User-defined conventional output, distinct from inventory value or cash settlement. */
export function scoreProduction(completed:CompletedProduction,hours:number,weights?:Partial<ProductionWeights>):ProductionScore {
 if(!Number.isFinite(hours)||hours<=0||Object.values(completed).some(v=>!Number.isFinite(v)||v<0))throw new Error('无效的完成产出或采样时长')
 const exp=completed.exp*24/hours,goldValue=completed.gold*500*24/hours,orderValue=completed.orderLmd*24/hours
 const w=normalizeProductionWeights(weights),factor=24/hours
 const weightedExp=w.exp*exp,weightedGold=w.gold*(goldValue+(completed.virtualGold??0)*500*factor),weightedOrders=w.orders*orderValue
 const weightedFragments=w.fragments*(completed.fragments??0)*factor,weightedOrundum=w.orundum*(completed.orundum??0)*factor
 const total=weightedExp+weightedGold+weightedOrders+weightedFragments+weightedOrundum
 if(!Number.isFinite(total))throw new Error('加权产出超出有效数值范围')
 return {exp,goldValue,orderValue,weightedExp,weightedGold,weightedOrders,weightedFragments,weightedOrundum,total}
}
