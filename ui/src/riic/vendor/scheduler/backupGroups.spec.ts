import {normalizeBackupGroups,sameBackupGroups} from './backupGroups'
import {describe,expect,it} from 'vitest'
import {createDefaultWorkspace} from '../workbench/defaults'
import {importMowerJson,exportMowerJson} from '../workbench/compat/mowerJson'
import {createBackupPlanController} from './backupPlans'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {prepareMowerShiftBackup} from './mowerShiftCycle'
import {MowerTask,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

function fixture(configure?:(workspace:ReturnType<typeof createDefaultWorkspace>)=>void){
 const workspace=createDefaultWorkspace()
 workspace.mainPlan.facilities.room_1_1.slots=[{occupant:{kind:'operator',operatorId:'char_123_fang'},groupId:null,replacements:['char_240_wyvern']}]
 workspace.compatibility.unrecognizedFields.backup_groups=[
  {id:'a',name:'A',trigger:"op_data.operators['芬'].is_working()"},
  {id:'b',name:'B',trigger:'True'},
 ]
 workspace.compatibility.backupPlans=[
  {name:'shared',trigger:'True'},
  {group_ids:['default'],type:'exclusive',trigger:'True'},
  {group_ids:['a'],trigger:'True'},
  {group_ids:['a'],type:'exclusive',trigger:'True'},
  {group_ids:['a'],type:'exclusive',trigger:'True'},
  {group_ids:['b'],trigger:'False'},
 ]
 configure?.(workspace)
 const compiled=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(compiled)
 config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(compiled,state)
 return {workspace,state,controller,source:getMowerSourceRuntime(state)}
}
describe('backup group runtime',()=>{
 it('shares a backup across only its listed groups',()=>{
  const f=fixture(workspace=>{(workspace.compatibility.backupPlans[0] as Record<string,unknown>).group_ids=['a','b']})
  const data=f.source.data
  data.operators.char_123_fang!.currentRoom=''
  f.controller.evaluate('END')
  expect(f.source.data.backupGroup).toBe('b')
  expect(f.controller.active[0]).toBe(true)
  f.source.data.backupGroup='default'
  f.source.data.operators.char_123_fang!.currentRoom='room_1_1';f.source.data.operators.char_123_fang!.currentIndex=0
  expect(f.state.mowerShiftModel!.select!(f.source.data).conditions[0]).toBe(true)
 })
 it('uses the default exclusive only when all custom conditions are false',()=>{
  const f=fixture(workspace=>{workspace.compatibility.unrecognizedFields.backup_groups=[{id:'a',name:'A',trigger:'False'},{id:'b',name:'B',trigger:'False'}]})
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([true,true,false,false,false,false])
  expect(f.source.data.backupGroup).toBe('default')
 })
 it('evaluates group-only inventory conditions for observation wakeups',()=>{
  const f=fixture(workspace=>{workspace.compatibility.unrecognizedFields.backup_groups=[{id:'a',name:'A',trigger:"op_data.inventory_count('赤金') > 0"},{id:'b',name:'B',trigger:'False'}]})
  expect(f.state.mowerBackupObservationWakeMicros).toBeTypeOf('function')
 })
 it('uses group priority without inferring selection from enabled backups',()=>{
  const f=fixture(),data=f.source.data,op=data.operators.char_123_fang!
  op.currentRoom='';op.currentIndex=-1
  f.controller.evaluate('END')
  expect(f.controller.active).toEqual([false,false,false,false,false,false])
  expect(f.source.data.backupGroup).toBe('b')
  f.source.data.operators.char_123_fang!.currentRoom='room_1_1';f.source.data.operators.char_123_fang!.currentIndex=0
  f.controller.evaluate('END')
  expect(f.source.data.backupGroup).toBe('a')
  expect(f.controller.active).toEqual([false,false,true,true,false,false])
 })
 it('keeps the active exclusive even when an earlier one is eligible',()=>{
  const f=fixture(),data=f.source.data
  data.backupGroup='a';data.planConditions=[false,false,true,false,true,false]
  data.operators.char_123_fang!.currentRoom='room_1_1'
  data.operators.char_123_fang!.currentIndex=0
  const selected=f.state.mowerShiftModel!.select!(data)
  expect(selected).toEqual({groupId:'a',conditions:[false,false,true,false,true,false]})
 })
 it('keeps projected group selection isolated until activation',()=>{
  const f=fixture(),task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['char_240_wyvern']}})
  f.source.data.operators.char_123_fang!.currentRoom='room_1_1'
  f.source.data.operators.char_123_fang!.currentIndex=0
  prepareMowerShiftBackup(f.source.data,task,f.state.mowerShiftModel!)
  expect(task.backupGroup).toBe('b')
  expect(f.source.data.backupGroup).toBe('default')
  f.state.mowerShiftModel!.activate(task.backupShiftConditions!,task)
  expect(f.source.data.backupGroup).toBe('b')
 })
 it('roundtrips groups and types through calculator JSON export',()=>{
  const f=fixture(),json=exportMowerJson(f.workspace)
  const imported=importMowerJson(json)
  expect(imported.compatibility.unrecognizedFields.backup_groups).toEqual(f.workspace.compatibility.unrecognizedFields.backup_groups)
  expect(imported.compatibility.backupPlans).toEqual(f.workspace.compatibility.backupPlans)
 })
})


describe('concurrent groups and exclusions',()=>{
 const concurrent=(workspace:ReturnType<typeof createDefaultWorkspace>)=>{
  workspace.compatibility.unrecognizedFields.backup_groups=[
   {id:'a',name:'A',trigger:'True',exclusive_with:[]},
   {id:'b',name:'B',trigger:'True',exclusive_with:[]},
  ]
  const last=workspace.compatibility.backupPlans[5] as Record<string,unknown>
  last.type='exclusive';last.trigger='True'
 }
 it('selects independent exclusive backups and converges unchanged observations',()=>{
  const f=fixture(concurrent)
  f.controller.evaluate('END')
  expect(f.source.data.backupGroup).toEqual(['a','b'])
  expect(f.controller.active).toEqual([false,false,true,true,false,true])
  expect(f.controller.evaluate('END')).toBe(false)
  expect(f.controller.evaluate('END')).toBe(false)
 })
 it('preserves shared exclusive slots and retained independent choices',()=>{
  const f=fixture(workspace=>{
   concurrent(workspace)
   const shared=workspace.compatibility.backupPlans[3] as Record<string,unknown>
   shared.group_ids=['a','b']
  })
  const model=f.state.mowerShiftModel!,data=f.source.data
  expect(model.select!(data).conditions).toEqual([false,false,true,true,false,false])
  data.planConditions=[false,false,true,false,true,true]
  expect(model.select!(data).conditions).toEqual([false,false,true,false,true,true])
 })
 it('keeps concurrent group projection isolated until activation',()=>{
  const f=fixture(concurrent),task=new MowerTask({type:T.SELF_CORRECTION,plan:{room_1_1:['char_123_fang']}})
  f.source.data.operators.char_123_fang!.currentRoom='room_1_1'
  f.source.data.operators.char_123_fang!.currentIndex=0
  prepareMowerShiftBackup(f.source.data,task,f.state.mowerShiftModel!)
  expect(task.backupGroup).toEqual(['a','b'])
  expect(f.source.data.backupGroup).toBe('default')
  f.state.mowerShiftModel!.activate(task.backupShiftConditions!,task)
  expect(f.source.data.backupGroup).toEqual(['a','b'])
  expect(f.controller.evaluate('END')).toBe(false)
 })
 it('normalizes exclusions symmetrically without changing the imported source',()=>{
  const source=[{id:'a',name:'A',exclusive_with:['b']},{id:'b',name:'B',exclusive_with:[]},{id:'c',name:'C',exclusive_with:[]}]
  const before=structuredClone(source),normalized=normalizeBackupGroups(source)
  expect(source).toEqual(before)
  expect(normalized.map(group=>group.exclusive_with)).toEqual([[],['b'],['a'],[]])
  expect(normalizeBackupGroups(normalized)).toEqual(normalized)
  expect(sameBackupGroups(['a','b'],['a','b'])).toBe(true)
 })
 it('uses only accepted groups to block later groups and respects priority',()=>{
  const f=fixture(workspace=>{
   concurrent(workspace)
   workspace.compatibility.unrecognizedFields.backup_groups=[
    {id:'a',name:'A',trigger:'True',exclusive_with:['b']},
    {id:'b',name:'B',trigger:'True',exclusive_with:['c']},
    {id:'c',name:'C',trigger:'True',exclusive_with:[]},
   ]
   workspace.compatibility.backupPlans.push({group_ids:['c'],type:'exclusive',trigger:'True'})
  })
  f.controller.evaluate('END')
  expect(f.source.data.backupGroup).toEqual(['a','c'])
  expect(f.controller.active).toEqual([false,false,true,true,false,false,true])
 })
 it.each([
  {groups:[{id:'a',name:'A',exclusive_with:['missing']}]},
  {groups:[{id:'a',name:'A',exclusive_with:['a']}]},
  {groups:[{id:'a',name:'A',exclusive_with:null}]},
  {groups:[{id:'a',name:'A',exclusive_with:['default']},{id:'default',name:'Default',exclusive_with:[]}]},
 ])('rejects invalid saved exclusions %#',({groups})=>{
  expect(()=>normalizeBackupGroups(groups)).toThrow()
 })
 it('defaults new groups to true while preserving legacy and explicitly empty conditions',()=>{
  const groups=normalizeBackupGroups([
   {id:'new',name:'New',exclusive_with:[]},
   {id:'legacy',name:'Legacy'},
   {id:'empty',name:'Empty',exclusive_with:[],trigger:{}},
  ])
  expect(groups.map(group=>group.trigger)).toEqual([{},{left:'True',operator:'',right:''},{},{}])
 })
})
