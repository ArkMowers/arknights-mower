import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-alpha-metadata.json'
import currentOracle from './fixtures/mower-alpha-selection-20261013.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerMetadata} from './mowerMetadata'
import {alphaRebalanceClosingDorms} from './mowerAlphaDorm'

describe('current alpha metadata with preserved October 3 inputs',()=>{
 for(const fixture of oracle.metadata)it(fixture.name,()=>{
  const input=fixture.input,operators=Object.fromEntries(input.rows.map(row=>[row.name,new MowerOperatorState({
   name:row.name,room:row.room,index:'index' in row?row.index:undefined,
   replacement:'replacement' in row?row.replacement:undefined,
   operatorType:'operator_type' in row?row.operator_type as 'high'|'low':undefined,
   restingPriority:'resting_priority' in row?row.resting_priority as 'high'|'low':undefined,
   currentRoom:row.current_room,currentIndex:row.current_index,mood:'mood' in row?row.mood:24,timeStampMicros:0,
  })]))
  const data=new MowerSchedulingData({alpha:true,operators,plan:structuredClone(input.plan),
   dorms:input.beds.map(b=>new MowerDormState([String(b.position[0]),Number(b.position[1])],b.name,b.time===undefined?undefined:toMowerMicros(b.time))),nowMicros:0,freeRoom:input.freeRoom})
  if('recentReturn' in input)data.recentShiftOnByRestUnit.set('operator:A',0)
  const queue=new MowerTaskQueue()
  if(input.pending)queue.tasks.push(new MowerTask({type:T[input.pending.type as keyof typeof T],time:input.pending.time,plan:structuredClone(input.pending.plan)}))
  const original=structuredClone(data.dorms),positions=Object.values(operators).map(o=>[o.name,o.currentRoom,o.currentIndex])
  planMowerMetadata(data,queue)
  const expected=fixture.output.map(t=>({type:t.type,timeMicros:toMowerMicros(t.time),plan:t.plan,metadata:t.metadata,strict:t.strict}))
  if(fixture.name==='individual-release'){
   // ae9fc322 keeps the actual bed's release after a projected return; the old oracle stays unchanged.
   expected.push({type:'RELEASE_DORM',timeMicros:toMowerMicros(3),plan:{dormitory_1:['Current','Current','Free','Current','Current']},metadata:'A',strict:false})
  }
  expect(queue.tasks.map(t=>({type:t.type.key,timeMicros:t.timeMicros,plan:t.plan,metadata:t.metadata,strict:t.strictMoodLimit}))).toEqual(expected)
  expect(data.dorms).toEqual(original);expect(Object.values(operators).map(o=>[o.name,o.currentRoom,o.currentIndex])).toEqual(positions)
 })
 it('recalls the whole main group when a temporary bed closes',()=>{
  const {input,output}=oracle.closing
  const operators=Object.fromEntries(input.rows.map(row=>[row.name,new MowerOperatorState({name:row.name,room:row.room,index:row.index,group:row.group,replacement:row.replacement,operatorType:'high',restingPriority:'high',currentRoom:'current_room' in row?row.current_room:'',currentIndex:'current_index' in row?row.current_index:-1,mood:'mood' in row?row.mood:24,timeStampMicros:0})]))
  const data=new MowerSchedulingData({alpha:true,operators,plan:structuredClone(input.plan),dorms:input.beds.map(b=>new MowerDormState([String(b.position[0]),Number(b.position[1])],b.name,toMowerMicros(b.time),input.rows.some(o=>o.room===b.position[0]&&o.index===b.position[1]&&o.replacement.includes('Free')))),nowMicros:0})
  const plan=structuredClone(input.intent)
  expect([...alphaRebalanceClosingDorms(data,plan,input.recalled)].sort()).toEqual(output.recalled)
  expect(plan).toEqual(output.plan)
  expect(data.dorms.map(b=>({position:b.position,name:b.name,time:b.timeMicros===undefined?null:b.timeMicros/3_600_000_000}))).toEqual(output.beds)
 })
})


describe('current alpha group recovery gap and configured wait cap',()=>{
 function returnTime(times:number[],enabled=true,threshold=60,maxWait=0){
  const operators=Object.fromEntries(times.map((_,index)=>{const name='N'+index;return [name,new MowerOperatorState({name,room:'central',index,group:'G',operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:index,mood:12,timeStampMicros:0})]}))
  const data=new MowerSchedulingData({alpha:true,operators,plan:{central:Object.keys(operators),dormitory_1:times.map(()=>'Free')},dorms:times.map((time,index)=>new MowerDormState(['dormitory_1',index],'N'+index,toMowerMicros(time))),nowMicros:0,groupRestInFullOnMoodGap:enabled,groupMoodGapThresholdMinutes:threshold,groupMoodGapMaxExtraWaitHours:maxWait})
  const queue=new MowerTaskQueue();planMowerMetadata(data,queue)
  return queue.tasks.find(task=>task.type===T.SHIFT_ON)!.time
 }
 // Reuse the historical inputs. ae9fc322 anchors the gap cap at the normal return, eight minutes early.
 const expected:Record<string,number>={
  'earliest bed first':5,'latest bed first':5,'gap option disabled':1-8/60,
  'gap equals threshold':1-8/60,'positive extra wait limit':1-8/60+1,
 }
 for(const fixture of currentOracle.groupRecoveryGaps)it(fixture.name,()=>{
  const {times,enabled,thresholdMinutes,maxWaitHours}=fixture.input
  expect(returnTime(times,enabled,thresholdMinutes,maxWaitHours)).toBeCloseTo(expected[fixture.name]!,8)
 })
})
