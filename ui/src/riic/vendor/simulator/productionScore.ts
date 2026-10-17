import { scoreProduction, type CompletedProduction, type ProductionScore } from '../domain/productionScore'
import type { ScheduleSimulationReport } from './scheduleSimulation'
import { virtualGoldEquivalent } from '../rules/orderValue'

/** Potential output values completed orders; settled output values paid orders. */
export function simulationOutputOrders(report:ScheduleSimulationReport) {
 const type=report.production?.assumptions.outputMode==='potential'?'order-completed':'order-collected'
 return (report.production?.events??[]).filter(e=>e.type===type&&e.time>report.assumptions.warmupHours&&e.time<=report.elapsedHours&&e.order).map(e=>e.order!)
}

/** Sample-window quantities shared by scores and the calculation summary. */
export function simulationOutputAmounts(report:ScheduleSimulationReport):CompletedProduction {
 const p=report.production
 if(!p?.success||!report.success||report.observedHours<=0)throw new Error('模拟未完成，无法评分')
 const orders=simulationOutputOrders(report)
 const virtualGold=orders.reduce((n,order)=>n+virtualGoldEquivalent(order),0)
 if(p.assumptions.outputMode!=='potential') {
  const received=p.sample.inflows
  return {exp:received.exp??0,gold:received.gold??0,orderLmd:received.lmd??0,
   fragments:received.fragment??0,orundum:received.orundum??0,virtualGold}
 }
 // Completed items include potential output that has not yet been collected.
 const fragments=p.manufacturing.filter(r=>r.product==='fragment').reduce((n,r)=>n+r.sampleCompletedItems,0)
 const orundum=orders.reduce((n,order)=>n+(order.orundumReward??0),0)
 return {...p.sample.completed,virtualGold,fragments,orundum}
}

/** Score the selected output mode without counting initial inventory as income. */
export function scoreSimulationProduction(report:ScheduleSimulationReport):ProductionScore {
 return scoreProduction(simulationOutputAmounts(report),report.observedHours,report.inputs.options.productionWeights)
}
