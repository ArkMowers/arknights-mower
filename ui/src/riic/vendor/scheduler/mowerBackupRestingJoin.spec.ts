import {describe,expect,it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {prepareMowerShiftBackup,prepareMowerShiftCycle} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'

function fixture(inDorm=false,configure?:(workspace:ReturnType<typeof createDefaultWorkspace>)=>void,training=false){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities))room.slots=[]
 const slot=(name:string,group:string,cover:string)=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:group,replacements:[id(cover)]})
 workspace.mainPlan.facilities.room_1_1.slots=[slot('芬','g','克洛丝')]
 workspace.mainPlan.facilities.room_1_2.slots=[slot('香草','g','空爆')]
 workspace.mainPlan.facilities.recycle.level=1
 workspace.mainPlan.facilities.recycle.slots=[slot('旅骨','g','星源')]
 workspace.mainPlan.facilities.dormitory_1.slots=[slot('杜林','',''),...Array.from({length:4},()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]}))]
 workspace.mainPlan.facilities.dormitory_1.slots[0]!.replacements=[]
 workspace.compatibility.backupPlans=[{trigger:"op_data.operators['芬'].is_working()",plan:{recycle:{plans:[{agent:'星源',group:'',replacement:['旅骨']}]}}}]
 if(training){
  workspace.mainPlan.facilities.recycle.slots=[]
  workspace.mainPlan.facilities.train.slots=[slot('望','','梅尔'),slot('旅骨','g','星源')]
  workspace.compatibility.backupPlans=[{trigger:"op_data.operators['芬'].is_working()",plan:{train:{plans:[{agent:'Current',group:'',replacement:[]},{agent:'星源',group:'',replacement:['旅骨']}]}}}]
 }
 configure?.(workspace)
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state)
 const initial=getMowerSourceRuntime(state)
 for(const position of config.positions){const op=initial.data.operators[position.primary]!;op.currentRoom=position.roomId;op.currentIndex=Number(position.id.slice(position.id.lastIndexOf('_')+1));op.timeStampMicros=0}
 controller.evaluate('END')
 expect(controller.active).toEqual(workspace.compatibility.backupPlans!.map((_,i)=>i===0))
 const source=getMowerSourceRuntime(state)
 source.queue.tasks=[];delete state.mowerBackupGenerated
 for(const op of Object.values(source.data.operators)){op.currentRoom='';op.currentIndex=-1;op.mood=22;op.timeStampMicros=0}
 for(const [name,room,index] of [['克洛丝','room_1_1',0],['空爆','room_1_2',0],['星源','recycle',0],['杜林','dormitory_1',0],['芬','dormitory_1',1],['香草','dormitory_1',2]] as const){const op=source.data.operators[id(name)]!;op.currentRoom=room;op.currentIndex=index}
  if(training){const cover=source.data.operators[id('星源')]!;cover.currentRoom='train';cover.currentIndex=1}
 for(const [name,index] of [['芬',1],['香草',2]] as const){const bed=source.data.dorms.find(b=>b.position[0]==='dormitory_1'&&b.position[1]===index)!;bed.name=id(name);bed.timeMicros=toMowerMicros(4)}
 const joining=source.data.operators[id('旅骨')]!;joining.mood=12
 if(inDorm){joining.currentRoom='dormitory_1';joining.currentIndex=3;const bed=source.data.dorms.find(b=>b.position[1]===3)!;bed.name=joining.name;bed.timeMicros=toMowerMicros(5)}
 source.data.groupShiftState.g=true
 return {workspace,state,controller,source,joining}
}
const staffing=(f:ReturnType<typeof fixture>):{plan:MowerTaskPlan}=>f.state.mowerBackupGenerated!.find(task=>Object.keys(task.plan).length)??{plan:{}}

describe('restored primary joins its resting group',()=>{
 it.each([false,true])('keeps replacements and admits the restored member, already resting=%s',inDorm=>{
  const f=fixture(inDorm),before=f.source.data.dorms.map(b=>[b.name,b.timeMicros])
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false])
  const task=staffing(f),projected=projectMowerArrangements(f.source.data,[task.plan])
  expect(Object.entries(task.plan).filter(([room])=>!room.startsWith('dorm')).flatMap(([,row])=>row)).not.toContain(id('旅骨'))
  expect(projected.groupIsResting('g')).toBe(true)
  for(const name of ['芬','香草','旅骨'])expect(projected.operators[id(name)]!.isResting()).toBe(true)
  expect(projected.currentOperator('recycle',0)?.name).toBe(id('星源'))
  expect(f.source.data.dorms.map(b=>[b.name,b.timeMicros])).toEqual(before)
 })
 it('lets an already full restored member wait without consuming a bed',()=>{
  const f=fixture();f.joining.mood=24
  f.controller.evaluate('END')
  const projected=projectMowerArrangements(f.source.data,[staffing(f).plan])
  expect(projected.operators[id('旅骨')]!.currentRoom).toBe('')
  expect(projected.getDormByName(id('旅骨'))).toBeUndefined()
  expect(projected.groupIsResting('g')).toBe(true)
 })

 it('admits an unknown-mood restored member instead of assuming full recovery',()=>{
  const f=fixture();f.joining.mood=24;f.joining.timeStampMicros=undefined
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false])
  expect(projectMowerArrangements(f.source.data,[staffing(f).plan]).operators[id('旅骨')]!.isResting()).toBe(true)
 })
 it('lets an explicit entry task return the restored primary',()=>{
  const f=fixture(false,w=>w.compatibility.backupPlans!.push({trigger:"op_data.operators['芬'].is_resting()",plan:{},task:{recycle:['旅骨']}}))
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false,true])
  expect(staffing(f).plan.recycle).toEqual([id('旅骨')])
  expect(Object.entries(staffing(f).plan).filter(([room])=>room.startsWith('dorm')).flatMap(([,row])=>row)).not.toContain(id('旅骨'))
 })
 it('preserves an explicit dorm resident and waits for another reserved bed to release',()=>{
  const f=fixture(false,w=>w.compatibility.backupPlans!.push({trigger:"op_data.operators['芬'].is_resting()",plan:{},task:{dormitory_1:['Current','Current','Current','夕','Current']}}))
  const pending=new MowerTask({time:2,type:T.RE_ORDER,plan:{dormitory_1:['Current','Current','Current','Current','Free']}})
  f.source.queue.tasks=[pending]
  expect(f.controller.evaluate('END')).toBe(false)
  expect(f.controller.active).toEqual([true,false])
  expect(f.source.queue.tasks).toEqual([pending])
  f.source.queue.tasks=[];f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false,true])
  expect(staffing(f).plan.dormitory_1?.[3]).toBe(id('夕'))
  const projected=projectMowerArrangements(f.source.data,[staffing(f).plan])
  expect(projected.getDormByName(id('旅骨'))?.[1].position).toEqual(['dormitory_1',4])
 })
 it('does not treat the current shift intent as a separate pending reservation',()=>{
  const f=fixture(),task=new MowerTask({type:T.SHIFT_OFF,plan:{dormitory_1:['Current','Current','Current','Free','Free']}})
  f.source.queue.tasks=[task]
  prepareMowerShiftBackup(f.source.data,task,f.state.mowerShiftModel!,[])
  expect(task.backupShiftConditions).toEqual([false])
  expect(projectMowerArrangements(f.source.data,[task.plan]).operators[id('旅骨')]!.isResting()).toBe(true)
  expect(f.controller.active).toEqual([true])
 })

 it('leaves a protected restored training member off the admission list',()=>{
  const f=fixture(false,undefined,true),before=f.source.data.dorms.map(b=>[b.name,b.timeMicros])
  f.source.data.busyRestingNames.add(id('旅骨'))
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false])
  expect(staffing(f).plan.train).toBeUndefined()
  expect(Object.values(staffing(f).plan).flat()).not.toContain(id('旅骨'))
  expect(f.source.data.dorms.map(b=>[b.name,b.timeMicros])).toEqual(before)
  expect(f.source.data.currentOperator('train',1)?.name).toBe(id('星源'))
 })
 it('adds the restored member during the complete shift preview',()=>{
  const f=fixture(),task=new MowerTask({type:T.SHIFT_OFF,plan:{dormitory_1:['Current','Current','Current','Free','Free']}})
  f.source.queue.tasks=[task]
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(task.backupShiftConditions).toEqual([false])
  const projected=projectMowerArrangements(f.source.data,[task.plan])
  expect(projected.groupIsResting('g')).toBe(true)
  for(const name of ['芬','香草','旅骨'])expect(projected.operators[id(name)]!.isResting()).toBe(true)
  expect(projected.currentOperator('recycle',0)?.name).toBe(id('星源'))
  expect(f.controller.active).toEqual([true])
 })

 it('restores the removed member in the same final arrangement as the group downshift',()=>{
  const f=fixture(),before=f.source.data.dorms.map(b=>[b.name,b.timeMicros])
  for(const [name,room] of [['芬','room_1_1'],['香草','room_1_2']] as const){
   const primary=f.source.data.operators[id(name)]!,cover=f.source.data.currentOperator(room,0)!
   primary.currentRoom=room;primary.currentIndex=0;primary.mood=0
   cover.currentRoom='';cover.currentIndex=-1
  }
  for(const bed of f.source.data.dorms)bed.reset()
  f.source.data.groupShiftState.g=false
  const task=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:[id('克洛丝')],room_1_2:[id('空爆')],dormitory_1:['Current',id('芬'),id('香草'),'Current','Current']}})
  f.source.queue.tasks=[task]
  prepareMowerShiftCycle(f.source.data,task,f.source.queue,f.state.mowerShiftModel!)
  expect(task.backupShiftConditions).toEqual([false])
  const projected=projectMowerArrangements(f.source.data,[task.plan])
  for(const name of ['芬','香草','旅骨'])expect(projected.operators[id(name)]!.isResting()).toBe(true)
  expect(projected.currentOperator('recycle',0)?.name).toBe(id('星源'))
  expect(f.source.data.operators[id('芬')]!.currentRoom).toBe('room_1_1')
  expect(f.source.data.dorms.every(b=>!b.name)).toBe(true)
  expect(before.some(([name])=>name===id('芬'))).toBe(true)
 })

 it('preserves a new admission and explicit dorm move when the same transition changes dorm order',()=>{
  const f=fixture(false,w=>{
   w.compatibility.backupPlans=[{trigger:"op_data.operators['芬'].is_working()",conf:{dorm_order:'dormitory_1,dormitory_1_low'},plan:{recycle:{plans:[{agent:'星源',group:'',replacement:['旅骨']}]}}},{trigger:"op_data.operators['芬'].is_resting()",plan:{},task:{dormitory_1:['Current','Current','Current','Current','芬']}}]
  })
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false,true])
  expect(staffing(f).plan.dormitory_1?.[4]).toBe(id('芬'))
  const projected=projectMowerArrangements(f.source.data,[staffing(f).plan])
  for(const name of ['芬','香草','旅骨'])expect(projected.operators[id(name)]!.isResting()).toBe(true)
  expect(projected.operators[id('芬')]!.currentIndex).toBe(4)
 })

 it('rejects bed contraction atomically when migration would recall the newly admitted group',()=>{
  const f=fixture(false,w=>{
   const slot=(name:string,group:string,cover:string)=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:group,replacements:cover?[id(cover)]:[]})
   w.mainPlan.facilities.room_1_3.type='manufacture';w.mainPlan.facilities.room_1_3.product='gold'
   w.mainPlan.facilities.room_1_3.slots=[slot('夕','h','梅尔')]
   w.mainPlan.facilities.dormitory_1.slots[1]=slot('安赛尔','','')
   w.compatibility.backupPlans=[{trigger:"op_data.operators['芬'].is_working()",plan:{
    recycle:{plans:[{agent:'星源',group:'',replacement:['旅骨']}]},
    dormitory_1:{plans:[{agent:'Current',group:'',replacement:[]},{agent:'Free',group:'',replacement:[]},...Array.from({length:3},()=>({agent:'Current',group:'',replacement:[]}))]},
   }}]
  })
  const guest=f.source.data.operators[id('夕')]!,cover=f.source.data.operators[id('梅尔')]!,bed=f.source.data.dorms.find(b=>b.position[1]===3)!
  guest.currentRoom='dormitory_1';guest.currentIndex=3;guest.mood=0
  cover.currentRoom='room_1_3';cover.currentIndex=0
  f.source.data.groupShiftState.h=true;bed.name=guest.name;bed.timeMicros=toMowerMicros(10)
  const pending=new MowerTask({time:2,type:T.SKILL_UPGRADE});f.source.queue.tasks=[pending]
  const before=f.source.data.dorms.map(b=>[b.name,b.timeMicros]),config=f.state.config,observations=Object.values(f.source.data.operators).map(op=>[op.name,op.currentRoom,op.currentIndex,op.mood,op.timeStampMicros])
  for(let pass=0;pass<3;pass++){
   expect(f.controller.evaluate('END')).toBe(false)
   expect(f.controller.active).toEqual([true]);expect(f.state.config).toBe(config)
   expect(f.source.queue.tasks).toEqual([pending]);expect(pending.time).toBe(2)
   expect(f.source.data.dorms.map(b=>[b.name,b.timeMicros])).toEqual(before)
   expect(Object.values(f.source.data.operators).map(op=>[op.name,op.currentRoom,op.currentIndex,op.mood,op.timeStampMicros])).toEqual(observations)
   expect(f.state.mowerBackupGenerated).toBeUndefined()
  }
  guest.currentRoom='room_1_3';guest.currentIndex=0;cover.currentRoom='';cover.currentIndex=-1
  f.source.data.groupShiftState.h=false;bed.reset()
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false])
  expect(f.source.queue.tasks).toContain(pending);expect(pending.time).toBe(2)
  const projected=projectMowerArrangements(f.source.data,[staffing(f).plan])
  for(const name of ['芬','香草','旅骨'])expect(projected.operators[id(name)]!.isResting()).toBe(true)
 })
 it.each(['beds','member'] as const)('retains a failed transition and unchanged reservations until %s release',reservation=>{
  const f=fixture(),plan:MowerTaskPlan=reservation==='beds'?{dormitory_1:['Current','Current','Current','Free','Free']}:{factory:[id('旅骨')]}
  const pending=new MowerTask({time:2,type:T.RE_ORDER,plan});f.source.queue.tasks=[pending]
  const before=f.source.data.dorms.map(b=>[b.name,b.timeMicros])
  for(let pass=0;pass<3;pass++){
   expect(f.controller.evaluate('END')).toBe(false)
   expect(f.controller.active).toEqual([true])
   expect(f.source.queue.tasks).toEqual([pending]);expect(pending.time).toBe(2)
   expect(f.source.data.dorms.map(b=>[b.name,b.timeMicros])).toEqual(before)
  }
  f.source.queue.tasks=[];f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false])
  expect(projectMowerArrangements(f.source.data,[staffing(f).plan]).operators[id('旅骨')]!.isResting()).toBe(true)
 })
})
