import {describe,it,expect} from 'vitest'
import native from './fixtures/mower-drone-operations-alpha.json'
import {MOWER_TASK_TYPES as T,MowerTask,MowerTaskQueue,type MowerTaskPlan} from './mowerTaskQueue'
import {
 executeMowerDroneOperation,
 type MowerDroneOperationState,type MowerDroneOperationSeam,
 type MowerDroneOperationRequest,type MowerDroneOperationObservation,
} from './mowerDroneOperations'
function record(raw:unknown):Record<string,unknown>{
 if(!raw||typeof raw!=='object'||Array.isArray(raw))throw new Error('Invalid native fixture object')
 return raw as Record<string,unknown>
}
function string(raw:unknown):string{if(typeof raw!=='string')throw new Error('Invalid fixture string');return raw}
function finite(raw:unknown):number{if(typeof raw!=='number'||!Number.isFinite(raw))throw new Error('Invalid fixture number');return raw}
function plan(raw:unknown):MowerTaskPlan{
 return Object.fromEntries(Object.entries(record(raw)).map(([room,names])=>{
  if(!Array.isArray(names))throw new Error('Invalid fixture plan')
  return [room,names.map(string)]
 }))
}
function observation(raw:unknown){
 const value=record(raw)
 if(!Object.prototype.hasOwnProperty.call(value,'value'))throw new Error('Explicit native observation value is required')
 if(value.removeOriginalIndices!==undefined&&!Array.isArray(value.removeOriginalIndices))throw new Error('Invalid native identity mutation')
 return {
  kind:string(value.kind),elapsedMicros:finite(value.elapsedMicros),value:value.value,
  error:value.error===undefined?undefined:string(value.error),
  removeOriginalIndices:value.removeOriginalIndices===undefined?undefined:(value.removeOriginalIndices as unknown[]).map(finite),
 }
}
function requestFields(request:MowerDroneOperationRequest):Record<string,unknown>{
 switch(request.kind){
  case 'enter-room':return {room:request.room}
  // action labels identify native call sites for the host; source call arguments remain complete.
  case 'tap':return {target:structuredClone(request.target),...(request.intervalSeconds===undefined?{}:{interval:request.intervalSeconds}),...(request.yRate===undefined?{}:{y_rate:request.yRate})}
  case 'wait-interface':return {interval:request.intervalSeconds,...(request.accelerateTemplate===undefined?{}:{accelerate_template:request.accelerateTemplate})}
  case 'find':return {name:request.name}
  case 'cache-facility-page':return {room:request.room,facility:request.facility}
  case 'tap-drone-accelerate':return {template:request.template,control:request.control}
  case 'return-main':return {scene:'infra-main'}
  default:return {}
 }
}
// The frozen alpha fixture records the old reserve bug. Keep its source commit and
// JSON unchanged; only these superseded traces use the independent contract below.
const supersededReserveTraces = new Set([
 'manufacture-equal-limit-opens-no-minus-confirms',
 'manufacture-runorder-rooms-minus-count-minus-limit',
 'manufacture-one-drone-surplus-one-minus',
 'manufacture-three-drone-surplus-three-minus',
 'manufacture-notReturn-stops-after-confirm',
 'manufacture-skipEnter-still-detail-and-cache',
 'manufacture-201-has-no-trade-recognition-stop',
 'manufacture-different-screen-floating-minus-and-y_rate',
 'manufacture-zero-count-zero-reserve-still-confirm',
 'manufacture-return-main-exception-propagates',
 'manufacture-minus-tap-exception-before-confirm',
 'manufacture-confirm-exception-before-navigation',
])
describe('unchanged ordinary alpha trade/manufacture drone branches',()=>{
 it('identifies exactly the frozen reserve traces replaced by corrected contract tests',()=>{
  expect(native.sourceCommit).toBe('c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88')
  expect(native.cases.filter(test=>supersededReserveTraces.has(test.name)).map(test=>test.name).sort())
   .toEqual([...supersededReserveTraces].sort())
 })
 it.each(native.cases.filter(test=>!supersededReserveTraces.has(test.name)))('matches every source output field of $name',test=>{
  expect(native.sourceCommit).toBe('c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88')
  const input=test.input,queue=new MowerTaskQueue()
  queue.tasks=input.tasks.map(raw=>{
   const type=Object.values(T).find(type=>type.key===raw.type)
   if(!type)throw new Error('Unknown native task type')
   return new MowerTask({time:raw.seconds/3600,type,metadata:raw.metadata,plan:plan(raw.plan)})
  })
  const originals=[...queue.tasks],trace:Record<string,unknown>[]=[]
  let clock=input.nowMicros,observationIndex=0
  const state:MowerDroneOperationState={
   retainManufacturingReserve:!input.notCustomize&&input.runOrderRooms.length>0,
   repeatTradeAcceleration:input.droneRoom===null||(input.droneRoom===input.room&&input.runOrderRooms.includes(input.room)),
   room:input.room,width:input.width,height:input.height,skipEnter:input.skipEnter,notCustomize:input.notCustomize,
   notReturn:input.notReturn,waitingScenes:input.waitingScenes,droneCountLimit:input.droneCountLimit,
  }
  const seam:MowerDroneOperationSeam={
   nowMicros:()=>clock,
  }
  const generator=executeMowerDroneOperation(state,seam)
  const observations=input.observations.map(observation)
  let error:{message:string}|null=null,result:false|null=null
  try{
   let next=generator.next()
   while(!next.done){
    const request=next.value,observed=observations[observationIndex++]
    if(!observed)throw new Error('Missing explicit native observation for '+request.kind)
    expect(observed.kind).toBe(request.kind)
    clock+=observed.elapsedMicros
    if(observed.removeOriginalIndices!==undefined){
     const removed=new Set(observed.removeOriginalIndices.map(index=>originals[index]))
     queue.tasks=queue.tasks.filter(task=>!removed.has(task))
    }
    trace.push({kind:request.kind,request:requestFields(request),value:structuredClone(observed.value),nowMicros:clock})
    if(observed.error!==undefined)next=generator.throw(new Error(observed.error))
    else{
     const reply:MowerDroneOperationObservation={kind:request.kind,observedAtMicros:clock,value:observed.value}
     next=generator.next(reply)
    }
   }
   result=next.value
  }catch(caught){error={message:caught instanceof Error?caught.message:String(caught)}}
  expect(observationIndex).toBe(observations.length)
  expect({
   result,error,nowMicros:clock,
   tasks:queue.tasks.map(task=>({type:task.type.key,timeMicros:task.timeMicros,metadata:task.metadata,adjusted:task.adjusted,
    plan:task.plan,originalIndex:originals.includes(task)?originals.indexOf(task):null})),trace,
  }).toEqual(test.output)
 })
})

interface ReserveCase {
 name:string
 available:number
 threshold:number
 spend:number|null
 reductions:number
 skipEnter?:boolean
 notReturn?:boolean
 width?:number
 height?:number
}
const reserveCases:ReserveCase[]=[
 {name:'250 drones reserve 20 and spend 230',available:250,threshold:20,spend:230,reductions:20},
 {name:'exact threshold spends zero',available:20,threshold:20,spend:0,reductions:20},
 {name:'below threshold never opens panel',available:19,threshold:20,spend:null,reductions:0},
 {name:'one surplus spends one',available:21,threshold:20,spend:1,reductions:20},
 {name:'three surplus spends three',available:23,threshold:20,spend:3,reductions:20},
 {name:'zero threshold spends all',available:250,threshold:0,spend:250,reductions:0},
 {name:'empty stock and zero threshold still confirms zero',available:0,threshold:0,spend:0,reductions:0},
 {name:'201 is valid manufacture stock',available:201,threshold:199,spend:2,reductions:199},
 {name:'skipEnter still opens details',available:250,threshold:20,spend:230,reductions:20,skipEnter:true},
 {name:'notReturn stops after confirmation',available:250,threshold:20,spend:230,reductions:20,notReturn:true},
 {name:'scaled screen retains relative coordinates',available:250,threshold:20,spend:230,reductions:20,width:1281,height:721},
]
const manufactureScope=[[100,100],[200,200]]
const maximumScope=[[300,300],[400,400]]
type ReserveFailure='all-in'|'minus-reserve'|'confirm-manufacture'|'return-main'
function runReserveContract(test:ReserveCase,failure?:ReserveFailure){
 const state:MowerDroneOperationState={
  retainManufacturingReserve:true,repeatTradeAcceleration:false,room:'room_1_2',
  width:test.width??1920,height:test.height??1080,skipEnter:test.skipEnter??false,
  notCustomize:false,notReturn:test.notReturn??false,droneCountLimit:test.threshold,waitingScenes:[],
 }
 let clock=0,selected=7,spent:number|null=null,error:unknown,result:false|null|undefined
 const trace:MowerDroneOperationRequest[]=[]
 const generator=executeMowerDroneOperation(state,{nowMicros:()=>clock})
 try{
  let next=generator.next()
  while(!next.done){
   const request=next.value
   trace.push(request)
   clock+=17
   if(failure&&(request.kind==='return-main'?failure==='return-main':request.kind==='tap'&&request.action===failure)){
    next=generator.throw(new Error('controlled '+failure+' failure'))
    continue
   }
   let value:unknown=null
   if(request.kind==='find')value=manufactureScope
   else if(request.kind==='read-drone-count')value=test.available
   else if(request.kind==='tap-drone-accelerate')value=maximumScope
   else if(request.kind==='tap'){
    if(request.action==='all-in')selected=test.available
    else if(request.action==='minus-reserve')selected=Math.max(0,selected-1)
    else if(request.action==='confirm-manufacture')spent=selected
   }
   next=generator.next({kind:request.kind,observedAtMicros:clock,value})
  }
  result=next.value
 }catch(caught){error=caught}
 return {trace,spent,result,error,generator}
}
describe('corrected manufacturing reserve contract',()=>{
 it.each(reserveCases)('$name',test=>{
  const actual=runReserveContract(test)
  expect(actual.error).toBeUndefined()
  expect(actual.result).toBeNull()
  expect(actual.spent).toBe(test.spend)
  const width=test.width??1920,height=test.height??1080
  const expected:MowerDroneOperationRequest[]=[
   ...(test.skipEnter?[]:[{kind:'enter-room' as const,room:'room_1_2'}]),
   {kind:'tap',action:'detail',target:[width*.05,height*.95],intervalSeconds:3},
   {kind:'wait-interface',intervalSeconds:3},
   {kind:'find',name:'manufacture_accelerate'},
   {kind:'cache-facility-page',room:'room_1_2',facility:'manufacture'},
   {kind:'read-drone-count'},
  ]
  if(test.spend!==null){
   expected.push(
    {kind:'tap-drone-accelerate',template:'manufacture_accelerate',control:'all_in'},
    {kind:'tap',action:'all-in',target:maximumScope},
    ...Array.from({length:test.reductions},():MowerDroneOperationRequest=>({
     kind:'tap',action:'minus-reserve',target:[width*.7,height*.5],intervalSeconds:.1,
    })),
    {kind:'tap',action:'confirm-manufacture',target:manufactureScope,yRate:1},
   )
   if(!test.notReturn)expected.push({kind:'return-main'})
  }
  expect(actual.trace).toEqual(expected)
 })
 it.each([
  {failure:'all-in',spend:null,reductions:0},
  {failure:'minus-reserve',spend:null,reductions:1},
  {failure:'confirm-manufacture',spend:null,reductions:20},
  {failure:'return-main',spend:230,reductions:20},
 ] as const)('propagates $failure failure without subsequent actions',({failure,spend,reductions})=>{
  const actual=runReserveContract(reserveCases[0]!,failure)
  expect(actual.error).toEqual(new Error('controlled '+failure+' failure'))
  expect(actual.result).toBeUndefined()
  expect(actual.spent).toBe(spend)
  const actions=actual.trace.flatMap(request=>request.kind==='tap'?[request.action]:request.kind==='return-main'?['return-main']:[])
  expect(actions).toEqual([
   'detail','all-in',...Array.from({length:reductions},()=> 'minus-reserve'),
   ...(failure==='confirm-manufacture'||failure==='return-main'?['confirm-manufacture']:[]),
   ...(failure==='return-main'?['return-main']:[]),
  ])
  expect(actual.generator.next().done).toBe(true)
 })
})
