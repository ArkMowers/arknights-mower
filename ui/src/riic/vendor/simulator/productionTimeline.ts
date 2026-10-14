import { readMowerProductSwitchSettings, MOWER_MANUFACTURING_FORMULAS, manufacturingProductId, planMowerProductSwitchDrones } from './mowerProductSwitching'
import { hasOperatorSkill, runOrderSkillRank } from '../domain/operatorContext'
import { resolveDroneCapacity } from '../domain/droneCapacity'
import { MOWER_INVENTORY_ITEMS } from '../domain/simulationInventory'
import { parseProduct, serializeProduct } from '../domain/mowerProducts'
import type {AppConfig} from '../domain/types'
import {OPERATOR_MAP} from '../domain/operators'
import {evaluateManufacturingCapacity,type OperatorEfficiencyResult} from '../engine/operatorRules'
import {evaluateTradeOrderCapacity} from '../engine/orderCapacity'
import type {CompiledSchedule} from '../scheduler/types'
import type {RuntimeState} from '../scheduler/rosterRuntime'
import {getOrderDistribution,selectBaseOrder,type SpecialCapture,type OrderMode} from '../rules/orderRules'
import {startOrder,advanceOrder,finishOrder,type ActiveOrder} from './orderTimeline'
import {createLedger,type ResourceAmounts,type ResourceKind} from './resourceLedger'
import {createDroneState,generateDrones,spendDrones} from './droneTimeline'
import {MANUFACTURING_FORMULAS,startManufacturing,authorizeManufacturingBatch,advanceManufacturing,collectManufacturing,nextManufacturingEvent,updateManufacturingCapacity,type ManufacturingFormulaId,type ManufacturingState} from './manufacturingTimeline'
import { evaluateRecycleEfficiency } from '../engine/supportFacilitySkills'
import { createRecycleTimeline, type RecycleProduction } from './recycleTimeline'

/** Reject legacy persisted/API options as well as typed callers. */
export function assertRunOrderMode(mode: unknown): void {
 if(mode==='natural')throw new Error('自然跑单已全面禁用，当前仅支持理想跑单')
 if(mode!==undefined&&mode!=='ideal')throw new Error('当前仅支持理想跑单')
}

export interface ProductionOptions {
 outputMode?:'settled'|'potential'
 inventoryMode?:'unlimited'|'finite'
 allowGoldDebt?:boolean
 seed?:number;initialResources?:ResourceAmounts;collectionIntervalHours?:number
 runOrderMode?:'ideal'
 droneTarget?:'gold'|'exp'|'none'|'trading';droneTradingRoomId?:string;droneRoomId?:string;droneReserve?:number
 fragmentFormulaByRoom?:Record<string,'fragment-orirock'|'fragment-device'>
}
export interface ProductionFrame {desiredProducts?:Record<string,string>;time:number;config:AppConfig;active:Set<string>;morale:Map<string,number>;evaluations:Record<string,OperatorEfficiencyResult>}
export interface ProductionEvent {time:number;type:string;roomId?:string;orderId?:string;amount?:number;operatorIds?:string[];delta?:ResourceAmounts;order?:CompletedOrder;fromProduct?:string;toProduct?:string}
type CompletedOrder=ReturnType<typeof finishOrder>
interface ManufactureRoom {completedByProduct:Record<string,number>;pendingSwitch?:{target:string;accelerated:boolean;readyAt?:number};roomId:string;state:ManufacturingState;blockedHours:number;blockedMaterialHours:number;collectedItems:number}
interface TradeRoom {product:string;roomId:string;active:ActiveOrder|null;pending:CompletedOrder[];completedOrders:number;collectedOrders:number;blockedHours:number;limit:number|null;disabled:boolean;rng:number}
export interface ProductionReport {
 recycle?: RecycleProduction
 success:boolean;ledger:ReturnType<typeof createLedger>;sample:{completed:{exp:number;gold:number;orderLmd:number};opening:ResourceAmounts;closing:ResourceAmounts;inflows:ResourceAmounts;outflows:ResourceAmounts;net:ResourceAmounts}
 materialsConsumed:ResourceAmounts
 drones:ReturnType<typeof createDroneState>
 manufacturing:{roomId:string;product:string;completedItems:number;sampleCompletedItems:number;pendingItems:number;remainingBaseMinutes:number;blockedHours:number;blockedMaterialHours:number}[]
 trading:{roomId:string;completedOrders:number;collectedOrders:number;pendingOrders:CompletedOrder[];remainingBaseMinutes:number|null;blockedHours:number}[]
 events:ProductionEvent[];assumptions:{outputMode:'settled'|'potential';inventoryMode:'unlimited'|'finite';allowGoldDebt:boolean;seed:number;runOrderMode:'ideal';droneTarget:'gold'|'exp'|'none'|'trading';droneRoomId?:string;droneReserve:number;collectionIntervalHours:number;orderSnapshotPolicy:string}
}
const EPS=1e-8
const resources:ResourceKind[]=['gold','lmd','exp','fragment','orundum','drone','orirock','device']
const difference=(a:ResourceAmounts,b:ResourceAmounts)=>Object.fromEntries(resources.map(k=>[k,(a[k]??0)-(b[k]??0)])) as ResourceAmounts
function capture(frame:ProductionFrame,roomId:string):SpecialCapture {
 const room=frame.config.rooms.find(r=>r.id===roomId)!
 const skill=(id:string,buffId:string)=>frame.active.has(id)&&hasOperatorSkill(frame.config,id,buffId)
 const rank=(kind:'proviso'|'tequila')=>Math.max(0,...room.operatorIds.filter(id=>frame.active.has(id)).map(id=>runOrderSkillRank(frame.config,id,kind))) as 0|1|2
 // Preserve the configured level restriction even when low-level quality produces four-gold orders.
 return {proviso:rank('proviso'),tequila:room.level===3?rank('tequila'):0,uOfficial:room.operatorIds.some(id=>skill(id,'trade_ord_spd&wt[000]')),closure:room.operatorIds.some(id=>skill(id,'trade_ord_closure[000]')),pepe:room.operatorIds.some(id=>skill(id,'trade_ord_pepe[000]'))}
}
/** Shares the roster clock. Only this controller owns inventories and immutable order snapshots. */
export function createProductionTimeline(schedule:CompiledSchedule,state:RuntimeState,options:ProductionOptions,warmupHours:number,diagnostic:(code:string,message:string)=>void,nativeScheduler=false){
 assertRunOrderMode(options.runOrderMode)
 const advanced=schedule.sourceWorkspace.compatibility.unrecognizedFields.advanced_settings as Record<string,unknown>|undefined
 const switchSettings=readMowerProductSwitchSettings(advanced?.product_switching)
 const switchErrors=new Set<string>()
 const outputMode=options.outputMode??'settled',potential=outputMode==='potential',inventoryMode=options.inventoryMode??'unlimited',unlimitedMaterials=potential||inventoryMode==='unlimited'
 if(!['unlimited','finite'].includes(inventoryMode))throw new Error('Invalid inventory mode')
 if(!['settled','potential'].includes(outputMode))throw new Error('Invalid output mode')
 const seed=options.seed??1,target=options.droneTarget??'gold',reserve=options.droneReserve??0,interval=potential?0:options.collectionIntervalHours??schedule.assumptions.collectionIntervalHours
 if(!Number.isSafeInteger(seed)||seed<0||seed>0xffffffff||!['gold','exp','none','trading'].includes(target))throw new Error('Invalid production strategy/seed')
 const droneCapacity=resolveDroneCapacity(schedule.sourceWorkspace)
 if(![reserve,interval].every(x=>Number.isFinite(x)&&x>=0)||!Number.isInteger(reserve)||(droneCapacity>0?reserve>=droneCapacity:reserve>0))throw new Error('Invalid production timing/reserve')
 const initial={gold:schedule.assumptions.initialGold,fragment:schedule.assumptions.initialFragments,drone:schedule.assumptions.initialDrones,...options.initialResources,...(potential?{gold:0,fragment:0,lmd:0,exp:0,orundum:0,orirock:0,device:0}:{})}
 for(const k of Object.keys(initial))if(!resources.includes(k as ResourceKind))throw new Error(`Unknown initial resource ${k}`)
 const ledger=createLedger(initial),materialsConsumed:ResourceAmounts={}
 let drones=createDroneState(initial.drone??0,droneCapacity),serial=0,valid=true,nextCollection=interval||Infinity
 const events:ProductionEvent[]=[],manufactures=new Map<string,ManufactureRoom>(),trades=new Map<string,TradeRoom>()
 // Capture the original main plan once; a speculative backup must not change its own predicate.
 const baseProducts=Object.fromEntries(Object.values(schedule.sourceWorkspace.mainPlan.facilities).map(room=>{
  const raw=schedule.sourceWorkspace.compatibility.facilityMetadata?.[room.roomId]?.rawProduct
  return [room.roomId,typeof raw==='string'&&parseProduct(raw)===room.product?raw:serializeProduct(room.type,room.product)??null]
 }))
 Object.defineProperties(state,{
  mowerInventoryCounts:{configurable:true,enumerable:true,get:()=>Object.fromEntries(MOWER_INVENTORY_ITEMS.map(item=>[item.name,ledger.balances[item.resource]??0]))},
  mowerFacilityProducts:{configurable:true,enumerable:true,get:()=>({...baseProducts,...actualProducts()})},
 })
 let recycle: ReturnType<typeof createRecycleTimeline> | undefined
 const capacityByEvaluation=new WeakMap<ProductionFrame['evaluations'],Map<string,{moodBand:string;bonus:number}>>()
 let opening:ResourceAmounts|undefined=warmupHours===0?{...ledger.balances}:undefined,openingIn:ResourceAmounts={},openingOut:ResourceAmounts={}
 const unsupported=(code:string,message:string)=>{valid=false;diagnostic(code,message)}
 const record=(type:string,extra:Omit<ProductionEvent,'type'|'time'>={},time=state.time)=>events.push({time,type,...extra})
 // Append-only, local ownership: avoid cloning the complete ledger for every manufactured item.
 const transact=(delta:ResourceAmounts,reason:string,time=state.time)=>{
  for(const [key,n] of Object.entries(delta))if(!resources.includes(key as ResourceKind)||!Number.isFinite(n))throw new Error('Invalid production transaction')
  for(const [key,n] of Object.entries(delta))if((ledger.balances[key as ResourceKind]??0)+n<0&&!(key==='gold'&&options.allowGoldDebt===true))return false
  for(const [key,n] of Object.entries(delta)){const k=key as ResourceKind;ledger.balances[k]=(ledger.balances[k]??0)+n;const totals=n>=0?ledger.inflows:ledger.outflows;totals[k]=(totals[k]??0)+Math.abs(n)}
  const id=`${++serial}:${reason}`;ledger.entries.push({reason:id,delta:{...delta}});ledger.appliedReasons.push(id);record(reason,{delta},time);return true
 }
 const completedTotals=()=>({exp:[...manufactures.values()].reduce((n,m)=>n+(m.completedByProduct.exp??0)*1000,0),gold:[...manufactures.values()].reduce((n,m)=>n+(m.completedByProduct.gold??0),0),orderLmd:events.filter(e=>e.type==='order-completed').reduce((n,e)=>n+(e.order?.lmdReward??0),0)})
 let openingCompleted={exp:0,gold:0,orderLmd:0}
 let openingManufactured=new Map<string,number>()
 const completedSample=()=>{const total=completedTotals();return {exp:total.exp-openingCompleted.exp,gold:total.gold-openingCompleted.gold,orderLmd:total.orderLmd-openingCompleted.orderLmd}}
 const markObservation=()=>{if(!opening&&state.time>=warmupHours-EPS){opening={...ledger.balances};openingIn={...ledger.inflows};openingOut={...ledger.outflows};openingCompleted=completedTotals();openingManufactured=new Map([...manufactures].map(([id,m])=>[id,m.state.lifetimeItems]));recycle?.markObservation()}}
 const cost=(m:ManufacturingState):ResourceAmounts=>Object.fromEntries(m.formula.costs.map(c=>[c.id==='4001'?'lmd':c.id==='30012'?'orirock':'device',-c.count]))
 const advanceManufacture=(m:ManufactureRoom,work:number)=>{
  const progress=advanceManufacturing(m.state,work)
  m.completedByProduct[m.state.formula.product]=(m.completedByProduct[m.state.formula.product]??0)+progress.completedItems
  m.state=progress.state
  return progress
 }
 const fund=(m:ManufactureRoom)=>{
  if(m.pendingSwitch&&m.state.awaitingPayment)return
  if(!m.state.awaitingPayment||m.state.storedWeight+m.state.formula.storageWeight>m.state.capacityWeight+EPS)return
  const delta=cost(m.state)
  if(!Object.keys(delta).length||unlimitedMaterials||transact(delta,`manufacture-start:${m.roomId}`)){
   for(const [key,value] of Object.entries(delta)){const k=key as ResourceKind;materialsConsumed[k]=(materialsConsumed[k]??0)-value}
   m.state=authorizeManufacturingBatch(m.state,true).state
  }
 }
 const collect=(roomId?:string,includeTrade=true,includeManufacture=true,orderLimit=Infinity)=>{
  for(const m of manufactures.values())if(includeManufacture&&(roomId===undefined||roomId===m.roomId)&&m.state.pendingItems){const n=m.state.pendingItems*(m.state.formula.product==='exp'?1000:1);transact({[m.state.formula.product]:n},`collect-manufacture:${m.roomId}`);m.collectedItems+=m.state.pendingItems;m.state=collectManufacturing(m.state).state}
  for(const t of trades.values())if(includeTrade&&(roomId===undefined||roomId===t.roomId)){let count=0;while(t.pending.length&&count++<orderLimit){const o=t.pending[0]!,delta={gold:unlimitedMaterials?0:-o.goldCost,fragment:unlimitedMaterials?0:-o.fragmentCost,lmd:o.lmdReward,orundum:o.orundumReward};if(!transact(delta,`collect-order:${o.id}`))break;materialsConsumed.gold=(materialsConsumed.gold??0)+o.goldCost;materialsConsumed.fragment=(materialsConsumed.fragment??0)+o.fragmentCost;t.pending.shift();t.collectedOrders++;record('order-collected',{roomId:t.roomId,orderId:o.id,order:o})}}
 }
 const rng=(t:TradeRoom)=>{t.rng=(Math.imul(1664525,t.rng)+1013904223)>>>0;return t.rng/4294967296}
 const synchronize=(frame:ProductionFrame)=>{
  if(frame.config.facilities.recycle&&!recycle)recycle=createRecycleTimeline(frame.config.facilities.recycle)
  for(const room of frame.config.rooms){
   const evaluation=frame.evaluations[room.id]!
   if(room.type==='manufacture'){
    let m=manufactures.get(room.id)
    if(!m){const formula:ManufacturingFormulaId=room.product==='exp'?'exp-medium':room.product==='fragment'?(options.fragmentFormulaByRoom?.[room.id]??(schedule.sourceWorkspace.compatibility.facilityMetadata?.[room.id]?.rawProduct==='orirock_device'?'fragment-device':'fragment-orirock')):'gold'
     if(room.level<MANUFACTURING_FORMULAS[formula].requiredRoomLevel){unsupported('MANUFACTURE_FORMULA_LEVEL',`${room.id}：所选配方不满足设施等级，未计产出`);continue}
     m={completedByProduct:{},roomId:room.id,state:startManufacturing({formula,capacityWeight:0,paymentAuthorized:false}),blockedHours:0,blockedMaterialHours:0,collectedItems:0};manufactures.set(room.id,m)}
    // The same efficiency snapshot has stable staffing and capacity-relevant mood boundaries.
    let capacities=capacityByEvaluation.get(frame.evaluations)
    if(!capacities){capacities=new Map();capacityByEvaluation.set(frame.evaluations,capacities)}
    const moodBand=room.operatorIds.map(id=>Number((frame.morale.get(id)??24)<12)).join('')
    let cached=capacities.get(room.id)
    if(!cached||cached.moodBand!==moodBand){cached={moodBand,bonus:evaluateManufacturingCapacity(room,frame.config,frame.active,frame.morale)};capacities.set(room.id,cached)}
    const bonus=cached.bonus
    const capacity=[24,36,54][room.level-1]!+bonus
    m.state=updateManufacturingCapacity(m.state,Math.max(0,capacity))
   }else if(room.type==='trading'){
    let t=trades.get(room.id)
    if(!t){let hash=seed;for(const c of room.id)hash=Math.imul(hash^c.charCodeAt(0),16777619)>>>0;t={product:room.strategy==='orundum'?'orundum':'lmd',roomId:room.id,active:null,pending:[],completedOrders:0,collectedOrders:0,blockedHours:0,limit:0,disabled:false,rng:hash};trades.set(room.id,t)}
    const capacity=evaluateTradeOrderCapacity(room,frame.config,frame.active,evaluation);t.limit=capacity.limit
    if(capacity.limit===null)unsupported('UNQUANTIFIED_ORDER_CAPACITY',`${room.id}：${capacity.unquantified.join('；')}，停止新单获取`)
   }
  }
 }
 const switchProduct=(m:ManufactureRoom,target:string,direct=false)=>{
  const formula=MOWER_MANUFACTURING_FORMULAS[target]!
  const fromProduct=manufacturingProductId(m.state.formula.id)
  if(direct&&!m.state.awaitingPayment)record('product-switch-cancelled-work',{roomId:m.roomId,amount:m.state.formula.baseMinutes-m.state.remainingBaseMinutes,fromProduct,toProduct:target})
  // Collect completed old products before replacing the formula; partial work has no output.
  collect(m.roomId,false,true)
  const previous=m.state
  m.state={...startManufacturing({formula,capacityWeight:previous.capacityWeight,paymentAuthorized:false}),lifetimeItems:previous.lifetimeItems,lifetimeBatches:previous.lifetimeBatches}
  delete m.pendingSwitch
  record('product-switched',{roomId:m.roomId,fromProduct,toProduct:target})
 }
 const synchronizeProducts=(frame:ProductionFrame)=>{
  if(!switchSettings.enable||!frame.desiredProducts)return
  const reject=(room:string,target:string,reason:string)=>{const key=room+':'+target+':'+reason;if(!switchErrors.has(key)){switchErrors.add(key);unsupported('PRODUCT_SWITCH_UNSUPPORTED',`${room}：${reason}`)}}
  for(const m of manufactures.values()){
   const target=frame.desiredProducts[m.roomId]??manufacturingProductId(m.state.formula.id)
   if(target===manufacturingProductId(m.state.formula.id)){delete m.pendingSwitch;continue}
   const formula=MOWER_MANUFACTURING_FORMULAS[target],room=frame.config.rooms.find(r=>r.id===m.roomId)!
   if(!formula||room.level<MANUFACTURING_FORMULAS[formula].requiredRoomLevel){reject(m.roomId,target,'切换目标配方未知或设施等级不足');delete m.pendingSwitch;continue}
   if(m.pendingSwitch?.target!==target)m.pendingSwitch={target,accelerated:false}
   if(m.state.awaitingPayment){
    // An unfunded idle facility has no current unit to finish.
    if(m.pendingSwitch.readyAt===undefined)m.pendingSwitch.readyAt=state.time+(m.pendingSwitch.accelerated&&switchSettings.grandet_mode?switchSettings.waiting_seconds/3600:0)
    if(state.time>=m.pendingSwitch.readyAt-EPS)switchProduct(m,target)
   }
  }
  const pending=[...manufactures.values()].filter(m=>m.pendingSwitch&&!m.pendingSwitch.accelerated&&!m.state.awaitingPayment)
  const plans=pending.map(m=>({m,...planMowerProductSwitchDrones(m.state.remainingBaseMinutes*60,switchSettings,manufacturingProductId(m.state.formula.id),m.pendingSwitch!.target)}))
  const required=plans.reduce((sum,p)=>sum+p.drones,0),insufficient=required>Math.floor(drones.stock+EPS)
  for(const plan of plans){
   const {m}=plan,pendingSwitch=m.pendingSwitch!
   if(insufficient&&!plan.naturalOnly){if(switchSettings.direct_when_drones_insufficient)switchProduct(m,pendingSwitch.target,true);continue}
   pendingSwitch.accelerated=true
   if(plan.drones){
    drones=spendDrones(drones,plan.drones).state;transact({drone:-plan.drones},'product-switch-drone')
    const result=advanceManufacture(m,plan.drones*3)
    record('product-switch-drone',{roomId:m.roomId,amount:plan.drones})
    if(result.unusedBaseMinutes>EPS)record('product-switch-drone-loss',{roomId:m.roomId,amount:result.unusedBaseMinutes})
   }
   if(m.state.awaitingPayment){pendingSwitch.readyAt=state.time+(switchSettings.grandet_mode?switchSettings.waiting_seconds/3600:0);if(state.time>=pendingSwitch.readyAt-EPS)switchProduct(m,pendingSwitch.target)}
  }
  for(const t of trades.values()){
   const target=frame.desiredProducts[t.roomId]??t.product
   if(target===t.product)continue
   const room=frame.config.rooms.find(r=>r.id===t.roomId)!
   if(!['lmd','orundum'].includes(target)||room.level<3){reject(t.roomId,target,'贸易订单类型切换需要三级设施及有效订单类型');continue}
   const previous=t.product;t.product=target
   record('product-switched',{roomId:t.roomId,fromProduct:previous,toProduct:target})
  }
 }
 const actualProducts=()=>Object.fromEntries([...manufactures.values()].map(m=>[m.roomId,manufacturingProductId(m.state.formula.id)]).concat([...trades.values()].map(t=>[t.roomId,t.product])))
 const finish=(frame:ProductionFrame)=>{
  for(const t of trades.values())if(t.active&&t.active.remainingBaseMinutes<=EPS){
   const a=t.active,c=capture(frame,t.roomId)
   if(a.base.mode==='gold'){
    const policy=(state.config.runOrderPolicies??schedule.runOrderPolicies).find(p=>p.roomId===t.roomId)
    const level=schedule.rooms.find(r=>r.roomId===t.roomId)!.level
    const runners=policy?.orderedOperatorIds.filter(id=>{const name=OPERATOR_MAP.get(id)?.name;return name==='但书'||level===3&&name==='龙舌兰'||name==='U-Official'})??[]
    if(runners.length){
     c.uOfficial=c.uOfficial||runners.some(id=>hasOperatorSkill(frame.config,id,'trade_ord_spd&wt[000]'))
     c.proviso=Math.max(c.proviso??0,...runners.map(id=>runOrderSkillRank(frame.config,id,'proviso'))) as 0|1|2
     c.tequila=Math.max(c.tequila??0,...runners.map(id=>runOrderSkillRank(frame.config,id,'tequila'))) as 0|1|2
     record('run-order-ideal',{roomId:t.roomId,orderId:a.id,operatorIds:[...new Set(runners)]})
    }
   }
   // Workload-changing modes are explicit acquisition-start snapshots; later staffing cannot reroll them.
   c.pepe=a.base.mode==='pepe';c.closure=a.base.mode==='closure'
   const snapshot=finishOrder({...a,remainingBaseMinutes:0},c,state.time)
   t.pending.push(snapshot);t.completedOrders++;t.active=null
   record('order-completed',{roomId:t.roomId,orderId:a.id,order:snapshot})
  }
 }
 const openWork=(frame:ProductionFrame)=>{
  for(const m of manufactures.values())fund(m)
  for(const t of trades.values())if(!t.active&&!t.disabled&&t.limit!==null&&t.pending.length<t.limit){
   const room=frame.config.rooms.find(r=>r.id===t.roomId)!,c=capture(frame,t.roomId)
   if(t.product!=='orundum'){
    const policy=(state.config.runOrderPolicies??schedule.runOrderPolicies).find(p=>p.roomId===t.roomId)
    for(const id of policy?.orderedOperatorIds??[]){
     if(hasOperatorSkill(frame.config,id,'trade_ord_pepe[000]'))c.pepe=true
     if(hasOperatorSkill(frame.config,id,'trade_ord_closure[000]'))c.closure=true
    }
   }
   const orderMode:OrderMode=t.product==='orundum'?'orundum':c.pepe?'pepe':c.closure?'closure':'gold'
   if(orderMode==='pepe'&&target==='trading')diagnostic('PEPE_DRONE_UNVERIFIED',`${t.roomId}：佩佩订单无人机加速未核实；保留无人机库存，不计加速`)
   try{const base=selectBaseOrder(getOrderDistribution(room.level,frame.evaluations[t.roomId]!.quality,orderMode),rng(t));t.active=startOrder({id:`${t.roomId}:${t.completedOrders+1}`,startedAt:state.time,base});record('order-started',{roomId:t.roomId,orderId:t.active.id})}
   catch(error){t.disabled=true;unsupported('ORDER_DISTRIBUTION_UNSUPPORTED',`${t.roomId}：${String(error)}`)}
  }
 }
 const chargeRate=(f:ProductionFrame)=>Math.max(0,1+f.config.rooms.filter(r=>r.type==='power').reduce((n,r)=>n+(f.evaluations[r.id]!.efficiencyPercent-100)/100,0))/6
 let nextDailyClear=24
  const spendSurplus=()=>{
   if(nativeScheduler)return
   const isDailyClear=state.time>=nextDailyClear-EPS
   const isCapacityReached=drones.stock>=drones.capacity-EPS
   if(target==='none'||(!isCapacityReached&&!isDailyClear))return
   let budget=Math.max(0,Math.floor(drones.stock+EPS)-reserve)
   if(budget<=0)return
   if(target==='trading'){
    const targetTrade=(options.droneRoomId||options.droneTradingRoomId)?trades.get((options.droneRoomId||options.droneTradingRoomId)!):[...trades.values()][0]
    if(targetTrade?.active&&targetTrade.active.base.mode!=='pepe'&&targetTrade.active.remainingBaseMinutes>EPS){
     while(budget>0&&targetTrade.active&&targetTrade.active.remainingBaseMinutes>EPS){
      const remaining=targetTrade.active.remainingBaseMinutes
      const n=Math.min(budget,Math.ceil((remaining-EPS)/3))
      if(n<=0)break
      const spent=spendDrones(drones,n);drones=spent.state;transact({drone:-n},'trade-drone');budget-=n
      targetTrade.active=advanceOrder(targetTrade.active,{elapsedMinutes:0,efficiency:1,droneBaseMinutes:spent.baseMinutes}).order
      record('trade-drone',{roomId:targetTrade.roomId,amount:n})
     }
    }
    return
   }
   for(const m of manufactures.values()){
    if(options.droneRoomId ? m.roomId!==options.droneRoomId : m.state.formula.product!==target)continue
    // Whole drones supply base work; excess crosses a paid, capacity-checked batch boundary.
    while(budget>0){
     fund(m);let remaining=nextManufacturingEvent(m.state);if(remaining===null)break
     if(remaining<=EPS){advanceManufacture(m,remaining+EPS);if(interval===0)collect(m.roomId);fund(m);remaining=nextManufacturingEvent(m.state);if(remaining===null)break}
     const n=Math.min(budget,Math.max(1,Math.ceil((remaining-EPS)/3)))
     if(n<=0)break
     const spent=spendDrones(drones,n);drones=spent.state;transact({drone:-n},'manufacture-drone');budget-=n
     let remainingWork=spent.baseMinutes
     while(remainingWork>EPS){
      const progress=advanceManufacture(m,remainingWork);remainingWork=progress.unusedBaseMinutes
      if(interval===0)collect(m.roomId)
      fund(m)
      if(!progress.consumedBaseMinutes||nextManufacturingEvent(m.state)===null)break
     }
     if(remainingWork>EPS)record('unused-drone-base-minutes',{roomId:m.roomId,amount:remainingWork})
     record('manufacture-drone',{roomId:m.roomId,amount:n})
    }
    if(!budget)break
   }
  }
  const settle=(getFrame:()=>ProductionFrame)=>{
   let frame=getFrame();synchronize(frame);synchronizeProducts(frame);finish(frame)
   if(!nativeScheduler&&(interval===0||state.time>=nextCollection-EPS)){
    collect();const collected=recycle?.collect()??0;if(collected)record('recycle-collected',{roomId:'recycle',amount:collected})
    if(interval>0)nextCollection=(Math.floor((state.time+EPS)/interval)+1)*interval
   }
   frame=getFrame();synchronize(frame);synchronizeProducts(frame);openWork(frame)
   while(true){
    const beforeSpending=serial
    spendSurplus()
    if(serial===beforeSpending)break
    finish(getFrame());collect(undefined,!nativeScheduler);openWork(getFrame())
   }
   if(state.time>=nextDailyClear-EPS){
    nextDailyClear=(Math.floor((state.time+EPS)/24)+1)*24
   }
   markObservation()
  }
  const nextStep=(maximum:number,getFrame:(offset:number)=>ProductionFrame)=>{
   let dt=Math.min(maximum,nativeScheduler?Infinity:nextCollection-state.time)
   for(const m of manufactures.values())if(m.pendingSwitch){
    if(m.pendingSwitch.readyAt!==undefined)dt=Math.min(dt,Math.max(0,m.pendingSwitch.readyAt-state.time))
    else if(!m.pendingSwitch.accelerated)dt=Math.min(dt,1/60)
   }
   const zero=getFrame(0)
   if(recycle)dt=Math.min(dt,recycle.nextEventHours(evaluateRecycleEfficiency(zero.config,{activeIds:zero.active}).efficiencyPercent))
   // Capped charging is an event; smaller numerical steps must not change spending policy.
   const targetTrade=(options.droneRoomId||options.droneTradingRoomId)?trades.get((options.droneRoomId||options.droneTradingRoomId)!):[...trades.values()][0]
   const rate=chargeRate(zero),canSpend=target==='trading'?(targetTrade?.active!==null&&targetTrade?.active!==undefined):(target!=='none'&&[...manufactures.values()].some(m=>(options.droneRoomId?m.roomId===options.droneRoomId:m.state.formula.product===target)&&nextManufacturingEvent(m.state)!==null))
   if(!nativeScheduler&&target!=='none'){
    if(canSpend&&rate>0&&drones.stock<drones.capacity-EPS)dt=Math.min(dt,(drones.capacity-drones.stock)/rate/60)
    if(nextDailyClear>state.time+EPS)dt=Math.min(dt,nextDailyClear-state.time)
   }
   const crosses=(h:number)=>{const f=getFrame(h/2)
    for(const m of manufactures.values()){const n=nextManufacturingEvent(m.state);if(n!==null&&h*60*f.evaluations[m.roomId]!.efficiencyPercent/100>=n)return true}
    for(const t of trades.values())if(t.active){const factor=t.active.base.efficiencyAffected?f.evaluations[t.roomId]!.efficiencyPercent/100:1
     let distance=t.active.remainingBaseMinutes
     if(h*60*factor>=Math.max(0,distance))return true
    }
    return false
   }
   if(crosses(dt)){let lo=0,hi=dt;for(let n=0;n<48;n++){const mid=(lo+hi)/2;if(crosses(mid))hi=mid;else lo=mid}dt=hi}
   return dt
  }
  const advance=(hours:number,frame:ProductionFrame)=>{
   if(recycle)recycle.advance(hours,evaluateRecycleEfficiency(frame.config,{activeIds:frame.active}).efficiencyPercent)
   const previous=drones;drones=generateDrones(drones,hours*60,chargeRate(frame));const accepted=drones.stock-previous.stock
   if(accepted>0)transact({drone:accepted},'drone-generated',state.time+hours)
   for(const m of manufactures.values()){
    if(m.state.blockedByStorage)m.blockedHours+=hours
    else if(m.state.awaitingPayment)m.blockedMaterialHours+=hours
    advanceManufacture(m,hours*60*frame.evaluations[m.roomId]!.efficiencyPercent/100)
   }
   for(const t of trades.values())if(t.active)t.active=advanceOrder(t.active,{elapsedMinutes:hours*60,efficiency:frame.evaluations[t.roomId]!.efficiencyPercent/100}).order;else if(!t.disabled)t.blockedHours+=hours
  }
  const report=():ProductionReport=>({success:valid,ledger,sample:{completed:completedSample(),opening:opening??{...ledger.balances},closing:{...ledger.balances},inflows:difference(ledger.inflows,openingIn),outflows:difference(ledger.outflows,openingOut),net:difference(ledger.balances,opening??ledger.balances)},materialsConsumed:{...materialsConsumed},drones,events,
   ...(recycle?{recycle:recycle.report()}:{}),
   assumptions:{outputMode,inventoryMode,allowGoldDebt:options.allowGoldDebt===true,seed,runOrderMode:'ideal',droneTarget:target,droneRoomId:options.droneRoomId,droneReserve:reserve,collectionIntervalHours:interval,orderSnapshotPolicy:'acquisition-start-v1: base draw and Pepe/Closure workload at start; U-Official/Proviso/Tequila conversion at completion; payment at collection; simultaneous facilities use schedule order'},
   manufacturing:[...manufactures.values()].map(m=>({roomId:m.roomId,product:m.state.formula.product,completedItems:m.state.lifetimeItems,sampleCompletedItems:m.state.lifetimeItems-(openingManufactured.get(m.roomId)??0),pendingItems:m.state.pendingItems,remainingBaseMinutes:m.state.remainingBaseMinutes,blockedHours:m.blockedHours,blockedMaterialHours:m.blockedMaterialHours})),
   trading:[...trades.values()].map(t=>({roomId:t.roomId,completedOrders:t.completedOrders,collectedOrders:t.collectedOrders,pendingOrders:t.pending,remainingBaseMinutes:t.active?.remainingBaseMinutes??null,blockedHours:t.blockedHours}))})
  if(switchSettings.enable)diagnostic('PRODUCT_SWITCH_SIMULATION_MODEL','切产物按当前份基础工作量、共享无人机库存及配置的损耗和等待规则推进；旧产物先收取，已有贸易订单保留。确认缓冲按暂停开工建模，未模拟设备识别、页面操作及换班前批量切换的驻场等待。')
  if(switchSettings.enable&&switchSettings.direct_when_drones_insufficient)diagnostic('PRODUCT_SWITCH_CANCEL_COST_MODEL','直接取消当前制造份时不计完成产物，保留已发生的开工扣料；游戏取消时的材料返还规则未实测。')
  if(potential)diagnostic('POTENTIAL_OUTPUT_MODEL','直观产出模式：忽略材料库存不足，设施容量与收取按 Mower 排班执行，完成即计产出；账本为测算辅助，不代表实际到账。无人机仍按所选策略及实际生成量使用。')
  diagnostic('IDEAL_RUN_ORDER_ASSUMPTIONS','理想跑单按已解锁的佩佩/可露希尔候选决定新单模式，在普通订单完成时应用 U-Official/但书/龙舌兰效果；保留 Mower 任务读取、排序与唤醒，不临时换人、不等待、不消耗跑单干员心情或无人机。常规排班和无人机目标策略仍执行。')
  diagnostic('DRONE_ALLOCATION_POLICY',nativeScheduler?`无人机由 Mower 的任务阶段使用：每 ${schedule.assumptions.droneIntervalHours ?? 3} 小时待办检查、${schedule.assumptions.droneCountLimit ?? 100} 架判断门槛；按所选设施加速，不额外消耗跑单无人机。`:`无人机采用满仓及每日彻底清空加速${options.droneRoomId&&target!=='none'?`设施(${options.droneRoomId})`:target==='gold'?'赤金':target==='exp'?'作战记录':target==='trading'?`贸易站(${options.droneTradingRoomId??'默认'})`:'关闭'}、保留 ${reserve} 架策略，以保证计算稳定。`)

  // Concrete facilities are the only owner of production timers and drone stock.
  // Native scheduling adapters read these at the observation clock, never from a
  // projected daily total or a previous task deadline.
  const nativeManufactureDroneMaximum=(room:string)=>{
   const m=manufactures.get(room)
   if(!m||nextManufacturingEvent(m.state)===null)return 0
   const batches=m.pendingSwitch?1:Math.max(0,Math.floor((m.state.capacityWeight-m.state.storedWeight+EPS)/m.state.formula.storageWeight))
   const baseMinutes=batches?m.state.remainingBaseMinutes+(batches-1)*m.state.formula.baseMinutes:0
   return Math.min(Math.floor(drones.stock+EPS),Math.ceil(Math.max(0,baseMinutes-EPS)/3))
  }
  const nativeSpendManufacturingDrones=(room:string,count:number)=>{
   const m=manufactures.get(room)
   if(!m)throw new Error('Native manufacture facility is unavailable: '+room)
   if(!Number.isInteger(count)||count<0||count>nativeManufactureDroneMaximum(room))throw new Error('Native manufacture drone selection exceeds available work')
   if(count===0)return
   const spent=spendDrones(drones,count);drones=spent.state
   transact({drone:-count},'native-manufacture-drone')
   let work=spent.baseMinutes
   while(work>EPS){
    fund(m)
    const progress=advanceManufacture(m,work);work=progress.unusedBaseMinutes
    fund(m)
    if(!progress.consumedBaseMinutes||nextManufacturingEvent(m.state)===null)break
   }
   if(work>EPS)record('unused-drone-base-minutes',{roomId:room,amount:work})
   record('native-manufacture-drone',{roomId:room,amount:count})
  }
  const nativeRemainingSeconds=(room:string,frame:ProductionFrame)=>{
   const trade=trades.get(room)
   if(!trade)throw new Error('Native trade facility is unavailable: '+room)
   const active=trade.active
   if(!active)return 0
   const efficiency=active.base.efficiencyAffected?frame.evaluations[room]!.efficiencyPercent/100:1
   if(efficiency<=0)throw new Error('Native trade timer is unavailable: '+room)
   return Math.max(0,active.remainingBaseMinutes/efficiency*60)
  }
  const nativeSpendTradeDrones=(room:string,count:number,frame:ProductionFrame)=>{
   const trade=trades.get(room)
   if(!trade?.active)throw new Error('Native drone request requires a current trade order: '+room)
   if(trade.active.base.mode==='pepe')throw new Error('Pepe drone interaction is unverified')
   const spent=spendDrones(drones,count)
   drones=spent.state
   transact({drone:-count},'native-trade-drone')
   trade.active=advanceOrder(trade.active,{elapsedMinutes:0,efficiency:1,droneBaseMinutes:spent.baseMinutes}).order
   record('native-trade-drone',{roomId:room,amount:count})
   finish(frame);openWork(frame)
  }
  const nativeAcceptOrder=(room:string,frame:ProductionFrame)=>{finish(frame);const trade=trades.get(room);if(!trade)throw new Error('Native trade facility is unavailable: '+room);const before=trade.collectedOrders;collect(room,true,false,1);openWork(frame);return trade.collectedOrders>before}
  return {settle,nextStep,advance,report,actualProducts,
   nativePendingRecycleItems:()=>recycle?.report().pendingItems??0,
   nativeCollectRecycleItems:()=>{const collected=recycle?.collect()??0;if(collected)record('recycle-collected',{roomId:'recycle',amount:collected})},
   nativeHasTrade:(room:string)=>trades.has(room),nativeHasManufacture:(room:string)=>manufactures.has(room),nativeManufactureDroneMaximum,nativeSpendManufacturingDrones,
   nativePendingTradeOrders:(room?:string)=>[...trades.values()].filter(t=>room===undefined||t.roomId===room).reduce((n,t)=>n+t.pending.length,0),
   nativePendingManufacturingItems:()=>[...manufactures.values()].reduce((n,m)=>n+m.state.pendingItems,0),
   nativeCollectTradeOrders:(frame:ProductionFrame)=>{finish(frame);collect(undefined,true,false);openWork(frame)},
   nativeCollectManufacturingItems:(frame:ProductionFrame)=>{finish(frame);collect(undefined,false,true);openWork(frame)},
   nativeRemainingSeconds,nativeTradeDroneAvailable:(room:string)=>trades.get(room)?.active?.base.mode!=='pepe',nativeTradeRequiredDrones:(room:string)=>{const active=trades.get(room)?.active;return active&&active.base.mode!=='pepe'?Math.ceil(Math.max(0,active.remainingBaseMinutes-EPS)/3):0},nativeSpendTradeDrones,nativeAcceptOrder,nativeDroneCount:()=>Math.floor(drones.stock+EPS)}

}
