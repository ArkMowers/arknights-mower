import {describe,it,expect} from 'vitest'
import {MowerSchedulingData} from './mowerSchedulingData'
import {MowerOperatorState} from './mowerOperatorState'
import {mowerCorrectionPlan} from './mowerCorrection'
import {prepareMowerShiftCycle,type MowerShiftModel} from './mowerShiftCycle'
import {projectMowerArrangements} from './mowerObservations'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,type MowerTaskPlan} from './mowerTaskQueue'

function fixture(){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,index,currentRoom,currentIndex,group,replacement,mood] of [
  ['A','central',0,'',-1,'g',['R'],0],
  ['B','recycle',0,'recycle',0,'g',['S'],15],
  ['C','meeting',0,'',-1,'',['Q'],24],
  ['M','dormitory_1',0,'',-1,'g',['N'],24],
  ['R','',-1,'central',0,'',[],.01],
  ['S','',-1,'',-1,'',[],24],
  ['Q','',-1,'meeting',0,'',[],24],
  ['N','',-1,'dormitory_1',0,'',[],24],
 ] as const)operators[name]=new MowerOperatorState({name,room,index,currentRoom,currentIndex,group,replacement:[...replacement],mood,timeStampMicros:0,operatorType:room?'high':'low'})
 operators.M!.groupBindings=[{group:'g',replacement:['N']},{group:'h',replacement:['N']}]
 operators.A!.exhaustRequire=true
 const data=new MowerSchedulingData({alpha:true,plan:{central:['A'],recycle:['B'],meeting:['C'],dormitory_1:['M']},operators,dorms:[],nowMicros:10_800_000_000,planConditions:[false],groupShiftState:{g:true,h:false}})
 const model:MowerShiftModel={count:1,evaluate:d=>[d.operators.A!.currentRoom==='central'&&d.operators.A!.mood<10],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];return next},transition:(_old,_next,original,conditions):MowerTaskPlan=>conditions[0]&&!original[0]?{central:['R']}:{},explicitSlots:(original,conditions)=>new Set(conditions[0]&&!original[0]?['central\0'+0]:[]),activate:()=>{}}
 return {data,model}
}
describe('explicit departures constrain incidental correction',()=>{
 it('does not treat an unchanged working member as a group return while preserving its reread',()=>{
  const {data}=fixture()
  const plan=mowerCorrectionPlan(data,false,new Set(['central\0'+0]))
  expect(plan.recycle).toEqual(['B'])
  expect(Object.values(plan).flat()).not.toContain('M')
  expect(data.groupIsResting('g')).toBe(true)
  expect(data.operators.A!.currentRoom).toBe('')
 })
 it('converges an independent return after a backup veto adds explicit slots to the same positions',()=>{
  const {data,model}=fixture(),queue=new MowerTaskQueue(),task=new MowerTask({type:T.SHIFT_ON,plan:{meeting:['C']}})
  queue.tasks=[task]
  expect(()=>prepareMowerShiftCycle(data,task,queue,model)).not.toThrow()
  expect(task.plan).toEqual({meeting:['C']})
  expect(task.backupExplicitSlots).toContain('central\0'+0)
  expect(task.groupShiftTransitions.g).toBeUndefined()
  expect(data.operators.A!.mood).toBe(0)
  expect(data.currentOperator('central',0)?.name).toBe('R')
  expect(data.currentOperator('dormitory_1',0)?.name).toBe('N')
 })
 it('still restores shared residents when a primary actually returns',()=>{
  const {data}=fixture()
  data.operators.A!.mood=24
  const plan=mowerCorrectionPlan(data)
  expect(plan.central).toEqual(['A'])
  expect(plan.dormitory_1).toEqual(['M'])
 })
})
