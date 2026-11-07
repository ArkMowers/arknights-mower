import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {projectMowerArrangements} from './mowerObservations'
import {mowerIsDormReplacement} from './mowerCorrection'
import {mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {commitMowerGroupShifts,mowerArrangementGroupTransitions} from './mowerSharedGroups'
import {prepareMowerShiftBackup,prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'

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
  transition:():MowerTaskPlan=>explicitDeparture?{room_1_1:['S']}: {},
  activate:()=>{},
 }
 const queue=new MowerTaskQueue();queue.tasks=[task]
 return {data,task,model,queue}
}

describe('group return survives a backup workaholic override',()=>{
 it('completes fixed targets on a retained charging return without ordinary replanning',()=>{
  const {data,task,model,queue}=fixture()
  data.operators.A!.workaholic=true
  task.plan={central:['A']};task.fiaReturnTarget='A';task.executionRetained=true
  const originalTime=task.timeMicros
  model.evaluate=()=>{throw new Error('charging return must keep its existing arrangement')}
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.plan).toEqual({central:['A'],dormitory_1:['D','Current','Current']})
  expect(task.timeMicros).toBe(originalTime)
  expect(queue.tasks).toEqual([task])
  expect(data.groupIsResting('g')).toBe(true)
  expect(data.operators.R!.currentRoom).toBe('dormitory_1')
 })
 it('returns the fixed dorm member when the backup enabled zero-mood work before dispatch',()=>{
  const {data,task,model,queue}=fixture()
  data.operators.A!.workaholic=true;data.planConditions=[true]
  task.groupShiftTransitions={};model.evaluate=()=>[true]
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.plan.dormitory_1?.[0]).toBe('D')
  expect(task.groupShiftTransitions.g).toBe(false)
  const after=projectMowerArrangements(data,[task.plan])
  commitMowerGroupShifts(after,task.groupShiftTransitions)
  expect(after.groupIsResting('g')).toBe(false)
  expect(after.operators.D!.currentRoom).toBe('dormitory_1')
  expect(mowerIsDormReplacement(after,'R')).toBe(false)
  after.operators.C!.replacement=['R']
  const nextPlan={}
  expect(mowerGetRestingPlan(after,['C'],[],nextPlan,{isDormReplacement:name=>mowerIsDormReplacement(after,name)})).toBe(true)
  expect(nextPlan).toMatchObject({room_1_1:['R']})
  expect(data.groupIsResting('g')).toBe(true)
  expect(data.operators.R!.currentRoom).toBe('dormitory_1')
 })

 it('completes a partial zero-mood return before preview instead of leaving its dorm cover occupied',()=>{
  const {data,task,model,queue}=fixture()
  data.operators.A!.workaholic=true;data.planConditions=[true]
  task.plan={central:['A']};task.groupShiftTransitions={};model.evaluate=()=>[true]
  prepareMowerShiftCycle(data,task,queue,model)
  expect(task.plan.dormitory_1?.[0]).toBe('D')
  expect(task.groupShiftTransitions.g).toBe(false)
 })

 it.each(['missing','current','replacement','complete','observed'] as const)('confirms only complete zero-mood group returns: %s',target=>{
  const {data}=fixture();data.operators.A!.workaholic=true
  const plan:MowerTaskPlan={central:['A']}
  if(target!=='missing')plan.dormitory_1=[target==='complete'?'D':target==='replacement'?'R':'Current','Current','Current']
  if(target==='observed'){data.operators.D!.setProjectedPosition('dormitory_1',0);data.operators.R!.setProjectedPosition('',-1)}
  expect(mowerArrangementGroupTransitions(data,plan).g).toBe(['complete','observed'].includes(target)?false:undefined)
  expect(data.groupIsResting('g')).toBe(true)
 })

 it('keeps other resting bindings on a shared dorm member when a zero-mood group returns',()=>{
  const {data,task,model,queue}=fixture()
  data.operators.D!.groupBindings=[{group:'g',replacement:['R']},{group:'h',replacement:['R']}]
  data.groupShiftState.h=true;data.operators.C!.setProjectedPosition('',-1);data.operators.S!.setProjectedPosition('room_1_1',0)
  data.operators.A!.workaholic=true;data.planConditions=[true];model.evaluate=()=>[true]
  prepareMowerShiftCycle(data,task,queue,model)
  const after=projectMowerArrangements(data,[task.plan]);commitMowerGroupShifts(after,task.groupShiftTransitions)
  expect(after.groupIsResting('g')).toBe(false)
  expect(after.groupIsResting('h')).toBe(true)
  expect(after.currentOperator('dormitory_1',0)?.name).toBe('R')
 })

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

 it.each([false,true])('confirms an incidental zero-mood placement only for a complete group, complete=%s',complete=>{
  const {data,task,model}=fixture()
  data.groupShiftState.h=true
  data.operators.C!.setProjectedPosition('',-1)
  data.operators.S!.setProjectedPosition('room_1_1',0)
  if(!complete){
   data.plan.dormitory_1![2]='E'
   data.operators.E=new MowerOperatorState({name:'E',room:'dormitory_1',index:2,group:'h',operatorType:'high',mood:24,timeStampMicros:0})
  }
  const swap=model.swap
  model.swap=(state,conditions)=>{
   const next=swap(state,conditions)
   next.operators.C!.workaholic=conditions[0]!
   return next
  }
  model.transition=()=>({room_1_1:['C']})
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.plan.room_1_1).toEqual(['C'])
  expect(task.groupShiftTransitions).toEqual(complete?{g:false,h:false}:{g:false})
  const projected=projectMowerArrangements(model.swap(data,[true]),[task.plan])
  commitMowerGroupShifts(projected,task.groupShiftTransitions)
  expect(projected.groupShiftState).toEqual({g:false,h:!complete})
 })

 it.each([false,true])('drops an obsolete return after the backup replaces its primary, explicit=%s',explicit=>{
  const {data,task,model}=fixture()
  model.evaluate=()=>[true]
  model.swap=(state,conditions)=>{
   const next=projectMowerArrangements(state,[])
   if(conditions[0]){
    next.plan={...next.plan,central:['B']}
    Object.assign(next.operators.A!,{room:'',index:-1,group:'',operatorType:'low'})
    Object.assign(next.operators.B!,{room:'central',index:0,operatorType:'high'})
   }
   next.planConditions=[...conditions]
   return next
  }
  model.explicitSlots=()=>new Set(explicit?['central\0'+'0']:[])
  model.transition=()=>({central:['B']})
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.plan.central).toEqual(['B'])
  expect(task.groupShiftTransitions.g).toBeUndefined()
  const projected=projectMowerArrangements(model.swap(data,[true]),[task.plan])
  commitMowerGroupShifts(projected,task.groupShiftTransitions)
  expect(projected.groupIsResting('g')).toBe(true)
  expect(data.plan.central).toEqual(['A'])
  expect(data.groupIsResting('g')).toBe(true)
 })

 it('preserves a planned departure when the same primary becomes workaholic',()=>{
  const {data,task,model}=fixture()
  data.operators.A!.setProjectedPosition('central',0)
  data.operators.B!.setProjectedPosition('',-1)
  data.operators.D!.setProjectedPosition('dormitory_1',0)
  data.operators.R!.setProjectedPosition('',-1)
  data.dorms[0]!.name=''
  data.groupShiftState.g=false
  task.type=T.SHIFT_OFF
  task.plan={central:['B'],dormitory_1:['R','A','Current']}
  task.groupShiftTransitions={g:true}
  model.evaluate=()=>[true]
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.groupShiftTransitions.g).toBe(true)
  expect(data.groupIsResting('g')).toBe(false)
 })

 it('retains the original return when a backup changes the same primary group',()=>{
  const {data,task,model}=fixture()
  const swap=model.swap
  model.swap=(state,conditions)=>{
   const next=swap(state,conditions)
   if(conditions[0])next.operators.A!.group='h'
   return next
  }
  prepareMowerShiftBackup(data,task,model,[])
  expect(task.groupShiftTransitions.g).toBe(false)
  expect(task.plan.dormitory_1?.[0]).toBe('D')
  expect(data.operators.A!.group).toBe('g')
  expect(data.groupIsResting('g')).toBe(true)
 })
})
