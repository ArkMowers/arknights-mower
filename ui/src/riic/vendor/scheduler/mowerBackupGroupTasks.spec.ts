import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerDormState,MowerSchedulingData} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T,toMowerMicros} from './mowerTaskQueue'
import {planMowerMetadata} from './mowerMetadata'
import {projectMowerArrangements} from './mowerObservations'
import {readMowerBackupGroupTasks,syncMowerBackupGroupTasks,filterMowerHeldReturns,validateMowerGroupTasks,type MowerBackupGroupTask} from './mowerBackupGroupTasks'
import {createDefaultWorkspace} from '../workbench/defaults'
import {importMowerJson,exportMowerJson} from '../workbench/compat/mowerJson'
import {validateBackupPlans} from '../workbench/validateBackupPlans'

function fixture(mode:MowerBackupGroupTask['mode']='while_active',action:MowerBackupGroupTask['action']='off'){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,index,group,replacement,currentRoom,currentIndex] of [
  ['A','central',0,'g',['B'],'dormitory_1',2],
  ['C','contact',0,'g',['D'],'dormitory_1',3],
  ['B','',-1,'',[],'central',0],['D','',-1,'',[],'contact',0],
  ['E','room_1_1',0,'h',['F'],'room_1_1',0],['F','',-1,'',[],'',-1],
  ['K1','dormitory_1',0,'',[],'dormitory_1',0],['K2','dormitory_1',1,'',[],'dormitory_1',1],
 ] as const)operators[name]=new MowerOperatorState({name,room,index,group,replacement:[...replacement],currentRoom,currentIndex,mood:12,timeStampMicros:0,operatorType:room?'high':'low'})
 const data=new MowerSchedulingData({alpha:true,nowMicros:0,operators,plan:{central:['A'],contact:['C'],room_1_1:['E'],dormitory_1:['K1','K2','Free','Free','Free']},dorms:[new MowerDormState(['dormitory_1',2],'A',toMowerMicros(4)),new MowerDormState(['dormitory_1',3],'C',toMowerMicros(4)),new MowerDormState(['dormitory_1',4])],groupShiftState:{g:true,h:false},planConditions:[true],backupGroupTasks:[[{group:'g',action,mode}]]})
 const queue=new MowerTaskQueue(),state={issued:new Set<string>()}
 return {data,queue,state}
}

describe('backup group task lifetime',()=>{
 it('shares pending work for compatible requests from two backups',()=>{
  const {data:original,queue,state}=fixture('once','on')
  original.backupGroupTasks=[...original.backupGroupTasks,...original.backupGroupTasks];original.planConditions=[true,true]
  for(let n=0;n<6;n++)syncMowerBackupGroupTasks(original,queue,state)
  expect(queue.tasks).toHaveLength(1)
  const data=projectMowerArrangements(original,[queue.tasks[0]!.plan]);data.groupShiftState.g=false;queue.tasks=[]
  syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks).toEqual([]);expect(state.issued.size).toBe(2)
 })
 it('round-trips group tasks and independent advanced settings, and validates declared group names',()=>{
  const source=JSON.parse(exportMowerJson(createDefaultWorkspace()))
  source.advanced_settings={group_mood_gap_threshold_minutes:90,group_mood_gap_max_extra_wait_hours:0}
  source.backup_plans=[{name:'休息',plan:{},group_tasks:[{group:'g',action:'off',mode:'while_active'}]},{name:'岗位',plan:{contact:{plans:[{agent:'絮雨',group:'g'}]}}}]
  const workspace=importMowerJson(JSON.stringify(source)),output=JSON.parse(exportMowerJson(workspace))
  expect(output.backup_plans).toEqual(source.backup_plans)
  expect(output.advanced_settings).toEqual(source.advanced_settings)
  const validate=()=>({criticalErrors:[],warnings:[],issues:[],isValid:true,power:{generation:0,consumption:0,margin:0,sufficient:true}})
  expect(validateBackupPlans(workspace,validate).filter(issue=>issue.message.includes('组名不存在'))).toEqual([])
  workspace.compatibility.backupPlans[0].group_tasks[0].group='missing'
  expect(validateBackupPlans(workspace,validate)).toContainEqual(expect.objectContaining({severity:'critical',message:expect.stringContaining('组名不存在')}))
 })
 it('issues once per activation and preserves explicit returns through metadata rebuilds',()=>{
  const {data,queue,state}=fixture('once','on')
  syncMowerBackupGroupTasks(data,queue,state)
  const task=queue.tasks[0]!
  expect(task.plan).toEqual({central:['A'],contact:['C']})
  planMowerMetadata(data,queue)
  expect(queue.tasks).toContain(task)
  queue.tasks=[]
  syncMowerBackupGroupTasks(data,queue,state);expect(queue.tasks).toEqual([])
  data.planConditions=[false];syncMowerBackupGroupTasks(data,queue,state)
  data.planConditions=[true];syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks.filter(t=>t.backupGroupRequest)).toHaveLength(1)
 })
 it.each(['while_active','forced'] as const)('suppresses ordinary returns in %s and restores the recovery deadline on exit',mode=>{
  const {data,queue,state}=fixture(mode)
  planMowerMetadata(data,queue)
  expect(queue.tasks.filter(t=>t.type===T.SHIFT_ON)).toEqual([])
  data.planConditions=[false];syncMowerBackupGroupTasks(data,queue,state)
  planMowerMetadata(data,queue)
  const task=queue.tasks.find(t=>t.type===T.SHIFT_ON)!
  expect(task).toBeDefined();expect(task.timeMicros).toBeGreaterThan(0)
 })
 it('keeps unrelated groups in a mixed ordinary return',()=>{
  const {data,queue}=fixture()
  const task=new MowerTask({type:T.SHIFT_ON,plan:{central:['A'],contact:['C'],room_1_1:['E']}})
  queue.tasks=[task];filterMowerHeldReturns(data,queue)
  expect(task.plan).toEqual({room_1_1:['E']});expect(queue.tasks).toEqual([task])
 })
 it('waits for supported recovery before restoring the held departure without duplicating requests',()=>{
  const {data:original,queue,state}=fixture()
  const data=projectMowerArrangements(original,[{central:['A'],contact:['C']}]);data.groupShiftState.g=false
  data.urgentRecoverySupporters={E:['A','C']}
  for(let n=0;n<6;n++)syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks).toEqual([])
  delete data.urgentRecoverySupporters.E
  syncMowerBackupGroupTasks(data,queue,state)
  const request=queue.tasks[0]!,time=request.timeMicros
  for(let n=0;n<6;n++)syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks).toEqual([request]);expect(request.timeMicros).toBe(time);expect(request.type).toBe(T.EXHAUST_OFF)
 })
 it('cancels unstarted requests on exit but retains a started handoff',()=>{
  const {data,queue,state}=fixture('once','on')
  syncMowerBackupGroupTasks(data,queue,state)
  const task=queue.tasks[0]!;task.arrangementStarted=true
  data.planConditions=[false];syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks).toEqual([task])
  task.arrangementStarted=false;syncMowerBackupGroupTasks(data,queue,state)
  expect(queue.tasks).toEqual([])
 })
 it('keeps parked requests unique and cancels them on exit',()=>{
  const {data:original,queue,state}=fixture()
  const data=projectMowerArrangements(original,[{central:['A'],contact:['C']}]);data.groupShiftState.g=false
  syncMowerBackupGroupTasks(data,queue,state)
  const request=queue.tasks[0]!,parked=[request];queue.tasks=[]
  for(let n=0;n<6;n++)syncMowerBackupGroupTasks(data,queue,state,parked)
  expect(queue.tasks).toEqual([]);expect(parked).toEqual([request])
  data.planConditions=[false];syncMowerBackupGroupTasks(data,queue,state,parked)
  expect(parked).toEqual([])
 })
 it('rejects unknown groups and conflicting active directions',()=>{
  const {data}=fixture()
  data.backupGroupTasks=[[{group:'missing',action:'off',mode:'once'}]]
  expect(()=>validateMowerGroupTasks(data)).toThrow('找不到工作主班')
  data.backupGroupTasks=[[{group:'g',action:'off',mode:'forced'}],[{group:'g',action:'on',mode:'once'}]];data.planConditions=[true,true]
  expect(()=>validateMowerGroupTasks(data)).toThrow('相反')
 })
 it.each([[{group:'g',action:'on',mode:'forced'}],[{group:'g',action:'off'},{group:'g',action:'off'}],[{group:' g',action:'off'}]].map(entry=>[entry]))('rejects invalid schema %j',entry=>{
  expect(()=>readMowerBackupGroupTasks(entry)).toThrow()
 })
})
