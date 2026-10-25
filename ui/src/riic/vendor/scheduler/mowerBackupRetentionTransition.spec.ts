import {describe,expect,it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime,settleRoster} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {projectMowerArrangements} from './mowerObservations'
import {prepareMowerShiftCycle,cloneMowerShiftTask} from './mowerShiftCycle'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {alphaPosition} from './mowerAlphaDorm'
import {MowerOperatorState} from './mowerOperatorState'
import {retainMowerFailedTask,resumeMowerFailedTasks} from './mowerTaskFailure'
import {mowerBackupRetentionTaskPlan} from './mowerBackupRetention'
import {prepareMowerDormSelection} from './mowerSelection'

const dorm='dormitory_1',actor=id('夕')
function fixture(conf:Record<string,unknown>={},replacement=false,explicitWork=false,overlap=false){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities))room.slots=[]
 const slot=(name:string,cover='')=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:null,replacements:cover?[id(cover)]:[]})
 workspace.mainPlan.facilities.central.slots=[slot('芬',replacement?'夕':'克洛丝')]
 workspace.mainPlan.facilities[dorm].slots=[slot('杜林'),slot('闪灵'),...Array.from({length:3},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))]
 workspace.compatibility.backupPlans=[{trigger:"op_data.inventory_count('赤金') >= 10",conf:{free_room_exclusions:[actor],...conf},...(explicitWork?{task:{central:[actor]}}:{})}]
 if(overlap)workspace.compatibility.backupPlans.push({trigger:"op_data.inventory_count('赤金') >= 1",conf:{free_room_exclusions:[actor]}})
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true;config.mowerTaskScheduling={...config.mowerTaskScheduling,adjustForRunOrders:false}
 const state=createRosterRuntime(config);state.mowerInventoryCounts={赤金:0}
 const controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 source.queue.tasks=[];source.initial=false;source.firstInit=false
 for(const op of Object.values(source.data.operators)){op.currentRoom=op.room;op.currentIndex=op.index;op.mood=24;op.timeStampMicros=0}
 return {state,source,controller,schedule}
}
function enter(f:ReturnType<typeof fixture>){f.state.mowerInventoryCounts={赤金:10};f.controller.evaluate('END')}
function resident(f:ReturnType<typeof fixture>,mood=5){
 enter(f);f.source.queue.tasks=[];delete f.state.mowerBackupGenerated
 const op=f.source.data.operators[actor]!
 Object.assign(op,{currentRoom:dorm,currentIndex:2,mood,timeStampMicros:0,dormRecoveryRoom:dorm,dormRecoveryIndex:2})
 f.source.data.dorms[0]!.name=actor;f.state.bedOccupants[dorm+'_2']=actor;f.state.morale[actor]=mood
 return op
}
const planned=(f:ReturnType<typeof fixture>)=>projectMowerArrangements(f.source.data,(f.state.mowerBackupGenerated??[]).map(task=>task.plan))

describe('backup dorm retention transitions',()=>{
 it('registers retention-only actors without fabricating an observation and admits them at full mood',()=>{
  const f=fixture();expect(f.source.data.operators[actor]).toBeUndefined();enter(f)
  expect(f.controller.active).toEqual([true]);expect(planned(f).operators[actor]!.currentRoom).toBe(dorm)
  expect(f.source.data.operators[actor]!.currentRoom).toBe('');expect(f.source.data.operators[actor]!.timeStampMicros).toBeUndefined()
  expect(f.state.mowerBackupGenerated![0]!.backupRetentionAdmissions).toEqual([actor])
 })
 it.each(['shift','product'] as const)('admits a capped idle actor in the complete %s preview',path=>{
  const f=fixture(),task=new MowerTask({type:T.SHIFT_OFF});task.productShiftLocked=path==='product'
  f.source.queue.tasks=[task];f.state.mowerInventoryCounts={赤金:10}
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  const next=f.state.mowerShiftModel!.swap(f.source.data,task.backupShiftConditions!,task.backupGroup)
  expect(projectMowerArrangements(next,[task.plan]).operators[actor]!.currentRoom).toBe(dorm)
  expect(task.backupRetentionAdmissions).toContain(actor);expect(f.controller.active).toEqual([false])
 })
 it.each(['free_blacklist','workaholic'])('uses the final effective retention policy with %s',key=>{
  const f=fixture({[key]:[actor]});enter(f)
  expect(f.controller.active).toEqual([true]);expect(f.source.data.freeRoomExcluded(actor)).toBe(false)
  expect(f.state.diagnostics.some(d=>d.code==='mower-backup-deferred')).toBe(false)
 })
 it('clears a former retained low-mood resident with an explicit empty slot',()=>{
  const f=fixture();resident(f);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const task=f.state.mowerBackupGenerated![0]!
  expect(task.plan[dorm]![2]).toBe('');expect(task.backupRetentionReleasedNames).toContain(actor)
  expect(planned(f).operators[actor]!.currentRoom).toBe('')
  const cloned=cloneMowerShiftTask(task);cloned.backupRetentionReleasedNames.push('other');expect(task.backupRetentionReleasedNames).toEqual([actor])
 })
 it('preserves a queued low-mood exit through the complete final execution preview',()=>{
  const f=fixture();resident(f);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const task=f.state.mowerBackupGenerated![0]!
  f.source.queue.tasks=[task]
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(task.backupRetentionReleasedNames).toContain(actor)
  expect(Object.values(task.plan).flat()).not.toContain(actor)
  expect(projectMowerArrangements(f.source.data,[task.plan]).operators[actor]!.currentRoom).toBe('')
 })
 it.each([5,24])('preserves a new resident occupying the former exit bed at mood %s through prepare and actual execution',mood=>{
  const f=fixture();const old=resident(f);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const task=f.state.mowerBackupGenerated![0]!,name=id('香草')
  expect(task.backupRetentionEmptySlots[alphaPosition(dorm,2)]).toBe(actor)
  old.currentRoom='';old.currentIndex=-1
  f.source.data.operators[name]=new MowerOperatorState({name,mood,timeStampMicros:0,currentRoom:dorm,currentIndex:2})
  f.source.data.dorms[0]!.name=name;f.state.bedOccupants[dorm+'_2']=name;f.state.morale[name]=mood
  f.source.queue.tasks=[task]
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(projectMowerArrangements(f.source.data,[task.plan]).operators[name]!.currentRoom).toBe(dorm)
  const actual=new MowerTask({type:T.RE_ORDER,plan:{[dorm]:['Current','Current','','Current','Current']}})
  actual.backupRetentionReleasedNames=[actor];actual.backupRetentionEmptySlots={[alphaPosition(dorm,2)]:actor};actual.backupShiftActive=true
  f.source.queue.tasks=[actual]
  settleRoster(f.state,{workRate:()=>1,recoveryRate:()=>4})
  expect(f.state.bedOccupants[dorm+'_2']).toBe(name);expect(f.source.data.operators[actor]!.currentRoom).toBe('')
 })
 it('cancels an old empty departure when the same actor becomes retained again',()=>{
  const f=fixture();resident(f);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const old=f.state.mowerBackupGenerated![0]!,actual=cloneMowerShiftTask(old)
  f.source.queue.tasks=[old];f.state.mowerInventoryCounts={赤金:10};f.controller.evaluate('END')
  expect(f.controller.active).toEqual([true]);expect(old.plan[dorm]).toBeUndefined()
  expect(f.source.queue.tasks).not.toContain(old)
  actual.backupShiftActive=true;f.source.queue.tasks=[actual]
  settleRoster(f.state,{workRate:()=>1,recoveryRate:()=>4})
  expect(f.state.bedOccupants[dorm+'_2']).toBe(actor)
 })
 it.each([5,24])('preserves the original resident when a later primary job supersedes an old exit at mood %s',mood=>{
  const f=fixture();resident(f,mood);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const task=f.state.mowerBackupGenerated![0]!,op=f.source.data.operators[actor]!
  op.room='central';op.index=0
  expect(mowerBackupRetentionTaskPlan(f.source.data,task)[dorm]).toBeUndefined()
  const names=[...task.plan[dorm]!];prepareMowerDormSelection(f.source.data,names,dorm,false,false,task);expect(names[2]).toBe(actor)
  task.backupShiftActive=true;f.source.queue.tasks=[task]
  settleRoster(f.state,{workRate:()=>1,recoveryRate:()=>4})
  expect(f.state.bedOccupants[dorm+'_2']).toBe(actor);expect(op.currentRoom).toBe(dorm)
 })
 it('keeps the exit idle during actual selection of another Free bed',()=>{
  const f=fixture();resident(f);f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  const task=f.state.mowerBackupGenerated![0]!,other=id('香草')
  task.plan[dorm]![3]='Free';task.backupShiftActive=true
  f.state.config.availableIdleOperators=[other];f.state.morale[other]=10;f.source.queue.tasks=[task]
  settleRoster(f.state,{workRate:()=>1,recoveryRate:()=>4})
  expect(f.source.data.operators[actor]!.currentRoom).toBe('');expect(Object.values(f.state.bedOccupants)).not.toContain(actor)
  expect(Object.values(f.state.bedOccupants)).not.toContain('');expect(f.state.bedOccupants[dorm+'_3']).toBe(other)
 })
 it('cancels only an unstarted policy admission, retaining other operations and its original time',()=>{
  const f=fixture();enter(f);const pending=f.state.mowerBackupGenerated![0]!
  pending.plan.central=[id('芬')];pending.backupShiftIntent=structuredClone(pending.plan);pending.dormFillPlan=structuredClone(pending.plan);pending.timeMicros=toMowerMicros(2)
  f.source.queue.tasks=[pending];f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false]);expect(f.source.queue.tasks).toContain(pending)
  expect(pending.plan.central).toEqual([id('芬')]);expect(Object.values(pending.plan).flat()).not.toContain(actor)
  expect(pending.timeMicros).toBe(toMowerMicros(2));expect(f.source.data.operators[actor]!.currentRoom).toBe('')
  expect(Object.values(pending.backupShiftIntent!).flat()).not.toContain(actor);expect(Object.values(pending.dormFillPlan).flat()).not.toContain(actor)
  prepareMowerShiftCycle(f.source.data,pending,f.source.queue,f.state.mowerShiftModel!)
  expect(Object.values(pending.plan).flat()).not.toContain(actor);expect(pending.timeMicros).toBe(toMowerMicros(2))
 })
 it('removes a stale policy admission from the final execution preview',()=>{
  const f=fixture();enter(f);const task=f.state.mowerBackupGenerated![0]!
  f.source.queue.tasks=[task];f.state.mowerInventoryCounts={赤金:0}
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(task.backupShiftConditions).toEqual([false]);expect(Object.values(task.plan).flat()).not.toContain(actor)
  const next=f.state.mowerShiftModel!.swap(f.source.data,[false])
  expect(projectMowerArrangements(next,[task.plan]).operators[actor]!.currentRoom).toBe('')
 })
 it.each(['occupied','slot','name','product'] as const)('rejects a required admission atomically when blocked by %s',kind=>{
  const f=fixture(),time=toMowerMicros(3),original=new MowerTask({type:T.SHIFT_OFF,time:3,plan:{central:[id('芬')]}})
  f.source.queue.tasks=[original]
  for(const bed of f.source.data.dorms){
   const [room,index]=bed.position
   if(kind==='occupied'){
    const name=id(['香草','空爆','安德切尔'][index-2]!)
    f.source.data.operators[name]=new MowerOperatorState({name,mood:1,currentRoom:room,currentIndex:index,timeStampMicros:0});bed.name=name
   }else if(kind==='product')f.source.data.reservedProductBeds.set(alphaPosition(room,index),id('香草'))
   else f.source.queue.tasks.push(new MowerTask({type:T.RE_ORDER,time:1,plan:{[room]:['Current','Current',...Array.from({length:3},()=>kind==='slot'?'Free':actor)]}}))
  }
  const before=f.source.data.dorms.map(b=>[b.name,b.timeMicros]);enter(f)
  expect(f.controller.active).toEqual([false]);expect(f.source.queue.tasks).toContain(original);expect(original.timeMicros).toBe(time)
  expect(original.plan).toEqual({central:[id('芬')]});expect(f.source.data.dorms.map(b=>[b.name,b.timeMicros])).toEqual(before)
  const count=f.state.diagnostics.length
  for(let i=0;i<3;i++)f.controller.evaluate('END')
  expect(f.state.diagnostics.length).toBe(count)
  if(kind==='occupied'){
   const bed=f.source.data.dorms[0]!,op=f.source.data.operators[bed.name]!
   op.currentRoom='';op.currentIndex=-1;bed.reset();f.controller.evaluate('END')
   expect(f.controller.active).toEqual([true]);expect(original.timeMicros).toBe(time)
  }
 })
 it('keeps a bed failure suspended through clock changes and unchanged observations while independent work dispatches',()=>{
  const f=fixture(),task=new MowerTask({type:T.SHIFT_OFF,time:2,plan:{central:[id('芬')]}}),independent=new MowerTask({type:T.CLUE,time:3})
  f.source.queue.tasks=[task,independent];task.backupRetentionWait={names:[actor]}
  retainMowerFailedTask(f.state,f.source.data,task,'副表宿舍保留安排尚无可用床位，保留原任务',[dorm])
  const old=structuredClone(task.plan),time=task.timeMicros
  f.state.time=4;f.source.data.nowMicros=toMowerMicros(4)
  for(const op of Object.values(f.source.data.operators))op.timeStampMicros=toMowerMicros(4)
  expect(resumeMowerFailedTasks(f.state,f.source.data,f.source.queue)).toBe(false)
  expect(f.source.queue.find()).toBe(independent);expect(task.plan).toEqual(old);expect(task.timeMicros).toBe(time)
  f.state.mowerInventoryCounts={赤金:10}
  expect(resumeMowerFailedTasks(f.state,f.source.data,f.source.queue)).toBe(true);expect(task.timeMicros).toBe(time)
 })
 it.each(['arrangementStarted','backupShiftActive','executionRetained'] as const)('preserves a %s task when controller policy changes',field=>{
  const f=fixture();enter(f);const task=f.state.mowerBackupGenerated![0]!
  task.plan.central=[id('芬')];task.timeMicros=toMowerMicros(2);task[field]=true
  f.source.queue.tasks=[task];const plan=structuredClone(task.plan)
  f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(toMowerMicros(2))
 })
 it('revalidates only an expired policy admission after a failed mixed task resumes on a policy change',()=>{
  const f=fixture();enter(f);const task=f.state.mowerBackupGenerated![0]!
  task.plan.central=[id('克洛丝')];task.backupExplicitSlots.add(alphaPosition('central',0));task.timeMicros=toMowerMicros(2)
  f.source.queue.tasks=[task];retainMowerFailedTask(f.state,f.source.data,task,'实际选人失败')
  const plan=structuredClone(task.plan)
  f.state.mowerInventoryCounts={赤金:0};f.controller.evaluate('END')
  expect(task.plan).toEqual(plan);expect(task.executionFailure).toBeDefined()
  expect(resumeMowerFailedTasks(f.state,f.source.data,f.source.queue)).toBe(true)
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(Object.values(task.plan).flat()).not.toContain(actor);expect(task.plan.central).toEqual([id('克洛丝')]);expect(task.timeMicros).toBe(toMowerMicros(2))
 })
 it('admits an idle ordinary replacement retained by the final policy',()=>{
  const f=fixture({},true);enter(f)
  expect(planned(f).operators[actor]!.currentRoom).toBe(dorm)
 })
 it('keeps a retained actor with a primary job at the primary job',()=>{
  const f=fixture({free_room_exclusions:[id('芬')]});enter(f)
  expect(planned(f).operators[id('芬')]!.currentRoom).toBe('central')
 })
 it('keeps a current-batch explicit working arrangement',()=>{
  const f=fixture({},false,true);enter(f)
  expect(planned(f).operators[actor]!.currentRoom).toBe('central')
 })
 it('does not release an actor still retained by another active backup',()=>{
  const f=fixture({},false,false,true);resident(f)
  f.state.mowerInventoryCounts={赤金:1};f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false,true]);expect(planned(f).operators[actor]!.currentRoom).toBe(dorm)
  expect((f.state.mowerBackupGenerated??[]).some(task=>task.backupRetentionReleasedNames.includes(actor))).toBe(false)
 })
 it('does not pull an actually working no-primary actor into retention',()=>{
  const f=fixture();f.source.data.operators[actor]=new MowerOperatorState({name:actor,mood:5,timeStampMicros:0,currentRoom:'meeting',currentIndex:0})
  enter(f);expect(planned(f).operators[actor]!.currentRoom).toBe('meeting')
 })
 it('does not displace an existing recovering resident',()=>{
  const f=fixture(),name=id('香草'),bed=f.source.data.dorms[0]!
  f.source.data.operators[name]=new MowerOperatorState({name,mood:3,currentRoom:dorm,currentIndex:2,timeStampMicros:0});bed.name=name
  enter(f);const final=planned(f)
  expect(final.operators[name]!.currentIndex).toBe(2);expect(final.operators[actor]!.currentIndex).not.toBe(2)
 })
})
