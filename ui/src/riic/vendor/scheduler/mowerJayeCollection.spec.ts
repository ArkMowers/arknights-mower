import {describe,expect,it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {compileRosterSchedule} from './compileRosterSchedule'
import {simulateSchedule} from '../simulator/scheduleSimulation'
import {createRosterRuntime,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,mowerRunOrderContext} from './mowerSourceRuntime'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {runDefaultTradeSegment,type RunOrderPlanningState} from './mowerRunOrderPlanning'
import {acceptMowerTradeOrders} from './mowerAcceptOrder'
import {advanceMowerMaintenanceOrders} from './mowerMaintenanceScheduling'

function workspace(){
 const plan=createDefaultWorkspace()
 for(const room of Object.values(plan.mainPlan.facilities)){room.level=0;room.slots=[]}
 const trade=plan.mainPlan.facilities.room_3_1
 trade.level=3;trade.product='orundum';trade.slots=[{occupant:{kind:'operator',operatorId:'char_272_strong'},groupId:null,replacements:[]}]
 plan.mainPlan.conf.workaholic=['char_272_strong']
 return plan
}
describe('elite-zero Jaye order collection',()=>{
 it.each(['override','inventory'] as const)('collects orundum at its observed deadline using elite-zero %s',mode=>{
  const report=simulateSchedule(compileRosterSchedule(workspace(),{idleOperators:[]}),{schedulingModel:'mower-alpha',sampleHours:8,jayeElite0:mode==='override',...(mode==='inventory'?{operatorInventory:[{operator:'char_272_strong',elitePhase:0,level:45}]}:{}),production:{inventoryMode:'finite',outputMode:'settled',droneTarget:'none',initialResources:{fragment:10000}}})
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  const completed=report.production!.events.find(event=>event.type==='order-completed')!,collected=report.production!.events.find(event=>event.type==='order-collected')!
  expect(completed).toBeDefined();expect(collected).toBeDefined()
  expect(collected.time-completed.time).toBeLessThan(1/60)
  expect(report.events.filter(event=>event.type==='shift-off'||event.type==='shift-on')).toEqual([])
  expect(report.production!.events.filter(event=>event.type==='native-trade-drone')).toEqual([])
 })
 it.each([{product:'orundum',elite0:true,working:true,expected:true},{product:'lmd',elite0:true,working:true,expected:false},{product:'orundum',elite0:false,working:true,expected:false},{product:'orundum',elite0:true,working:false,expected:false}])('requires actual elite-zero Jaye in a selling-orundum station: %j',({product,elite0,working,expected})=>{
  const config:RuntimeConfig={mowerAlpha:true,mowerJayeElite0:elite0,positions:[{id:'room_3_1_0',roomId:'room_3_1',primary:'char_272_strong',candidates:[]}],beds:[],mowerSourcePlan:{room_3_1:[{agent:'char_272_strong',group:'',replacement:[]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]}}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),jaye=source.data.operators.char_272_strong!
  state.mowerFacilityProducts={room_3_1:product}
  jaye.currentRoom=working?'room_3_1':'';jaye.currentIndex=working?0:-1
  const [planning]=mowerRunOrderContext(state)
  expect(planning.isCollectionOnlyRoom?.('room_3_1')).toBe(expected)
  expect(planning.runOrderRooms.includes('room_3_1')).toBe(expected)
  if(expected){
   const obsolete=new MowerTask({time:1,type:T.RUN_ORDER,metadata:'room_3_1'});obsolete.runOrderCollectOnly=true;source.queue.tasks.push(obsolete)
   jaye.currentRoom='';jaye.currentIndex=-1
   expect(mowerRunOrderContext(state)[0].runOrderRooms).not.toContain('room_3_1')
   expect(source.queue.tasks).not.toContain(obsolete)
  }
 })
 it.each(['lmd','orundum'] as const)('retains ordinary runner membership only for selling-gold stations, product=%s',product=>{
  const config:RuntimeConfig={mowerAlpha:true,mowerJayeElite0:true,positions:[{id:'room_3_1_0',roomId:'room_3_1',primary:'char_272_strong',candidates:['char_4032_provs']}],beds:[],mowerSourcePlan:{room_3_1:[{agent:'char_272_strong',group:'a',replacement:[],groupBindings:[{group:'a',replacement:[]},{group:'b',replacement:['char_4032_provs']}]}]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]}}
  const state=createRosterRuntime(config);state.mowerFacilityProducts={room_3_1:product}
  const [planning]=mowerRunOrderContext(state)
  expect(planning.isCollectionOnlyRoom?.('room_3_1')).toBe(false)
  expect(planning.runOrderRooms.includes('room_3_1')).toBe(product==='lmd')
 })
 it('keeps unpaid orundum orders pending instead of inventing Originium shards',()=>{
  const report=simulateSchedule(compileRosterSchedule(workspace(),{idleOperators:[]}),{schedulingModel:'mower-alpha',sampleHours:8,jayeElite0:true,production:{inventoryMode:'finite',outputMode:'settled',droneTarget:'none',initialResources:{fragment:0}}})
  expect(report.success,JSON.stringify(report.diagnostics)).toBe(true)
  expect(report.production!.sample.inflows.orundum??0).toBe(0)
  expect(report.production!.sample.closing.fragment??0).toBe(0)
  expect(report.production!.events.some(event=>event.type==='order-completed')).toBe(true)
  expect(report.production!.events.some(event=>event.type==='order-collected')).toBe(false)
 })
 it('does not advance collect-only deadlines for maintenance or capture runner buffs',()=>{
  const task=new MowerTask({time:1,type:T.RUN_ORDER,metadata:'room_3_1'});task.runOrderCollectOnly=true
  advanceMowerMaintenanceOrders([task],0,{maintenance:[toMowerMicros(1),toMowerMicros(2)]})
  expect(task.timeMicros).toBe(toMowerMicros(1))
  const generator=acceptMowerTradeOrders({task,width:1920,height:1080},{nowMicros:()=>0}),requests:string[]=[]
  let next=generator.next(),taps=0
  while(!next.done){
   const request=next.value;requests.push(request.kind)
   if(request.kind==='tap-accept-order')taps++
   next=generator.next({kind:request.kind,observedAtMicros:0,value:request.kind==='find-order-ready'?(taps?null:{ready:true}):null})
  }
  expect(taps).toBe(1)
  expect(requests).not.toContain('read-buff-scores')
  expect(requests).not.toContain('save-order-image')
 })
 it.each([T.RUN_ORDER,T.REFRESH_TIME])('keeps an exhausted %s collection attempt without duplicate reads or tasks',type=>{
  const held=new MowerTask({time:1,type,metadata:'room_3_1'});held.runOrderCollectOnly=true;held.executionFailure={reason:'missing collection observation',rooms:['room_3_1'],snapshot:{intent:'',observations:{}}}
  const state:RunOrderPlanningState={plan:{room_3_1:[{replacement:[]}]},runOrderRooms:['room_3_1'],queue:new MowerTaskQueue(),configuredDelayMinutes:3,droneRoom:null,isCollectionOnlyRoom:()=>true,flags:{planned:false,todoTask:false,collectNotification:false}}
  state.queue.tasks=[held]
  for(let attempt=0;attempt<3;attempt++){
   const generator=runDefaultTradeSegment(state,{nowMicros:()=>toMowerMicros(2),currentDormOccupants:()=>undefined,scheduling:{adjustForRunOrders:false}})
   expect(generator.next().done).toBe(true)
   expect(state.queue.tasks).toEqual([held]);expect(held.timeMicros).toBe(toMowerMicros(1))
  }
 })
 it.each([false,true])('retains the observed deadline and zero staffing intent for collect-only=%s',collectOnly=>{
  const state:RunOrderPlanningState={plan:{room_3_1:[{replacement:[]}]},runOrderRooms:['room_3_1'],queue:new MowerTaskQueue(),configuredDelayMinutes:3,droneRoom:null,isCollectionOnlyRoom:()=>collectOnly,flags:{planned:false,todoTask:false,collectNotification:false}}
  const due=toMowerMicros(1),generator=runDefaultTradeSegment(state,{nowMicros:()=>0,currentDormOccupants:()=>undefined,scheduling:{adjustForRunOrders:false}})
  let next=generator.next()
  while(!next.done)next=generator.next({observedAtMicros:0,...(next.value.kind==='read-order'?{absoluteDueMicros:due}:{})})
  expect(state.queue.tasks).toHaveLength(1)
  expect(state.queue.tasks[0]!.timeMicros).toBe(collectOnly?due:due-toMowerMicros(3/60))
  expect(state.queue.tasks[0]!.observedOrderDueMicros).toBe(due)
  expect(state.queue.tasks[0]!.runOrderCollectOnly).toBe(collectOnly)
  expect(state.queue.tasks[0]!.plan).toEqual({})
 })
})
