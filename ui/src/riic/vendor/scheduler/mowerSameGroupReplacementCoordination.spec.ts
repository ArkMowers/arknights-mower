import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {planMowerReplacementHandoff} from './mowerReplacementCoordination'
import {planMowerAlphaExhaustSupport} from './mowerAlphaExhaustSupport'
import type {MowerTaskPlan} from './mowerTaskQueue'
function fixture(){
 const operators:Record<string,MowerOperatorState>={}
 const rows:Record<string,string[]>={room_1_1:['Worker'],room_1_2:['Resting'],dormitory_1:['Alice','Podenco','Free','Free','Free']}
 for(const [name,room,index,group,replacement] of [
  ['Alice','dormitory_1',0,'automation',['Podenco']],['Podenco','dormitory_1',1,'automation',['Q']],
  ['Worker','room_1_1',0,'automation',['X']],['Resting','room_1_2',0,'other',['X','Y']],
 ] as [string,string,number,string,string[]][])operators[name]=new MowerOperatorState({name,room,index,group,replacement,currentRoom:name==='Resting'?'dormitory_1':room,currentIndex:name==='Resting'?2:index,operatorType:'high',restingPriority:'high',mood:name==='Worker'?0:8,timeStampMicros:0})
 operators.X=new MowerOperatorState({name:'X',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0})
 operators.Q=new MowerOperatorState({name:'Q',mood:24,timeStampMicros:0})
 operators.Y=new MowerOperatorState({name:'Y',mood:24,timeStampMicros:0})
 return new MowerSchedulingData({alpha:true,plan:rows,operators,dorms:[new MowerDormState(['dormitory_1',2],'Resting'),new MowerDormState(['dormitory_1',3]),new MowerDormState(['dormitory_1',4])],nowMicros:0,groupShiftState:{automation:false,other:true}})
}
const candidates=['Alice','Podenco','Worker'],handoff={room_1_2:['Y']}
describe('replacement coordination preserves legal same-group primary swaps',()=>{
 it('admits the same-group manager replacement accepted by native rest planning',()=>{
  const data=fixture(),trial=projectMowerArrangements(data,[handoff]),rest:MowerTaskPlan={}
  mowerGetRestingPlan(trial,candidates,[],rest)
  expect(rest.room_1_1).toEqual(['X'])
  expect(rest.dormitory_1?.[0]).toBe('Podenco')
  expect(planMowerReplacementHandoff(data,candidates)).toEqual(handoff)
  expect(planMowerAlphaExhaustSupport(data,candidates)).toEqual(handoff)
 })
 it.each(['other-group','busy','reserved','excluded','mastery'])('keeps %s primary replacements unavailable',constraint=>{
  const data=fixture()
  if(constraint==='other-group')data.operators.Podenco!.group='other'
  if(constraint==='busy')data.busyRestingNames.add('Podenco')
  if(constraint==='excluded')data.excludedCandidates.add('Podenco')
  const options=constraint==='reserved'?{reservedNames:new Set(['Podenco'])}:constraint==='mastery'?{isMasteryBusy:(name:string)=>name==='Podenco'}:{}
  expect(planMowerReplacementHandoff(data,candidates,options)).toBeUndefined()
  expect(planMowerAlphaExhaustSupport(data,candidates,options)).toBeUndefined()
 })
})
