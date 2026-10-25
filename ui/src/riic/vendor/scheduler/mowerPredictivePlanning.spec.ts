import {describe,it,expect} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'
import {projectMowerArrangements} from './mowerObservations'
import {predictiveFixture} from '../../../__tests__/fixtures/predictiveMoodControl'
import {mowerAdvancedAssumptions} from './mowerAdvancedSettings'
import {planMowerOrdinary} from './mowerOrdinaryPlanning'
import {planMowerPredictiveDeparture,syncMowerPredictiveWake,consumeMowerPredictiveWake} from './mowerPredictivePlanning'
function fixture(enabled=true){
 const operators=Object.fromEntries(['A','B','X'].map((name,i)=>[name,new MowerOperatorState({name,room:i<2?'room_1_'+(i+1):'',index:i<2?0:-1,operatorType:i<2?'high':'low',restInFull:i<2,replacement:i<2?['X']:[],mood:i<2?i+2:24,timeStampMicros:0,currentRoom:i<2?'room_1_'+(i+1):'',currentIndex:i<2?0:-1})]))
 const data=new MowerSchedulingData({alpha:true,operators,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['Free']},dorms:[new MowerDormState(['dormitory_1',0])],nowMicros:0,policy:{restingThreshold:0,predictiveMoodControl:enabled},groupRestInFullOnMoodGap:false})
 const queue=new MowerTaskQueue(),diagnostics:unknown[]=[]
 const options={coordinationRates:(state:MowerSchedulingData)=>({work:Object.fromEntries(Object.values(state.operators).filter(o=>o.currentRoom&&!o.isResting()).map(o=>[o.name,1])),recovery:Object.fromEntries(Object.values(state.operators).filter(o=>o.isResting()).map(o=>[o.name,24]))}),onPredictiveDiagnostics:(d:unknown)=>diagnostics.push(d)}
 return {data,queue,options,diagnostics}
}
describe('predictive ordinary planning production entry',()=>{
 it('advances a complete ordinary group to unblock the next shared cover and bed',()=>{
  const {data,queue,options,diagnostics}=fixture()
  const plan=planMowerOrdinary(data,queue,options)
  expect(diagnostics).toHaveLength(1)
  expect(plan?.room_1_1).toEqual(['X'])
  expect(plan?.dormitory_1).toEqual(['A'])
  expect(queue.tasks.find(t=>t.type===T.SHIFT_OFF)?.moodControlEvidence?.names).toEqual(['A'])
  expect(data.operators.A!.currentRoom).toBe('room_1_1')
 })
 it('counts an exhausted protected primary in the same fixed work-position horizon',()=>{
  const input={moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300}
  const baseline=predictiveFixture(input);planMowerOrdinary(baseline.data,baseline.queue,baseline.options)
  const protectedCase=predictiveFixture(input),{data,queue,options,diagnostics}=protectedCase
  data.plan.room_1_3=['P'];data.operators.P=new MowerOperatorState({name:'P',room:'room_1_3',index:0,currentRoom:'room_1_3',currentIndex:0,operatorType:'high',mood:0,timeStampMicros:0,groupBindings:[{group:'one',replacement:[]},{group:'two',replacement:[]}]})
  planMowerOrdinary(data,queue,options)
  expect(diagnostics[0]!.result!.decision).toBe('operator:A')
  expect(diagnostics[0]!.result!.score[1]!-baseline.diagnostics[0]!.result!.score[1]!).toBeCloseTo(27*3600)
  expect(diagnostics[0]!.result!.events.some(e=>e.group==='operator:P')).toBe(false)
 })
 it('uses ordinary independent multi-binding admission at the original work position',()=>{
  const {data,queue,options,diagnostics}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300})
  data.operators.A!.groupBindings=[{group:'',replacement:['X']},{group:'other',replacement:['X']}]
  planMowerOrdinary(data,queue,options)
  expect(diagnostics[0]!.result!.decision).toBe('operator:A')
  expect(queue.tasks.some(t=>t.moodControlEvidence?.names.includes('A'))).toBe(true)
 })
 it('preserves pure service windows and refuses unknown physical completion',()=>{
  for(const type of [T.CLUE,T.FIAMMETTA]){
   const {data,queue,options,diagnostics}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300})
   const task=new MowerTask({type});queue.tasks.push(task)
   expect(planMowerPredictiveDeparture(data,queue,options)).toBeUndefined()
   const result=diagnostics[0]!.result!
   if(type===T.CLUE){expect(result.decision).toBe('operator:A');expect(result.events.find(e=>e.type==='departure-start')?.time).toBe(60)}
   else{expect(result.decision).toBeNull();expect(result.status).toBe('insufficient');expect(result.events).toEqual([])}
   expect(queue.tasks).toEqual([task]);expect(task.timeMicros).toBe(0);expect(data.operators.A!.currentRoom).toBe('room_1_1')
  }
 })
 it('checks physical plans and late critical tasks through the common horizon',()=>{
  for(const [type,time,plan] of [[T.NOT_SPECIFIC,0,{room_1_2:['Current']}],[T.EXHAUST_OFF,0,{room_1_2:['Current']}],[T.RUN_ORDER,10*3600,{}]] as const){
   const {data,queue,options,diagnostics}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300})
   const task=new MowerTask({type,plan:Object.fromEntries(Object.entries(plan).map(([room,row])=>[room,[...row]])),time:time/3600});queue.tasks.push(task)
   expect(planMowerPredictiveDeparture(data,queue,options)).toBeUndefined()
   expect(diagnostics[0]!.result).toMatchObject({decision:null,status:'insufficient'})
   expect(queue.tasks).toEqual([task]);expect(task.timeMicros).toBe(time*1_000_000)
  }
 })
 it('keeps an unknown physical task exactly at the common horizon insufficient',()=>{
  const {data,queue,options,diagnostics}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300})
  const task=new MowerTask({type:T.RUN_ORDER,time:27});queue.tasks.push(task)
  expect(planMowerPredictiveDeparture(data,queue,options)).toBeUndefined()
  expect(diagnostics[0]!.result).toMatchObject({decision:null,status:'insufficient'})
  expect(queue.tasks).toEqual([task]);expect(task.timeMicros).toBe(27*3_600_000_000)
 })
 it('preserves disabled and exhausted admission',()=>{
  for(const mode of ['disabled','exhaust']){
   const {data,queue,options}=fixture(mode!=='disabled')
   if(mode==='exhaust'){data.operators.A!.exhaustRequire=true;data.operators.B!.exhaustRequire=true}
   planMowerOrdinary(data,queue,options)
   expect(queue.tasks.some(t=>t.moodControlEvidence)).toBe(false)
  }
 })
 it('reuses identical input while the clock advances without moving physical resources',()=>{
  const {data,queue,options,diagnostics}=fixture()
  planMowerPredictiveDeparture(data,queue,options)
  data.nowMicros=1
  planMowerPredictiveDeparture(data,queue,options)
  expect(diagnostics[1]).toMatchObject({reused:true,candidates:0,events:0})
  expect(data.dorms[0]!.name).toBe('')
 })
})

describe('predictive wake and snapshot boundaries',()=>{
 it('maps both saved modes into the simulator without changing mood integration',()=>{
  for(const enabled of [false,true])expect(mowerAdvancedAssumptions({compatibility:{unrecognizedFields:{advanced_settings:{test_mood_calculation:enabled}}}} as never)).toMatchObject({predictiveMoodControl:enabled})
 })
 it('keeps one future memory event and consumes an expired version only once',()=>{
  const {data,queue,options}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:[],roomSeconds:0})
  planMowerPredictiveDeparture(data,queue,options);syncMowerPredictiveWake(data,queue);syncMowerPredictiveWake(data,queue)
  const wakes=queue.tasks.filter(t=>t.moodControlEvent)
  expect(wakes).toHaveLength(1);expect(wakes[0]!.plan).toEqual({})
  const wake=wakes[0]!,time=wake.timeMicros
  data.nowMicros=time;consumeMowerPredictiveWake(data,wake);queue.consume(wake);syncMowerPredictiveWake(data,queue)
  expect(queue.tasks.some(t=>t.moodControlEvent)).toBe(false)
  const retained=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['X']}});retained.executionRetained=true;queue.tasks.push(retained)
  data.policy.predictiveMoodControl=false;syncMowerPredictiveWake(data,queue)
  expect(queue.tasks).toContain(retained)
 })
 it('invalidates reused suggestions after a new successful observation',()=>{
  const {data,queue,options,diagnostics}=fixture()
  planMowerPredictiveDeparture(data,queue,options)
  data.operators.A!.timeStampMicros=1
  planMowerPredictiveDeparture(data,queue,options)
  expect(diagnostics[1]).toMatchObject({reused:false})
 })
 it('consumes a future early wake once and refuses it when new observations postpone its start',()=>{
  const {data,queue,options}=predictiveFixture({moods:{A:2,B:3,X:24},workRate:1,recoveryRate:24,threshold:0,exhaust:[],restInFull:['A','B'],roomSeconds:300})
  data.plan.room_1_3=['P'];data.operators.P=new MowerOperatorState({name:'P',room:'room_1_3',index:0,currentRoom:'dormitory_1',currentIndex:0,mood:23,timeStampMicros:0,operatorType:'high',restInFull:true})
  data.dorms[0]!.name='P';data.dorms[0]!.timeMicros=150_000_000
  const recovery=new MowerTask({type:T.SHIFT_ON,plan:{room_1_3:['P']}});recovery.timeMicros=150_000_000;queue.tasks.push(recovery)
  expect(planMowerPredictiveDeparture(data,queue,options)).toBeUndefined();syncMowerPredictiveWake(data,queue)
  const wake=queue.tasks.find(t=>t.moodControlEvent)!;expect(wake.timeMicros).toBe(450_000_000)
  data.nowMicros=wake.timeMicros;consumeMowerPredictiveWake(data,wake);queue.consume(wake)
  expect(planMowerPredictiveDeparture(data,queue,options)?.names).toEqual(['A'])
  syncMowerPredictiveWake(data,queue);expect(queue.tasks.some(t=>t.moodControlEvent)).toBe(false)
  data.operators.P!.timeStampMicros=data.nowMicros;recovery.timeMicros=600_000_000;data.dorms[0]!.timeMicros=600_000_000
  expect(planMowerPredictiveDeparture(data,queue,options)).toBeUndefined()
 })
 it('recomputes a determinate backup inside its own virtual snapshot',()=>{
  const {data,queue,options}=fixture();data.planConditions=[false]
  const model={count:1,evaluate:(state:MowerSchedulingData)=>[state.operators.A!.isResting()],swap:(state:MowerSchedulingData,conditions:boolean[])=>{const next=projectMowerArrangements(state,[]);next.planConditions=[...conditions];return next},transition:()=>({}),activate:()=>{throw new Error('preview must not activate the actual backup')}}
  planMowerPredictiveDeparture(data,queue,{...options,predictiveShiftModel:model})
  expect(data.planConditions).toEqual([false]);expect(data.operators.A!.currentRoom).toBe('room_1_1');expect(queue.tasks).toEqual([])
 })
})
