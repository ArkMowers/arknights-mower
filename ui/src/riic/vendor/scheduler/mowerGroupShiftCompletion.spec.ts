import {describe,expect,it} from 'vitest'
import {createRosterRuntime,type RuntimeConfig} from './rosterRuntime'
import {getMowerSourceRuntime,settleMowerSource} from './mowerSourceRuntime'
import {executeMowerTaskArrangementSteps} from './mowerTaskExecutor'
import {MowerTask,MowerTaskQueue,MOWER_TASK_TYPES as T} from './mowerTaskQueue'

const rates={workRate:()=>0,recoveryRate:()=>4}
function fixture(returning=false){
 const config:RuntimeConfig={mowerAlpha:true,positions:[{id:'room_1_1_0',roomId:'room_1_1',primary:'A',candidates:['R']}],
 beds:[{id:'dormitory_1_0',roomId:'dormitory_1',vip:true,managedRecovery:true}],
 mowerSourcePlan:{room_1_1:[{agent:'A',group:'g',replacement:['R']}],dormitory_1:[{agent:'M',group:'g',replacement:['Free']}]},
 mowerSourceRules:{workaholic:[],exhaustRequire:[],restInFull:[],lowPriority:[],refreshDrained:[],lingMode:0},
 mowerPolicy:{restingThreshold:.65,powerPlantCount:2,opeRestingPriority:[]},initialMorale:{A:returning?24:5,R:24,M:24}}
 const state=createRosterRuntime(config),source=getMowerSourceRuntime(state)
 source.initial=false;source.firstInit=false
 for(const op of Object.values(source.data.operators)){op.setProjectedPosition('',-1);op.timeStampMicros=0}
 source.data.operators.A!.setProjectedPosition(returning?'dormitory_1':'room_1_1',0)
 if(returning)source.data.operators.R!.setProjectedPosition('room_1_1',0)
 else source.data.operators.M!.setProjectedPosition('dormitory_1',0)
 source.data.groupShiftState.g=returning
 source.data.dorms[0]!.name=returning?'A':''
 source.data.dorms[0]!.timeMicros=returning?0:undefined
 state.occupants={room_1_1_0:returning?'R':'A'};state.bedOccupants={dormitory_1_0:returning?'A':'M'}
 const task=new MowerTask({type:returning?T.SHIFT_ON:T.SHIFT_OFF,plan:{room_1_1:[returning?'A':'R'],dormitory_1:[returning?'M':'A']}})
 task.backupShiftActive=true;task.groupShiftTransitions={g:!returning};source.queue.tasks=[task]
 return {state,source,task}
}

describe('completed group arrangements precede post-shift planning',()=>{
 it.each([false,true])('commits unfinished group recovery before the backup and correction branch; backup changed=%s',changed=>{
  const {state,source}=fixture(),observed:boolean[]=[],corrections:Record<string,string[]>[]=[]
  settleMowerSource(state,rates,phase=>{
   if(phase==='BEGINNING'&&source.activeTask?.derivedCorrection)corrections.push(structuredClone(source.activeTask.plan))
   if(phase!=='BEFORE_PLANNING')return false
   observed.push(source.data.groupIsResting('g'))
   if(changed)state.mowerBackupGenerated=[new MowerTask()]
   return changed
  })
  expect(observed[0]).toBe(true)
  expect(corrections.flatMap(plan=>Object.values(plan).flat())).not.toContain('M')
  expect(state.bedOccupants.dormitory_1_0).toBe('A')
  expect(state.occupants.room_1_1_0).toBe('R')
  expect(source.data.operators.A!.mood).toBe(5)
  expect(source.data.groupIsResting('g')).toBe(true)
 })
 it('still restores the fixed dorm primary when the recovered group returns',()=>{
  const {state,source}=fixture(true),observed:boolean[]=[]
  settleMowerSource(state,rates,phase=>{
   if(phase!=='BEFORE_PLANNING')return false
   observed.push(source.data.groupIsResting('g'));state.mowerBackupGenerated=[new MowerTask()];return true
  })
  expect(observed[0]).toBe(false)
  expect(state.occupants.room_1_1_0).toBe('A')
  expect(state.bedOccupants.dormitory_1_0).toBe('M')
  expect(source.data.groupIsResting('g')).toBe(false)
 })
 it.each(['yield','defer','failure'] as const)('does not complete group state while the arrangement is unfinished: %s',kind=>{
  const task=new MowerTask({type:T.SHIFT_OFF,plan:{room_1_1:['R'],dormitory_1:['A']}}),queue=new MowerTaskQueue(),calls:string[]=[]
  queue.tasks=[task]
  const steps=executeMowerTaskArrangementSteps(task,queue,{
   alpha:true,protectShift:true,backup:phase=>{calls.push(phase);return {changed:false,generated:[]}},
   arrangeRoom:room=>{if(room==='dormitory_1'&&kind==='failure')throw new Error('readback failed')},
   deferRoom:room=>room==='dormitory_1'&&kind==='defer',
   completeGroupShift:()=>{calls.push('complete')},metadata:()=>{calls.push('metadata')},
  })
  expect(steps.next().done).toBe(false)
  expect(calls).not.toContain('complete')
  if(kind==='defer')expect(steps.next()).toEqual({done:true,value:false})
  if(kind==='failure')expect(()=>steps.next()).toThrow('readback failed')
  expect(calls).not.toContain('complete')
  expect(calls).not.toContain('BEFORE_PLANNING')
 })
})
