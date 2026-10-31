import {afterEach,describe,expect,it,vi} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {MowerDormState} from './mowerSchedulingData'
import {validateMowerCoordinationSupport} from './mowerAlphaExhaustSupport'
import {coalesceMowerBackupTransition,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import * as ordinaryPlanning from './mowerOrdinaryPlanning'

const model:MowerShiftModel={count:0,evaluate:data=>data.planConditions,swap:data=>data,transition:()=>({}),activate:()=>{}}
const rates={workRate:()=>1,recoveryRate:()=>4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}
function generatedSupport(recall=false,holdMode?:'while_active'|'forced',requestGroup=false,sharedFollower=false){
 const rows={room_1_1:[{agent:'A',group:requestGroup?'requested':'',replacement:['X']}],room_1_2:[{agent:'B',group:'resting',replacement:recall?['X']:['X','Y']}],room_1_3:[{agent:'C',group:'',replacement:['Z']}],contact:[{agent:'D',group:'resting',replacement:['W']}],dormitory_1:[...['K1','K2'].map(agent=>({agent,group:'',replacement:[]})),...['Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))]}
 if(sharedFollower){rows.room_1_1[0]!.group='requested';Object.assign(rows.contact[0]!,{group:'requested',groupBindings:[{group:'requested',replacement:['W']},{group:'resting',replacement:['W']}]})}
 const config:RuntimeConfig={
  mowerAlpha:true,mowerSourcePlan:rows,
  positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),
  beds:[{id:'dormitory_1_2',roomId:'dormitory_1',vip:true},{id:'dormitory_1_3',roomId:'dormitory_1',vip:false},{id:'dormitory_1_4',roomId:'dormitory_1',vip:false}],
  initialMorale:{A:0,B:4,C:4,D:4,X:24,Y:24,Z:24,W:24},idleOperators:[],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
  mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000},
 }
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false
 for(const position of config.positions){const op=data.operators[position.primary]!;Object.assign(op,{currentRoom:position.roomId,currentIndex:Number(position.id.slice(position.id.lastIndexOf('_')+1)),mood:state.morale[op.name]??24,timeStampMicros:0})}
 state.occupants.room_1_2_0='X';state.occupants.contact_0='W';state.bedOccupants.dormitory_1_2='B';state.bedOccupants.dormitory_1_3='D'
 Object.assign(data.operators.B!,{currentRoom:'dormitory_1',currentIndex:2,mood:4,timeStampMicros:0})
 Object.assign(data.operators.X!,{currentRoom:'room_1_2',currentIndex:0,mood:24,timeStampMicros:0})
 Object.assign(data.operators.D!,{currentRoom:'dormitory_1',currentIndex:3,mood:4,timeStampMicros:0})
 Object.assign(data.operators.W!,{currentRoom:'contact',currentIndex:0,mood:24,timeStampMicros:0})
 data.dorms=[new MowerDormState(['dormitory_1',2],'B',toMowerMicros(5)),new MowerDormState(['dormitory_1',3],'D',toMowerMicros(5)),new MowerDormState(['dormitory_1',4])]
 if(recall)for(const name of ['B','C','D']){state.morale[name]=20;Object.assign(data.operators[name]!,{mood:20,timeStampMicros:0,depletionRate:1})}
 const exhausted=new MowerTask({type:T.EXHAUST_OFF,metadata:sharedFollower?'A,D':'A'})
 if(holdMode||requestGroup){
  const groupTasks=[[{group:requestGroup?'requested':'resting',action:'off' as const,mode:holdMode??'while_active' as const}]]
  data.backupGroupTasks=groupTasks;data.planConditions=[true]
  state.mowerShiftModel={...model,count:1,groupTasks}
 }
 source.queue.tasks=requestGroup?[]:[exhausted]
 settleMowerSource(state,rates)
 const requested=requestGroup?source.queue.tasks.find(t=>t.backupGroupRequest&&t.type===T.EXHAUST_OFF)!:exhausted
 if(requestGroup)for(let n=0;n<30&&!requested.executionFailure&&!Object.values(state.bedOccupants).includes('A');n++){
  settleMowerSource(state,rates)
  advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
 }
 expect(source.queue.tasks).toContain(requested)
 expect(requested.executionFailure).toBeDefined();expect(requested.timeMicros).toBe(0)
 const support=source.queue.tasks.find(task=>task.type===T.SELF_CORRECTION)!,retry=source.queue.tasks.find(task=>task.type===T.EXHAUST_OFF)!
 if(holdMode==='forced'){expect(support).toBeUndefined();return {state,source,data:source.data,queue:source.queue,support,retry}}
 expect(support).toBeDefined();expect(retry).toBe(requested)
 expect(support.plan).toEqual(recall?{room_1_2:['B'],contact:['D']}:{room_1_2:['Y']})
 return {state,source,data:source.data,queue:source.queue,support,retry}
}

afterEach(()=>vi.restoreAllMocks())
describe('exhaust support dispatch preserves native recovery capacity',()=>{
 it('keeps an existing shared-follower cover while releasing another cover',()=>{
  const {state,source,data,support}=generatedSupport(false,undefined,false,true)
  expect(support.plan).toEqual({room_1_2:['Y']})
  expect(validateMowerCoordinationSupport(data,support.plan,['A','D'],{urgentExhaust:true,reservedNames:new Set(['W'])})).toBe(false)
  for(let n=0;n<40&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   if(!Object.values(state.bedOccupants).includes('A'))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('Y')
  expect(state.occupants.contact_0).toBe('W')
  expect(source.queue.tasks).not.toContain(support)
  expect(data.operators.B!.currentRoom).toBe('dormitory_1')
 })
 for(const recall of [false,true])it(`keeps the last bed available after ${recall?'group recall':'cover swap'} from real runtime generation`,()=>{
  const {data,queue,support,retry}=generatedSupport(recall),original=structuredClone(support.plan),before=JSON.stringify(data),time=support.timeMicros
  prepareMowerShiftCycle(data,support,queue,model)
  expect(support.plan).toEqual(original)
  expect(support.timeMicros).toBe(time)
  expect(JSON.stringify(data)).toBe(before)
  expect(support.exhaustSupport).toBe(true)
  expect(retry.exhaustSupport).toBe(false)
  const confirmed=projectMowerArrangements(data,[support.plan]),off:MowerTaskPlan={}
  expect(ordinaryPlanning.mowerGetRestingPlan(confirmed,['A'],[],off)).toBe(true)
  Object.assign(off,ordinaryPlanning.mowerTryReorder(confirmed,off))
  expect(off.room_1_1).toEqual(['X'])
  expect(off.dormitory_1).toContain('A')
  expect(off.dormitory_1).not.toContain('C')
 })
 it('still applies backup transitions required by the support arrangement',()=>{
  const {data,queue,support}=generatedSupport()
  data.planConditions=[false]
  const backup:MowerShiftModel={...model,count:1,evaluate:d=>[d.operators.X!.currentRoom!=='room_1_2'],swap:(d,conditions)=>{d.planConditions=[...conditions];return d},transition:(_previous,_next,_original,conditions):MowerTaskPlan=>conditions[0]?{room_1_3:['Z']}:{} }
  prepareMowerShiftCycle(data,support,queue,backup)
  expect(support.plan).toEqual({room_1_2:['Y'],room_1_3:['Z']})
  expect(support.backupShiftConditions).toEqual([true])
  expect(data.planConditions).toEqual([false])
  expect(data.operators.X!.currentRoom).toBe('room_1_2')
 })
 it('does not consume or rewrite support through overlapping backup coalescing',()=>{
  const {data,queue,support,retry}=generatedSupport(),before=structuredClone(support.plan),time=support.timeMicros
  const normal=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_2:['X']}})
  queue.tasks.push(normal)
  const result=coalesceMowerBackupTransition(data,{room_1_2:['B']},queue.tasks)
  expect(result.consumed).toEqual([normal])
  expect(support.plan).toEqual(before);expect(support.timeMicros).toBe(time)
  expect(queue.tasks).toContain(support);expect(queue.tasks).toContain(retry)
 })
 it('keeps support out of ordinary coalescing and preserves its flag in preview clones',()=>{
  const {data,queue,support,retry}=generatedSupport(),ordinary=new MowerTask({type:T.SELF_CORRECTION})
  queue.tasks.push(ordinary)
  const observed:MowerTask[]=[]
  const rest=ordinaryPlanning.mowerResting
  vi.spyOn(ordinaryPlanning,'mowerResting').mockImplementation((d,q,o)=>{observed.push(...q.tasks);return rest(d,q,o)})
  prepareMowerShiftCycle(data,ordinary,queue,model)
  expect(queue.tasks).toContain(support);expect(queue.tasks).toContain(retry)
  const copy=observed.find(task=>task.type===T.SELF_CORRECTION&&task.plan.room_1_2?.[0]==='Y')
  expect(copy).toBeDefined();expect(copy).not.toBe(support);expect(copy?.exhaustSupport).toBe(true)
  expect(copy?.plan).not.toBe(support.plan)
  expect(ordinary.exhaustSupport).toBe(false)
 })
 it('keeps ordinary corrections eligible for the full cycle',()=>{
  const {data,support}=generatedSupport(),ordinary=new MowerTask({type:T.SELF_CORRECTION,plan:structuredClone(support.plan)}),queue=new MowerTaskQueue()
  queue.tasks=[ordinary]
  prepareMowerShiftCycle(data,ordinary,queue,model)
  expect(ordinary.exhaustSupport).toBe(false)
  expect(ordinary.plan.dormitory_1).toContain('C')
 })
})


describe('urgent support backup dependencies',()=>{
 it.each([[false,false],[true,false],[false,true],[true,true]])('validates the final backup before recall (replacement removed=%s, ordinary=%s)',(blocked,ordinary)=>{
  const {state,source,data,support,retry}=generatedSupport(true),time=retry.timeMicros
  support.ordinaryCoordination=ordinary;retry.ordinaryCoordination=ordinary
  if(ordinary){data.operators.A!.exhaustRequire=false;state.config.mowerSourceRules!.exhaustRequire=[]}
  if(!ordinary)data.groupRecoveryFullMembers.resting=['B','D']
  data.planConditions=[false]
  const activations:boolean[][]=[]
  state.mowerShiftModel={...model,count:1,evaluate:d=>[d.operators.B!.currentRoom==='room_1_2'],swap:(d,conditions)=>{
   d.planConditions=[...conditions]
   if(blocked&&conditions[0])d.operators.A!.replacement=[]
   return d
  },activate:conditions=>{activations.push([...conditions]);source.data.planConditions=[...conditions]}}
  for(let n=0;n<30&&!support.executionFailure&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   if(!support.executionFailure)advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  if(blocked){
   expect(support.executionFailure).toBeDefined()
   const failure=support.executionFailure,supportTime=support.timeMicros
   for(let n=0;n<12;n++)settleMowerSource(state,rates)
   expect(source.queue.tasks.filter(t=>t.exhaustSupport)).toEqual([support])
   expect(source.queue.tasks).toContain(retry)
   expect(retry.timeMicros).toBe(time);expect(support.timeMicros).toBe(supportTime)
   expect(support.executionFailure).toBeDefined()
   expect(support.executionFailure).toBe(failure)
   expect(activations).toEqual([])
   expect(state.occupants.room_1_2_0).toBe('X')
   // A changed backup is relevant evidence; the retained handoff can now finish.
   state.mowerShiftModel.swap=(d,conditions)=>{d.planConditions=[...conditions];return d}
   Object.assign(source.data.operators.B!,{timeStampMicros:source.data.nowMicros+1})
   for(let n=0;n<40&&!Object.values(state.bedOccupants).includes('A');n++){
    settleMowerSource(state,rates)
    if(!Object.values(state.bedOccupants).includes('A'))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
   }
  }
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(activations).toContainEqual([true])
 })
})

function sharedManagerRecall({ explicitFull = false, managerFull = false, workingFollower = false, otherResting = false, alternate = false } = {}) {
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={
  room_1_1:[{agent:'A',group:'request',replacement:['X']}],
  room_1_2:[{agent:'B',group:'recovering',replacement:alternate?['X','Y']:['X']}],
  dormitory_1:[{agent:'M',group:'recovering',replacement:['L'],groupBindings:[
   {group:'recovering',replacement:['L','L2']},{group:'request',replacement:['L2']},
   ...(otherResting?[{group:'third',replacement:['L2']}]:[])
  ]},{agent:'K',group:'',replacement:[]},...[2,3,4].map(()=>({agent:'Free',group:'',replacement:[]}))]
 }
 if(workingFollower){rows.room_1_3=[rows.dormitory_1![0]!];rows.dormitory_1![0]={agent:'Fixed',group:'',replacement:[]}}
 const config:RuntimeConfig={mowerAlpha:true,mowerSourcePlan:rows,
  positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((slot,index)=>slot.agent==='Free'?[]:[{id:`${room}_${index}`,roomId:room,primary:slot.agent,candidates:slot.replacement,group:slot.group,permanent:room.startsWith('dorm'),dormitory:room.startsWith('dorm')}])),
  beds:[2,3,4].map(index=>({id:`dormitory_1_${index}`,roomId:'dormitory_1',vip:index===2})),
  initialMorale:{A:0,B:8,M:24,K:24,Fixed:24,X:24,Y:24,L:24,L2:24},idleOperators:['Y','L2'],
  mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},
  mowerSourceRules:{workaholic:[],exhaustRequire:['A'],restInFull:[...(explicitFull?['B']:[]),...(managerFull?['M']:[])],lowPriority:[],refreshDrained:[],lingMode:0},
  mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data
 source.initial=false;source.firstInit=false
 state.occupants={room_1_1_0:'A',room_1_2_0:'X',dormitory_1_0:workingFollower?'Fixed':otherResting?'L2':'L',dormitory_1_1:'K'}
 if(workingFollower)state.occupants.room_1_3_0=otherResting?'L2':'L'
 state.bedOccupants={dormitory_1_2:'B'}
 for(const op of Object.values(data.operators))Object.assign(op,{currentRoom:'',currentIndex:-1,mood:state.morale[op.name]??24,timeStampMicros:0})
 for(const [slot,name] of Object.entries({...state.occupants,...state.bedOccupants})){const index=slot.lastIndexOf('_');Object.assign(data.operators[name]!,{currentRoom:slot.slice(0,index),currentIndex:Number(slot.slice(index+1))})}
 data.dorms=[new MowerDormState(['dormitory_1',2],'B',toMowerMicros(4)),new MowerDormState(['dormitory_1',3]),new MowerDormState(['dormitory_1',4])]
 if(managerFull){state.morale.M=8;state.bedOccupants.dormitory_1_3='M';Object.assign(data.operators.M!,{currentRoom:'dormitory_1',currentIndex:3,mood:8});data.dorms[1]=new MowerDormState(['dormitory_1',3],'M',toMowerMicros(4))}
 data.groupShiftState={recovering:true,request:false,...(otherResting?{third:true}:{})}
 const exhausted=new MowerTask({type:T.EXHAUST_OFF,metadata:'A'})
 source.queue.tasks=[exhausted]
 return {state,source,data,exhausted}
}

describe('urgent recall with a shared dormitory manager',()=>{
 it.each([false,true])('releases a shared cover without requiring the shared manager to recall (other resting=%s)',otherResting=>{
  const {state,source,data,exhausted}=sharedManagerRecall({otherResting})
  settleMowerSource(state,rates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)
  expect(support).toBeDefined()
  expect(support?.plan.room_1_2).toEqual(['B'])
  expect(data.groupShiftState).toMatchObject({recovering:true,request:false})
  expect(source.queue.tasks).toContain(exhausted)
  expect(exhausted.timeMicros).toBe(0)
  for(let n=0;n<40&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   if(!Object.values(state.bedOccupants).includes('A'))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(state.occupants.room_1_1_0).toBe('X')
  expect(state.occupants.room_1_2_0).toBe('B')
  expect(state.occupants.dormitory_1_0).toBe('L2')
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(new Set(Object.values({...state.occupants,...state.bedOccupants})).size).toBe(Object.keys({...state.occupants,...state.bedOccupants}).length)
  expect(source.data.groupShiftState).toMatchObject({recovering:false,request:true})
 })
 it.each([false,true])('protects explicit full recovery only when the shared manager actually returns (other resting=%s)',otherResting=>{
  const {state,source}=sharedManagerRecall({otherResting,managerFull:true})
  settleMowerSource(state,rates)
  const support=source.queue.tasks.find(task=>task.exhaustSupport)
  if(otherResting){expect(support).toBeDefined();expect(support?.plan.dormitory_1?.[0]).not.toBe('M')}
  else expect(support).toBeUndefined()
  expect(Object.values(state.bedOccupants)).toContain('M')
 })
 it('tries an available later replacement before recalling its owner or shared manager',()=>{
  const {state,source}=sharedManagerRecall({alternate:true})
  settleMowerSource(state,rates)
  expect(source.queue.tasks.find(task=>task.exhaustSupport)?.plan).toEqual({room_1_2:['Y']})
  expect(Object.values(state.bedOccupants)).toContain('B')
 })
 it('retains the due request without redispatch until explicit full recovery is observed',()=>{
  const {state,source,data,exhausted}=sharedManagerRecall({explicitFull:true})
  settleMowerSource(state,rates)
  expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(false)
  const failure=exhausted.executionFailure
  const dispatches=source.trace.filter(item=>item.type==='EXHAUST_OFF'&&item.metadata==='A').length
  for(let n=0;n<10;n++)settleMowerSource(state,rates)
  expect(source.trace.filter(item=>item.type==='EXHAUST_OFF'&&item.metadata==='A')).toHaveLength(dispatches)
  expect(source.queue.tasks).toContain(exhausted)
  expect(exhausted.executionFailure).toBe(failure)
  expect(exhausted.timeMicros).toBe(0)
  state.morale.B=24
  Object.assign(data.operators.B!,{mood:24,timeStampMicros:data.nowMicros+1})
  data.dorms[0]!.timeMicros=data.nowMicros
  for(let n=0;n<40&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   if(!Object.values(state.bedOccupants).includes('A'))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.occupants.room_1_2_0).toBe('B')
 })

 it('finishes the urgent departure after recall changes the effective backup work stations',()=>{
  const {state,source,exhausted}=sharedManagerRecall()
  source.data.planConditions=[true]
  const activeRooms={A:'room_1_1',B:'room_1_2'},inactiveRooms={A:'room_1_2',B:'room_1_1'}
  const backup:MowerShiftModel={count:1,evaluate:data=>[data.operators.B!.isResting()],
   swap:(data,conditions)=>{
    const next=projectMowerArrangements(data,[]),rooms=conditions[0]?activeRooms:inactiveRooms
    next.planConditions=[...conditions]
    for(const name of ['A','B'] as const){next.operators[name]!.room=rooms[name];next.plan[rooms[name]]=[name]}
    return next
   },
   transition:(_before,_after,original,conditions):MowerTaskPlan=>original[0]===conditions[0]?{}:
    conditions[0]?{room_1_1:['A'],room_1_2:['X']}:{room_1_1:['B'],room_1_2:['A']},
   activate:conditions=>{source.data=backup.swap(source.data,conditions)}
  }
  state.mowerShiftModel=backup
  const deadline=exhausted.timeMicros
  for(let n=0;n<60&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   if(!Object.values(state.bedOccupants).includes('A'))advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(state.occupants.room_1_1_0).toBe('B')
  expect(state.occupants.room_1_2_0).toBe('X')
  expect(state.occupants.dormitory_1_0).toBe('L2')
  expect(source.data.planConditions).toEqual([false])
  expect(exhausted.timeMicros).toBe(deadline)
  expect(source.queue.tasks.filter(task=>task.executionFailure&&task.coordinationRequestNames.includes('A'))).toEqual([])
 })

 it.each([false,true])('retains explicit group full recovery for a shared work primary (other resting=%s)',otherResting=>{
  const {state,source,exhausted}=sharedManagerRecall({otherResting,managerFull:true,workingFollower:true})
  settleMowerSource(state,rates)
  expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(false)
  expect(source.queue.tasks).toContain(exhausted)
  expect(exhausted.timeMicros).toBe(0)
  expect(state.occupants.room_1_2_0).toBe('X')
  expect(Object.values(state.bedOccupants)).toEqual(expect.arrayContaining(['B','M']))
 })

})

describe('backup group requests in real dispatch',()=>{
 it('protects the occupied cover of a forced group even when an alternate could keep the group resting',()=>{
  const {state,source,retry}=generatedSupport(false,'forced')
  for(let n=0;n<8;n++)settleMowerSource(state,rates)
  expect(source.queue.tasks.some(task=>task.exhaustSupport)).toBe(false)
  expect(source.queue.tasks).toContain(retry)
  expect(state.occupants.room_1_2_0).toBe('X')
  expect(Object.values(state.bedOccupants)).toEqual(expect.arrayContaining(['B','D']))
 })
 it.each(['while_active','forced'] as const)('allows dependency recall only with coordinated hold (%s)',mode=>{
  const {state,source,support,retry}=generatedSupport(true,mode)
  const deadline=retry.timeMicros
  for(let n=0;n<50&&mode!=='forced'&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  if(mode==='while_active'){
   expect(Object.values(state.bedOccupants)).toContain('A')
   expect(state.occupants.room_1_2_0).toBe('B')
   const admission=state.time
   for(let n=0;n<400&&!source.data.operators.B!.isResting();n++){
    settleMowerSource(state,rates)
    advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
   }
   expect(source.data.operators.B!.isResting()).toBe(true)
   expect(source.data.groupIsResting('resting')).toBe(true)
   expect(state.time-admission).toBeGreaterThan(1)
  }else{
   expect(retry.executionFailure).toBeDefined()
   const failure=retry.executionFailure,time=retry.timeMicros
   for(let n=0;n<8;n++)settleMowerSource(state,rates)
   expect(retry.executionFailure).toBe(failure);expect(retry.timeMicros).toBe(time)
   expect(source.queue.tasks).toContain(retry);expect(retry.timeMicros).toBe(deadline)
   expect(state.occupants.room_1_2_0).toBe('X')
   const unrelated=new MowerTask({time:state.time,type:T.NOT_SPECIFIC})
   source.queue.tasks.push(unrelated)
   for(let n=0;n<30&&source.queue.tasks.includes(unrelated);n++){
    settleMowerSource(state,rates)
    advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
   }
   expect(source.queue.tasks).not.toContain(unrelated)
   source.data.planConditions=[false]
   for(let n=0;n<60&&!Object.values(state.bedOccupants).includes('A');n++){
    settleMowerSource(state,rates)
    advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
   }
   expect(Object.values(state.bedOccupants)).toContain('A')
  }
 })
 it('creates a group departure request and preserves its owner through cover handoff',()=>{
  const {state,source}=generatedSupport(false,undefined,true)
  const request=source.queue.tasks.find(t=>t.type===T.EXHAUST_OFF&&t.backupGroupRequest)!
  expect(request).toBeDefined()
  const support=source.queue.tasks.find(t=>t.exhaustSupport)!
  expect(support).toBeDefined();expect(support.backupGroupRequest).toEqual(request.backupGroupRequest)
  for(let n=0;n<50&&!Object.values(state.bedOccupants).includes('A');n++){
   settleMowerSource(state,rates)
   advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(Object.values(state.bedOccupants)).toContain('A')
  expect(source.data.groupIsResting('requested')).toBe(true)
 })
})
