/**
 * Native reload 7985-8015, alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88.
 * MIT, Copyright 2021 Nano. Page/recognition/action results are explicit I/O.
 */
export interface MowerReloadState {
 rooms:readonly string[];reloadTimeMicros:number|null
 width:number;height:number;waitingScenes:readonly string[]
}
export type MowerReloadRequest=
 |{kind:'enter-room';room:string}
 |{kind:'tap';target:[number,number];intervalSeconds:.25|.5}
 |{kind:'scene'|'waiting-solver'|'update'|'back'}
 |{kind:'navigate';scene:'INFRA_MAIN'}
 |{kind:'save-exception';errorType:string;message:string}
export interface MowerReloadObservation {kind:MowerReloadRequest['kind'];value:unknown;observedAtMicros:number}
export interface MowerReloadSeam {
 nowMicros():number
 /** Use the shared native exit class (including subclasses), not matching error-message text. */
 isMowerExit(error:unknown):boolean
}
export type MowerReloadGenerator=Generator<MowerReloadRequest,null,MowerReloadObservation>

function nativeTruthy(value:unknown):boolean {
 if(value===null||value===undefined||value===false||value===0||value==='')return false
 if(Array.isArray(value))return value.length!==0
 return typeof value!=='object'||Object.keys(value).length!==0
}
function* observed(seam:MowerReloadSeam,request:MowerReloadRequest):Generator<MowerReloadRequest,unknown,MowerReloadObservation>{
 const response=yield request
 if(!response||response.kind!==request.kind||!Object.prototype.hasOwnProperty.call(response,'value')||response.value===undefined)
  throw new Error('Explicit matching reload observation is required; None is null')
 if(!Number.isSafeInteger(response.observedAtMicros)||response.observedAtMicros!==seam.nowMicros())
  throw new Error('Reload observation must describe the advanced scheduler wall clock')
 return response.value
}
/**
 * Errors recovered to infra_main do not abort later rooms, but suppress the final timestamp.
 * The fourth recovery back rethrows the original object; recovery I/O errors propagate themselves.
 * Empty rooms still executes the native timestamp tail, with no invented device success response.
 */
export function* executeMowerReload(state:MowerReloadState,seam:MowerReloadSeam):MowerReloadGenerator{
 let error=false
 for(const room of state.rooms){
  try{
   yield* observed(seam,{kind:'enter-room',room})
   for(let i=0;i<3;i++)yield* observed(seam,{kind:'tap',target:[state.width*.05,state.height*.95],intervalSeconds:.25})
   yield* observed(seam,{kind:'tap',target:[state.width*.75,state.height*.3],intervalSeconds:.5})
   yield* observed(seam,{kind:'tap',target:[state.width*.75,state.height*.9],intervalSeconds:.5})
   const page=yield* observed(seam,{kind:'scene'})
   if(typeof page==='string'&&state.waitingScenes.includes(page)){
    if(!nativeTruthy(yield* observed(seam,{kind:'waiting-solver'})))return null
   }
   yield* observed(seam,{kind:'navigate',scene:'INFRA_MAIN'})
  }catch(caught){
   if(seam.isMowerExit(caught))throw caught
   yield* observed(seam,{kind:'save-exception',errorType:caught instanceof Error?caught.name:typeof caught,message:caught instanceof Error?caught.message:String(caught)})
   error=true
   yield* observed(seam,{kind:'update'})
   let backCount=0
   while((yield* observed(seam,{kind:'scene'}))!=='INFRA_MAIN'){
    yield* observed(seam,{kind:'back'})
    backCount++
    if(backCount>3)throw caught
   }
  }
 }
 if(!error)state.reloadTimeMicros=seam.nowMicros()
 return null
}
