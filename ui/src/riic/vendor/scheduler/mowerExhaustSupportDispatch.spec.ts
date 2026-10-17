import {afterEach,describe,expect,it,vi} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,type RuntimeConfig,type RuntimeState} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {MowerDormState} from './mowerSchedulingData'
import {coalesceMowerBackupTransition,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import * as ordinaryPlanning from './mowerOrdinaryPlanning'

const model:MowerShiftModel={count:0,evaluate:data=>data.planConditions,swap:data=>data,transition:()=>({}),activate:()=>{}}
const rates={workRate:()=>1,recoveryRate:()=>4,forecastRates:(state:RuntimeState)=>({work:Object.fromEntries(Object.keys(state.morale).map(name=>[name,1])),recovery:Object.fromEntries(Object.keys(state.morale).map(name=>[name,4]))})}
function generatedSupport(recall=false){
 const rows={room_1_1:[{agent:'A',group:'',replacement:['X']}],room_1_2:[{agent:'B',group:'resting',replacement:recall?['X']:['X','Y']}],room_1_3:[{agent:'C',group:'',replacement:['Z']}],contact:[{agent:'D',group:'resting',replacement:['W']}],dormitory_1:[...['K1','K2'].map(agent=>({agent,group:'',replacement:[]})),...['Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))]}
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
 const exhausted=new MowerTask({type:T.EXHAUST_OFF,metadata:'A'})
 source.queue.tasks=[exhausted]
 settleMowerSource(state,rates)
 expect(source.queue.tasks).toContain(exhausted)
 expect(exhausted.executionFailure).toBeDefined();expect(exhausted.timeMicros).toBe(0)
 const support=source.queue.tasks.find(task=>task.type===T.SELF_CORRECTION)!,retry=source.queue.tasks.find(task=>task.type===T.EXHAUST_OFF)!
 expect(support).toBeDefined();expect(retry).toBe(exhausted)
 expect(support.plan).toEqual(recall?{room_1_2:['B'],contact:['D']}:{room_1_2:['Y']})
 return {state,source,data:source.data,queue:source.queue,support,retry}
}

afterEach(()=>vi.restoreAllMocks())
describe('exhaust support dispatch preserves native recovery capacity',()=>{
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
 it.each([false,true])('validates the final backup before recall (replacement removed=%s)',blocked=>{
  const {state,source,data,support,retry}=generatedSupport(true),time=retry.timeMicros
  data.groupRecoveryFullMembers.resting=['B','D']
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
