/**
 * Native accept_order body at alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88:7752-7783.
 * MIT, Copyright 2021 Nano. Device recognition and action duration are explicit I/O.
 * A completed order is collected only by the tap-accept-order request, never by a read.
 */
import {MOWER_TASK_TYPES as T,type MowerTask} from './mowerTaskQueue'
export interface MowerAcceptOrderState { task:MowerTask|null;width:number;height:number }
export type MowerAcceptOrderRequest=
 |{kind:'cache-trade-page';room:string;facility:'trade'}
 |{kind:'find-order-ready';name:'order_ready';scope:[[450,675],[600,750]]}
 |{kind:'recog-update'}
 |{kind:'sleep';seconds:0.5|0.15}
 |{kind:'read-buff-scores'}
 |{kind:'has-distinct-buff';scores:unknown}
 |{kind:'is-stable-buff';scores:unknown;newScores:unknown}
 |{kind:'save-screencap';category:'run_order'}
 |{kind:'save-order-image'}
 |{kind:'tap-accept-order';target:[number,number];intervalSeconds:0.5}
export interface MowerAcceptOrderObservation {
 kind:MowerAcceptOrderRequest['kind'];observedAtMicros:number
 /** Explicit source method response; native None is null. */
 value:unknown
}
export interface MowerAcceptOrderSeam { nowMicros():number }
export type MowerAcceptOrderGenerator=Generator<MowerAcceptOrderRequest,null,MowerAcceptOrderObservation>
function* observed(seam:MowerAcceptOrderSeam,request:MowerAcceptOrderRequest):
 Generator<MowerAcceptOrderRequest,unknown,MowerAcceptOrderObservation>{
 const observation=yield request
 if(!observation||observation.kind!==request.kind||!Object.prototype.hasOwnProperty.call(observation,'value')||observation.value===undefined)
  throw new Error('Explicit matching accept_order observation is required; None is null')
 if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
  throw new Error('accept_order observation must describe the advanced scheduler wall clock')
 return observation.value
}
function boolean(value:unknown):boolean{
 if(typeof value!=='boolean')throw new Error('Explicit order-reader predicate observation is required')
 return value
}
export function* acceptMowerTradeOrders(state:MowerAcceptOrderState,seam:MowerAcceptOrderSeam):MowerAcceptOrderGenerator{
 if(state.task!==null&&state.task.type===T.RUN_ORDER&&state.task.metadata)
  yield* observed(seam,{kind:'cache-trade-page',room:state.task.metadata,facility:'trade'})
 let wait=0
 // Both native loops use identity with None; a false response is not None.
 while((yield* observed(seam,{kind:'find-order-ready',name:'order_ready',scope:[[450,675],[600,750]]}))===null){
  if(wait>6)break
  yield* observed(seam,{kind:'recog-update'})
  yield* observed(seam,{kind:'sleep',seconds:0.5})
  wait+=1
 }
 let notTake=true
 while((yield* observed(seam,{kind:'find-order-ready',name:'order_ready',scope:[[450,675],[600,750]]}))!==null){
  if(notTake){
   let scores=yield* observed(seam,{kind:'read-buff-scores'})
   if(!boolean(yield* observed(seam,{kind:'has-distinct-buff',scores}))){
    for(let attempt=0;attempt<2;attempt+=1){
     yield* observed(seam,{kind:'sleep',seconds:0.15})
     yield* observed(seam,{kind:'recog-update'})
     const newScores=yield* observed(seam,{kind:'read-buff-scores'})
     if(boolean(yield* observed(seam,{kind:'has-distinct-buff',scores:newScores}))||
        boolean(yield* observed(seam,{kind:'is-stable-buff',scores,newScores})))break
     scores=newScores
    }
   }
   yield* observed(seam,{kind:'save-screencap',category:'run_order'})
   yield* observed(seam,{kind:'save-order-image'})
   notTake=false
  }
  yield* observed(seam,{kind:'tap-accept-order',target:[state.width*0.25,state.height*0.25],intervalSeconds:0.5})
 }
 return null
}
