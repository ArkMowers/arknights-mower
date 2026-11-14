/**
 * I/O continuation bridge for pinned Mower scheduling generators.
 * Source c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
 * The host owns time, morale and production. Observations occur after the host
 * resumes the boundary, never when the request is first issued.
 */
export interface MowerNativeIOBoundary<Observation> {
  delayMicros:number
  observe:()=>Observation
}
export type MowerNativeIOWork<Observation>=MowerNativeIOBoundary<Observation>|Generator<MowerNativeIOYield,Observation,void>
export interface MowerNativeIOYield {
  room:string
  delayMicros:number
  nativeRunOrderIO:true
}
export function* bridgeMowerNativeIO<Request extends {kind:string;room?:string},Observation,Result>(
  steps:Generator<Request,Result,Observation>,
  perform:(request:Request)=>MowerNativeIOWork<Observation>,
  roomOf:(request:Request)=>string=request=>request.room??'',
):Generator<MowerNativeIOYield,Result,void>{
  let next=steps.next()
  while(!next.done){
    let boundary:MowerNativeIOWork<Observation>
    try{boundary=perform(next.value)}catch(error){next=steps.throw(error);continue}
    if('next' in boundary){
      let observation:Observation
      try{observation=yield* boundary}catch(error){next=steps.throw(error);continue}
      next=steps.next(observation);continue
    }
    if(!Number.isSafeInteger(boundary.delayMicros)||boundary.delayMicros<0)
      throw new Error('Invalid native scheduling I/O duration')
    yield {room:roomOf(next.value),delayMicros:boundary.delayMicros,nativeRunOrderIO:true}
    let observation:Observation
    try{observation=boundary.observe()}catch(error){next=steps.throw(error);continue}
    next=steps.next(observation)
  }
  return next.value
}
