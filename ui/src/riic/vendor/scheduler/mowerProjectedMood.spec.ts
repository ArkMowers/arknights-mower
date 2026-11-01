import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {alphaPrioritizeRecovery} from './mowerAlphaDorm'
import {projectMowerArrangements} from './mowerObservations'
import {mowerSchedulingMoodObservation} from './mowerSchedulingMood'
import {toMowerMicros} from './mowerTaskQueue'

const R='dormitory_1',now=toMowerMicros(4)
function fixture(){
 const operators=Object.fromEntries([
  new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',restingPriority:'high',mood:19,timeStampMicros:toMowerMicros(2),depletionRate:1}),
  new MowerOperatorState({name:'B',room:'room_1_1',index:1,currentRoom:'room_1_1',currentIndex:1,operatorType:'high',restingPriority:'high',mood:18.5,timeStampMicros:toMowerMicros(3.5),depletionRate:1}),
  new MowerOperatorState({name:'Resident',room:R,index:0,currentRoom:R,currentIndex:0,mood:12,timeStampMicros:0,depletionRate:1}),
 ].map(op=>[op.name,op]))
 return new MowerSchedulingData({alpha:true,nowMicros:now,plan:{room_1_1:['A','B'],[R]:['Resident','Free','Free']},operators,dorms:[new MowerDormState([R,1]),new MowerDormState([R,2])]})
}
const admission={[R]:['Current','B','A']}

describe('position projection preserves scheduling mood',()=>{
 it('allocates the first recovery bed by current deficit despite differently aged readings',()=>{
  const data=fixture(),before=JSON.stringify(data.operators)
  for(let attempt=0;attempt<3;attempt++){
   const plan=alphaPrioritizeRecovery(data,structuredClone(admission))
   expect(plan[R]).toEqual(['Current','A','B'])
  }
  expect(JSON.stringify(data.operators)).toBe(before)
 })
 it('preserves source mood and timestamps through entry, departure and nested projections',()=>{
  const data=fixture(),projected=projectMowerArrangements(data,[admission])
  const nested=projectMowerArrangements(projected,[{room_1_1:['A','Resident']}])
  for(const name of ['A','B','Resident']){
   expect(mowerSchedulingMoodObservation(projected,name)).toEqual(mowerSchedulingMoodObservation(data,name))
   expect(mowerSchedulingMoodObservation(nested,name)).toEqual(mowerSchedulingMoodObservation(data,name))
   expect(projected.operators[name]!.mood).toBe(data.operators[name]!.mood)
   expect(projected.operators[name]!.timeStampMicros).toBe(data.operators[name]!.timeStampMicros)
  }
  expect(data.operators.A!.currentRoom).toBe('room_1_1')
  expect(data.operators.Resident!.currentRoom).toBe(R)
 })
 it.each(['unknown','predicted','future','card'] as const)('retains %s observation validity',kind=>{
  const data=fixture(),op=data.operators.A!
  if(kind==='unknown')op.timeStampMicros=undefined
  if(kind==='predicted')op.moodIsPrediction=true
  if(kind==='future')op.timeStampMicros=now+1
  if(kind==='card')data.dormMoodEstimates.set('A',[10,now-1])
  const projected=projectMowerArrangements(data,[admission])
  expect(mowerSchedulingMoodObservation(projected,'A')).toEqual(kind==='card'?[10,now-1]:undefined)
 })
})
