import { scoreProduction, type CompletedProduction, type ProductionScore } from '../domain/productionScore'
import type { ScheduleSimulationReport } from './scheduleSimulation'
import { virtualGoldEquivalent } from '../rules/orderValue'

/** Potential output values completed orders; settled output values paid orders. */
export function simulationOutputOrders(report:ScheduleSimulationReport) {
 const type=report.production?.assumptions.outputMode==='potential'?'order-completed':'order-collected'
 return (report.production?.events??[]).filter(e=>e.type===type&&e.time>report.assumptions.warmupHours&&e.time<=report.elapsedHours&&e.order&&(type==='order-completed'||e.order.completedAt>report.assumptions.warmupHours)).map(e=>e.order!)
}

/** Sample-window quantities shared by scores and the calculation summary. */
export function simulationOutputAmounts(report:ScheduleSimulationReport):CompletedProduction {
 const p=report.production
 if(!p?.success||!report.success||report.observedHours<=0)throw new Error('模拟未完成，无法评分')
 if(p.assumptions.expectationMode&&p.expected)return {...p.expected.output}
 const orders=simulationOutputOrders(report)
 const virtualGold=orders.reduce((n,order)=>n+virtualGoldEquivalent(order),0)
 if(p.assumptions.outputMode!=='potential') {
  const received=p.sample.inflows,excluded=p.sample.warmupReceipts??{}
  const receipts:Record<string,number>={},receiptCounts:Record<string,number>={}
  const externalKinds=new Set<string>(),openingReceipts=new Set<string>()
  for(const event of p.events??[]){
   if(event.time<report.assumptions.warmupHours||event.time>report.elapsedHours)continue
   for(const [kind,value] of Object.entries(event.delta??{}))if(value>0){
    if(event.type==='external-material'){if(event.time>report.assumptions.warmupHours)externalKinds.add(kind)}
    else if(event.time===report.assumptions.warmupHours)openingReceipts.add(kind)
    else {receipts[kind]=(receipts[kind]??0)+value;receiptCounts[kind]=(receiptCounts[kind]??0)+1}
   }
  }
  const operations=Math.max(1,p.events?.length??0,p.ledger?.entries.length??0)
  const amount=(kind:'exp'|'gold'|'lmd'|'fragment'|'orundum')=>{
   // Opening-clock transactions require the saved snapshot's ordering, not timestamp inference.
   const direct=externalKinds.has(kind)&&!openingReceipts.has(kind)
   const incoming=direct?receipts[kind]??0:received[kind]??0,warmup=excluded[kind]??0,external=direct?0:p.sample.external?.[kind]??0
   const value=incoming-warmup-external
   // Keep external flows out of the receipt sum; legacy counters retain scale-aware negative roundoff only.
   const scale=Math.max(Math.abs(incoming),Math.abs(warmup),Math.abs(external))
   const accumulationError=4*Number.EPSILON*Math.max(1,direct?receiptCounts[kind]??0:operations)*scale
   const error=direct?accumulationError:Math.max(accumulationError,1e-8*Math.min(1,scale))
   return value<0&&-value<=error?0:value
  }
  return {exp:amount('exp'),gold:amount('gold'),orderLmd:amount('lmd'),
   fragments:amount('fragment'),orundum:amount('orundum'),virtualGold}
 }
 // Completed items include potential output that has not yet been collected.
 const orundum=orders.reduce((n,order)=>n+(order.orundumReward??0),0)
 return {...p.sample.completed,virtualGold,orundum}
}

/** Score the selected output mode without counting initial inventory as income. */
export function scoreSimulationProduction(report:ScheduleSimulationReport):ProductionScore {
 return scoreProduction(simulationOutputAmounts(report),report.observedHours,report.inputs.options.productionWeights)
}
