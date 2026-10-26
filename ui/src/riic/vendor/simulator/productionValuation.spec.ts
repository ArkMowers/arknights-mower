import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from '../scheduler/scheduleAdapter'
import {createRosterRuntime} from '../scheduler/rosterRuntime'
import {projectScheduleState,simulateSchedule} from './scheduleSimulation'
import {createProductionTimeline,type ProductionFrame} from './productionTimeline'
import {evaluateOperators} from '../engine/operatorRules'
import {compileOperatorInventory} from '../domain/operatorInventory'
import {inventoryOperatorRecords} from '../domain/operatorContext'
import {scoreProduction,scoreProductionAdjustment} from '../domain/productionScore'
import {scoreSimulationProduction,simulationOutputAmounts} from './productionScore'
import {mowerReportMetrics} from '../workbench/mowerReportMetrics'
import {simulationReportToCalculationReport} from '../workbench/calculationBridge'

function workspace(product:'exp'|'gold'|'fragment'|'money'|'orundum',tequila=false){
 const ws=createDefaultWorkspace()
 for(const room of Object.values(ws.mainPlan.facilities)){room.level=0;room.slots=[]}
 const room=ws.mainPlan.facilities[product==='money'||product==='orundum'?'room_3_1':'room_1_1']
 room.level=product==='money'&&!tequila?1:3;room.product=product
 if(tequila)room.slots=[{occupant:{kind:'operator',operatorId:'char_486_takila'},groupId:null,replacements:[]}]
 return ws
}
function controller(product:Parameters<typeof workspace>[0],warmup=0,tequila=false,drone=0){
 const ws=workspace(product,tequila),schedule=compileRosterSchedule(ws,{idleOperators:[]}),state=createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
 let records=tequila?inventoryOperatorRecords(compileOperatorInventory([{operator:'龙舌兰',elitePhase:0,level:1}])):undefined
 const frame=():ProductionFrame=>{const config=projectScheduleState(schedule,state),active=new Set(Object.keys(state.morale)),morale=new Map(Object.entries(state.morale));config.operatorRecords=records;return {time:state.time,config,active,morale,evaluations:Object.fromEntries(config.rooms.map(room=>[room.id,{...evaluateOperators(room,config,active,morale),efficiencyPercent:100}]))}}
 const production=createProductionTimeline(schedule,state,{outputMode:'settled',inventoryMode:'finite',seed:1,droneTarget:'none',initialResources:{gold:10,drone}},warmup,()=>{},true)
 production.settle(frame)
 const advance=(hours:number,settle=true)=>{production.advance(hours,frame());state.time+=hours;if(settle)production.settle(frame)}
 return {production,frame,advance,state,removeSkills:()=>{records=inventoryOperatorRecords(compileOperatorInventory([{operator:'龙舌兰',elitePhase:0,level:1}]))!;records.char_486_takila={...records.char_486_takila!,skills:[]}}}
}
const options={droneTarget:'none' as const,outputMode:'settled' as const,inventoryMode:'finite' as const,allowGoldDebt:false}
describe('sample-boundary work in progress valuation',()=>{
 it.each(['settled','potential'] as const)('counts half a manufacturing batch in %s scores without collecting it',outputMode=>{
  const ws=workspace('exp'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:1.5,production:{...options,outputMode}})
  const p=report.production!,summary=simulationReportToCalculationReport(ws,report).summary!
  expect(p.sample.inflows.exp??0).toBe(0)
  expect(p.sample.completed.exp).toBe(0)
  expect(p.valuation!.closing.amounts.exp).toBeCloseTo(500,8)
  expect(p.valuation!.closing.manufacturing).toMatchObject([{product:'exp',progress:.5,quantity:.5}])
  expect(summary.exp).toBe(0)
  expect(mowerReportMetrics(report)).toMatchObject({exp:0,goldValue:0,orderLmd:0,mower82:8000})
  expect(summary.totalScore82).toBeCloseTo(8000,8)
  expect(summary.valuation).toMatchObject({completedScore:{daily:0,total:0},adjustment:{score:{daily:8000,total:500}}})
  expect(p.events.some(e=>e.type.startsWith('collect-manufacture'))).toBe(false)
 })
 it('values drone base work even when no wall-clock time elapses',()=>{
  const test=controller('gold',0,false,12)
  test.production.nativeSpendManufacturingDrones('room_1_1',12)
  test.production.finalize(test.frame())
  expect(test.state.time).toBe(0)
  expect(test.production.report().valuation!.closing.amounts.gold).toBeCloseTo(.5,8)
  expect(test.production.report().sample.inflows.gold??0).toBe(0)
  expect(test.production.report().drones.consumed).toBe(12)
 })
 it('subtracts the opening three-quarter batch after sampling completes it',()=>{
  const ws=workspace('exp'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{warmupHours:2.25,sampleHours:.75,production:options})
  expect(report.production!.sample.inflows.exp).toBe(1000)
  expect(report.production!.valuation!.opening.amounts.exp).toBeCloseTo(750,8)
  expect(report.production!.valuation!.closing.amounts.exp).toBe(0)
  expect(report.production!.valuation!.adjustment.exp).toBeCloseTo(-750,8)
  expect(scoreSimulationProduction(report).valuationAdjustment!.total).toBeCloseTo(-24000,8)
  expect(scoreSimulationProduction(report).total).toBeCloseTo(8000,8)
 })
 it('excludes unstarted unfunded manufacturing and values only the current authorized batch',()=>{
  const ws=workspace('fragment'),schedule=compileRosterSchedule(ws,{idleOperators:[]})
  const unfunded=simulateSchedule(schedule,{sampleHours:.5,production:options})
  expect(unfunded.production!.valuation!.closing.manufacturing).toEqual([])
  const funded=simulateSchedule(schedule,{sampleHours:.5,production:{...options,initialResources:{lmd:1600,orirock:2}},productionWeights:{fragments:10}})
  expect(funded.production!.valuation!.closing.amounts.fragments).toBeCloseTo(.5,8)
  expect(funded.production!.sample.outflows.lmd).toBe(1600)
  expect(funded.production!.sample.inflows.fragment??0).toBe(0)
  expect(scoreSimulationProduction(funded).weightedFragments).toBeCloseTo(240,8)
 })
 it('estimates a half order without spending gold or creating an order completion',()=>{
  const ws=workspace('money'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:1.2,production:options})
  expect(report.production!.valuation!.closing.amounts.orderLmd).toBeCloseTo(500,8)
  expect(report.production!.sample.inflows.lmd??0).toBe(0)
  expect(report.production!.sample.outflows.gold??0).toBe(0)
  expect(report.production!.events.filter(e=>e.type==='order-started')).toHaveLength(1)
  expect(report.production!.events.some(e=>e.type==='order-completed'||e.type==='order-collected')).toBe(false)
 })
 it('quotes unlocked boundary skills and their premium without physical or random side effects',()=>{
  const test=controller('money',0,true)
  test.advance(2.3,false)
  const before=structuredClone(test.production.report())
  test.production.finalize(test.frame())
  const after=test.production.report(),quoted=after.valuation!.closing
  expect(quoted.trading).toMatchObject([{kind:'tequila',goldCost:4,lmdReward:2250}])
  expect(quoted.amounts.orderLmd).toBeCloseTo(1125,8)
  expect(quoted.amounts.virtualGold).toBeCloseTo(.25,8)
  expect(after.events).toEqual(before.events)
  expect(after.ledger).toEqual(before.ledger)
  expect(after.trading).toEqual(before.trading)
  expect(after.drones).toEqual(before.drones)
  test.production.finalize(test.frame())
  expect(test.production.report()).toEqual(after)
 })
 it('preserves a negative boundary revaluation when a skill disappears',()=>{
  const test=controller('money',2.3,true)
  test.advance(2.3)
  test.removeSkills()
  test.production.finalize(test.frame())
  const v=test.production.report().valuation!
  expect(v.opening.amounts.orderLmd).toBeCloseTo(1125,8)
  expect(v.closing.amounts.orderLmd).toBeCloseTo(1000,8)
  expect(v.adjustment.orderLmd).toBeCloseTo(-125,8)
  expect(v.adjustment.virtualGold).toBeCloseTo(-.25,8)
  expect(scoreProductionAdjustment(v.adjustment,1).total).toBeCloseTo(-3000,8)
 })
 it('keeps pre-warmup completed records in physical receipts while excluding their income attribution',()=>{
  const test=controller('exp',4)
  test.advance(3);test.advance(1)
  test.advance(.5,false);test.production.finalize(test.frame())
  const p=test.production.report()
  expect(p.sample.inflows.exp).toBe(1000)
  expect(p.sample.net.exp).toBe(1000)
  expect(p.ledger.balances.exp).toBe(1000)
  expect(p.sample.warmupReceipts!.exp).toBe(1000)
  expect(p.valuation!.adjustment.exp).toBeCloseTo(1000/6,8)
 })
 it('keeps delayed warmup order payments in the ledger and excludes them from income and premiums',()=>{
  const test=controller('money',3)
  test.advance(2.4);test.advance(.6)
  test.advance(.5,false);test.production.finalize(test.frame())
  const p=test.production.report()
  expect(p.sample.inflows.lmd).toBe(1000)
  expect(p.sample.net.lmd).toBe(1000)
  expect(p.sample.warmupReceipts!.lmd).toBe(1000)
  const ws=workspace('money'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:.1,production:options})
  report.production=p;report.assumptions.warmupHours=3;report.elapsedHours=3.5;report.observedHours=.5
  expect(simulationOutputAmounts(report).orderLmd).toBe(0)
 })
 it('excludes a delayed warmup special-order premium from sampled receipts',()=>{
  const test=controller('money',5,true)
  test.advance(4.6);test.advance(.4);test.advance(.1,false);test.production.finalize(test.frame())
  const p=test.production.report()
  expect(p.sample.inflows.lmd).toBe(2250)
  expect(p.sample.warmupReceipts!.lmd).toBe(2250)
  const ws=workspace('money'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:.1,production:options})
  report.production=p;report.assumptions.warmupHours=5;report.elapsedHours=5.1;report.observedHours=.1
  expect(simulationOutputAmounts(report)).toMatchObject({orderLmd:0,virtualGold:0})
 })
 it('values unfinished orundum proportionally without consuming fragments',()=>{
  const ws=workspace('orundum'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:1,production:options,productionWeights:{orundum:2}})
  expect(report.production!.valuation!.closing.amounts.orundum).toBeCloseTo(10,8)
  expect(report.production!.sample.outflows.fragment??0).toBe(0)
  expect(scoreSimulationProduction(report).total).toBeCloseTo(480,8)
 })
 it('keeps completed output validation nonnegative and refuses failed simulation scoring',()=>{
  expect(()=>scoreProduction({exp:-1,gold:0,orderLmd:0},1)).toThrow()
  const ws=workspace('exp'),report=simulateSchedule(compileRosterSchedule(ws,{idleOperators:[]}),{sampleHours:10,maxEvents:1,production:options})
  expect(report.success).toBe(false)
  expect(report.production!.valuation).toBeUndefined()
  expect(()=>scoreSimulationProduction(report)).toThrow()
 })
})
