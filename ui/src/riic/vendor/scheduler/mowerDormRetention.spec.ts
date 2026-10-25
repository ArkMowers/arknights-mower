import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {alphaPosition,alphaPrioritizeRecovery} from './mowerAlphaDorm'
import {mowerTryReorder} from './mowerOrdinaryPlanning'
import {projectMowerArrangements} from './mowerObservations'
import {planMowerMetadata,planMowerMoodLimitReleases} from './mowerMetadata'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {prepareMowerRelease} from './mowerRelease'
import {prepareMowerDormSelection} from './mowerSelection'
import {mowerAssignDormGroup} from './mowerDormAssignment'
import {completeMowerBackupDepartureRecovery} from './mowerBackupDepartureRecovery'

const R1='dormitory_1',R2='dormitory_2'
function fixture(){
 const plan={central:['G'],room_1_2:['U'],recycle:['Y'],[R1]:['K0','K1','K2','K3','Free'],[R2]:['K4','K5','Free','Free','Free']}
 const operators:Record<string,MowerOperatorState>={}
 for(const [room,row] of Object.entries(plan))row.forEach((name,index)=>{if(name!=='Free')operators[name]=new MowerOperatorState({name,room,index,operatorType:'high',restingPriority:'high',currentRoom:room,currentIndex:index,mood:10,timeStampMicros:0,replacement:room.startsWith('dorm')?[]:[name+'Cover']})})
 for(const name of ['GCover','UCover','YCover'])operators[name]=new MowerOperatorState({name,mood:5,timeStampMicros:0})
 for(const [name,room,index,mood] of [['Y',R1,4,10],['U',R2,3,12],['YCover',R2,4,5]] as const)Object.assign(operators[name]!,{currentRoom:room,currentIndex:index,mood})
 operators.G!.mood=23.9
 return new MowerSchedulingData({alpha:true,plan,operators,dorms:[new MowerDormState([R1,4],'Y',toMowerMicros(2)),new MowerDormState([R2,2]),new MowerDormState([R2,3],'U',toMowerMicros(2)),new MowerDormState([R2,4],'YCover',toMowerMicros(2))],nowMicros:0,freeRoom:true,freeRoomExclusions:['U'],restingPriorityNames:['G']})
}
function cap(data:MowerSchedulingData,name='U',limit=12){Object.assign(data.operators[name]!,{mood:limit,upperLimit:limit,restMoodLimit:true,customMoodLimit:true})}
function merged(){const task=new MowerTask({type:T.RELEASE_DORM,time:1,plan:{[R2]:['Current','Current','Current','Free','Free']},metadata:'U,YCover',strictMoodLimit:true,moodLimit:12});task.releaseTargets={U:[R2,3],YCover:[R2,4]};task.executionRetained=true;return task}

describe('dorm retention allows movement and work without idle release',()=>{
 it('reorders the captain into the first dorm while preserving every resident',()=>{
  const data=fixture(),before=data.dorms.map(b=>[...b.position,b.timeMicros]);data.dorms[1]!.name='G'
  const plan=mowerTryReorder(data,{})!,after=projectMowerArrangements(data,[plan])
  expect(after.operators.G!.currentRoom).toBe(R1)
  expect(after.operators.U!.isResting()).toBe(true)
  expect(new Set(after.dorms.map(b=>b.name))).toEqual(new Set(['G','U','Y','YCover']))
  expect(data.dorms.map(b=>[...b.position,b.timeMicros])).toEqual(before)
 })
 it('moves a retained first-bed resident across rooms when the priority target arrives',()=>{
  const data=fixture();data.operators.U!.setProjectedPosition(R1,4);data.operators.Y!.setProjectedPosition(R2,3);data.dorms[0]!.name='U';data.dorms[2]!.name='Y'
  const after=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,{[R2]:['Current','Current','G','Current','Current']})])
  expect(after.operators.G!.currentRoom).toBe(R1);expect(after.operators.U!.currentRoom).toBe(R2)
 })
 it('keeps configured priority after the retained resident reaches its personal cap',()=>{
  const data=fixture();cap(data,'U',24);data.restingPriorityNames=['U']
  expect(data.restMoodComplete('U')).toBe(true)
  const after=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,{[R2]:['Current','Current','G','Current','Current']})])
  expect(after.currentOperator(R1,4)?.name).toBe('U')
 })
 it.each(['slot','name','product'])('preserves a real %s reservation',kind=>{
  const data=fixture(),slots=new Set<string>(),names=new Set<string>()
  if(kind==='slot')slots.add(alphaPosition(R2,3));else if(kind==='name')names.add('U');else data.reservedProductBeds.set(alphaPosition(R2,3),'U')
  const after=projectMowerArrangements(data,[alphaPrioritizeRecovery(data,{[R2]:['Current','Current','G','Current','Current']},{},slots,names)])
  expect(after.currentOperator(R2,3)?.name).toBe('U')
 })
 it.each([false,true])('keeps a capped resident when idle release is %s',freeRoom=>{
  const data=fixture();cap(data);data.freeRoom=freeRoom
  expect(data.restMoodComplete('U')).toBe(true);expect(planMowerMoodLimitReleases(data)).toEqual([])
  const names=['Current','Current','U','Free','Current'];prepareMowerDormSelection(data,names,R2,true)
  expect(names[2]).toBe('U')
  const eviction=['Current','Current','Current','Free','Current'];prepareMowerDormSelection(data,eviction,R2)
  expect(eviction[3]).toBe('U')
  const work=['U'];prepareMowerDormSelection(data,work,'room_1_2');expect(work).toEqual(['U'])
 })
 it('revalidates a stale merged strict release before metadata planning',()=>{
  const data=fixture();cap(data);cap(data,'YCover');const task=merged(),time=task.timeMicros,queue=new MowerTaskQueue();queue.tasks=[task]
  expect(prepareMowerRelease(data,queue,task)).toBe(true)
  expect(task.timeMicros).toBe(time);expect(task.releaseDormTargets()).toEqual({YCover:[R2,4]})
  expect(task.plan[R2]![3]).toBe('Current')
 })
 it('cancels only the retained member in a saved release task during metadata planning',()=>{
  const data=fixture();cap(data);cap(data,'YCover');const task=merged(),time=task.timeMicros,queue=new MowerTaskQueue();queue.tasks=[task]
  planMowerMetadata(data,queue)
  expect(queue.tasks).toContain(task);expect(task.timeMicros).toBe(time);expect(task.releaseDormTargets()).toEqual({YCover:[R2,4]})
  expect(task.plan[R2]![3]).toBe('Current')
 })
 it('rejects required retained standby admission atomically when every bed is reserved',()=>{
  const data=fixture();cap(data);data.standbyNames=['U'];const before=data.dorms.map(b=>[...b.position,b.name,b.timeMicros])
  expect(mowerAssignDormGroup(data,['U'],undefined,undefined,{},new Set(data.dorms.map(b=>alphaPosition(...b.position))))).toBeUndefined()
  expect(data.dorms.map(b=>[...b.position,b.name,b.timeMicros])).toEqual(before)
 })
 it('rejects a capped retained primary departure when no bed is available',()=>{
  const data=fixture();cap(data);data.operators.U!.setProjectedPosition('room_1_2',0);data.dorms[2]!.reset()
  const plan={room_1_2:['UCover']}
  expect(completeMowerBackupDepartureRecovery(data,plan,new Set([alphaPosition('room_1_2',0)]),new Set(data.dorms.map(b=>alphaPosition(...b.position))))).toBeUndefined()
  expect(data.operators.U!.currentRoom).toBe('room_1_2');expect(plan).toEqual({room_1_2:['UCover']})
 })
 it.each(['令','夕'])('counts retained %s recovery complete and plans the ordinary group return',name=>{
  const data=fixture(),op=data.operators.U!,mate=data.operators.Y!
  op.nativeName=name;op.group=mate.group='group';cap(data);mate.restInFull=true;mate.mood=6;data.groupShiftState.group=true
  const queue=new MowerTaskQueue()
  for(let i=0;i<3;i++){planMowerMetadata(data,queue);expect(queue.tasks.filter(t=>t.type===T.SHIFT_ON)).toHaveLength(1);expect(queue.tasks.some(t=>t.type===T.RELEASE_DORM&&t.releaseDormTargets().U)).toBe(false)}
  expect(data.restMoodComplete('U')).toBe(true);expect(op.isResting()).toBe(true)
  mate.mood=24;for(const bed of data.dorms)if(['U','Y'].includes(bed.name))bed.timeMicros=0
  planMowerMetadata(data,queue)
  const task=queue.tasks.find(t=>t.type===T.SHIFT_ON)!
  expect(task.plan.room_1_2).toEqual(['U']);expect(task.plan.recycle).toEqual(['Y']);expect(task.timeMicros).toBeLessThanOrEqual(0)
  const after=projectMowerArrangements(data,[task.plan]),finished=new MowerTaskQueue();planMowerMetadata(after,finished)
  expect(after.operators.U!.currentRoom).toBe('room_1_2');expect(finished.tasks.some(t=>t.type===T.SHIFT_ON&&t.plan.room_1_2?.includes('U'))).toBe(false)
 })
})
