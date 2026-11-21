/**
 * Ordinary trade/manufacture drone tasks.
 * Source c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
 * Manufacturing reserve correction: select MAX, then subtract the configured reserve.
 * Observed absolute deadlines/counts and device timing come from I/O; no production fitting.
 */
export interface MowerDroneOperationState {
  retainManufacturingReserve:boolean
  readonly repeatTradeAcceleration:boolean
  room:string
  width:number
  height:number
  skipEnter:boolean
  notCustomize:boolean
  notReturn:boolean
  droneCountLimit:number
  waitingScenes:readonly unknown[]
}
export type MowerDroneOperationRequest=
  |{kind:'enter-room';room:string}
  |{kind:'tap';action:'detail'|'all-in'|'confirm-all'|'minus-reserve'|'confirm-manufacture';target:unknown;intervalSeconds?:3|0.1;yRate?:1}
  |{kind:'wait-interface';intervalSeconds:1|3;accelerateTemplate?:'bill_accelerate'}
  |{kind:'find';name:'manufacture_accelerate'|'bill_accelerate'}
  |{kind:'tap-drone-accelerate';template:'bill_accelerate'|'manufacture_accelerate';control:'all_in'}
  |{kind:'cache-facility-page';room:string;facility:'manufacture'}
  |{kind:'recog-update'}
  |{kind:'accept-order'}
  |{kind:'return-main'}
  |{kind:'read-drone-count'}
  |{kind:'scene'}
  |{kind:'waiting-solver'}
export interface MowerDroneOperationObservation {
  kind:MowerDroneOperationRequest['kind']
  observedAtMicros:number
  /** Explicit value for every step; None is null. */
  value:unknown
}
export interface MowerDroneOperationSeam {
  nowMicros():number
}
export type MowerDroneOperationGenerator=Generator<MowerDroneOperationRequest,false|null,MowerDroneOperationObservation>
function* observed(
  seam:MowerDroneOperationSeam,request:MowerDroneOperationRequest,
):Generator<MowerDroneOperationRequest,unknown,MowerDroneOperationObservation>{
  const observation=yield request
  if(!observation||observation.kind!==request.kind||!Object.prototype.hasOwnProperty.call(observation,'value')||observation.value===undefined)
    throw new Error('Explicit matching native drone observation is required; None is null')
  if(!Number.isSafeInteger(observation.observedAtMicros)||observation.observedAtMicros!==seam.nowMicros())
    throw new Error('Drone observation must describe the advanced scheduler wall clock')
  return observation.value
}
function finite(value:unknown,label:string):number{
  if(typeof value!=='number'||!Number.isFinite(value))throw new Error('Explicit '+label+' observation is required')
  return value
}
function nativeTruthy(value:unknown):boolean{
  if(value===null||value===false||value===0||value==='')return false
  if(Array.isArray(value))return value.length!==0
  if(typeof value==='object')return Object.keys(value).length!==0
  return true
}
function* waitingAfterTap(
  state:MowerDroneOperationState,seam:MowerDroneOperationSeam,
):Generator<MowerDroneOperationRequest,boolean,MowerDroneOperationObservation>{
  const scene=yield* observed(seam,{kind:'scene'})
  if(state.waitingScenes.includes(scene)){
    const result=yield* observed(seam,{kind:'waiting-solver'})
    if(typeof result!=='boolean')throw new Error('Explicit waiting-solver result is required')
    return result
  }
  return true
}
/** Full native drone facility branch. Selected quantity remains a device observation/action effect. */
export function* executeMowerDroneOperation(
  state:MowerDroneOperationState,seam:MowerDroneOperationSeam,
):MowerDroneOperationGenerator{
  const retainReserve=state.retainManufacturingReserve
  if(!state.skipEnter)yield* observed(seam,{kind:'enter-room',room:state.room})
  yield* observed(seam,{kind:'tap',action:'detail',target:[state.width*.05,state.height*.95],intervalSeconds:3})
  yield* observed(seam,{kind:'wait-interface',intervalSeconds:3})
  const manufacture=yield* observed(seam,{kind:'find',name:'manufacture_accelerate'})
  if(nativeTruthy(manufacture)){
    yield* observed(seam,{kind:'cache-facility-page',room:state.room,facility:'manufacture'})
    const count=finite(yield* observed(seam,{kind:'read-drone-count'}),'drone-count')
    if(count<state.droneCountLimit)return null
    const allInScope=yield* observed(seam,{kind:'tap-drone-accelerate',template:'manufacture_accelerate',control:'all_in'})
    yield* observed(seam,{kind:'tap',action:'all-in',target:allInScope})
    if(retainReserve){
      const tapTimes=state.droneCountLimit
      if(!Number.isSafeInteger(tapTimes))throw new Error('Native manufacture minus count must be an integer')
      for(let tap=0;tap<tapTimes;tap+=1)
        yield* observed(seam,{kind:'tap',action:'minus-reserve',target:[state.width*.7,state.height*.5],intervalSeconds:.1})
    }
    yield* observed(seam,{kind:'tap',action:'confirm-manufacture',target:manufacture,yRate:1})
  }else{
  let accelerate=yield* observed(seam,{kind:'find',name:'bill_accelerate'})
  while(nativeTruthy(accelerate)){
    const allIn=yield* observed(seam,{kind:'tap-drone-accelerate',template:'bill_accelerate',control:'all_in'})
    yield* observed(seam,{kind:'tap',action:'all-in',target:allIn})
    yield* observed(seam,{kind:'tap',action:'confirm-all',target:[state.width*.75,state.height*.8]})
    if(!(yield* waitingAfterTap(state,seam)))return null
    yield* observed(seam,{kind:'recog-update'})
    yield* observed(seam,{kind:'accept-order'})
    if(!state.repeatTradeAcceleration)break
    if(state.notCustomize){
      const count=finite(yield* observed(seam,{kind:'read-drone-count'}),'drone-count')
      if(count<state.droneCountLimit||count===201)break
    }
    accelerate=yield* observed(seam,{kind:'find',name:'bill_accelerate'})
  }
  }
  if(state.notReturn)return null
  yield* observed(seam,{kind:'return-main'})
  return null
}
