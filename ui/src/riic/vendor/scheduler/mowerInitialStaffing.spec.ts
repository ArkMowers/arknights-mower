import {mowerInitialStaffingBlocked} from './mowerInitialStaffing'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {mowerCorrectionPlan} from './mowerCorrection'
import {projectMowerArrangements} from './mowerObservations'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function fixture(){
 const make=(name:string,room:string,index:number,group='',replacement:string[]=[])=>new MowerOperatorState({name,room,index,group,replacement,currentRoom:room,currentIndex:index,mood:24,timeStampMicros:0,operatorType:room?'high':'low'})
 const operators={A:make('A','room_1_1',0,'g',['R']),B:make('B','room_1_2',0,'g',['S']),R:make('R','',-1),S:make('S','',-1),K:make('K','dormitory_1',0)}
 operators.A.mood=0;operators.A.currentRoom='';operators.A.currentIndex=-1;operators.B.mood=5
 operators.R.currentRoom='room_1_1';operators.R.currentIndex=0
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,plan:{room_1_1:['A'],room_1_2:['B'],dormitory_1:['K','Free','Free','Free','Free']},operators,dorms:[1,2,3,4].map(i=>new MowerDormState(['dormitory_1',i])),policy:{restingThreshold:.65}})
 const model:MowerShiftModel={count:0,evaluate:d=>d.planConditions,swap:d=>d,transition:()=>({}),activate:()=>{}}
 return {data,model}
}
describe('initial staffing merges correction with ordinary departures',()=>{
 it('rests low-mood primaries directly without an intermediate return',()=>{
  const {data,model}=fixture(),task=Object.assign(new MowerTask({type:T.SELF_CORRECTION,plan:mowerCorrectionPlan(data)}),{initialStaffing:true}),queue=new MowerTaskQueue()
  expect(task.plan.room_1_1).toEqual(['A']);queue.tasks=[task]
  prepareMowerShiftCycle(data,task,queue,model)
  const projected=projectMowerArrangements(data,[task.plan])
  expect(projected.operators.A!.isResting()).toBe(true)
  expect(projected.operators.B!.isResting()).toBe(true)
  expect(projected.currentOperator('room_1_1',0)?.name).toBe('R')
  expect(projected.currentOperator('room_1_2',0)?.name).toBe('S')
  expect(task.plan.room_1_1??[]).not.toContain('A')
  expect(data.operators.A!.currentRoom).toBe('')
 })
 it.each(['explicit','due'])('retains %s return intent during initialization',kind=>{
  const {data,model}=fixture(),task=Object.assign(new MowerTask({type:T.SELF_CORRECTION,plan:mowerCorrectionPlan(data)}),{initialStaffing:true}),queue=new MowerTaskQueue()
  queue.tasks=[task]
  if(kind==='explicit')task.backupExplicitSlots.add('room_1_1\0'+'0')
  else queue.tasks.push(new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['A']}}))
  prepareMowerShiftCycle(data,task,queue,model)
  expect(projectMowerArrangements(data,[task.plan]).operators.A!.currentRoom).toBe('room_1_1')
 })
 it('keeps an observed low-mood dorm resident resting when its timer is unknown',()=>{
  const {data}=fixture(),op=data.operators.A!
  op.currentRoom='dormitory_1';op.currentIndex=1;op.mood=24;op.timeStampMicros=undefined;data.dorms[0]!.name='A';data.dormMoodEstimates.set('A',[5,0])
  data.operators.B!.currentRoom='';data.operators.B!.currentIndex=-1;data.operators.B!.mood=24
  const plan=mowerCorrectionPlan(data)
  expect(plan.room_1_1??[]).not.toContain('A')
  expect(data.dormMoodEstimates.get('A')).toEqual([5,0])
  expect(op.timeStampMicros).toBeUndefined()
 })
})

it('applies the merged initial arrangement with a known idle primary through real source dispatch',()=>{
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={room_1_1:[{agent:'A',group:'g',replacement:['R']}],room_1_2:[{agent:'B',group:'g',replacement:['S']}],dormitory_1:['K0','K1','K2','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))}
 const config:RuntimeConfig={mowerAlpha:true,mowerSourcePlan:rows,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,dormitory:room.startsWith('dorm'),permanent:room.startsWith('dorm')}])),beds:[3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===3})),initialMorale:{A:0,B:5,R:24,S:24},idleOperators:[],mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}}
 const state=createRosterRuntime(config)
 state.occupants.room_1_1_0='R'
 const source=getMowerSourceRuntime(state)
 source.data.operators.A!.mood=0;source.data.operators.A!.timeStampMicros=0
 settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
 expect(state.occupants.room_1_1_0).toBe('R')
 expect(state.occupants.room_1_2_0).toBe('S')
 expect(Object.values(state.bedOccupants).sort()).toEqual(['A','B'])
 expect(source.trace.some(task=>task.plan.room_1_1?.includes('A'))).toBe(false)
 expect(state.diagnostics.filter(d=>d.code==='mower-task-exception')).toEqual([])
})

function startupFixture(){
 const state=createRosterRuntime({mowerAlpha:true,mowerRunOrderEnabled:false,mowerTaskScheduling:{adjustForRunOrders:false},
  mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}]},
  positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']}],beds:[],initialMorale:{A:24,R:24},idleOperators:[],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}})
 state.occupants.room_1_1_0='R'
 const source=getMowerSourceRuntime(state);source.initial=false;source.firstInit=false;source.initialStaffingPending=true;source.queue.tasks=[]
 return {state,source}
}

describe('initial staffing waits for explicit arrangements',()=>{
 it.each([T.SHIFT_ON,T.SHIFT_OFF,T.SELF_CORRECTION])('preserves a failed $key and its deadline until its dependency is released',type=>{
  const {state,source}=startupFixture(),task=new MowerTask({type,plan:{room_1_1:['A']}})
  source.queue.tasks=[task];retainMowerFailedTask(state,source.data,task,'waiting for a relevant observation',['room_1_1'])
  const failure=task.executionFailure,at=task.timeMicros
  for(let index=0;index<3;index++){
   settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
   expect(source.initialStaffingPending).toBe(true)
   expect(source.queue.tasks).toContain(task);expect(task.executionFailure).toBe(failure);expect(task.timeMicros).toBe(at)
   expect(source.trace).toEqual([])
  }
  source.queue.consume(task)
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.initialStaffingPending).toBe(false)
  expect(state.occupants.room_1_1_0).toBe('A')
  const trace=[...source.trace]
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  expect(source.trace).toEqual(trace)
 })
 it('allows ordinary releases and future returns while retaining an active backup dependency',()=>{
  const release=new MowerTask({type:T.RELEASE_DORM,plan:{dormitory_1:['Free']}}),future=new MowerTask({time:1,type:T.SHIFT_ON,plan:{room_1_1:['A']}})
  expect(mowerInitialStaffingBlocked([release,future],0)).toBe(false)
  future.backupShiftActive=true
  expect(mowerInitialStaffingBlocked([release,future],0)).toBe(true)
  expect(future.time).toBe(1)
 })
 it('keeps an explicit parked recovery task as a dependency',()=>{
  const task=new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['A']}})
  expect(mowerInitialStaffingBlocked([task],0)).toBe(true)
  task.plan={}
  expect(mowerInitialStaffingBlocked([task],0)).toBe(false)
 })
})
