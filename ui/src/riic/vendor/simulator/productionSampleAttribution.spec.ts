import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from '../scheduler/scheduleAdapter'
import {createRosterRuntime} from '../scheduler/rosterRuntime'
import {projectScheduleState,type ScheduleSimulationReport} from './scheduleSimulation'
import {createProductionTimeline,type ProductionFrame,type ProductionReport} from './productionTimeline'
import {evaluateOperators} from '../engine/operatorRules'
import {compileOperatorInventory} from '../domain/operatorInventory'
import {inventoryOperatorRecords} from '../domain/operatorContext'
import {scoreSimulationProduction,simulationOutputAmounts} from './productionScore'

function workspace(product:'exp'|'gold'|'fragment'|'money'|'orundum',tequila=false){
 const ws=createDefaultWorkspace()
 for(const room of Object.values(ws.mainPlan.facilities)){room.level=0;room.slots=[]}
 const room=ws.mainPlan.facilities[product==='money'||product==='orundum'?'room_3_1':'room_1_1']
 room.level=product==='money'&&!tequila?1:3;room.product=product
 if(tequila)room.slots=[{occupant:{kind:'operator',operatorId:'char_486_takila'},groupId:null,replacements:[]}]
 return ws
}
function controller(product:Parameters<typeof workspace>[0],warmup=0,tequila=false){
 const ws=workspace(product,tequila),schedule=compileRosterSchedule(ws,{idleOperators:[]}),state=createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
 const records=tequila?inventoryOperatorRecords(compileOperatorInventory([{operator:'龙舌兰',elitePhase:0,level:1}])):undefined
 const frame=():ProductionFrame=>{const config=projectScheduleState(schedule,state),active=new Set(Object.keys(state.morale)),morale=new Map(Object.entries(state.morale));config.operatorRecords=records;return {time:state.time,config,active,morale,evaluations:Object.fromEntries(config.rooms.map(room=>[room.id,{...evaluateOperators(room,config,active,morale),efficiencyPercent:100}]))}}
 const production=createProductionTimeline(schedule,state,{outputMode:'settled',inventoryMode:'finite',seed:1,droneTarget:'none',initialResources:{gold:10}},warmup,()=>{},true)
 production.settle(frame)
 const advance=(hours:number,settle=true)=>{production.advance(hours,frame());state.time+=hours;if(settle)production.settle(frame)}
 return {production,frame,advance,state}
}
function reportFor(production:ProductionReport,start:number,end:number){
 return {success:true,production,observedHours:end-start,elapsedHours:end,assumptions:{warmupHours:start},inputs:{options:{}}} as ScheduleSimulationReport
}
describe('sample income attribution for delayed warmup collections',()=>{
 it('keeps warmup records in physical receipts and excludes their income without valuing the unfinished batch',()=>{
  const test=controller('exp',4)
  test.advance(3);test.advance(1);test.advance(.5,false);test.production.finalize(test.frame())
  const p=test.production.report(),report=reportFor(p,4,4.5)
  expect(p.sample.inflows.exp).toBe(1000)
  expect(p.sample.net.exp).toBe(1000)
  expect(p.ledger.balances.exp).toBe(1000)
  expect(p.sample.warmupReceipts!.exp).toBe(1000)
  expect(simulationOutputAmounts(report).exp).toBe(0)
  expect(scoreSimulationProduction(report).total).toBe(0)
  expect(p).not.toHaveProperty('valuation')
 })
 it('keeps delayed warmup order payments in the ledger while excluding their sampled income',()=>{
  const test=controller('money',3)
  test.advance(2.4);test.advance(.6);test.advance(.5,false);test.production.finalize(test.frame())
  const p=test.production.report(),report=reportFor(p,3,3.5)
  expect(p.sample.inflows.lmd).toBe(1000)
  expect(p.sample.net.lmd).toBe(1000)
  expect(p.sample.outflows.gold).toBe(2)
  expect(p.ledger.balances.gold).toBe(8)
  expect(p.sample.warmupReceipts!.lmd).toBe(1000)
  expect(simulationOutputAmounts(report)).toMatchObject({orderLmd:0,virtualGold:0})
  expect(scoreSimulationProduction(report).total).toBe(0)
  expect(p.events.filter(e=>e.type==='order-collected')).toMatchObject([{time:3.5,order:{completedAt:2.4,lmdReward:1000}}])
 })
 it('also excludes the special-order premium belonging to a completed warmup order',()=>{
  const test=controller('money',5,true)
  test.advance(4.6);test.advance(.4);test.advance(.1,false);test.production.finalize(test.frame())
  const p=test.production.report(),report=reportFor(p,5,5.1)
  expect(p.sample.inflows.lmd).toBe(2250)
  expect(p.sample.net.lmd).toBe(2250)
  expect(p.sample.outflows.gold).toBe(4)
  expect(p.sample.warmupReceipts!.lmd).toBe(2250)
  expect(simulationOutputAmounts(report)).toMatchObject({orderLmd:0,virtualGold:0})
  expect(scoreSimulationProduction(report).total).toBe(0)
 })
})
