import {waitMowerDroneInterface,tapMowerDroneAccelerate,type MowerDroneInterfaceObservation} from '../scheduler/mowerDroneInterface'
import type {MowerTodoTaskObservation} from '../scheduler/mowerTodoTask'
import {acceptMowerTradeOrders,type MowerAcceptOrderRequest,type MowerAcceptOrderObservation} from '../scheduler/mowerAcceptOrder'
import {getMowerSourceRuntime} from '../scheduler/mowerSourceRuntime'
import type {MowerNotificationObservation} from '../scheduler/mowerNotification'
/**
 * Explicit headless facility observations for the native Mower task policy.
 * Production and morale use the host clock. Stable pages and continuous timers
 * are declared simulation inputs; these are not pixel/OCR equivalence claims.
 */
import type {RuntimeState,RuntimeRates} from '../scheduler/rosterRuntime'
import {mowerRunOrderContext} from '../scheduler/mowerSourceRuntime'
import {bridgeMowerNativeIO} from '../scheduler/mowerRunOrderBridge'
import {executeMowerDroneOperation,type MowerDroneOperationRequest,type MowerDroneOperationObservation} from '../scheduler/mowerDroneOperations'
import type {createProductionTimeline,ProductionFrame} from './productionTimeline'
import {toMowerMicros} from '../scheduler/mowerTaskQueue'
type Controller=ReturnType<typeof createProductionTimeline>
export function createMowerProductionIO(state:RuntimeState,production:Controller,frame:()=>ProductionFrame):Pick<RuntimeRates,'mowerRunOrderIO'|'mowerNotificationIO'|'mowerTodoListVisible'|'mowerTodoTaskIO'>{
 const now=()=>toMowerMicros(state.time)
 const ui=state.mowerUI??={scene:'INFRA_MAIN',lastRoom:''}
 let detailPage=false,todoPage=false,receiptBlocked=false
 const absoluteDue=(room:string)=>now()+toMowerMicros(production.nativeRemainingSeconds(room,frame())/3600)
 function* accept(room:string){
  const generator=acceptMowerTradeOrders({task:getMowerSourceRuntime(state).activeTask??null,width:1920,height:1080},{nowMicros:now})
  return yield* bridgeMowerNativeIO(generator,(request:MowerAcceptOrderRequest)=>({
   delayMicros:request.kind==='sleep'?toMowerMicros(request.seconds/3600):request.kind==='tap-accept-order'?500_000:0,
   observe:():MowerAcceptOrderObservation=>{
    let value:unknown=null
    switch(request.kind){
     case 'cache-trade-page':detailPage=true;ui.scene='INFRA_DETAILS';ui.lastRoom=room;break
     case 'find-order-ready':value=!receiptBlocked&&production.nativePendingTradeOrders(room)>0?{control:'order_ready'}:null;break
     case 'read-buff-scores':value=[1];break
     case 'has-distinct-buff':case 'is-stable-buff':value=true;break
     case 'tap-accept-order':receiptBlocked=!production.nativeAcceptOrder(room,frame());break
    }
    return {kind:request.kind,observedAtMicros:now(),value}
   }
  }),()=>room)
 }
 function* drone(room:string,flags:{notCustomize:boolean;notReturn:boolean;skipEnter:boolean}){
  if(production.nativeHasTrade(room)&&!production.nativeTradeDroneAvailable(room))return null
  const [planning,seam]=mowerRunOrderContext(state)
  let selectedQuantity=0,panelOpen=false
  const droneCountLimit=state.config.mowerDroneCountLimit??100
  function* facilityInterface(request:Extract<MowerDroneOperationRequest,{kind:'wait-interface'|'tap-drone-accelerate'}>){
   const helper=request.kind==='wait-interface'
    ?waitMowerDroneInterface({width:1920,height:1080},{nowMicros:now},{intervalSeconds:request.intervalSeconds,accelerateTemplate:request.accelerateTemplate})
    :tapMowerDroneAccelerate({nowMicros:now},{accelerateTemplate:request.template,allInTemplate:request.control})
   const value=yield* bridgeMowerNativeIO(helper,step=>({
    delayMicros:step.kind==='tap'?toMowerMicros(step.intervalSeconds/3600):step.kind==='sleep'?toMowerMicros((step.seconds??1)/3600):0,
    observe:():MowerDroneInterfaceObservation=>{
     let value:unknown=null
     if(step.kind==='find'){
      if(step.name==='all_in')value=panelOpen?{control:'all_in'}:null
      if(step.name==='manufacture_accelerate'&&detailPage&&!receiptBlocked&&production.nativeHasManufacture(room))value={control:step.name}
      if(step.name==='bill_accelerate'&&detailPage&&!receiptBlocked&&production.nativeHasTrade(room))value={control:step.name}
     }else if(step.kind==='tap'){
      if(step.action==='accelerate'){
       panelOpen=true
       if(production.nativeHasManufacture(room)){
        const input=state.config.mowerDeviceObservations?.initialManufactureDroneSelection??'max'
        selectedQuantity=input==='max'?production.nativeManufactureDroneMaximum(room):input
        if(!Number.isInteger(selectedQuantity)||selectedQuantity<0||selectedQuantity>production.nativeManufactureDroneMaximum(room))throw new Error('Invalid observed initial manufacture drone selection')
       }
      }else detailPage=true
     }
     return {kind:step.kind,observedAtMicros:now(),value}
    }
   }),()=>room)
   return {kind:request.kind,observedAtMicros:now(),value}
  }
  const generator=executeMowerDroneOperation({
   retainManufacturingReserve:!flags.notCustomize,
   get repeatTradeAcceleration(){return planning.droneRoom===null||(planning.droneRoom===room&&planning.runOrderRooms.includes(room))},
   room,width:1920,height:1080,...flags,droneCountLimit,waitingScenes:[],
  },seam)
  return yield* bridgeMowerNativeIO(generator,(request:MowerDroneOperationRequest)=>{
   if(request.kind==='wait-interface'||request.kind==='tap-drone-accelerate')return facilityInterface(request)
   if(request.kind==='accept-order')return (function*(){
    const value=yield* accept(room)
    return {kind:request.kind,observedAtMicros:now(),value}
   })()
   return {
   delayMicros:request.kind==='tap'?toMowerMicros((request.intervalSeconds??1)/3600):0,
   observe:():MowerDroneOperationObservation=>{
    let value:unknown=null
    switch(request.kind){
     case 'enter-room':detailPage=true;ui.scene='INFRA_DETAILS';ui.lastRoom=room;receiptBlocked=false;break
     case 'tap':
      if(request.action==='detail')detailPage=true
      if(request.action==='all-in'&&production.nativeHasManufacture(room))selectedQuantity=production.nativeManufactureDroneMaximum(room)
      if(request.action==='minus-reserve')selectedQuantity=Math.max(0,selectedQuantity-1)
      if(request.action==='confirm-manufacture'){production.nativeSpendManufacturingDrones(room,selectedQuantity);panelOpen=false}
      if(request.action==='confirm-all'){
       panelOpen=false
       const count=Math.min(production.nativeDroneCount(),production.nativeTradeRequiredDrones(room))
       if(count>0)production.nativeSpendTradeDrones(room,count,frame())
      }
      break
     case 'find':
      // A trade room can remain visible after its last whole drone is spent.
      // Report the accelerate control only while another drone can change the order.
      const available=request.name==='manufacture_accelerate'
       ?production.nativeHasManufacture(room)
       :production.nativeHasTrade(room)&&production.nativeDroneCount()>0&&production.nativeTradeRequiredDrones(room)>0
      value=detailPage&&!receiptBlocked&&available?{control:request.name}:null
      break
     case 'read-drone-count':value=production.nativeDroneCount();break
     case 'scene':value=receiptBlocked?'trade-insufficient-material':'trade-ready';break
     case 'waiting-solver':value=true;break
     case 'return-main':detailPage=false;ui.scene='INFRA_MAIN';receiptBlocked=false;break
    }
    return {kind:request.kind,observedAtMicros:now(),value}
   }
  }},()=>room)
 }
 return {
  mowerTodoTaskIO:request=>{
   if(request.kind==='drone')return (function*(){
    const value=yield* drone(request.room,{notCustomize:false,notReturn:false,skipEnter:false})
    return {kind:request.kind,observedAtMicros:now(),value} satisfies MowerTodoTaskObservation
   })()
   throw new Error('Native '+request.kind+' requires its lifecycle observation adapter')
  },
  mowerTodoListVisible:()=>todoPage,
  mowerNotificationIO:request=>({
   delayMicros:request.kind==='sleep'?1_000_000:['tap-notification','tap-collect','tap-close-todo'].includes(request.kind)?1_000_000:0,
   observe:():MowerNotificationObservation=>{
    let value:unknown=null
    switch(request.kind){
     case 'detect-notification':value=production.nativePendingTradeOrders()>0||production.nativePendingManufacturingItems()>0||production.nativePendingRecycleItems()>0?{control:'infra_notification'}:null;break
     case 'tap-notification':todoPage=true;ui.scene='INFRA_TODOLIST';break
     case 'find-collect':value=request.resource==='bill'&&production.nativePendingTradeOrders()>0||request.resource==='factory'&&production.nativePendingManufacturingItems()>0||request.resource==='recycle'&&production.nativePendingRecycleItems()>0?{control:request.name}:null;break
     case 'tap-collect':
      if(request.resource==='bill')production.nativeCollectTradeOrders(frame())
      if(request.resource==='factory')production.nativeCollectManufacturingItems(frame())
      if(request.resource==='recycle')production.nativeCollectRecycleItems()
      break
     case 'tap-close-todo':todoPage=false;ui.scene='INFRA_MAIN';break
    }
    return {kind:request.kind,observedAtMicros:now(),value}
   }
  }),
  mowerRunOrderIO:request=>{
   return {
    delayMicros:request.kind==='return-main'?state.config.mowerDeviceTiming?.roomReturnMicros??0:0,
    observe:()=>{
     if(request.kind==='enter-room'){detailPage=true;ui.scene='INFRA_DETAILS';ui.lastRoom=request.room;receiptBlocked=false}
     if(request.kind==='return-main'){detailPage=false;ui.scene='INFRA_MAIN'}
     return {observedAtMicros:now(),...(request.kind==='read-order'?{absoluteDueMicros:absoluteDue(request.room)}:{})}
    }
   }
  },
 }
}
