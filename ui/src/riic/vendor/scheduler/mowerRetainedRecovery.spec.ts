import {admitMowerDerivedTasks} from './mowerTaskDerivation'
import {describe,it,expect} from 'vitest'
import {createRosterRuntime,settleRoster,advanceRoster,nextRosterActionHours,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {MowerDormState} from './mowerSchedulingData'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerMetadata} from './mowerMetadata'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import {mowerUpdateDetail} from './mowerObservations'
function fixture(){
 const rows:NonNullable<RuntimeConfig['mowerSourcePlan']>={room_1_1:[{agent:'A',group:'a',replacement:['X']}],room_1_2:[{agent:'B',group:'b',replacement:['Y']},{agent:'S',group:'b',replacement:['Z']}],dormitory_1:['K0','K1','Free','Free','Free'].map(agent=>({agent,group:'',replacement:[]}))}
 const config:RuntimeConfig={mowerAlpha:true,positions:Object.entries(rows).flatMap(([room,row])=>row.flatMap((p,index)=>p.agent==='Free'?[]:[{id:room+'_'+index,roomId:room,primary:p.agent,candidates:p.replacement,group:p.group,dormitory:room.startsWith('dorm'),permanent:room.startsWith('dorm')}])),beds:[2,3,4].map(index=>({id:'dormitory_1_'+index,roomId:'dormitory_1',vip:index===2})),mowerSourcePlan:rows,mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],standby:['S'],lingMode:0},mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},initialMorale:{A:0,B:24,S:24},idleOperators:['I0','I1','I2'],mowerRunLoopClock:{minimumClockStepMicros:1,notificationSleepMicros:1_000_000}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state),data=source.data,queue=source.queue
 source.initial=false
 for(const p of config.positions){const op=data.operators[p.primary]!;Object.assign(op,{currentRoom:p.roomId,currentIndex:Number(p.id.slice(p.id.lastIndexOf('_')+1)),mood:state.morale[op.name]??24,timeStampMicros:0})}
 for(const [name,index,cover] of [['B',2,'Y'],['S',3,'Z']] as const){
  const op=data.operators[name]!,worker=data.operators[cover]!
  state.occupants['room_1_2_'+op.index]=cover;state.bedOccupants['dormitory_1_'+index]=name
  Object.assign(worker,{currentRoom:'room_1_2',currentIndex:op.index,mood:24,timeStampMicros:0})
  Object.assign(op,{currentRoom:'dormitory_1',currentIndex:index,mood:24,timeStampMicros:0})
 }
 data.dorms=[new MowerDormState(['dormitory_1',2],'B',0),new MowerDormState(['dormitory_1',3],'S',0),new MowerDormState(['dormitory_1',4])];data.groupShiftState={a:false,b:true}
 for(const op of Object.values(data.operators))if(op.timeStampMicros===undefined)op.timeStampMicros=0
 const task=new MowerTask({type:T.SHIFT_OFF,time:-1,plan:{room_1_1:['X'],dormitory_1:['Current','Current','A','Current','S']}})
 queue.tasks=[task];retainMowerFailedTask(state,data,task,'blocked incidental bed reordering')
 return {state,source,data,queue,task}
}
const returned=(tasks:MowerTask[])=>tasks.find(t=>t.type===T.SHIFT_ON&&t.plan.room_1_2?.includes('B'))
describe('failed incidental dorm moves release normal recovered-group returns',()=>{
 it('admits the complete normal return without replaying or changing the retained main request',()=>{
  const {data,queue,task,state}=fixture(),before=structuredClone(task.plan)
  planMowerMetadata(data,queue)
  expect(returned(queue.tasks)?.plan.room_1_2).toEqual(['B','S'])
  expect(task.plan).toEqual(before);expect(task.timeMicros).toBe(toMowerMicros(-1));expect(task.executionFailure).toBeDefined()
  for(let i=0;i<3;i++){planMowerMetadata(data,queue);expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)}
  expect(returned(queue.tasks)?.plan.room_1_2).toEqual(['B','S'])
 })
 it('keeps the normal recovery deadline when admitting a future return that will release a dependency',()=>{
  const {data,queue,task}=fixture()
  data.operators.B!.mood=8;data.dorms[0]!.timeMicros=toMowerMicros(4)
  planMowerMetadata(data,queue)
  const normal=returned(queue.tasks)!
  expect(normal?.plan.room_1_2).toEqual(['B','S'])
  expect(normal.timeMicros).toBeGreaterThan(data.nowMicros)
  expect(normal.timeMicros).toBeLessThanOrEqual(toMowerMicros(4))
  expect(task.executionFailure).toBeDefined()
 })
 it('uses the original request rather than failed backup additions and removes stale added dorm moves only after observation',()=>{
  const {data,state,queue,task}=fixture()
  task.backupShiftIntent=structuredClone(task.plan)
  task.plan.dormitory_1![4]='B';task.plan.room_1_2=['B','S']
  retainMowerFailedTask(state,data,task,'failed speculative backup')
  const intent=structuredClone(task.backupShiftIntent),time=task.timeMicros
  planMowerMetadata(data,queue)
  expect(returned(queue.tasks)?.plan.room_1_2).toEqual(['B','S'])
  expect(task.plan.dormitory_1![4]).toBe('B')
  mowerUpdateDetail(data,'B',24,'room_1_2',0,true);mowerUpdateDetail(data,'S',24,'room_1_2',1,true)
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(task.plan.dormitory_1![4]).toBe('Current')
  expect(task.backupShiftIntent?.room_1_1).toEqual(intent.room_1_1)
  expect(task.backupShiftIntent?.dormitory_1![2]).toBe('A')
  expect(task.timeMicros).toBe(time);expect(queue.tasks).toContain(task)
 })
 it.each(['primary-intent','explicit-slot','active-arrangement','product-lock'])('keeps %s protected',kind=>{
  const {data,queue,task}=fixture()
  if(kind==='primary-intent')task.plan.room_1_2=['Y','Current']
  if(kind==='explicit-slot')task.backupExplicitSlots.add('dormitory_1\0'+4)
  if(kind==='active-arrangement')task.backupShiftActive=true
  if(kind==='product-lock'){task.productShiftLocked=true;task.productLockNames.add('S')}
  planMowerMetadata(data,queue)
  expect(returned(queue.tasks)).toBeUndefined()
 })
 it('prunes only incidental dorm moves after an observed actual return, retaining original work and time',()=>{
  const {state,data,queue,task}=fixture()
  mowerUpdateDetail(data,'B',24,'room_1_2',0,true);mowerUpdateDetail(data,'S',24,'room_1_2',1,true)
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(queue.tasks).toContain(task);expect(task.timeMicros).toBe(toMowerMicros(-1))
  expect(task.plan).toEqual({room_1_1:['X'],dormitory_1:['Current','Current','A','Current','Current']})
  expect(task.executionFailure).toBeUndefined()
 })
 it('removes a blocked group’s Free clear step for a shared follower whose current group differs',()=>{
  const {state,data,task}=fixture(),follower=data.operators.S!
  follower.group='c';follower.groupBindings=[{group:'b',replacement:['Z']},{group:'c',replacement:['Z']}]
  const held=new MowerTask({type:T.SHIFT_ON,plan:{room_1_2:['B','Current']}})
  retainMowerFailedTask(state,data,held,'real pending return')
  const candidate=new MowerTask({type:T.SHIFT_ON,plan:{room_1_2:['B','S'],dormitory_1:['Current','Current','Current','Free','Current']}})
  expect(admitMowerDerivedTasks(data,[task,held],[candidate])).toEqual([])
 })
 it('clears an incidental standby entry already working before the anchor’s observed return',()=>{
  const {state,data,queue,task}=fixture()
  mowerUpdateDetail(data,'S',24,'room_1_2',1,true)
  retainMowerFailedTask(state,data,task,'standby incidental bed move')
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(false)
  expect(task.plan.dormitory_1![4]).toBe('S')
  mowerUpdateDetail(data,'B',24,'room_1_2',0,true)
  expect(resumeMowerFailedTasks(state,data,queue)).toBe(true)
  expect(task.plan.dormitory_1![4]).toBe('Current')
  expect(task.plan.room_1_1).toEqual(['X']);expect(task.timeMicros).toBe(toMowerMicros(-1))
 })
 it('executes the full return, releases its cover and completes the original rest without sending the standby back',()=>{
  const {state,data,queue,task}=fixture(),rates={workRate:()=>1,recoveryRate:()=>4}
  planMowerMetadata(data,queue)
  const finished=()=>state.occupants.room_1_2_0==='B'&&state.occupants.room_1_2_1==='S'&&Object.values(state.bedOccupants).includes('A')
  for(let i=0;i<35&&!finished();i++){
   settleRoster(state,rates)
   if(!finished())advanceRoster(state,Math.max(nextRosterActionHours(state,rates),1/3_600_000_000),rates)
  }
  expect(state.time).toBeLessThan(1/60)
  expect(state.occupants.room_1_2_0).toBe('B');expect(state.occupants.room_1_2_1).toBe('S')
  expect(Object.values(state.bedOccupants)).toContain('A');expect(Object.values(state.bedOccupants)).not.toContain('S')
  expect(task.timeMicros).toBe(toMowerMicros(-1))
  expect(state.events.some(event=>event.type==='shift-on'&&event.operators.includes('B'))).toBe(true)
 })
})
