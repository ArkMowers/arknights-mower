import {describe,expect,it} from 'vitest'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerOperatorState} from './mowerOperatorState'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(storage:string){
  const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,
   positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R'],group:'g'}],
   beds:[{id:'dormitory_1_0',roomId:'dormitory_1',vip:true}],initialMorale:{A:0,R:24},
   mowerPolicy:{restingThreshold:0,powerPlantCount:2,opeRestingPriority:[]},
   mowerSourcePlan:{room_1_1:[{agent:'A',group:'g',replacement:['R']}],dormitory_1:[{agent:'Free',group:'',replacement:[]}]},
   mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
  }
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),op=source.data.operators.A!
  source.initial=false;source.firstInit=false
  op.currentRoom='room_1_1';op.currentIndex=0;op.mood=0;op.timeStampMicros=0
  if(storage.endsWith('standby')){
   source.data.operators.S=new MowerOperatorState({name:'S',alpha:true,room:'room_1_2',index:0,group:'g',operatorType:'high',restingPriority:'standby',currentRoom:'room_1_2',currentIndex:0,mood:0,timeStampMicros:0})
   source.data.operators.I=new MowerOperatorState({name:'I',alpha:true,room:'factory',index:0,group:'g',operatorType:'high',currentRoom:'',currentIndex:-1,mood:24,timeStampMicros:0})
   source.data.plan.room_1_2=['S'];source.data.plan.factory=['I']
  }
  const task=new MowerTask({type:T.SHIFT_OFF,time:-1,plan:{room_1_1:['R'],dormitory_1:['A']}})
  task.ordinaryCoordination=true;task.coordinationRequestNames=['A'];task.executionRetained=true
  const time=task.timeMicros,plan=structuredClone(task.plan),rates={workRate:()=>1,recoveryRate:()=>4}
  if(storage.startsWith('queued'))source.queue.tasks=[task]
  else{
   source.queue.tasks=[]
   source.waitingRecovery=[{task,reason:'backup-veto',conditionIndexes:[],observedNames:[],observation:'[[],{},[],[]]',deadlines:{},names:[],rooms:[]}]
   source.data.waitingRecoveryNames=new Set(['A','R'])
  }
  source.runReturn={wakeMicros:toMowerMicros(1),finishFallback:false}
  const pending=()=>[...source.queue.tasks,...source.waitingRecovery?.map(wait=>wait.task)??[]]
  return {state,source,op,task,time,plan,rates,pending}
}
function admitWorker({state,source,op}:ReturnType<typeof fixture>):void {
 state.occupants.room_1_1_0='R';state.bedOccupants.dormitory_1_0='A'
 op.currentRoom='dormitory_1';op.currentIndex=0;op.mood=0;op.moodIsPrediction=false;op.timeStampMicros=toMowerMicros(state.time)
 const cover=source.data.operators.R!;cover.currentRoom='room_1_1';cover.currentIndex=0;cover.timeStampMicros=op.timeStampMicros
 source.data.dorms[0]!.name='A';source.data.dorms[0]!.timeMicros=toMowerMicros(6);source.data.groupShiftState.g=true
}

describe('completed ordinary recovery across pending storage',()=>{
 it.each(['queued','parked','queued-working-standby','parked-working-standby'])('completes the same %s request after another arrangement admits its worker',storage=>{
  const f=fixture(storage),{state,source,op,task,time,plan,rates,pending}=f
  for(const reading of ['measured','prediction','unknown']){
   op.mood=reading==='prediction'?24:0;op.moodIsPrediction=reading==='prediction';op.timeStampMicros=reading==='unknown'?undefined:0
   state.time+=1/60
   settleRoster(state,rates)
   expect(pending()).toContain(task);expect(task.timeMicros).toBe(time);expect(task.plan).toEqual(plan)
   expect(task.coordinationCompletedRequestNames??[]).toEqual([])
  }
  admitWorker(f)
  settleRoster(state,rates)
  expect(pending()).not.toContain(task)
  expect(task.coordinationCompletedRequestNames).toEqual(['A'])
  expect(source.data.waitingRecoveryNames.has('A')).toBe(false)
  expect(task.timeMicros).toBe(time);expect(task.plan).toEqual(plan)
  expect(source.trace).toEqual([])
 })
 it.each(['requested','exhausted','full','support','started','product','explicit','forced'])('preserves unfinished or protected work: %s',kind=>{
  const f=fixture('queued-working-standby'),{state,source,task,time,plan,rates,pending}=f
  admitWorker(f)
  source.data.operators.I!.workaholic=true
  if(kind==='requested')task.coordinationRequestNames=['A','S']
  if(kind==='exhausted')source.data.operators.S!.exhaustRequire=true
  if(kind==='full')source.data.operators.S!.restInFull=true
  if(kind==='support')task.exhaustSupport=true
  if(kind==='started')task.arrangementStarted=true
  if(kind==='product')task.productShiftLocked=true
  if(kind==='explicit')task.backupExplicitSlots.add('dormitory_1\0'+0)
  if(kind==='forced')task.backupGroupRequest={backup:0,group:'g',action:'off',mode:'once'}
  retainMowerFailedTask(state,source.data,task,'unfinished recovery')
  for(let attempt=0;attempt<3;attempt++){
   settleRoster(state,rates);resumeMowerFailedTasks(state,source.data,source.queue)
   expect(pending()).toContain(task);expect(task.timeMicros).toBe(time);expect(task.plan).toEqual(plan)
  }
 })
 it.each(['low','prediction','unknown','measured'])('requires an idle personally requested standby to have observed full mood: %s',reading=>{
  const f=fixture('queued-working-standby'),{state,source,task,rates,pending}=f
  admitWorker(f)
  const standby=source.data.operators.S!
  standby.currentRoom='';standby.currentIndex=-1;standby.mood=reading==='low'?0:24
  standby.moodIsPrediction=reading==='prediction';standby.timeStampMicros=reading==='unknown'?undefined:0
  source.data.operators.C=new MowerOperatorState({name:'C',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0})
  standby.replacement=['C'];task.coordinationRequestNames=['S']
  expect(source.data.isStandby('S')).toBe(true)
  settleRoster(state,rates)
  expect(pending().includes(task)).toBe(reading!=='measured')
 })
 it('releases only the completed parked owner during another active room wait',()=>{
  const f=fixture('parked'),{state,source,task,time,rates,pending}=f
  admitWorker(f)
  const other=new MowerTask({type:T.SHIFT_ON,plan:{room_1_1:['R']}})
  source.waitingRecovery!.push({...source.waitingRecovery![0]!,task:other})
  source.data.waitingRecoveryNames=new Set(['A','R'])
  const active=new MowerTask({type:T.CLUE})
  source.execution={task:active,steps:(function*(){throw new Error('room return has not completed')})(),wakeMicros:toMowerMicros(2),intent:{},data:source.data}
  settleRoster(state,rates)
  expect(pending()).not.toContain(task);expect(pending()).toContain(other)
  expect(source.data.waitingRecoveryNames).toEqual(new Set(['R']))
  expect(source.execution.task).toBe(active);expect(task.timeMicros).toBe(time)
 })
})
