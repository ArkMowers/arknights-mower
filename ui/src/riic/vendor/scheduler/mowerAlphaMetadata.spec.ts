import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-alpha-metadata.json'
import currentOracle from './fixtures/mower-alpha-selection-20261013.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerMetadata} from './mowerMetadata'
import {alphaRebalanceClosingDorms} from './mowerAlphaDorm'
import {generateMowerDormTasks} from './mowerDormTasks'
import {projectMowerArrangements} from './mowerObservations'
import {splitMowerRecoveryTask} from './mowerGroupRecovery'
import {admitMowerDerivedTasks} from './mowerTaskDerivation'

describe('dorm migrations depend on their returning source owner',()=>{
 function fixture(){
  const operators={
   A:new MowerOperatorState({name:'A',room:'meeting',index:0,group:'G',operatorType:'high',currentRoom:'dormitory_1',currentIndex:2,mood:12,timeStampMicros:0}),
   M:new MowerOperatorState({name:'M',room:'dormitory_1',index:1,group:'G',replacement:['Free'],operatorType:'high'}),
   L:new MowerOperatorState({name:'L',currentRoom:'dormitory_1',currentIndex:1,mood:24,timeStampMicros:0}),
   I:new MowerOperatorState({name:'I',room:'contact',index:0,operatorType:'high',currentRoom:'dormitory_1',currentIndex:3,mood:24,timeStampMicros:0}),
  }
  const data=new MowerSchedulingData({alpha:true,operators,plan:{meeting:['A'],contact:['I'],dormitory_1:['Free','M','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',1],'L',0,true),new MowerDormState(['dormitory_1',2],'A',toMowerMicros(1)),new MowerDormState(['dormitory_1',3],'I',0),new MowerDormState(['dormitory_1',4])],nowMicros:0,groupShiftState:{G:true}})
  const task=new MowerTask({type:T.SHIFT_ON,plan:{meeting:['A'],contact:['I'],dormitory_1:['Current','M','Current','Current','L']}})
  return {data,task}
 }
 it.each([true,false])('keeps the dorm cover with its recovering group when splitting by slot: %s',bySlot=>{
  const {data,task}=fixture(),independent:MowerTask[]=[]
  splitMowerRecoveryTask(data,task,independent,['A'],bySlot)
  expect(independent.map(sibling=>sibling.plan)).toEqual([{contact:['I']}])
  expect(task.plan).toEqual({meeting:['A'],dormitory_1:['Current','M','Current','Current','L']})
  expect(task.timeMicros).toBe(0)
  expect(data.operators.L!.currentRoom).toBe('dormitory_1')
 })
 it('removes a migration when the source owner return is waiting for recovery',()=>{
  const {data,task}=fixture();data.waitingRecoveryNames=new Set(['A','M'])
  const candidates=admitMowerDerivedTasks(data,[],[task])
  expect(candidates.map(candidate=>candidate.plan)).toEqual([{contact:['I']}])
  expect(data.operators.L!.currentIndex).toBe(1)
 })
 it('removes a migration when retained work prevents the source owner return',()=>{
  const {data,task}=fixture(),retained=new MowerTask({type:T.SHIFT_OFF,plan:{meeting:['A']}})
  retained.executionRetained=true
  const candidates=admitMowerDerivedTasks(data,[retained],[task])
  expect(candidates.map(candidate=>candidate.plan)).toEqual([{contact:['I']}])
  expect(retained.plan).toEqual({meeting:['A']})
  expect(data.operators.L!.currentIndex).toBe(1)
 })
 it.each(['waiting','retained'])('allows independent work to leave a temporary dorm bed under %s protection',barrier=>{
  const {data,task}=fixture()
  data.operators.L!.currentIndex=4;data.operators.I!.currentIndex=1
  task.plan.dormitory_1=['Current','M','Current','Current','Current']
  const retained=new MowerTask({type:T.SHIFT_OFF,plan:{meeting:['A']}});retained.executionRetained=true
  if(barrier==='waiting')data.waitingRecoveryNames=new Set(['A','M'])
  const candidates=admitMowerDerivedTasks(data,barrier==='retained'?[retained]:[],[task])
  expect(candidates.map(candidate=>candidate.plan)).toEqual([{contact:['I']}])
  expect(data.operators.I!.currentRoom).toBe('dormitory_1')
 })
})

describe.each([true,false])('return snapshots distinguish work from incidental dorm moves (alpha: %s)',alpha=>{
 function fixture(){
  const operators={
   A:new MowerOperatorState({name:'A',room:'meeting',index:0,replacement:['R'],operatorType:'high',currentRoom:'dormitory_1',currentIndex:2,mood:21,timeStampMicros:0}),
   B:new MowerOperatorState({name:'B',room:'contact',index:0,replacement:['S'],operatorType:'high',currentRoom:'contact',currentIndex:0,mood:24,timeStampMicros:0}),
   D:new MowerOperatorState({name:'D',room:'dormitory_1',index:0,operatorType:'high',currentRoom:'dormitory_1',currentIndex:0,mood:24,timeStampMicros:0}),
   R:new MowerOperatorState({name:'R',currentRoom:'meeting',currentIndex:0,mood:24,timeStampMicros:0}),
   S:new MowerOperatorState({name:'S',mood:24,timeStampMicros:0}),
  }
  const bed=new MowerDormState(['dormitory_1',2],'A',toMowerMicros(1))
  const data=new MowerSchedulingData({alpha,operators,plan:{meeting:['A'],contact:['B'],dormitory_1:['D','Free','Free','Free','Free']},dorms:[bed,new MowerDormState(['dormitory_1',3]),new MowerDormState(['dormitory_1',4])],nowMicros:0,freeRoom:false,planConditions:[true]})
  return {data,bed}
 }
 it.each(['dormitory_1','contact'])('validates a saved return target in %s',(room)=>{
  const {data,bed}=fixture(),before=structuredClone(data.dorms)
  const tasks=generateMowerDormTasks([{timeMicros:bed.timeMicros!,dorms:[bed],restInFull:false}],data,{A:[room,room.startsWith('dorm')?4:0]})
  expect(tasks.map(task=>task.plan)).toEqual([{[room.startsWith('dorm')?'meeting':'contact']:['A']}])
  expect(tasks[0]!.time).toBeCloseTo(1-8/60,8)
  expect(data.dorms).toEqual(before)
  expect(data.operators.A!.currentRoom).toBe('dormitory_1')
 })
 for(const workFirst of [true,false])for(const savedWork of [true,false])it(`rebuilds one working return across unchanged metadata (${workFirst}, ${savedWork})`,()=>{
  const {data}=fixture(),queue=new MowerTaskQueue(),dorm={dormitory_1:['Current','Current','Current','Current','A']},work=savedWork?{contact:['A']}:{}
  queue.tasks=[new MowerTask({type:T.SHIFT_ON,time:1,plan:workFirst?{...work,...dorm}:{...dorm,...work}})]
  for(let pass=0;pass<3;pass++){
   planMowerMetadata(data,queue)
   const returns=queue.tasks.filter(task=>task.type===T.SHIFT_ON)
   expect(returns.map(task=>task.plan)).toEqual([{[savedWork?'contact':'meeting']:['A']}])
   expect(returns[0]!.time).toBeCloseTo(1-8/60,8)
   expect(data.operators.A!.currentRoom).toBe('dormitory_1')
   expect(data.getDormByName('A')?.[1].name).toBe('A')
  }
  const confirmed=projectMowerArrangements(data,queue.tasks.map(task=>task.plan))
  expect(confirmed.operators.A!.currentRoom).toBe(savedWork?'contact':'meeting')
  const rebuilt=new MowerTaskQueue();planMowerMetadata(confirmed,rebuilt)
  expect(rebuilt.tasks.some(task=>Object.values(task.plan).some(row=>row.includes('A')))).toBe(false)
 })
 it('keeps a configured dormitory primary return',()=>{
  const {data}=fixture(),bed=new MowerDormState(['dormitory_1',3],'D',toMowerMicros(1))
  data.operators.D!.currentRoom='';data.operators.D!.currentIndex=-1
  const tasks=generateMowerDormTasks([{timeMicros:bed.timeMicros!,dorms:[bed],restInFull:false}],data,{D:['dormitory_1',0]})
  expect(tasks[0]!.plan.dormitory_1?.[0]).toBe('D')
 })
})

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


describe('ungrouped primary recovery returns',()=>{
 function fixture(priority:'high'|'low'|'standby',resident:boolean,full:boolean,freeRoom:boolean){
  const operators={
   A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,replacement:['R'],operatorType:'high',restingPriority:priority,currentRoom:resident?'dormitory_1':'',currentIndex:resident?0:-1,mood:full?24:20,timeStampMicros:0}),
   H:new MowerOperatorState({name:'H',room:'room_1_2',index:0,replacement:['S'],operatorType:'high',restingPriority:'high',currentRoom:'dormitory_1',currentIndex:1,mood:12,timeStampMicros:0}),
   R:new MowerOperatorState({name:'R',currentRoom:'room_1_1',currentIndex:0,mood:20,timeStampMicros:0}),
   S:new MowerOperatorState({name:'S',currentRoom:'room_1_2',currentIndex:0,mood:20,timeStampMicros:0}),
  }
  const data=new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A'],room_1_2:['H'],dormitory_1:['Free','Free']},dorms:[new MowerDormState(['dormitory_1',0],resident?'A':'',resident?toMowerMicros(.5):undefined),new MowerDormState(['dormitory_1',1],'H',toMowerMicros(2))],nowMicros:0,freeRoom,standbyNames:priority==='standby'?['A']:[]})
  return {data,queue:new MowerTaskQueue()}
 }
 for(const priority of ['high','low','standby'] as const)for(const freeRoom of [false,true])it(`keeps the resident's own return with ${priority} priority and freeRoom=${freeRoom}`,()=>{
  const {data,queue}=fixture(priority,true,false,freeRoom)
  const before=structuredClone(data.dorms)
  for(let n=0;n<2;n++){
   planMowerMetadata(data,queue)
   const tasks=queue.tasks.filter(t=>t.type===T.SHIFT_ON&&t.plan.room_1_1?.includes('A'))
   expect(tasks).toHaveLength(1)
   expect(tasks[0]!.timeMicros).toBe(toMowerMicros(.5-8/60))
   expect(tasks[0]!.plan.room_1_2?.includes('H')??false).toBe(false)
   expect(data.dorms).toEqual(before)
  }
 })
 for(const countdown of [undefined,toMowerMicros(.5)])for(const requireFull of [false,true])for(const freeRoom of [false,true])it(`returns a full resident from valid mood, countdown=${countdown}, requireFull=${requireFull}, freeRoom=${freeRoom}`,()=>{
  const {data,queue}=fixture('standby',true,true,freeRoom)
  data.dorms[0]!.timeMicros=countdown
  data.operators.A!.restInFull=requireFull
  planMowerMetadata(data,queue)
  const tasks=queue.tasks.filter(t=>t.type===T.SHIFT_ON&&t.plan.room_1_1?.includes('A'))
  expect(tasks).toHaveLength(1)
  expect(tasks[0]!.timeMicros).toBeLessThanOrEqual(0)
  expect(tasks[0]!.timeMicros).toBeGreaterThanOrEqual(-1_000_000)
  expect(tasks[0]!.plan.room_1_2?.includes('H')??false).toBe(false)
  expect(data.operators.A!.currentRoom).toBe('dormitory_1')
  expect(data.dorms[0]!.timeMicros).toBe(countdown)
 })
 for(const priority of ['low','standby'] as const)for(const freeRoom of [false,true])it(`returns the full idle ${priority} primary immediately with freeRoom=${freeRoom}`,()=>{
  const {data,queue}=fixture(priority,false,true,freeRoom)
  for(let n=0;n<2;n++){
   planMowerMetadata(data,queue)
   const tasks=queue.tasks.filter(t=>t.type===T.SHIFT_ON&&t.plan.room_1_1?.includes('A'))
   expect(tasks).toHaveLength(1)
   expect(tasks[0]!.timeMicros).toBe(0)
   expect(tasks[0]!.plan.room_1_2?.includes('H')??false).toBe(false)
   expect(data.operators.A!.currentRoom).toBe('')
   expect(data.operators.R!.currentRoom).toBe('room_1_1')
  }
 })
 for(const priority of ['low','standby'] as const)for(const observation of ['full','partial','unknown','prediction','newer-low-card','full-card'])it(`checks ${observation} mood for ${priority} priority without another return deadline`,()=>{
  const {data,queue}=fixture(priority,false,true,false),op=data.operators.A!
  data.nowMicros=1
  data.dorms[1]!.timeMicros=undefined
  if(observation==='partial')op.mood=10
  if(observation==='unknown')op.timeStampMicros=undefined
  if(observation==='prediction')op.moodIsPrediction=true
  if(observation==='newer-low-card'||observation==='full-card'){
   op.mood=observation==='full-card'?10:24
   data.dormMoodEstimates.set('A',[observation==='full-card'?24:10,1])
  }
  planMowerMetadata(data,queue)
  const returns=queue.tasks.filter(t=>t.type===T.SHIFT_ON)
  if(observation==='full'||observation==='full-card'){
   expect(returns).toHaveLength(1)
   expect(returns[0]!.timeMicros).toBe(1)
   expect(returns[0]!.plan).toEqual({room_1_1:['A']})
  }else expect(returns).toEqual([])
 })
 it('keeps a reserved full primary pending and returns after the reservation is released',()=>{
  const {data,queue}=fixture('standby',false,true,false)
  const locked=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['R']}})
  locked.productShiftLocked=true;locked.productLockNames.add('A');locked.productLockSlots.add('room_1_1:0')
  queue.tasks.push(locked)
  for(let n=0;n<2;n++){
   planMowerMetadata(data,queue)
   expect(queue.tasks.some(t=>t.type===T.SHIFT_ON&&t.plan.room_1_1?.includes('A'))).toBe(false)
   expect(queue.tasks).toContain(locked)
  }
  queue.tasks=queue.tasks.filter(t=>t!==locked)
  planMowerMetadata(data,queue)
  const task=queue.tasks.find(t=>t.type===T.SHIFT_ON&&t.plan.room_1_1?.includes('A'))!
  expect(task.timeMicros).toBe(0)
  expect(data.operators.A!.currentRoom).toBe('')
 })

})
