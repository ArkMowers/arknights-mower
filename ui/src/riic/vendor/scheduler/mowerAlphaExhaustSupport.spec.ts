import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-alpha-exhaust-support.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {planMowerExhaustSupport} from './mowerExhaustPlanning'
import {toMowerMicros} from './mowerTaskQueue'

describe('alpha exhaust coordination with simulator recall safety',()=>{
 for(const c of oracle.cases)it(c.kind,()=>{
  const matching=c.kind==='matching',protectedRest=c.kind==='protected',extra=['matching','alternate','exhausted-alternate'].includes(c.kind)
  const operators:Record<string,MowerOperatorState>={A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',restingPriority:'high',replacement:matching?['X','Y']:['X'],exhaustRequire:true,mood:4,timeStampMicros:0}),X:new MowerOperatorState({name:'X',mood:10,timeStampMicros:0,currentRoom:matching?'':'room_1_2',currentIndex:matching?-1:0}),Y:new MowerOperatorState({name:'Y',mood:c.kind==='exhausted-alternate'?0:10,timeStampMicros:0})}
  const name=matching?'C':'B';operators[name]=new MowerOperatorState({name,room:'room_1_2',index:0,currentRoom:matching?'room_1_2':'dormitory_1',currentIndex:matching?0:2,operatorType:'high',restingPriority:'high',replacement:['alternate','exhausted-alternate'].includes(c.kind)?['X','Y']:['X'],exhaustRequire:protectedRest,restInFull:protectedRest,mood:4,timeStampMicros:0})
  for(const [index,name] of ['K1','K2'].entries())operators[name]=new MowerOperatorState({name,room:'dormitory_1',index,currentRoom:'dormitory_1',currentIndex:index,operatorType:'high',mood:4,timeStampMicros:0})
  const data=new MowerSchedulingData({alpha:true,plan:{room_1_1:['A'],dormitory_1:['K1','K2','Free','Free','Free'],room_1_2:[name]},operators,dorms:[new MowerDormState(['dormitory_1',2],matching?'':'B',matching?undefined:toMowerMicros(2)),...(extra?[new MowerDormState(['dormitory_1',3])]:[])],nowMicros:0,reservedProductReplacements:new Set(c.kind==='reserved'?['X']:[])})
  const before=JSON.stringify(data)
  // The pinned native oracle recalls without an endurance forecast; the simulator refuses that unsafe fallback.
  const unprovenRecall=['recall','exhausted-alternate'].includes(c.kind)
  expect(planMowerExhaustSupport(data,matching?['A','C']:['A'])??null).toEqual(unprovenRecall?null:c.plan)
  expect(JSON.stringify(data)).toBe(before);expect(c.preserved).toBe(true)
 })
})
