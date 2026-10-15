import {describe,it,expect} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from '../scheduler/scheduleAdapter'
import {createRosterRuntime,advanceRoster,type RuntimeRates} from '../scheduler/rosterRuntime'
import {projectScheduleState} from './scheduleSimulation'
import {evaluateOperators} from '../engine/operatorRules'
import {createProductionTimeline,type ProductionFrame} from './productionTimeline'
import {createMowerProductionIO} from './mowerNativeProductionIO'

const targetRoom='room_2_1'
function fixture(stock:number,reserve:number,runOrder=true,initialSelection?:number|'max'){
 const ws=createDefaultWorkspace()
 for(const room of Object.values(ws.mainPlan.facilities))room.slots=[]
 ws.mainPlan.facilities[targetRoom].product='exp'
 ws.mainPlan.facilities[targetRoom].slots=[{occupant:{kind:'operator',operatorId:'芬'},groupId:null,replacements:[]}]
 if(runOrder)ws.mainPlan.facilities.room_3_1.slots=[{occupant:{kind:'operator',operatorId:'砾'},groupId:null,replacements:['但书']}]
 const schedule=compileRosterSchedule(ws),state=createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
 state.config.mowerDroneCountLimit=reserve
 if(initialSelection!==undefined)state.config.mowerDeviceObservations={initialManufactureDroneSelection:initialSelection}
 const frame=():ProductionFrame=>{
  const config=projectScheduleState(schedule,state),active=new Set(Object.keys(state.morale)),morale=new Map(Object.entries(state.morale))
  return {time:state.time,config,active,morale,evaluations:Object.fromEntries(config.rooms.map(room=>[room.id,evaluateOperators(room,config,active,morale)]))}
 }
 const production=createProductionTimeline(schedule,state,{outputMode:'potential',droneTarget:'none',initialResources:{drone:stock}},0,()=>{},true)
 production.settle(frame)
 const rates:RuntimeRates={workRate:()=>1,recoveryRate:()=>2,...createMowerProductionIO(state,production,frame)}
 let naturalBaseMinutes=0
 function advance(hours:number){
  // Production advances to the next completion before opening the following batch.
  // A whole-hour jump would discard work after a batch boundary in this fixture.
  let remaining=hours,steps=0
  while(remaining>1e-12){
   if(++steps>1000)throw new Error('Production advance did not terminate')
   const duration=production.nextStep(remaining,frame)
   if(duration<=0)throw new Error('Production advance made no progress')
   const current=frame()
   naturalBaseMinutes+=duration*60*current.evaluations[targetRoom]!.efficiencyPercent/100
   production.advance(duration,current)
   advanceRoster(state,duration,rates)
   production.settle(frame)
   remaining-=duration
  }
 }
 function accelerate(){
  const work=rates.mowerTodoTaskIO!({kind:'drone',room:targetRoom},state)
  if(!('next' in work))throw new Error('Expected nested native drone continuation')
  let next=work.next(),steps=0
  while(!next.done){
   if(++steps>1000)throw new Error('Native drone did not terminate')
   const hours=next.value.delayMicros/3_600_000_000
   if(hours>0)advance(hours)
   next=work.next()
  }
 }
 return {production,advance,accelerate,naturalBaseMinutes:()=>naturalBaseMinutes}
}
function assertAccounting(test:ReturnType<typeof fixture>,spent:number,debits:number){
 const report=test.production.report()
 expect(report.drones.consumed).toBe(spent)
 expect(report.ledger.outflows.drone??0).toBe(spent)
 expect(report.ledger.entries.filter(entry=>entry.delta.drone!==undefined&&entry.delta.drone<0)).toHaveLength(debits)
 expect(report.events.filter(event=>event.type==='native-manufacture-drone'&&event.amount!==undefined)).toHaveLength(debits)
 expect(report.drones.stock).toBeCloseTo(report.drones.initial+report.drones.generated-report.drones.overflow-spent,8)
 expect(report.ledger.balances.drone).toBeCloseTo(report.drones.stock,8)
 // One drone advances three base minutes; one medium record takes 180.
 // Confirmation completes products without collecting them into the inventory.
 const work=test.naturalBaseMinutes()+spent*3
 const completed=Math.floor(work/180)
 const room=report.manufacturing.find(item=>item.roomId===targetRoom)!
 expect(room.completedItems).toBe(completed)
 expect(room.pendingItems).toBe(completed)
 expect(report.sample.completed.exp).toBe(report.manufacturing.filter(item=>item.product==='exp').reduce((sum,item)=>sum+item.completedItems*1000,0))
 expect(room.remainingBaseMinutes).toBeCloseTo(180-(work%180),7)
 expect(report.ledger.inflows.exp??0).toBe(0)
}

describe('native manufacture drone reserve',()=>{
 it.each([
  {stock:250,reserve:20,spent:230},
  {stock:20,reserve:20,spent:0},
  {stock:19,reserve:20,spent:0},
  {stock:250,reserve:0,spent:250},
 ])('spends $spent from $stock with a $reserve reserve and a run-order room',({stock,reserve,spent})=>{
  const test=fixture(stock,reserve)
  test.accelerate()
  assertAccounting(test,spent,spent>0?1:0)
  const remaining=test.production.report().drones.stock
  expect(remaining).toBeGreaterThanOrEqual(Math.min(stock,reserve))
  expect(remaining).toBeLessThan(Math.min(stock,reserve)+1)
 })
 it('uses all available drones without a run-order room',()=>{
  const test=fixture(250,20,false)
  test.accelerate()
  assertAccounting(test,250,1)
 })
 it.each([0,120,'max'] as const)('selects the maximum before reserving, regardless of initial selection %s',initial=>{
  const test=fixture(150,100,true,initial)
  test.accelerate()
  assertAccounting(test,50,1)
  expect(test.production.report().drones.stock).toBeGreaterThanOrEqual(100)
  expect(test.production.report().drones.stock).toBeLessThan(101)
 })
 it('spends only replenished surplus on later visits and debits once per visit',()=>{
  const test=fixture(250,20)
  test.accelerate()
  assertAccounting(test,230,1)
  let totalSpent=230
  for(let visit=2;visit<=4;visit+=1){
   test.advance(1)
   const before=test.production.report().drones.stock
   // The fixture stays away from an integer boundary during UI time.
   expect(before%1).toBeLessThan(.9)
   const available=Math.floor(before)-20
   expect(available).toBeGreaterThan(0)
   test.accelerate()
   totalSpent+=available
   assertAccounting(test,totalSpent,visit)
   const remaining=test.production.report().drones.stock
   expect(remaining).toBeGreaterThanOrEqual(20)
   expect(remaining).toBeLessThan(21)
  }
 })
})
