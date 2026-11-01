import {afterEach,describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from '../scheduler/compileRosterSchedule'
import {simulateSchedule,type ScheduleSimulationOptions} from './scheduleSimulation'
import {scoreSimulationProduction} from './productionScore'
import {simulationReportToCalculationReport} from '../workbench/calculationBridge'
import * as productionTimeline from './productionTimeline'
import * as rosterRuntime from '../scheduler/rosterRuntime'
import {getMowerSourceRuntime} from '../scheduler/mowerSourceRuntime'
import {MowerTask,MOWER_TASK_TYPES} from '../scheduler/mowerTaskQueue'
import * as shiftCycle from '../scheduler/mowerShiftCycle'
import {MowerShiftPreviewError} from '../scheduler/mowerNativeErrors'

function fixture(product:'gold'|'exp'|'fragment'|'money'|'orundum'='gold',manufacture=false){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities)){room.level=0;room.slots=[]}
 const room=workspace.mainPlan.facilities[product==='money'||product==='orundum'?'room_3_1':'room_1_1']
 room.level=product==='money'?1:3;room.product=product
 if(manufacture){workspace.mainPlan.facilities.room_1_1.level=3;workspace.mainPlan.facilities.room_1_1.product='gold'}
 return workspace
}
const production={outputMode:'settled' as const,inventoryMode:'finite' as const,allowGoldDebt:false,droneTarget:'none' as const,initialResources:{gold:0,fragment:0,lmd:0,exp:0,orundum:0,orirock:0,device:0,drone:0}}
function run(product:Parameters<typeof fixture>[0],options:ScheduleSimulationOptions={},manufacture=false){
 const workspace=fixture(product,manufacture)
 return {workspace,report:simulateSchedule(compileRosterSchedule(workspace,{idleOperators:[]}),{sampleHours:2.4,recordSegments:true,...options,production:{...production,...options.production}})}
}
function captureController(){
 const create=productionTimeline.createProductionTimeline
 let controller:ReturnType<typeof create>|undefined
 let clock:Parameters<typeof create>[1]|undefined
 let beforeFinalization:{production:ReturnType<ReturnType<typeof create>['report']>;runtime:string}|undefined
 const runtimeSnapshot=()=>JSON.stringify({time:clock!.time,morale:clock!.morale,occupants:clock!.occupants,bedOccupants:clock!.bedOccupants,events:clock!.events})
 vi.spyOn(productionTimeline,'createProductionTimeline').mockImplementation((...args)=>{
  clock=args[1];controller=create(...args)
  const finalize=controller.finalize
  vi.spyOn(controller,'finalize').mockImplementation(frame=>{beforeFinalization={production:structuredClone(controller!.report()),runtime:runtimeSnapshot()};finalize(frame)})
  return controller
 })
 return {controller:()=>controller!,clock:()=>clock!,before:()=>beforeFinalization!,runtimeSnapshot}
}
afterEach(()=>vi.restoreAllMocks())
describe('sample endpoint production collection',()=>{
 it('collects stored manufacturing output through the ledger, score and calculation summary',()=>{
  const {workspace,report}=run('exp',{sampleHours:3.1,production:{initialResources:{exp:9000,lmd:7000}}})
  expect(report.success).toBe(true)
  const p=report.production!
  expect(p.manufacturing[0]).toMatchObject({completedItems:1,sampleCompletedItems:1,pendingItems:0})
  expect(p.sample.opening.exp).toBe(9000)
  expect(p.sample.closing.exp).toBe(10000)
  expect(p.sample.inflows.exp).toBe(1000)
  expect(p.sample.net.exp).toBe(1000)
  expect(p.sample.inflows.lmd).toBe(0)
  expect(p.events.filter(e=>e.type==='collect-manufacture:room_1_1')).toEqual([{time:3.1,type:'collect-manufacture:room_1_1',delta:{exp:1000}}])
  const daily=1000*24/3.1
  expect(scoreSimulationProduction(report).exp).toBeCloseTo(daily,8)
  expect(simulationReportToCalculationReport(workspace,report).summary!.exp).toBeCloseTo(daily,8)
  expect(report.elapsedHours).toBe(3.1)
  expect(report.segments.reduce((n,s)=>n+s.end-s.start,0)).toBeCloseTo(3.1,8)
 })
 it.each([[2.999,0],[3,1000],[3.001,1000]])('collects only completed records at %s hours', (sampleHours,expected)=>{
  const {report}=run('exp',{sampleHours})
  expect(report.success).toBe(true)
  expect(report.production!.sample.inflows.exp).toBe(expected)
  expect(report.production!.sample.completed.exp).toBe(expected)
  expect(report.production!.manufacturing[0]!.pendingItems).toBe(0)
  expect(report.production!.events.every(event=>event.time<=sampleHours)).toBe(true)
 })
 it('finishes and pays an order exactly at the endpoint without acquiring another order',()=>{
  const {report}=run('money',{production:{initialResources:{gold:2}}})
  const p=report.production!
  expect(report.success).toBe(true)
  expect(p.sample.completed.orderLmd).toBe(1000)
  expect(p.sample.inflows.lmd).toBe(1000)
  expect(p.sample.outflows.gold).toBe(2)
  expect(p.sample.closing.gold).toBe(0)
  expect(p.trading[0]).toMatchObject({completedOrders:1,collectedOrders:1,pendingOrders:[],remainingBaseMinutes:null})
  expect(p.events.filter(e=>e.type==='order-started')).toHaveLength(1)
  expect(p.events.filter(e=>e.type==='order-completed')).toMatchObject([{time:2.4,orderId:'room_3_1:1'}])
  expect(p.events.filter(e=>e.type==='order-collected')).toMatchObject([{time:2.4,orderId:'room_3_1:1'}])
  expect(scoreSimulationProduction(report).orderValue).toBe(10000)
 })
 it('collects previously completed orders while preserving the unfinished next order',()=>{
  const {report}=run('money',{sampleHours:2.5,production:{initialResources:{gold:2}}})
  const p=report.production!
  expect(report.success).toBe(true)
  expect(p.trading[0]).toMatchObject({completedOrders:1,collectedOrders:1,pendingOrders:[]})
  expect(p.trading[0]!.remainingBaseMinutes).toBeCloseTo(138,7)
  expect(p.events.filter(e=>e.type==='order-collected')).toMatchObject([{time:2.5}])
  expect(p.events.filter(e=>e.type==='order-completed')[0]!.time).toBeCloseTo(2.4,8)
  expect(p.sample.inflows.lmd).toBe(1000)
 })
 it('does not finish or pay an order whose production ends after the sampling endpoint',()=>{
  const {report}=run('money',{sampleHours:2.399,production:{initialResources:{gold:2}}})
  expect(report.success).toBe(true)
  expect(report.production!.trading[0]).toMatchObject({completedOrders:0,collectedOrders:0,pendingOrders:[]})
  expect(report.production!.sample.inflows.lmd).toBe(0)
  expect(report.production!.sample.closing.gold).toBe(2)
 })
 it('uses already completed manufacturing output to fund terminal order delivery',()=>{
  const {report}=run('money',{},true)
  const p=report.production!
  expect(report.success).toBe(true)
  expect(p.sample.inflows).toMatchObject({gold:2,lmd:1000})
  expect(p.sample.outflows.gold).toBe(2)
  expect(p.sample.closing.gold).toBe(0)
  const receipts=p.events.filter(e=>e.type.startsWith('collect-'))
  expect(receipts.map(e=>e.type)).toEqual(['collect-manufacture:room_1_1','collect-order:room_3_1:1'])
  expect(receipts.every(e=>e.time===2.4)).toBe(true)
 })
 it.each([0,1])('keeps a completed order pending with only %s gold and no debt',gold=>{
  const {report}=run('money',{production:{initialResources:{gold}}})
  expect(report.success).toBe(true)
  const p=report.production!
  expect(p.trading[0]).toMatchObject({completedOrders:1,collectedOrders:0})
  expect(p.trading[0]!.pendingOrders).toHaveLength(1)
  expect(p.sample.closing.gold).toBe(gold)
  expect(p.sample.inflows.lmd).toBe(0)
  expect(p.events.some(e=>e.type==='order-collected')).toBe(false)
  expect(scoreSimulationProduction(report).total).toBe(0)
 })
 it('preserves explicit gold debt while refusing to replace missing fragments',()=>{
  const {report:gold}=run('money',{production:{allowGoldDebt:true}})
  expect(gold.production!.sample.closing.gold).toBe(-2)
  expect(gold.production!.sample.inflows.lmd).toBe(1000)
  const {report:orundum}=run('orundum',{sampleHours:2,production:{allowGoldDebt:true,initialResources:{fragment:1}}})
  expect(orundum.success).toBe(true)
  expect(orundum.production!.trading[0]!.pendingOrders).toHaveLength(1)
  expect(orundum.production!.sample.closing.fragment).toBe(1)
  expect(orundum.production!.sample.inflows.orundum).toBe(0)
 })
 it('does not charge a new manufacturing batch at the sampling endpoint',()=>{
  const {report}=run('fragment',{sampleHours:1,production:{initialResources:{lmd:3200,orirock:4}}})
  const p=report.production!
  expect(report.success).toBe(true)
  expect(p.manufacturing[0]).toMatchObject({completedItems:1,pendingItems:0})
  expect(p.sample.inflows.fragment).toBe(1)
  expect(p.sample.closing).toMatchObject({lmd:1600,orirock:2,fragment:1})
  expect(p.events.filter(e=>e.type==='manufacture-start:room_1_1')).toEqual([{time:0,type:'manufacture-start:room_1_1',delta:{orirock:-2,lmd:-1600}}])
 })
 it('is idempotent and neither advances work nor spends drones nor changes the roster',()=>{
  const captured=captureController()
  const {report}=run('money',{production:{initialResources:{gold:2,drone:250}}})
  const controller=captured.controller(),state=captured.clock()
  expect(controller.finalize).toHaveBeenCalledOnce()
  expect(captured.runtimeSnapshot()).toBe(captured.before().runtime)
  expect(controller.report().drones).toEqual(captured.before().production.drones)
  expect(controller.report().manufacturing).toEqual(captured.before().production.manufacturing)
  expect(controller.report().events.filter(e=>e.type==='order-started')).toEqual(captured.before().production.events.filter(e=>e.type==='order-started'))
  const before=structuredClone(controller.report()),runtime=JSON.parse(JSON.stringify({time:state.time,morale:state.morale,occupants:state.occupants,events:state.events}))
  controller.finalize(vi.mocked(controller.finalize).mock.calls[0]![0])
  expect(controller.report()).toEqual(before)
  expect({time:state.time,morale:state.morale,occupants:state.occupants,events:state.events}).toEqual(runtime)
  expect(report.production!.drones.consumed).toBe(0)
  expect(report.production!.drones.stock).toBe(250)
 })
 it('leaves an arrangement due exactly at the horizon pending without changing occupants',()=>{
  const workspace=fixture('gold'),create=rosterRuntime.createRosterRuntime
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
  workspace.mainPlan.conf.workaholic=['char_123_fang','char_240_wyvern']
  let state:rosterRuntime.RuntimeState|undefined,task:MowerTask|undefined
  vi.spyOn(rosterRuntime,'createRosterRuntime').mockImplementation(config=>{
   state=create(config)
   const source=getMowerSourceRuntime(state);source.initial=false
   task=new MowerTask({time:2.4,type:MOWER_TASK_TYPES.NOT_SPECIFIC,plan:{room_1_1:['char_240_wyvern']}})
   source.queue.tasks=[task]
   return state
  })
  const schedule=compileRosterSchedule(workspace,{idleOperators:[]})
  const report=simulateSchedule(schedule,{sampleHours:2.4,production})
  expect(report.success).toBe(true)
  expect(state!.time).toBe(2.4)
  expect(state!.occupants.room_1_1_0).toBe('char_123_fang')
  expect(getMowerSourceRuntime(state!).queue.tasks).toContain(task)
  expect(report.events.some(event=>event.time===2.4)).toBe(false)

 })
 it('does not collect terminal output from an interrupted event budget',()=>{
  const captured=captureController()
  const {report}=run('gold',{sampleHours:2,maxEvents:8})
  expect(report.success).toBe(false)
  expect(report.elapsedHours).toBeLessThan(2)
  expect(report.production!.manufacturing[0]!.pendingItems).toBe(1)
  expect(report.production!.sample.inflows.gold).toBe(0)
  expect(captured.controller().finalize).not.toHaveBeenCalled()
 })
 it('does not collect at the horizon when an execution failure remains unresolved',()=>{
  const captured=captureController(),workspace=fixture('gold')
  workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
  workspace.mainPlan.conf.workaholic=['char_123_fang','char_240_wyvern']
  workspace.compatibility.backupPlans=[{name:'forced correction',trigger:'True',plan:{room_1_1:{plans:[{agent:'香草',group:'',replacement:['芬']}]}}}]
  vi.spyOn(shiftCycle,'prepareMowerShiftCycle').mockImplementation(()=>{throw new MowerShiftPreviewError('terminal collection failure fixture')})
  const report=simulateSchedule(compileRosterSchedule(workspace,{idleOperators:[]}),{schedulingModel:'mower-alpha',sampleHours:4,production,consumptionOverrides:{char_123_fang:5}})
  expect(report.elapsedHours).toBe(4)
  expect(report.success).toBe(false)
  expect(report.diagnostics.some(d=>d.code==='MOWER_PENDING_TASK_FAILURE')).toBe(true)
  expect(captured.controller().finalize).not.toHaveBeenCalled()
 })
 it('retains ordinary warmup accounting with continuous inventory and no initial-stock income',()=>{
  const {report}=run('exp',{warmupHours:1,sampleHours:2,production:{initialResources:{exp:9000}}})
  expect(report.success).toBe(true)
  expect(report.elapsedHours).toBe(3)
  expect(report.observedHours).toBe(2)
  expect(report.production!.sample.opening.exp).toBe(9000)
  expect(report.production!.sample.inflows.exp).toBe(1000)
  expect(report.production!.sample.completed.exp).toBe(1000)
  expect(report.production!.sample.closing.exp).toBe(10000)
 })
 it('collects recycling counts at the endpoint without creating material value',()=>{
  const workspace=fixture('gold');workspace.mainPlan.facilities.room_1_1.level=0;workspace.mainPlan.facilities.recycle.level=1
  const report=simulateSchedule(compileRosterSchedule(workspace,{idleOperators:[]}),{sampleHours:48,production})
  expect(report.success).toBe(true)
  expect(report.production!.recycle).toMatchObject({completedItems:1,sampleCompletedItems:1,collectedItems:1,pendingItems:0})
  expect(report.production!.events.filter(e=>e.type==='recycle-collected')).toEqual([{time:48,type:'recycle-collected',roomId:'recycle',amount:1}])
  expect(scoreSimulationProduction(report).total).toBe(0)
  expect(Object.entries(report.production!.sample.inflows).filter(([key])=>key!=='drone').every(([,value])=>value===0)).toBe(true)
 })
})
