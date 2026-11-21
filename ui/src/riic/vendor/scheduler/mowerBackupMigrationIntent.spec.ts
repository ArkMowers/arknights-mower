import {describe,expect,it,vi} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {advanceRoster,createRosterRuntime,nextRosterActionHours,settleRoster,type RuntimeRates} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {projectMowerArrangements} from './mowerObservations'
import {prepareMowerShiftCycle} from './mowerShiftCycle'
import {resumeMowerFailedTasks} from './mowerTaskFailure'
import * as cycle from './mowerShiftCycle'
import {MowerTask,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'

function fixture(resting=false,explicitBed=false,moodGate=false,gateName='芬'){
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities))room.slots=[]
 const slot=(name:string,group:string,cover:string)=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:group||null,replacements:cover?[cover==='Free'?cover:id(cover)]:[]})
 workspace.mainPlan.facilities.central.slots=[slot('芬','g','克洛丝')]
 workspace.mainPlan.facilities.room_3_1.slots=[slot('乌有','g','伺夜')]
 workspace.mainPlan.facilities.room_3_2.slots=[slot('砾','h','香草')]
 workspace.mainPlan.facilities.room_1_1.slots=[slot('翎羽','','安德切尔')]
 workspace.mainPlan.facilities.meeting.slots=[slot('塞雷娅','','信仰搅拌机')]
 if(gateName!=='芬'){
  workspace.mainPlan.facilities.room_2_1.slots=[slot(gateName,'','')]
  workspace.mainPlan.conf.workaholic=[id(gateName)]
 }
 workspace.mainPlan.facilities.dormitory_1.slots=[slot('杜林','',''),slot('闪灵','',''),slot('麦哲伦','g','Free'),{occupant:{kind:'free' as const},groupId:null,replacements:[]},slot('桃金娘','','')]
 workspace.mainPlan.conf.free_room_exclusions=[id('塞雷娅')]
 workspace.compatibility.backupPlans=[{trigger:"op_data.operators['芬'].is_working() != True"+(moodGate?" and op_data.operators['"+gateName+"'].current_mood() < 10":""),plan:{
  meeting:{plans:[{agent:'信仰搅拌机',group:'',replacement:['塞雷娅']}]},
  room_3_1:{plans:[{agent:'砾',group:'h',replacement:['香草']}]},
  room_3_2:{plans:[{agent:'乌有',group:'g',replacement:['伺夜']}]},
 },task:{central:['克洛丝'],meeting:['信仰搅拌机'],room_1_1:['伺夜'],...(explicitBed?{dormitory_1:['Current','Current','Free','Current','Current']}:{})}}]
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true;config.mowerTaskScheduling={...config.mowerTaskScheduling,adjustForRunOrders:false}
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 source.queue.tasks=[];source.initial=false;source.firstInit=false
 for(const op of Object.values(source.data.operators)){op.currentRoom=op.room;op.currentIndex=op.index;op.mood=24;op.timeStampMicros=0}
 for(const name of ['芬','乌有']){source.data.operators[id(name)]!.mood=5;state.morale[id(name)]=5}
 if(moodGate){source.data.operators[id(gateName)]!.mood=5;state.morale[id(gateName)]=5}
 source.data.groupShiftState={g:resting,h:false}
 if(resting){
  source.data.operators[id('芬')]!.setProjectedPosition('dormitory_1',3)
  source.data.operators[id('克洛丝')]!.setProjectedPosition('central',0)
  source.data.dorms.find(bed=>bed.position[1]===3)!.name=id('芬')
  state.occupants.central_0=id('克洛丝');state.bedOccupants.dormitory_1_3=id('芬')
 }
 const task=new MowerTask({type:T.SHIFT_OFF,plan:{central:[id('克洛丝')],room_3_1:[id('伺夜')],dormitory_1:['Current','Current',id('乌有'),id('芬'),'Current']}})
 task.ordinaryCoordination=true;task.coordinationRequestNames=[id('芬')];source.queue.tasks=[task]
 return {state,controller,source,task}
}

describe('backup migration preserves ordinary group intent',()=>{
 it('keeps the departing group bed open for retained admission after a local primary recall',()=>{
  const {state,source,task}=fixture(),before=JSON.stringify(source.data)
  prepareMowerShiftCycle(source.data,task,source.queue,state.mowerShiftModel!)
  const effective=state.mowerShiftModel!.swap(source.data,task.backupShiftConditions!,task.backupGroup)
  const final=projectMowerArrangements(effective,[task.plan],task.groupShiftTransitions)
  expect(final.operators[id('芬')]!.currentRoom).toBe('dormitory_1')
  expect(final.operators[id('乌有')]!.currentRoom).toBe('room_3_2')
  expect(final.operators[id('塞雷娅')]!.currentRoom).toBe('dormitory_1')
  expect(task.groupShiftTransitions.g).toBe(true)
  expect(final.groupIsResting('g')).toBe(true)
  expect(JSON.stringify(source.data)).toBe(before)
 })
 it.each([{origins:[id('乌有')]},{origins:[id('芬'),id('乌有')]}])('retains an ordinary source that the backup only recalls locally: $origins',({origins})=>{
  const {state,source,task}=fixture(),before=structuredClone(task.plan),time=task.timeMicros
  task.coordinationRequestNames=[...origins]
  expect(()=>prepareMowerShiftCycle(source.data,task,source.queue,state.mowerShiftModel!)).toThrow('原下班目标未完成')
  expect(task.coordinationRequestNames).toEqual(origins)
  expect(task.plan).toEqual(before);expect(task.timeMicros).toBe(time);expect(source.queue.tasks).toContain(task)
  expect(source.data.groupShiftState.g).toBe(false)
 })
 it('does not reopen a completed source that has already returned to work',()=>{
  const {state,source,task}=fixture()
  task.coordinationRequestNames=[id('芬'),id('乌有')]
  task.coordinationCompletedRequestNames=[id('乌有')]
  prepareMowerShiftCycle(source.data,task,source.queue,state.mowerShiftModel!)
  expect(task.coordinationRequestNames).toEqual([id('芬')])
  expect(task.coordinationCompletedRequestNames).toEqual([id('乌有')])
 })
 it('suspends the unchanged original request, dispatches unrelated work and resumes when its backup exits',()=>{
  const {state,source,task,controller}=fixture(false,false,true)
  const pages=['INFRA_DETAILS','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','INFRA_CONFIDENTIAL','CLUE_GIVE_AWAY','INFRA_DETAILS'],clueRequests:string[]=[]
  const rates:RuntimeRates={workRate:()=>0,recoveryRate:()=>4,mowerClueIO:(request,current)=>({delayMicros:0,observe:()=>{
   clueRequests.push(request.kind)
   return {kind:request.kind,observedAtMicros:toMowerMicros(current.time),value:request.kind==='scene'?pages.shift()??'INFRA_DETAILS':null}
  }})}
  task.coordinationRequestNames=[id('乌有')]
  const plan=structuredClone(task.plan),time=task.timeMicros,independent=new MowerTask({type:T.CLUE})
  source.queue.tasks.push(independent)
  const preview=vi.spyOn(cycle,'prepareMowerShiftCycle')
  try{
   settleRoster(state,rates,0,controller.evaluate)
   expect(task.executionFailure?.kind).toBe('resource-wait')
   const attempts=preview.mock.calls.filter(([,candidate])=>candidate===task).length
   expect(attempts).toBe(1)
   for(let repeat=0;repeat<3;repeat++){
    advanceRoster(state,1/60,rates)
    settleRoster(state,rates,0,controller.evaluate)
   }
   expect(preview.mock.calls.filter(([,candidate])=>candidate===task)).toHaveLength(attempts)
   expect(source.queue.tasks).toContain(task);expect(source.queue.tasks,JSON.stringify({tasks:source.queue.tasks.map(t=>({type:t.type.key,time:t.time,failure:t.executionFailure?.reason})),execution:source.execution?.task.type.key,diagnostics:state.diagnostics})).not.toContain(independent)
   expect(source.trace.some(entry=>entry.type==='CLUE')).toBe(true)
   expect(clueRequests).toContain('read-time');expect(clueRequests).not.toContain('save-exception')
   expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(time)
   expect(task.coordinationRequestNames).toEqual([id('乌有')])
   state.morale[id('芬')]=24
   Object.assign(source.data.operators[id('芬')]!,{mood:24,timeStampMicros:source.data.nowMicros})
   for(let step=0;step<40&&source.queue.tasks.includes(task);step++){
    settleRoster(state,rates,0,controller.evaluate)
    if(!source.queue.tasks.includes(task))break
    const next=nextRosterActionHours(state,rates)
    if(!Number.isFinite(next))break
    if(next>0)advanceRoster(state,next,rates)
   }
   expect(source.queue.tasks).not.toContain(task)
   expect(source.data.operators[id('乌有')]!.isResting()).toBe(true)
   expect(task.timeMicros).toBe(time)
  }finally{preview.mockRestore()}
 })
 it('resumes for a new observation used only by the hypothetical backup condition',()=>{
  const {state,source,task,controller}=fixture(false,false,true,'巡林者'),rates={workRate:()=>0,recoveryRate:()=>4}
  const gate=id('巡林者'),unrelated=id('翎羽'),time=task.timeMicros,plan=structuredClone(task.plan)
  task.coordinationRequestNames=[id('乌有')]
  expect(Object.values(task.plan).flat()).not.toContain(gate)
  expect(Object.keys(task.plan)).not.toContain(source.data.operators[gate]!.currentRoom)
  expect(state.mowerShiftModel!.observationNames).toContain(gate)
  const preview=vi.spyOn(cycle,'prepareMowerShiftCycle')
  try{
   settleRoster(state,rates,0,controller.evaluate)
   expect(task.executionFailure?.kind).toBe('resource-wait')
   expect(source.data.planConditions).toEqual([false])
   expect(preview.mock.calls.filter(([,candidate])=>candidate===task)).toHaveLength(1)
   for(let repeat=0;repeat<3;repeat++){
    advanceRoster(state,1/60,rates)
    settleRoster(state,rates,0,controller.evaluate)
   }
   Object.assign(source.data.operators[unrelated]!,{mood:23,timeStampMicros:source.data.nowMicros})
   state.morale[unrelated]=23
   settleRoster(state,rates,0,controller.evaluate)
   expect(preview.mock.calls.filter(([,candidate])=>candidate===task)).toHaveLength(1)
   expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(time)
   expect(source.queue.tasks).toContain(task)
   expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(false)
   Object.assign(source.data.operators[gate]!,{mood:24,timeStampMicros:source.data.nowMicros,moodIsPrediction:true})
   state.morale[gate]=24
   expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(false)
   source.data.operators[gate]!.moodIsPrediction=false
   expect(state.mowerShiftModel!.select!(source.data).conditions).toEqual([false])
   expect(resumeMowerFailedTasks(state,source.data,source.queue)).toBe(true)
   expect(task.executionFailure).toBeUndefined()
   for(let step=0;step<40&&source.queue.tasks.includes(task);step++){
    settleRoster(state,rates,0,controller.evaluate)
    if(!source.queue.tasks.includes(task))break
    const next=nextRosterActionHours(state,rates)
    if(!Number.isFinite(next))break
    if(next>0)advanceRoster(state,next,rates)
   }
   expect(source.queue.tasks).not.toContain(task)
   expect(preview.mock.calls.filter(([,candidate])=>candidate===task).length).toBeGreaterThan(1)
   expect(source.data.operators[id('乌有')]!.isResting()).toBe(true)
   expect(source.data.planConditions).toEqual([false])
   expect(task.timeMicros).toBe(time)
  }finally{preview.mockRestore()}
 })
 it('applies the newly activated explicit departure before allocating retained residents',()=>{
  const {state,source}=fixture(false,true),model=state.mowerShiftModel!,data=source.data
  const intent={central:[id('芬')]}
  const seed=projectMowerArrangements(data,[intent]),next=model.swap(seed,[true])
  const reserved=new MowerTask({type:T.RE_ORDER,plan:{dormitory_1:['Current','Current','Current','Free','Current']}})
  const transition=model.transition(data,next,[false],[true],seed,[reserved],intent)
  expect(transition.dormitory_1![2]).toBe(id('塞雷娅'))
  expect(transition.central).toEqual([id('克洛丝')])
 })
 it.each([false,true])('executes the departure without interpreting a local recall as a group return; already resting=%s',resting=>{
  const {state,source,task,controller}=fixture(resting),rates={workRate:()=>0,recoveryRate:()=>4}
  for(let step=0;step<40&&source.queue.tasks.includes(task);step++){
   settleRoster(state,rates,0,controller.evaluate)
   if(!source.queue.tasks.includes(task))break
   const next=nextRosterActionHours(state,rates)
   if(!Number.isFinite(next))break
   if(next>0)advanceRoster(state,next,rates)
  }
  expect(source.queue.tasks).not.toContain(task)
  expect(source.data.operators[id('芬')]!.currentRoom).toBe('dormitory_1')
  expect(source.data.operators[id('乌有')]!.currentRoom).toBe('room_3_2')
  expect(source.data.operators[id('塞雷娅')]!.currentRoom).toBe('dormitory_1')
  expect(source.data.groupShiftState.g).toBe(true)
  if(!resting)expect(state.events.some(event=>event.type==='shift-off'&&event.operators.includes(id('芬')))).toBe(true)
 })
})
