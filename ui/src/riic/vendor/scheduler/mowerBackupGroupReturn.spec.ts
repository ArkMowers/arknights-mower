import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerIsDormReplacement} from './mowerCorrection'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {commitMowerGroupShifts,mowerArrangementGroupTransitions} from './mowerSharedGroups'
import {prepareMowerShiftBackup,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function fixture(explicitDeparture=false){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,index,group,replacement,currentRoom,currentIndex] of [
  ['A','central',0,'g',['B'],'dormitory_1',1],
  ['D','dormitory_1',0,'g',['R'],'',-1],
  ['B','',-1,'',[],'central',0],
  ['R','',-1,'',[],'dormitory_1',0],
  ['C','room_1_1',0,'h',['S'],'room_1_1',0],
  ['S','',-1,'',[],'',-1],
 ] as const)operators[name]=new MowerOperatorState({name,room,index,group,replacement:[...replacement],currentRoom,currentIndex,mood:24,timeStampMicros:0,operatorType:room?'high':'low'})
 const data=new MowerSchedulingData({
  alpha:true,nowMicros:0,operators,plan:{central:['A'],dormitory_1:['D','Free','Free'],room_1_1:['C']},
  dorms:[new MowerDormState(['dormitory_1',1],'A',0),new MowerDormState(['dormitory_1',2])],
  groupShiftState:{g:true,h:false},planConditions:[false],
 })
 const task=new MowerTask({type:T.SHIFT_ON,plan:{central:['A'],dormitory_1:['D','Free','Current']}})
 task.groupShiftTransitions={g:false}
 const model:MowerShiftModel={
  count:1,evaluate:state=>[state.operators.A!.currentRoom==='central'],
  swap:(state,conditions)=>{
   const next=projectMowerArrangements(state,[])
   next.operators.A!.workaholic=conditions[0]!
   next.planConditions=[...conditions]
   return next
  },
  explicitSlots:()=>new Set(explicitDeparture?['room_1_1\0'+'0']:[]),
  transition:()=>explicitDeparture?{room_1_1:['S']}: {},
  activate:()=>{},
 }
 const queue=new MowerTaskQueue();queue.tasks=[task]
 return {data,task,model,queue}
}

describe('group return survives a backup workaholic override',()=>{
 it.each([false,true])('retains the returning group alongside explicit departure=%s',explicitDeparture=>{
  const {data,task,model}=fixture(explicitDeparture)
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.backupShiftConditions).toEqual([true])
  expect(task.groupShiftTransitions.g).toBe(false)
  if(explicitDeparture)expect(task.groupShiftTransitions.h).toBe(true)
  const projected=projectMowerArrangements(model.swap(data,[true]),[task.plan])
  commitMowerGroupShifts(projected,task.groupShiftTransitions)
  expect(projected.groupIsResting('g')).toBe(false)
  expect(projected.currentOperator('dormitory_1',0)?.name).toBe('D')
  expect(projected.operators.R!.currentRoom).toBe('')
  expect(data.groupIsResting('g')).toBe(true)
  expect(data.currentOperator('dormitory_1',0)?.name).toBe('R')
 })

 it('keeps the return through the complete shift preview and releases the dorm cover',()=>{
  const {data,task,model,queue}=fixture()
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.groupShiftTransitions).toEqual({g:false})
  expect(task.plan.central).toEqual(['A'])
  expect(task.plan.dormitory_1?.[0]).toBe('D')
  const projected=projectMowerArrangements(model.swap(data,[true]),[task.plan])
  commitMowerGroupShifts(projected,task.groupShiftTransitions)
  expect(projected.groupIsResting('g')).toBe(false)
  expect(mowerIsDormReplacement(projected,'R')).toBe(false)
  projected.operators.C!.replacement=['R']
  const nextPlan={}
  expect(mowerGetRestingPlan(projected,['C'],[],nextPlan,{isDormReplacement:name=>mowerIsDormReplacement(projected,name)})).toBe(true)
  expect(nextPlan).toMatchObject({room_1_1:['R']})
  expect(data.groupShiftState).toEqual({g:true,h:false})
 })

 it('lets an explicit departure replace a return instead of preserving obsolete intent',()=>{
  const {data,task,model}=fixture()
  model.swap=(state,conditions)=>{const next=projectMowerArrangements(state,[]);next.planConditions=[...conditions];return next}
  model.explicitSlots=()=>new Set(['central\0'+'0'])
  model.transition=()=>({central:['B']})
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.groupShiftTransitions.g).toBe(true)
  expect(task.plan.central).toEqual(['B'])
  expect(mowerArrangementGroupTransitions(data,task.plan).g).toBe(true)
 })

 it('does not turn an incidental workaholic placement into another group return',()=>{
  const {data,task,model}=fixture()
  data.groupShiftState.h=true
  data.operators.C!.setProjectedPosition('',-1)
  data.operators.S!.setProjectedPosition('room_1_1',0)
  const swap=model.swap
  model.swap=(state,conditions)=>{
   const next=swap(state,conditions)
   next.operators.C!.workaholic=conditions[0]!
   return next
  }
  model.transition=()=>({room_1_1:['C']})
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.plan.room_1_1).toEqual(['C'])
  expect(task.groupShiftTransitions).toEqual({g:false})
  const projected=projectMowerArrangements(model.swap(data,[true]),[task.plan])
  commitMowerGroupShifts(projected,task.groupShiftTransitions)
  expect(projected.groupShiftState).toEqual({g:false,h:true})
 })
})
