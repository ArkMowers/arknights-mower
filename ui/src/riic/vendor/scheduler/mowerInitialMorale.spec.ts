import {describe,expect,it} from 'vitest'
import {advanceRoster,createRosterRuntime,nextRosterEventHours,settleRoster,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,makeMowerSchedulingData} from './mowerSourceRuntime'
import {createBackupPlanController} from './backupPlans'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createDefaultWorkspace} from '../workbench/defaults'
import {OPERATOR_MAP} from '../domain/operators'

const fia=[...OPERATOR_MAP.values()].find(op=>op.name==='菲亚梅塔')!.charId
function fixture(name=fia):RuntimeConfig{return {positions:[{id:'dormitory_1_0',roomId:'dormitory_1',primary:name,candidates:[],dormitory:true,permanent:true},{id:'work_0',roomId:'work',primary:'A',candidates:[],permanent:true}],beds:[],initialMorale:{[name]:24,A:5},fiammetta:{operatorId:name,orderedTargets:['A']}}}
describe('Fiammetta simulation starts at 16 morale',()=>{
 it.each([fia,'菲亚梅塔'])('overrides saved and default initial morale for %s without changing other workers',name=>{
  for(const configured of [undefined,0,12,24]){
   const config=fixture(name);if(configured===undefined)delete config.initialMorale![name];else config.initialMorale![name]=configured
   const state=createRosterRuntime(config)
   expect(state.morale[name]).toBe(16);expect(state.initialMorale![name]).toBe(16);expect(state.morale.A).toBe(5)
   expect(config.initialMorale?.[name]).toBe(configured)
  }
 })
 it('charges first after eight mood recovers and keeps the subsequent transferred value',()=>{
  const state=createRosterRuntime(fixture()),rates={workRate:()=>0,recoveryRate:()=>2}
  settleRoster(state,rates);expect(state.events.filter(e=>e.type==='fiammetta')).toEqual([])
  expect(nextRosterEventHours(state,rates)).toBe(4)
  advanceRoster(state,4,rates);settleRoster(state,rates)
  expect(state.events.find(e=>e.type==='fiammetta')?.time).toBe(4)
  expect(state.morale[fia]).toBe(5);expect(state.morale.A).toBe(24);expect(state.initialMorale![fia]).toBe(16)
 })
 it('does not restore full morale or restart at sixteen during source reconstruction',()=>{
  const config=fixture();config.mowerAlpha=true;config.mowerPolicy={restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]};config.mowerInitialMorale={fromUpperLimit:true,explicitOperators:[]}
  config.mowerSourcePlan={dormitory_1:[{agent:fia,group:'',replacement:['A']}],work:[{agent:'A',group:'',replacement:[]}]};config.mowerSourceRules={workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0}
  const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
  expect(state.morale[fia]).toBe(16)
  state.morale[fia]=21;state.time=2;makeMowerSchedulingData(state,source)
  expect(state.morale[fia]).toBe(21);expect(state.initialMorale![fia]).toBe(16)
 })
 it('initializes an operator first referenced by a backup at sixteen and preserves it across reevaluation',()=>{
  const workspace=createDefaultWorkspace()
  workspace.compatibility.backupPlans=[{trigger:'False',plan:{dormitory_1:{plans:[{agent:'菲亚梅塔',group:'',replacement:[]}]}}}]
  const schedule=compileRosterSchedule(workspace,{operatorMorale:{[fia]:24}}),state=createRosterRuntime(compiledScheduleToRuntimeConfig(schedule))
  createBackupPlanController(schedule,state)
  expect(state.morale[fia]).toBe(16);expect(state.initialMorale![fia]).toBe(16)
  state.morale[fia]=19;createBackupPlanController(schedule,state);expect(state.morale[fia]).toBe(19)
 })
})
