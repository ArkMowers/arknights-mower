import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-dorm-assignment-alpha-cases.json'
import {MowerOperatorState,type MowerOperatorOptions} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerFindDormSlot,mowerSlotTakable,mowerAssignDormGroup,mowerAvailableFree,mowerActiveHighRestingCount} from './mowerDormAssignment'
import {toMowerMicros} from './mowerTaskQueue'
describe('actual alpha default bed matrix',()=>{
 for(const fixture of oracle.cases)it(fixture.id,()=>{
  const v=fixture.input
  const operators=Object.fromEntries(v.operators.map(o=>[o.name,new MowerOperatorState({name:o.name,room:o.room,index:o.index,group:o.group,replacement:o.replacement,operatorType:o.operator_type,restingPriority:o.resting_priority,mood:o.mood,lowerLimit:o.lower_limit,upperLimit:o.upper_limit,currentRoom:o.current_room,currentIndex:o.current_index,timeStampMicros:o.timeStampHours===null?undefined:toMowerMicros(o.timeStampHours),depletionRate:o.depletion_rate,workshop:o.workshop,workaholic:o.workaholic,exhaustRequire:o.exhaust_require,restInFull:o.rest_in_full,restMoodLimit:(o.name==='令'&&v.config.ling_xi===1)||(o.name==='夕'&&v.config.ling_xi===2)} as MowerOperatorOptions)]))
  const data=new MowerSchedulingData({plan:Object.fromEntries(Object.entries(v.plan).filter((entry):entry is [string,string[]]=>Array.isArray(entry[1]))),operators,dorms:v.dorms.map(b=>new MowerDormState([String(b.position[0]),Number(b.position[1])],b.name,b.completedAtHours===null?undefined:toMowerMicros(b.completedAtHours))),nowMicros:toMowerMicros(v.nowHours)})
  let output:Record<string,unknown>
  if(v.action==='find')output={index:mowerFindDormSlot(data,v.names[0]!,new Set(v.used),v.groupResting)??null}
  else if(v.action==='slot')output={takable:mowerSlotTakable(data,data.dorms[0]!,v.groupResting,v.names[0])}
  else if(v.action==='group'){const beds=mowerAssignDormGroup(data,v.names);output={assignedIndices:beds?.map(b=>data.dorms.indexOf(b))??null}}
  else output={availableHigh:mowerAvailableFree(data),availableLow:mowerAvailableFree(data,'low'),activeHigh:mowerActiveHighRestingCount(data)}
  output.dorms=data.dorms.map(b=>({name:b.name,timeMicros:b.timeMicros??null}));output.operators=Object.values(data.operators).map(o=>({name:o.name,mood:o.mood,depletionRate:o.depletionRate,timeStampMicros:o.timeStampMicros??null}))
  expect(output).toEqual(fixture.output)
 })
})
