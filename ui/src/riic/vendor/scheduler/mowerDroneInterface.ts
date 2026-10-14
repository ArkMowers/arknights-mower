import {MowerRecognizeError} from './mowerNativeErrors'
/**
 * Native _wait_drone_interface 4176-4224 and _tap_drone_accelerate 4747-4778,
 * alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
 * Recognition and primitive actions are explicit I/O; retry state is executed here.
 * A sleep with no seconds uses native BaseSolver.sleep default 1s and recognition update.
 */
export interface MowerDroneInterfaceState {width:number;height:number}
export interface MowerDroneInterfaceWaitOptions {intervalSeconds?:number;accelerateTemplate?:string|null;pageTemplate?:string|null}
export interface MowerDroneAccelerateOptions {accelerateTemplate:string;allInTemplate:string;maxRetry?:number;intervalSeconds?:number}
export type MowerDroneInterfaceRequest=
 |{kind:'find';name:string}
 |{kind:'sleep';seconds?:0.2|0.5}
 |{kind:'tap';action:'open-order'|'close-detail'|'accelerate';target:unknown;intervalSeconds:number}
export interface MowerDroneInterfaceObservation {
 kind:MowerDroneInterfaceRequest['kind'];observedAtMicros:number;value:unknown
}
export interface MowerDroneInterfaceSeam {
 nowMicros():number
 /** Instrumentation only: native timed_step finally leaves its timing frame on success/error. */
 onTimingEnter?(name:'order_navigation'):void
 onTimingLeave?(name:'order_navigation'):void
}
export type MowerDroneInterfaceGenerator=Generator<MowerDroneInterfaceRequest,unknown,MowerDroneInterfaceObservation>
export class MowerDroneRecognizeError extends MowerRecognizeError {}
function* observed(seam:MowerDroneInterfaceSeam,request:MowerDroneInterfaceRequest):
 Generator<MowerDroneInterfaceRequest,unknown,MowerDroneInterfaceObservation>{
 const observation=yield request
 if(!observation||observation.kind!==request.kind||!Object.prototype.hasOwnProperty.call(observation,'value')||observation.value===undefined)
  throw new Error('Explicit matching drone-interface observation is required; None is null')
 if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
  throw new Error('Drone-interface observation must describe the advanced scheduler wall clock')
 return observation.value
}
function truthy(value:unknown):boolean{
 if(value===null||value===false||value===0||value==='')return false
 if(Array.isArray(value))return value.length!==0
 if(typeof value==='object')return Object.keys(value).length!==0
 return true
}
function* anyTemplate(seam:MowerDroneInterfaceSeam,templates:readonly string[]):
 Generator<MowerDroneInterfaceRequest,boolean,MowerDroneInterfaceObservation>{
 for(const name of templates)if((yield* observed(seam,{kind:'find',name}))!==null)return true
 return false
}
export function* waitMowerDroneInterface(
 state:MowerDroneInterfaceState,seam:MowerDroneInterfaceSeam,options:MowerDroneInterfaceWaitOptions={},
):MowerDroneInterfaceGenerator{
 seam.onTimingEnter?.('order_navigation')
 try{
  const interval=options.intervalSeconds??0.2,accelerate=options.accelerateTemplate??null,page=options.pageTemplate??null
  const templates=accelerate!==null?[accelerate]:['manufacture_accelerate','bill_accelerate']
  let pending:'open-order'|'close-detail'|null=null,retryReady=false
  for(let attempt=0;attempt<10;attempt+=1){
   if(truthy(yield* observed(seam,{kind:'find',name:'connecting'}))){
    retryReady=false
    yield* observed(seam,{kind:'sleep'})
    continue
   }
   if(yield* anyTemplate(seam,templates))return null
   const close=yield* observed(seam,{kind:'find',name:'arrange_check_in_on'})
   const action=close!==null?'close-detail':'open-order'
   if(page!==null&&pending==='open-order'&&(yield* observed(seam,{kind:'find',name:page}))!==null)return null
   if(pending===action&&!retryReady){
    retryReady=true
    yield* observed(seam,{kind:'sleep',seconds:0.2})
    continue
   }
   yield* observed(seam,{kind:'tap',action,target:close!==null?close:[state.width*.05,state.height*.95],intervalSeconds:interval})
   pending=action;retryReady=false
  }
  let ready=yield* anyTemplate(seam,templates)
  if(page!==null&&pending==='open-order')
   ready=ready||(yield* observed(seam,{kind:'find',name:page}))!==null
  // Native reads connecting even when ready is true.
  if(truthy(yield* observed(seam,{kind:'find',name:'connecting'}))||!ready)
   throw new MowerDroneRecognizeError('未成功进入订单或制造详情界面')
  return null
 }finally{seam.onTimingLeave?.('order_navigation')}
}
export function* tapMowerDroneAccelerate(
 seam:MowerDroneInterfaceSeam,options:MowerDroneAccelerateOptions,
):MowerDroneInterfaceGenerator{
 const maxRetry=options.maxRetry??3,interval=options.intervalSeconds??1
 let accelerate=yield* observed(seam,{kind:'find',name:options.accelerateTemplate})
 if(!Number.isSafeInteger(maxRetry))throw new TypeError("'float' object cannot be interpreted as an integer")
 for(let attempt=0;attempt<maxRetry;attempt+=1){
  if(accelerate===null)break
  yield* observed(seam,{kind:'tap',action:'accelerate',target:accelerate,intervalSeconds:interval})
  let allIn=yield* observed(seam,{kind:'find',name:options.allInTemplate})
  if(allIn!==null)return allIn
  accelerate=yield* observed(seam,{kind:'find',name:options.accelerateTemplate})
  if(accelerate===null){
   yield* observed(seam,{kind:'sleep',seconds:0.5})
   allIn=yield* observed(seam,{kind:'find',name:options.allInTemplate})
   if(allIn!==null)return allIn
   break
  }
 }
 throw new MowerDroneRecognizeError('无人机加速面板未出现：未识别到 '+options.allInTemplate)
}
