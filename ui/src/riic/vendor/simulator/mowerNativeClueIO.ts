import type {RuntimeState,RuntimeRates} from '../scheduler/rosterRuntime'
import type {MowerClueObservation} from '../scheduler/mowerClueLifecycle'
import {toMowerMicros} from '../scheduler/mowerTaskQueue'

/** Explicit empty clue inventory and stable UI input; native clue policy runs separately. */
export function createMowerClueIO(state:RuntimeState):Pick<RuntimeRates,'mowerClueIO'> {
 const ui=state.mowerUI??={scene:'INFRA_MAIN',lastRoom:''}
 let ctapSite='',ctapAt:number|null=null
 const now=()=>toMowerMicros(state.time)
 const end=state.config.mowerClueObservations?.partyEndMicros??null
 return {mowerClueIO:request=>{
  const delay=request.kind==='tap'?request.interval:request.kind==='sleep'?request.seconds:
   request.kind==='ctap'||request.kind==='back'?1:0
  return {
   delayMicros:toMowerMicros(delay/3600),
   observe:():MowerClueObservation=>{
    let value:unknown=null
    switch(request.kind){
     case 'navigate':ui.scene='INFRA_MAIN';break
     case 'enter-room':ui.scene='INFRA_DETAILS';ui.lastRoom=request.room;break
     case 'scene':value=ui.scene;break
     case 'find':break // Explicit no badges, board reward, place set or giveaway in this input.
     case 'tap':{
      const point=request.target
      if(Array.isArray(point)&&point[0]===330&&point[1]===1000)ui.scene='INFRA_CONFIDENTIAL'
      if(Array.isArray(point)&&point[0]===1868&&point[1]===54)ui.scene='INFRA_CONFIDENTIAL'
      break
     }
     case 'ctap':{
      const site=JSON.stringify(request.target),current=now()-1_000_000
      if(ctapSite!==site||ctapAt===null||current-ctapAt>10_000_000){
       ctapSite=site;ctapAt=current
       if(site==='[1799,578]')ui.scene='CLUE_GIVE_AWAY'
      }
      break
     }
     case 'back':ui.scene='INFRA_DETAILS';break
     case 'read-time':value=end===null?null:(end-now())/1_000_000;break
     case 'tap-element':value=false;break
     case 'waiting-solver':value=true;break
     case 'color':case 'clue-classify':case 'friend-name':
      throw new Error('The empty clue observation input has no '+request.kind+' result')
     case 'backup-plan':throw new Error('Source runtime must execute the actual END backup evaluator')
     case 'credit-shop-run':throw new Error('Mower credit shop requires its own lifecycle adapter')
     case 'save-exception':
      state.diagnostics.push({code:'mower-clue-observation-error',message:request.message});break
    }
    return {kind:request.kind,observedAtMicros:now(),value}
   }
  }
 }}
}
