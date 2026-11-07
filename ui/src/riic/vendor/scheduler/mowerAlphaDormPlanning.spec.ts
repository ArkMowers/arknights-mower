import {describe,it,expect} from 'vitest'
import {fillMowerAlphaEmptyDorms} from './mowerAlphaDormPlanning'
import {projectMowerArrangements} from './mowerObservations'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {mowerDormTaskReservations} from './mowerAlphaCandidates'

function fixture(){
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,priorityReplacement:['R'],
  operators:{
   A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',replacement:['R'],mood:24,timeStampMicros:0}),
   R:new MowerOperatorState({name:'R',mood:0,timeStampMicros:0}),
   S:new MowerOperatorState({name:'S',mood:24,timeStampMicros:0}),
  },
  plan:{room_1_1:['A'],dormitory_1:['Free'],dormitory_2:['Free']},
  dorms:[new MowerDormState(['dormitory_1',0]),new MowerDormState(['dormitory_2',0])],
 })
 return {data,queue:new MowerTaskQueue()}
}

describe('empty-bed planning with retained failures',()=>{
 it.each(['target-group','actual-occupant-group','dorm-occupant'] as const)('protects a failed arrangement\'s %s while filling an independent bed',dependency=>{
  const data=new MowerSchedulingData({alpha:true,nowMicros:0,
   operators:{
    S:new MowerOperatorState({name:'S',room:'room_1_1',index:0,currentRoom:'dormitory_2',currentIndex:0,operatorType:'high',replacement:['C'],group:'g',restInFull:true,mood:5,timeStampMicros:0}),
    R:new MowerOperatorState({name:'R',room:'room_1_2',index:0,operatorType:'high',replacement:['W'],group:'g',restingPriority:'standby',mood:0,timeStampMicros:0}),
    C:new MowerOperatorState({name:'C',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0}),
    W:new MowerOperatorState({name:'W',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0}),
    I:new MowerOperatorState({name:'I',mood:2,timeStampMicros:0}),
   },standbyNames:['R'],
   plan:{room_1_1:['S'],room_1_2:['R'],dormitory_1:['Free'],dormitory_2:['Free']},
   dorms:[new MowerDormState(['dormitory_1',0]),new MowerDormState(['dormitory_2',0],'S',toMowerMicros(5))],
  })
  if(dependency==='actual-occupant-group'){
   data.operators.S!.group='other'
   data.operators.C!.group='g'
  }else if(dependency==='dorm-occupant'){
   data.operators.S!.currentRoom='';data.operators.S!.currentIndex=-1
   data.operators.R!.currentRoom='dormitory_2';data.operators.R!.currentIndex=0
   data.dorms[1]!.name='R'
  }
  const queue=new MowerTaskQueue(),failed=new MowerTask({type:dependency==='dorm-occupant'?T.RELEASE_DORM:T.SHIFT_ON,time:-1,plan:dependency==='dorm-occupant'?{dormitory_2:['Free']}:{room_1_1:['S']}})
  failed.executionFailure={reason:'waiting for related observations',rooms:Object.keys(failed.plan),snapshot:{intent:'unchanged',observations:{}}}
  queue.tasks=[failed]
  const plan=failed.plan,time=failed.timeMicros,failure=failed.executionFailure,reserved=mowerDormTaskReservations(data,queue.tasks)
  expect(reserved.names.has('R')).toBe(true)
  expect(reserved.names.has(dependency==='dorm-occupant'?'R':'C')).toBe(true)
  expect(reserved.names.has('I')).toBe(false)
  if(dependency==='dorm-occupant')expect(reserved.slots.has('dormitory_2\0'+0)).toBe(true)
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(true)
  const fill=queue.tasks.find(task=>task!==failed&&task.type===T.FILL_DORM)
  expect(fill?.plan).toEqual({dormitory_1:['I']})
  expect(queue.tasks).toContain(failed)
  expect(failed.plan).toBe(plan)
  expect(failed.timeMicros).toBe(time)
  expect(failed.executionFailure).toBe(failure)
 })

 it('executes the independent priority replacement admission through source dispatch',()=>{
  const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,
   positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']},{id:'room_1_2_0',roomId:'room_1_2',primary:'S',candidates:[]}],
   beds:[{id:'dormitory_1_0',roomId:'dormitory_1',vip:true}],initialMorale:{A:24,S:24,R:0},idleOperators:[],
   mowerPolicy:{restingThreshold:0,powerPlantCount:2,opeRestingPriority:[]},
   mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],room_1_2:[{agent:'S',group:'',replacement:[]}],dormitory_1:[{agent:'Free',group:'',replacement:[]}]},
   mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0,priorityReplacement:['R']},
  }
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),failed=new MowerTask({type:T.SHIFT_OFF,time:-1,plan:{room_1_2:['Current']}})
  source.initial=false
  for(const [slot,name] of Object.entries(state.occupants)){
   const op=source.data.operators[name]!
   op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0
  }
  source.queue.tasks=[failed]
  retainMowerFailedTask(state,source.data,failed,'waiting for related observations')
  const time=failed.timeMicros,plan=failed.plan,failure=failed.executionFailure,rates={workRate:()=>1,recoveryRate:()=>4}
  for(let run=0;run<3;run++)settleRoster(state,rates)
  expect(state.bedOccupants.dormitory_1_0).toBe('R')
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(source.trace.filter(task=>task.type==='FILL_DORM')).toHaveLength(1)
  expect(source.trace.some(task=>task.type==='SHIFT_OFF')).toBe(false)
  expect(source.queue.tasks).toContain(failed)
  expect(failed.plan).toBe(plan)
  expect(failed.executionFailure).toBe(failure)
  expect(failed.timeMicros).toBe(time)
 })

 it.each([T.SHIFT_OFF,T.EXHAUST_OFF,T.FIAMMETTA,T.RELEASE_DORM,T.FILL_DORM])('admits a priority replacement beside a failed $key task without consuming its reservations',type=>{
  const {data,queue}=fixture(),failed=new MowerTask({time:-1,type,plan:{dormitory_2:['S']},metadata:'S'})
  failed.dormFillPlan={dormitory_2:['S']}
  failed.executionFailure={reason:'waiting for related observations',rooms:['dormitory_2'],snapshot:{intent:'unchanged',observations:{}}}
  queue.tasks=[failed]
  const time=failed.timeMicros,plan=failed.plan,failure=failed.executionFailure
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(true)
  const fill=queue.tasks.find(task=>task!==failed&&task.type===T.FILL_DORM)
  expect(fill?.plan).toEqual({dormitory_1:['R']})
  expect(queue.tasks).toContain(failed)
  expect(failed.plan).toBe(plan)
  expect(failed.executionFailure).toBe(failure)
  expect(failed.timeMicros).toBe(time)
  expect(data.operators.R!.currentRoom).toBe('')
  const projected=projectMowerArrangements(data,[fill!.plan])
  expect(projected.currentOperator('dormitory_1',0)?.name).toBe('R')
  expect(projected.currentOperator('dormitory_2',0)).toBeUndefined()
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(false)
  expect(queue.tasks.filter(task=>task.type===T.FILL_DORM&&task!==failed)).toEqual([fill])
  expect(queue.tasks).toContain(failed)
  expect(failed.timeMicros).toBe(time)
 })

 it.each([T.SHIFT_OFF,T.EXHAUST_OFF])('keeps a future dispatchable $key request ahead of empty-bed filling',type=>{
  const {data,queue}=fixture(),pending=new MowerTask({type,time:1,plan:{dormitory_2:['S']}})
  queue.tasks=[pending]
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(false)
  expect(queue.tasks).toEqual([pending])
  expect(data.operators.R!.currentRoom).toBe('')
 })

 it.each([T.SHIFT_ON,T.FIAMMETTA,T.SELF_CORRECTION,T.RE_ORDER])('keeps a due dispatchable $key arrangement ahead of empty-bed filling',type=>{
  const {data,queue}=fixture(),pending=new MowerTask({type,plan:{dormitory_2:['S']}})
  queue.tasks=[pending]
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(false)
  expect(queue.tasks).toEqual([pending])
 })

 it('keeps retained targets reserved after dispatch reopens',()=>{
  const {data,queue}=fixture(),pending=new MowerTask({type:T.FILL_DORM,time:1,plan:{dormitory_1:['R']}})
  pending.executionRetained=true
  pending.dormFillPlan={dormitory_1:['R']}
  queue.tasks=[pending]
  data.nowMicros=toMowerMicros(1)
  expect(fillMowerAlphaEmptyDorms(data,queue)).toBe(false)
  expect(queue.tasks[0]).toBe(pending)
  expect(pending.timeMicros).toBe(toMowerMicros(1))
 })
})
