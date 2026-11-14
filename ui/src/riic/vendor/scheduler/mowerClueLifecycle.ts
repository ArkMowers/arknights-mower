/**
 * ArkMowers alpha c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 default clue lifecycle.
 * MIT, Copyright 2021 Nano. Explicit UI observations are not pixel-equivalence.
 */
import {MowerTask,MOWER_TASK_TYPES,fromMowerMicros,roundMowerMicros,type MowerTaskQueue} from './mowerTaskQueue'
import type {MowerNotificationFlags} from './mowerNotification'
export type MowerClueScene='INFRA_MAIN'|'INFRA_DETAILS'|'CLUE_MESSAGE_BOARD'|'INFRA_CONFIDENTIAL'|'CLUE_DAILY'|'CLUE_RECEIVE'|'CLUE_PLACE'|'CLUE_GIVE_AWAY'|'CLUE_SUMMARY'|'INFRA_ARRANGE_ORDER'|string
export interface MowerClueLifecycleState {
 queue:MowerTaskQueue;flags:MowerNotificationFlags
 partyTimeMicros:number|null
 /** Native op_data cache can contain bool; the ordinary setter preserves non-date values. */
 dataPartyTime:number|boolean|null
 lastClueMicros:number|null
 leifengMode:boolean;clueCount:number;clueCountLimit:number
 mall:{shouldRunMowerMall?:boolean;maaMallEnable:boolean;maaMallMode:string}
 waitingScenes:readonly string[]
}
export type MowerClueRequest=
 |{kind:'navigate';scene:'INFRA_MAIN'}
 |{kind:'enter-room';room:'meeting'}
 |{kind:'scene'|'update'|'back'|'wait-product'|'waiting-solver'|'credit-shop-run'}
 |{kind:'find';name:string;scope:unknown}
 |{kind:'tap';target:unknown;interval:number}
 |{kind:'ctap';target:unknown}
 |{kind:'tap-element';name:string}
 |{kind:'sleep';seconds:number}
 |{kind:'color';target:unknown}
 |{kind:'clue-classify';scope:'daily'|'receive'}
 |{kind:'friend-name';scope:unknown}
 |{kind:'read-time';scope:unknown;default:null}
 |{kind:'backup-plan';timing:null}
 |{kind:'save-exception';message:string}
export interface MowerClueObservation {kind:MowerClueRequest['kind'];value:unknown;observedAtMicros:number}
export interface MowerClueSeam {nowMicros():number}
export type MowerClueGenerator=Generator<MowerClueRequest,null,MowerClueObservation>

function nativeTruthy(value:unknown):boolean {
 if(value===null||value===undefined||value===false||value===0||value==='')return false
 if(Array.isArray(value))return value.length!==0
 return typeof value!=='object'||Object.keys(value).length!==0
}
function* observed(seam:MowerClueSeam,request:MowerClueRequest):Generator<MowerClueRequest,unknown,MowerClueObservation> {
 const response=yield request
 if(!response||response.kind!==request.kind||!Object.prototype.hasOwnProperty.call(response,'value')||response.value===undefined)
  throw new Error('Explicit matching clue observation is required; None is null')
 if(!Number.isSafeInteger(response.observedAtMicros)||response.observedAtMicros!==seam.nowMicros())
  throw new Error('Clue observation must describe the advanced scheduler wall clock')
 return response.value
}
/** base_schedule.py:330-338; the local clear must not erase an unexpired op_data prediction. */
export function setMowerPartyTime(state:MowerClueLifecycleState,value:number|null,seam:MowerClueSeam):void {
 state.partyTimeMicros=value
 if(state.dataPartyTime===null||typeof state.dataPartyTime==='number'&&state.dataPartyTime<=seam.nowMicros())
  state.dataPartyTime=value
}
/** A confirmed UI read overrides the prediction even when the old prediction is in the future. */
export function setMowerDetectedPartyTime(state:MowerClueLifecycleState,value:number|null):void {
 state.partyTimeMicros=value;state.dataPartyTime=value
}
/** read_time returns remaining seconds. The clock is read after the device read returns. */
export function* readMowerPartyTime(seam:MowerClueSeam):Generator<MowerClueRequest,number|null,MowerClueObservation> {
 const seconds=yield* observed(seam,{kind:'read-time',scope:[[1768,438],[1902,480]],default:null})
 if(seconds===null)return null
 if(typeof seconds!=='number'||!Number.isFinite(seconds))throw new Error('Explicit party countdown seconds or null is required')
 const result=seam.nowMicros()+roundMowerMicros(seconds*1_000_000)
 if(!Number.isSafeInteger(result))throw new Error('Invalid Mower party time')
 return result
}
function* find(seam:MowerClueSeam,name:string,scope:unknown=null){return yield* observed(seam,{kind:'find',name,scope})}
function* tap(seam:MowerClueSeam,target:unknown,interval:number=1){yield* observed(seam,{kind:'tap',target,interval})}
function* scene(seam:MowerClueSeam){
 const value=yield* observed(seam,{kind:'scene'})
 if(typeof value!=='string')throw new Error('Explicit native clue scene is required')
 return value
}
/** Actual BaseSolver.get_pos: recognition scopes/rectangles use truncated center pixels. */
function position(target:unknown):[number,number] {
 if(!Array.isArray(target))throw new Error('Invalid native clue location')
 const point=(value:unknown):[number,number]=>{
  if(!Array.isArray(value)||typeof value[0]!=='number'||typeof value[1]!=='number')
   throw new Error('Invalid native clue coordinate')
  return [value[0],value[1]]
 }
 let x:number,y:number
 if(target.length===4){
  const a=point(target[0]),b=point(target[1]),c=point(target[2]),d=point(target[3])
  x=(a[0]+b[0]+c[0]+d[0])/4;y=(a[1]+d[1]+b[1]+c[1])/4
 }else if(target.length===2&&Array.isArray(target[0])){
  const a=point(target[0]),b=point(target[1]);x=(a[0]+b[0])/2;y=(a[1]+b[1])/2
 }else [x,y]=point(target)
 return [Math.trunc(x),Math.trunc(y)]
}
function* unlock(seam:MowerClueSeam){
 const target=yield* find(seam,'clue/button_unlock')
 if(target===null)return null
 const color=yield* observed(seam,{kind:'color',target:position(target)})
 if(!Array.isArray(color)||color.length!==3||color.some(v=>typeof v!=='number'))throw new Error('Explicit RGB unlock color is required')
 return color.every(v=>v>252)?target:null
}
/**
 * Complete reachable default clue_new control flow, including its local CTM and catch.
 * The original clue_status dictionary is never populated: candidate-list placement code
 * is unreachable from this function; fast_place and the empty-status unlock branch are live.
 * The host must run actual backup/shop cores before replying to their requests.
 */
export function* executeMowerClueNew(state:MowerClueLifecycleState,seam:MowerClueSeam):MowerClueGenerator {
 try{
  yield* observed(seam,{kind:'navigate',scene:'INFRA_MAIN'})
  yield* observed(seam,{kind:'enter-room',room:'meeting'})
  type Stage='message_board'|'daily'|'receive'|'place'|'give_away'|'party_time'
  const stages:Stage[]=['message_board','daily','receive','place','give_away','party_time']
  const complete=(stage:Stage)=>{const index=stages.indexOf(stage);if(index>=0)stages.splice(index,1)}
  const exit=[1239,144],bottomLeft=[680,1000]
  while(stages.length){
   const current=stages[0]!,page=yield* scene(seam)
   if(page==='INFRA_DETAILS'){
    if(current==='message_board'){
     yield* observed(seam,{kind:'wait-product'})
     if(nativeTruthy(yield* find(seam,'clue/title_party')))
      yield* observed(seam,{kind:'tap-element',name:'clue/title_party'})
     yield* observed(seam,{kind:'update'})
     let board=yield* find(seam,'clue/message_board')
     if(board===null){
      yield* tap(seam,bottomLeft)
      for(let i=0;i<3;i++){
       yield* observed(seam,{kind:'update'})
       board=yield* find(seam,'clue/message_board')
       if(nativeTruthy(board))break
       yield* observed(seam,{kind:'sleep',seconds:.5})
      }
     }
     if(nativeTruthy(board)){
      yield* tap(seam,board)
      let opened=false
      for(let i=0;i<6;i++){
       yield* observed(seam,{kind:'sleep',seconds:.5})
       yield* observed(seam,{kind:'update'})
       if((yield* scene(seam))==='CLUE_MESSAGE_BOARD'){opened=true;break}
      }
      if(opened){
       const collect=yield* find(seam,'clue/message_board_collect')
       if(nativeTruthy(collect)){
        yield* tap(seam,collect)
        for(let i=0;i<6;i++){
         yield* observed(seam,{kind:'sleep',seconds:.5})
         yield* observed(seam,{kind:'update'})
         if(!nativeTruthy(yield* find(seam,'clue/message_board_collect'))){
          yield* tap(seam,bottomLeft);break
         }
        }
       }
       yield* observed(seam,{kind:'back'})
       for(let i=0;i<4;i++){
        yield* observed(seam,{kind:'update'})
        if((yield* scene(seam))==='INFRA_DETAILS')break
        yield* observed(seam,{kind:'sleep',seconds:.5})
       }
      }
     }
     complete('message_board')
    }else if(current==='party_time'){
     yield* observed(seam,{kind:'wait-product'})
     const check=yield* find(seam,'clue/check_party')
     if(nativeTruthy(check))yield* tap(seam,check)
     const party=yield* readMowerPartyTime(seam)
     if(party!==null&&party>seam.nowMicros()){
      setMowerDetectedPartyTime(state,party)
      if(!state.queue.find({type:MOWER_TASK_TYPES.CLUE_PARTY}))
       state.queue.tasks.push(new MowerTask({time:fromMowerMicros(party-1000),type:MOWER_TASK_TYPES.CLUE_PARTY}))
     }else setMowerDetectedPartyTime(state,null)
     yield* observed(seam,{kind:'backup-plan',timing:null})
     complete('party_time')
    }else yield* tap(seam,[330,1000])
   }else if(page==='CLUE_MESSAGE_BOARD'){
    yield* observed(seam,{kind:'back'})
   }else if(page==='INFRA_CONFIDENTIAL'){
    if(current==='daily'){
     if(nativeTruthy(yield* find(seam,'clue/badge_new',[[1815,200],[1895,250]])))yield* tap(seam,[1800,270])
     else complete('daily')
    }else if(current==='receive'){
     if(nativeTruthy(yield* find(seam,'clue/badge_new',[[1815,360],[1895,410]])))yield* observed(seam,{kind:'ctap',target:[1800,430]})
     else complete('receive')
    }else if(current==='place'){
     const fast=yield* find(seam,'clue/fast_place')
     if(nativeTruthy(fast)){
      yield* tap(seam,fast,2)
      const target=yield* unlock(seam)
      if(nativeTruthy(target))yield* tap(seam,target)
     }
     complete('place')
    }else if(current==='give_away')yield* observed(seam,{kind:'ctap',target:[1799,578]})
    else if(current==='party_time')yield* observed(seam,{kind:'back'})
   }else if(page==='CLUE_DAILY'){
    let clue:unknown=null
    if(!nativeTruthy(yield* find(seam,'clue/icon_notification',[[1400,0],[1920,400]])))
     clue=yield* observed(seam,{kind:'clue-classify',scope:'daily'})
    if(nativeTruthy(clue)){
     yield* observed(seam,{kind:'tap-element',name:'clue/button_get'});complete('daily')
    }else yield* tap(seam,[1484,152])
   }else if(page==='CLUE_RECEIVE'){
    yield* observed(seam,{kind:'wait-product'})
    const clue=yield* observed(seam,{kind:'clue-classify',scope:'receive'})
    if(nativeTruthy(clue)){
     const scope=[[1580,220],[1880,255]]
     const name=yield* observed(seam,{kind:'friend-name',scope})
     if(name!==null&&typeof name!=='string')throw new Error('Explicit friend OCR text or null is required')
     yield* tap(seam,scope)
    }else{complete('receive');yield* tap(seam,exit)}
   }else if(page==='CLUE_PLACE'){
    const target=yield* unlock(seam)
    if(nativeTruthy(target))yield* tap(seam,target)
    else{complete('place');yield* tap(seam,exit)}
   }else if(page==='CLUE_GIVE_AWAY'){
    if(state.leifengMode||state.clueCount>state.clueCountLimit){
     const fast=yield* find(seam,'clue/fast_giveaway')
     if(nativeTruthy(fast))yield* tap(seam,fast)
    }
    complete('give_away');yield* tap(seam,[1868,54])
   }else if(page==='CLUE_SUMMARY'||page==='INFRA_ARRANGE_ORDER')yield* observed(seam,{kind:'back'})
   else if(state.waitingScenes.includes(page))yield* observed(seam,{kind:'waiting-solver'})
   else{
    yield* observed(seam,{kind:'navigate',scene:'INFRA_MAIN'})
    yield* observed(seam,{kind:'enter-room',room:'meeting'})
   }
  }
  if(state.mall.shouldRunMowerMall??(state.mall.maaMallEnable&&state.mall.maaMallMode==='mower')){
   yield* observed(seam,{kind:'credit-shop-run'})
   yield* observed(seam,{kind:'navigate',scene:'INFRA_MAIN'})
  }
 }catch(error){
  yield* observed(seam,{kind:'save-exception',message:error instanceof Error?error.message:String(error)})
 }
 return null
}
/** CLUE/CLUE_PARTY wrapper; ordinary todo calls clue_new directly and updates last_clue itself. */
export function* runMowerClueFlow(state:MowerClueLifecycleState,seam:MowerClueSeam):MowerClueGenerator {
 setMowerPartyTime(state,null,seam)
 yield* executeMowerClueNew(state,seam)
 state.lastClueMicros=seam.nowMicros()
 state.flags.collectNotification=true
 return null
}
