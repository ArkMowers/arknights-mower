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

function explicitRestingFixture(){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,currentRoom,currentIndex,group,replacement,mood] of [
  ['A','central','dormitory_1',0,'g',['R'],0],
  ['B','room_1_1','dormitory_1',1,'g',['S'],24],
  ['R','','central',0,'',[],24],
  ['S','','room_1_2',0,'',[],24],
  ['X','','room_1_1',0,'',[],24],
 ] as const)operators[name]=new MowerOperatorState({name,room,index:room?0:-1,currentRoom,currentIndex,group,replacement:[...replacement],mood,timeStampMicros:0,operatorType:room?'high':'low'})
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,operators,plan:{central:['A'],room_1_1:['B'],room_1_2:['S'],dormitory_1:['Free','Free']},dorms:[],groupShiftState:{g:true},planConditions:[]})
 return {data,slots:new Set(['room_1_1\0'+0,'room_1_2\0'+0])}
}
describe('explicit staffing cannot cause an incidental group recall',()=>{
 it('keeps unfinished recovery when a full member has an explicit cover outside its ordinary candidates',()=>{
  const {data,slots}=explicitRestingFixture()
  const plan=mowerCorrectionPlan(data,false,slots)
  expect(plan.central).toBeUndefined()
  expect(plan.room_1_1).toEqual(['X'])
  expect(data.operators.A!.isResting()).toBe(true)
 })
 it('still recalls the complete group when the conflicting work slot is ordinary',()=>{
  const {data}=explicitRestingFixture()
  expect(mowerCorrectionPlan(data).central).toEqual(['A'])
 })
 it('preserves a feasible exhausted departure through full-cycle correction',()=>{
  const {data,slots}=explicitRestingFixture()
  data.operators.A!.setProjectedPosition('central',0)
  data.operators.B!.setProjectedPosition('room_1_1',0)
  data.operators.R!.setProjectedPosition('',-1)
  data.operators.X!.setProjectedPosition('',-1)
  data.groupShiftState.g=false
  const task=new MowerTask({type:T.SHIFT_OFF,plan:{central:['R'],room_1_1:['X'],dormitory_1:['A','B']}})
  task.backupExplicitSlots=slots
  const queue=new MowerTaskQueue();queue.tasks=[task]
  const model:MowerShiftModel={count:0,evaluate:()=>[],swap:d=>projectMowerArrangements(d,[]),transition:()=>({}),activate:()=>{}}
  prepareMowerShiftCycle(data,task,queue,model)
  const plan=structuredClone(task.plan),time=task.timeMicros
  for(let repeat=0;repeat<3;repeat++)prepareMowerShiftCycle(data,task,queue,model)
  expect(task.plan).toEqual(plan);expect(task.timeMicros).toBe(time);expect(queue.tasks).toEqual([task])
  expect(data.currentOperator('central',0)?.name).toBe('A')
  const final=projectMowerArrangements(data,[task.plan])
  expect(final.operators.A!.isResting()).toBe(true)
  expect(final.currentOperator('central',0)?.name).toBe('R')
  expect(final.currentOperator('room_1_1',0)?.name).toBe('X')
  expect(task.groupShiftTransitions.g).toBe(true)
 })
})

function blockedDepartureFixture(){
 const {data}=explicitRestingFixture()
 data.planConditions=[false]
 data.groupShiftState.g=false
 for(const name of ['A','B']){const op=data.operators[name]!;op.setProjectedPosition(op.room,op.index)}
 data.operators.A!.exhaustRequire=true
 data.operators.R!.setProjectedPosition('',-1)
 data.operators.X!.setProjectedPosition('',-1)
 const task=new MowerTask({type:T.SHIFT_OFF,time:-1,plan:{central:['R'],room_1_1:['S'],dormitory_1:['A','B']}})
 const queue=new MowerTaskQueue();queue.tasks=[task]
 const model:MowerShiftModel={count:1,evaluate:d=>[d.operators.A!.isResting()],swap:(d,c)=>{const next=projectMowerArrangements(d,[]);next.planConditions=[...c];return next},transition:()=>({room_1_2:['S']}),explicitSlots:(original,conditions)=>new Set(conditions[0]&&!original[0]?['room_1_2\0'+0]:[]),activate:()=>{}}
 return {data,task,queue,model}
}
describe('required departure survives complete-cycle convergence',()=>{
 it('rejects a recalled required worker and retains every original source task',()=>{
  const {data,task,queue,model}=blockedDepartureFixture(),before=structuredClone(task.plan),time=task.timeMicros
  const ordinary=new MowerTask({type:T.SHIFT_OFF,plan:{}});ordinary.ordinaryCoordination=true
  queue.tasks.push(ordinary)
  expect(()=>prepareMowerShiftCycle(data,task,queue,model)).toThrow('原下班目标未完成')
  expect(task.plan).toEqual(before);expect(task.timeMicros).toBe(time);expect(queue.tasks).toEqual([task,ordinary])
  expect(data.currentOperator('central',0)?.name).toBe('A')
  model.transition=()=>({room_1_1:['S']})
  model.explicitSlots=(original,conditions)=>new Set(conditions[0]&&!original[0]?['room_1_1\0'+0]:[])
  prepareMowerShiftCycle(data,task,queue,model)
  expect(projectMowerArrangements(data,[task.plan]).operators.A!.isResting()).toBe(true)
  expect(task.timeMicros).toBe(time)
 })
 it('does not accept work from an explicit backup that exits in the same preview',()=>{
  const {data,task,queue,model}=blockedDepartureFixture()
  model.evaluate=d=>[d.operators.B!.isResting()]
  model.explicitTasks=[{central:['A']}]
  model.transition=(_old,_next,_original,conditions)=>conditions[0]?{central:['A']}:{room_1_2:['S']}
  model.explicitSlots=(original,conditions)=>new Set(conditions[0]&&!original[0]?['central\0'+0]:[])
  expect(()=>prepareMowerShiftCycle(data,task,queue,model)).toThrow('原下班目标未完成')
  expect(task.timeMicros).toBe(-3_600_000_000)
 })
 it('keeps a required departure separate from an independent ordinary source',()=>{
  const {data,task,queue,model}=blockedDepartureFixture(),time=task.timeMicros
  const ordinary=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_2:['S']}});ordinary.ordinaryCoordination=true
  queue.tasks.unshift(ordinary)
  prepareMowerShiftCycle(data,ordinary,queue,model)
  expect(queue.tasks).toContain(task);expect(task.timeMicros).toBe(time)
  expect(task.plan.dormitory_1).toEqual(['A','B'])
 })
 it.each(['ordinary','explicit'] as const)('permits the established %s departure exception',kind=>{
  const {data,task,queue,model}=blockedDepartureFixture()
  if(kind==='ordinary'){task.ordinaryCoordination=true;task.coordinationRequestNames=['A']}
  else if(kind==='explicit'){
   model.evaluate=()=>[true]
   model.explicitTasks=[{central:['A']}]
   model.transition=()=>({central:['A']})
   model.explicitSlots=()=>new Set(['central\0'+0])
  }
  expect(()=>prepareMowerShiftCycle(data,task,queue,model)).not.toThrow()
 })
})
