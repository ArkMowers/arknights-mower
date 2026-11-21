import {describe,it,expect} from 'vitest'
import {fillMowerAlphaEmptyDorms,prepareMowerAlphaDormFill,protectMowerAlphaDormFillDispatch} from './mowerAlphaDormPlanning'
import {projectMowerArrangements} from './mowerObservations'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {createRosterRuntime,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {retainMowerFailedTask} from './mowerTaskFailure'
import {mowerDormTaskReservations,planMowerAlphaDormFill} from './mowerAlphaCandidates'
import {planMowerOrdinary} from './mowerOrdinaryPlanning'

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


it('preserves a retained return recovery bed while an independent departure is reordered',()=>{
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,restingPriorityNames:['A'],
  plan:{room_1_1:['A'],room_1_2:['U'],dormitory_1:['Free'],dormitory_2:['Free']},
  operators:{
   A:new MowerOperatorState({name:'A',room:'room_1_1',index:0,currentRoom:'room_1_1',currentIndex:0,operatorType:'high',replacement:['X'],mood:5,timeStampMicros:0}),
   U:new MowerOperatorState({name:'U',room:'room_1_2',index:0,currentRoom:'dormitory_1',currentIndex:0,operatorType:'high',replacement:['Y'],restInFull:true,mood:5,timeStampMicros:0}),
   X:new MowerOperatorState({name:'X',mood:24,timeStampMicros:0}),
   Y:new MowerOperatorState({name:'Y',currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0}),
  },dorms:[new MowerDormState(['dormitory_1',0],'U',toMowerMicros(5)),new MowerDormState(['dormitory_2',0])],
 })
 const queue=new MowerTaskQueue(),pending=new MowerTask({type:T.SHIFT_ON,time:-1,plan:{room_1_2:['U']}})
 pending.executionRetained=true;pending.fiaReturnTarget='U';pending.fiaReturnMicros=0;queue.tasks=[pending]
 const reserved=mowerDormTaskReservations(data,queue.tasks),time=pending.timeMicros,intent=structuredClone(pending.plan)
 const plan=planMowerOrdinary(data,queue,{reservedNames:reserved.names,reservedSlots:reserved.slots})!
 const after=projectMowerArrangements(data,[plan])
 expect(after.currentOperator('room_1_1',0)?.name).toBe('X')
 expect(after.currentOperator('dormitory_1',0)?.name).toBe('U')
 expect(after.currentOperator('dormitory_2',0)?.name).toBe('A')
 expect(queue.tasks).toContain(pending);expect(pending.plan).toEqual(intent);expect(pending.timeMicros).toBe(time)
})

describe('ordinary dorm fill dispatch re-admission',()=>{
 function queuedFill(){
  const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,
   positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'R',candidates:['X']},{id:'room_1_2_0',roomId:'room_1_2',primary:'B',candidates:['Y']}],
   beds:[0,1,2].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===0})),
   initialMorale:{R:10,B:0,X:24,Y:24,I:2,J:24},idleOperators:['I','J'],
   mowerPolicy:{restingThreshold:0,powerPlantCount:2,opeRestingPriority:['R']},
   mowerSourcePlan:{room_1_1:[{agent:'R',group:'',replacement:['X']}],room_1_2:[{agent:'B',group:'',replacement:['Y']}],dormitory_1:[0,1,2].map(()=>({agent:'Free',group:'',replacement:[]}))},
   mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:['R'],lowPriority:[],refreshDrained:[],lingMode:0},
  }
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
  source.initial=false;source.firstInit=false
  state.occupants.room_1_1_0='X';state.occupants.room_1_2_0='Y';state.bedOccupants.dormitory_1_2='R'
  for(const op of Object.values(source.data.operators)){op.currentRoom='';op.currentIndex=-1;op.mood=state.morale[op.name]??24;op.timeStampMicros=0}
  for(const [slot,name] of Object.entries({...state.occupants,...state.bedOccupants})){if(!name)continue;const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1))}
  source.data.dorms[2]!.name='R';source.data.dorms[2]!.timeMicros=toMowerMicros(4)
  const fill=planMowerAlphaDormFill(source.data,source.queue,true)!
  expect(fill.plan.dormitory_1?.[0]).toBe('R')
  const departure=new MowerTask({type:T.SHIFT_OFF,time:1,plan:{dormitory_1:['B','Current','Current']}})
  source.queue.tasks.push(departure)
  return {state,source,fill,departure}
 }
 it.each(['queued','waiting'] as const)('does not move an unfinished resident into a newly %s departure bed through real source dispatch',where=>{
  const {state,source,fill,departure}=queuedFill(),time=fill.timeMicros,id=fill
  if(where==='waiting'){
   source.queue.tasks=source.queue.tasks.filter(task=>task!==departure)
   source.waitingRecovery=[{task:departure,reason:'backup-veto',conditionIndexes:[],observedNames:[],observation:'[[],{},[],[]]',deadlines:{},names:[],rooms:[]}]
  }
  settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
  const dispatched=source.trace.find(task=>task.type==='FILL_DORM')!
  expect(dispatched).toBeDefined()
  expect(dispatched.plan.dormitory_1?.[0]??'Current').toBe('Current')
  expect(Object.values(dispatched.plan).flat()).not.toContain('R')
  expect(state.bedOccupants.dormitory_1_2).toBe('R')
  expect(source.data.operators.R!.isResting()).toBe(true)
  expect(Object.values(state.bedOccupants)).toContain('I')
  expect(fill).toBe(id);expect(fill.arrangementStarted).toBe(true);expect(fill.timeMicros).toBe(time)
  expect(departure.plan).toEqual({dormitory_1:['B','Current','Current']})
  if(where==='waiting'){expect(source.waitingRecovery?.some(wait=>wait.task===departure)).toBe(true);expect(source.queue.tasks).not.toContain(departure)}
 })
 it.each(['started','retained','retry','restore','product','backup','strict','explicit'] as const)('preserves a %s fill and its original execution metadata',protection=>{
  const {source,fill,departure}=queuedFill()
  if(protection==='started')fill.arrangementStarted=true
  if(protection==='retained')fill.executionRetained=true
  if(protection==='retry')fill.arrangementRetryRoom='dormitory_1'
  if(protection==='restore')fill.dormRecoveryRestore=['R']
  if(protection==='product')fill.productShiftLocked=true
  if(protection==='backup')fill.backupShiftActive=true
  if(protection==='strict')fill.strictMoodLimit=true
  if(protection==='explicit')fill.backupExplicitSlots.add('dormitory_1\0'+0)
  const plan=fill.plan,intent=fill.dormFillPlan,time=fill.timeMicros
  expect(prepareMowerAlphaDormFill(source.data,fill,[fill,departure])).toBe(false)
  expect(fill.plan).toBe(plan);expect(fill.dormFillPlan).toBe(intent);expect(fill.timeMicros).toBe(time)
 })
 it('leaves an ordinary mood check without fill intent unchanged',()=>{
  const {data,queue}=fixture(),task=new MowerTask({type:T.NOT_SPECIFIC,metadata:'R'})
  const plan=task.plan
  expect(prepareMowerAlphaDormFill(data,task,queue.tasks)).toBe(false)
  expect(task.plan).toBe(plan)
 })
})


it('rebuilds a non-empty ordinary dorm replacement without requiring a vacant bed',()=>{
 const {data,queue}=fixture()
 data.operators.S!.currentRoom='dormitory_1';data.operators.S!.currentIndex=0
 data.operators.L=new MowerOperatorState({name:'L',currentRoom:'dormitory_2',currentIndex:0,mood:24,timeStampMicros:0})
 data.dorms[0]!.name='S';data.dorms[1]!.name='L'
 const fill=planMowerAlphaDormFill(data,queue,false)!
 expect(fill.type).toBe(T.NOT_SPECIFIC)
 const pending=new MowerTask({type:T.SHIFT_OFF,time:1,plan:{dormitory_1:['S']}}),time=fill.timeMicros
 expect(prepareMowerAlphaDormFill(data,fill,[fill,pending])).toBe(true)
 expect(fill.type).toBe(T.NOT_SPECIFIC)
 expect(fill.plan).toEqual({dormitory_2:['R']})
 expect(fill.timeMicros).toBe(time)
})

it('clears a stale ordinary fill when no current candidate remains eligible',()=>{
 const {data,queue}=fixture(),fill=planMowerAlphaDormFill(data,queue,true)!
 for(const op of Object.values(data.operators))if(!op.currentRoom){op.currentRoom='room_2_1';op.currentIndex=0}
 const time=fill.timeMicros
 expect(prepareMowerAlphaDormFill(data,fill,[fill])).toBe(false)
 expect(fill.plan).toEqual({});expect(fill.dormFillPlan).toEqual({});expect(fill.dormMoodResidents).toEqual([]);expect(fill.simpleDormFill).toBe(false)
 expect(fill.timeMicros).toBe(time)
})

it('does not rebuild a default-compatible ordinary fill',()=>{
 const {data,queue}=fixture(),fill=planMowerAlphaDormFill(data,queue,true)!,plan=fill.plan
 data.alpha=false
 expect(prepareMowerAlphaDormFill(data,fill,[])).toBe(false)
 expect(fill.plan).toBe(plan)
})


it('defers a newly re-admitted fill behind a critical support task without merging unrelated releases',()=>{
 const {data,queue}=fixture(),fill=planMowerAlphaDormFill(data,queue,true)!
 const support=new MowerTask({type:T.SWAP_SUPPORT,time:1/60,plan:{train:['S']}})
 const first=new MowerTask({type:T.RELEASE_DORM,time:2,plan:{dormitory_1:['Free']},metadata:'R'})
 const second=new MowerTask({type:T.RELEASE_DORM,time:2.01,plan:{dormitory_2:['Free']},metadata:'S'})
 queue.tasks.push(support,first,second)
 const firstPlan=first.plan,secondPlan=second.plan
 expect(prepareMowerAlphaDormFill(data,fill,[fill,support])).toBe(true)
 protectMowerAlphaDormFillDispatch(queue,data.nowMicros)
 expect(fill.simpleDormFill).toBe(true)
 expect(fill.timeMicros).toBeGreaterThan(support.timeMicros)
 expect(queue.find()).toBe(support)
 expect(queue.tasks.filter(task=>task.type===T.RELEASE_DORM)).toEqual([first,second])
 expect(first.plan).toBe(firstPlan);expect(second.plan).toBe(secondPlan)
 expect(first.timeMicros).toBe(toMowerMicros(2));expect(second.timeMicros).toBe(toMowerMicros(2.01))
})

it('budgets retained tasks on temporary copies and leaves failed tasks outside priority protection',()=>{
 const queue=new MowerTaskQueue(),retained=new MowerTask({type:T.FILL_DORM,plan:{dormitory_1:['R']}}),failed=new MowerTask({type:T.FILL_DORM,plan:{dormitory_2:['S']}})
 retained.executionRetained=true;retained.dormFillPlan=structuredClone(retained.plan)
 failed.executionFailure={reason:'unobserved',snapshot:{intent:'unchanged',observations:{}},rooms:['dormitory_2']}
 const support=new MowerTask({type:T.SWAP_SUPPORT,time:1/60,plan:{train:['S']}})
 queue.tasks=[retained,failed,support]
 const plan=retained.plan,time=retained.timeMicros,failure=failed.executionFailure,failedPlan=failed.plan,failedTime=failed.timeMicros
 protectMowerAlphaDormFillDispatch(queue,0)
 expect(queue.tasks).toContain(retained);expect(retained.plan).toBe(plan);expect(retained.timeMicros).toBe(time);expect(retained.simpleDormFill).toBe(false)
 expect(queue.tasks.at(-1)).toBe(failed);expect(failed.executionFailure).toBe(failure);expect(failed.plan).toBe(failedPlan);expect(failed.timeMicros).toBe(failedTime)
 expect(queue.find()).toBe(support)
})

it.each([false,true])('keeps a waiting return source bed while an independent bed is vacant=%s',vacant=>{
 const {data}=fixture()
 data.operators.S!.currentRoom='dormitory_1';data.operators.S!.currentIndex=0;data.dorms[0]!.name='S'
 if(!vacant){data.operators.L=new MowerOperatorState({name:'L',currentRoom:'dormitory_2',currentIndex:0,mood:24,timeStampMicros:0});data.dorms[1]!.name='L'}
 const fill=new MowerTask({type:T.NOT_SPECIFIC,plan:{dormitory_2:['R']}})
 fill.dormFillPlan=structuredClone(fill.plan)
 const waiting=new MowerTask({type:T.SHIFT_ON,time:1,plan:{room_1_1:['S']}}),plan=waiting.plan,time=waiting.timeMicros
 expect(prepareMowerAlphaDormFill(data,fill,[fill,waiting],{},[waiting])).toBe(true)
 expect(fill.plan).toEqual({dormitory_2:['R']})
 const projected=projectMowerArrangements(data,[fill.plan])
 expect(projected.currentOperator('dormitory_1',0)?.name).toBe('S')
 expect(projected.currentOperator('dormitory_2',0)?.name).toBe('R')
 expect(waiting.plan).toBe(plan);expect(waiting.timeMicros).toBe(time)
})

it('does not reserve every ordinary queued return source bed as a waiting dependency',()=>{
 const {data}=fixture()
 data.operators.S!.currentRoom='dormitory_1';data.operators.S!.currentIndex=0;data.dorms[0]!.name='S'
 data.operators.L=new MowerOperatorState({name:'L',currentRoom:'dormitory_2',currentIndex:0,mood:24,timeStampMicros:0});data.dorms[1]!.name='L'
 const fill=new MowerTask({type:T.NOT_SPECIFIC,plan:{dormitory_2:['R']}})
 fill.dormFillPlan=structuredClone(fill.plan)
 const pending=new MowerTask({type:T.SHIFT_ON,time:1,plan:{room_1_1:['S']}})
 expect(prepareMowerAlphaDormFill(data,fill,[fill,pending])).toBe(true)
 expect(fill.plan).toEqual({dormitory_1:['R']})
})

it('passes parked return source-bed reservations through actual ordinary fill dispatch',()=>{
 const config:RuntimeConfig={mowerAlpha:true,mowerRunOrderEnabled:false,
  positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']}],
  beds:['dormitory_1','dormitory_2'].map(room=>({id:room+'_0',roomId:room,vip:true})),
  initialMorale:{A:24,R:0,S:24,L:24},idleOperators:['S','L'],
  mowerPolicy:{restingThreshold:0,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourcePlan:{room_1_1:[{agent:'A',group:'',replacement:['R']}],dormitory_1:[{agent:'Free',group:'',replacement:[]}],dormitory_2:[{agent:'Free',group:'',replacement:[]}]},
  mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0,priorityReplacement:['R']},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 state.bedOccupants={dormitory_1_0:'S',dormitory_2_0:'L'}
 for(const op of Object.values(source.data.operators)){op.mood=state.morale[op.name]??24;op.timeStampMicros=0}
 for(const [slot,name] of Object.entries({...state.occupants,...state.bedOccupants})){const op=source.data.operators[name]!;op.currentRoom=slot.slice(0,slot.lastIndexOf('_'));op.currentIndex=Number(slot.slice(slot.lastIndexOf('_')+1));op.mood=state.morale[name]!;op.timeStampMicros=0}
 source.data.dorms[0]!.name='S';source.data.dorms[1]!.name='L'
 const fill=planMowerAlphaDormFill(source.data,source.queue,false)!
 expect(fill.plan).toEqual({dormitory_1:['R']})
 const waiting=new MowerTask({type:T.SHIFT_ON,time:1,plan:{room_1_1:['S']}})
 source.waitingRecovery=[{task:waiting,reason:'backup-veto',conditionIndexes:[],observedNames:[],observation:'[[],{},[],[]]',deadlines:{},names:[],rooms:[]}]
 settleRoster(state,{workRate:()=>1,recoveryRate:()=>4})
 expect(source.trace.some(task=>task.plan.dormitory_2?.includes('R'))).toBe(true)
 expect(source.trace.some(task=>task.plan.dormitory_1?.includes('R'))).toBe(false)
 expect(state.bedOccupants.dormitory_1_0).toBe('S')
 expect(state.bedOccupants.dormitory_2_0).toBe('R')
 expect(source.waitingRecovery?.some(wait=>wait.task===waiting)).toBe(true)
 expect(source.queue.tasks).not.toContain(waiting)
})
