import {describe,expect,it} from 'vitest'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {alphaRebalanceDorms} from './mowerAlphaDorm'
import {normalizeMowerSharedArrangement} from './mowerSharedGroups'
import {projectMowerArrangements} from './mowerObservations'
import {createDefaultWorkspace} from '../workbench/defaults'
import {resolveOperatorCharId as id} from '../domain/operatorIdentifiers'
import {compileRosterSchedule} from './compileRosterSchedule'
import {compiledScheduleToRuntimeConfig} from './scheduleAdapter'
import {createRosterRuntime} from './rosterRuntime'
import {createBackupPlanController} from './backupPlans'
import {getMowerSourceRuntime} from './mowerSourceRuntime'
import {toMowerMicros} from './mowerTaskQueue'

function fixture(mood=5){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,index,currentRoom,currentIndex,group,replacement] of [
  ['A','central',0,'dormitory_2',0,'g',['R']],
  ['B','room_1_1',0,'dormitory_1',0,'g',['S']],
  ['F','dormitory_1',0,'',-1,'g',['B']],
  ['Z','meeting',0,'',-1,'g',[]],
  ['R','',-1,'central',0,'',[]],
  ['S','',-1,'room_1_1',0,'',[]],
 ] as [string,string,number,string,number,string,string[]][]){
  operators[name]=new MowerOperatorState({name,room,index,currentRoom,currentIndex,group,replacement,mood:name==='B'?mood:12,timeStampMicros:0,operatorType:room?'high':'low'})
 }
 const data=new MowerSchedulingData({alpha:true,operators,plan:{central:['A'],room_1_1:['B'],meeting:['Z'],dormitory_1:['F','Free','Free'],dormitory_2:['Free']},dorms:[new MowerDormState(['dormitory_1',1]),new MowerDormState(['dormitory_1',2]),new MowerDormState(['dormitory_2',0],'A',toMowerMicros(3))],groupShiftState:{g:true},nowMicros:0})
 const bed=data.groupDorms[0]!
 bed.name='B';bed.timeMicros=toMowerMicros(2)
 return {data,bed}
}
function snapshot(data:MowerSchedulingData){return data.allDorms().map(b=>new MowerDormState([...b.position],b.name,b.timeMicros,b.autoFree))}

describe('fixed working covers during ordinary dorm migration',()=>{
 it.each([5,24])('preserves the actual cover and its recovery deadline at mood %s',mood=>{
  const {data,bed}=fixture(mood),deadline=bed.timeMicros
  const plan=alphaRebalanceDorms(data,snapshot(data))
  expect(normalizeMowerSharedArrangement(data,plan,{g:true})).toBe(true)
  const after=projectMowerArrangements(data,[plan])
  expect(after.currentOperator('dormitory_1',0)?.name).toBe('B')
  expect(after.operators.F!.currentRoom).toBe('')
  expect(after.getDormByName('B')?.[1].timeMicros).toBe(deadline)
  expect(bed.timeMicros).toBe(deadline)
  expect(Object.values(plan).flat()).not.toContain('B')
 })

 it.each(['','Z'])('uses the actual cover when the bed cache contains %j',cached=>{
  const {data,bed}=fixture(),previous=snapshot(data)
  bed.name=cached
  const plan=alphaRebalanceDorms(data,previous)
  expect(projectMowerArrangements(data,[plan]).currentOperator('dormitory_1',0)?.name).toBe('B')
  expect(Object.values(plan).flat()).not.toContain('B')
 })

 it('migrates a former cover after its configured replacement eligibility changes',()=>{
  const {data,bed}=fixture(),previous=snapshot(data)
  data.operators.F!.replacement=['Z']
  expect(data.recoveryDorm(bed,'B')).toBe(false)
  const plan=alphaRebalanceDorms(data,previous)
  expect(normalizeMowerSharedArrangement(data,plan,{g:true})).toBe(true)
  const after=projectMowerArrangements(data,[plan])
  expect(after.currentOperator('dormitory_1',0)?.name).not.toBe('B')
  expect(after.operators.B!.isResting()).toBe(true)
  expect(after.operators.B!.currentIndex).not.toBe(0)
 })

 it('does not reserve an ineligible actual resident solely because the slot is a group bed',()=>{
  const {data,bed}=fixture()
  data.operators.B!.currentRoom='';data.operators.B!.currentIndex=-1
  data.operators.Z!.currentRoom='dormitory_1';data.operators.Z!.currentIndex=0
  bed.name='Z'
  const plan=alphaRebalanceDorms(data,snapshot(data))
  expect(normalizeMowerSharedArrangement(data,plan,{g:true})).toBe(true)
  const after=projectMowerArrangements(data,[plan])
  expect(after.currentOperator('dormitory_1',0)?.name).not.toBe('Z')
  expect(after.operators.Z!.isResting()).toBe(true)
  expect(after.operators.Z!.currentIndex).not.toBe(0)
 })

 it('migrates a former resident when only its old cache still names the fixed bed',()=>{
  const {data}=fixture(),previous=snapshot(data)
  data.operators.B!.currentRoom='';data.operators.B!.currentIndex=-1
  const after=projectMowerArrangements(data,[alphaRebalanceDorms(data,previous)])
  expect(after.currentOperator('dormitory_1',0)?.name).not.toBe('B')
  expect(after.operators.B!.isResting()).toBe(true)
  expect(after.operators.B!.currentIndex).not.toBe(0)
 })

 it('preserves a new legal fixed cover while migrating the former cached resident',()=>{
  const {data}=fixture(),previous=snapshot(data)
  data.operators.F!.replacement=['B','Z']
  data.operators.B!.currentRoom='';data.operators.B!.currentIndex=-1
  data.operators.Z!.currentRoom='dormitory_1';data.operators.Z!.currentIndex=0
  const after=projectMowerArrangements(data,[alphaRebalanceDorms(data,previous)])
  expect(after.currentOperator('dormitory_1',0)?.name).toBe('Z')
  expect(after.operators.B!.isResting()).toBe(true)
  expect(after.operators.B!.currentIndex).not.toBe(0)
 })

 it('does not keep an obsolete source reservation after a complete explicit return',()=>{
  const {data}=fixture(),previous=snapshot(data)
  const returned=projectMowerArrangements(data,[{central:['A'],room_1_1:['B'],dormitory_1:['F','Current','Current']}])
  const migration=alphaRebalanceDorms(returned,previous,new Set(['A','B','F']))
  const after=projectMowerArrangements(returned,[migration])
  expect(after.currentOperator('central',0)?.name).toBe('A')
  expect(after.currentOperator('room_1_1',0)?.name).toBe('B')
  expect(after.currentOperator('dormitory_1',0)?.name).toBe('F')
 })
})

it('keeps an existing recovery occupant when a backup makes it a fixed working cover',()=>{
 const workspace=createDefaultWorkspace()
 for(const room of Object.values(workspace.mainPlan.facilities))room.slots=[]
 const slot=(name:string,group='',cover='')=>({occupant:{kind:'operator' as const,operatorId:id(name)},groupId:group||null,replacements:cover?[cover==='Free'?'Free':id(cover)]:[]})
 const free=()=>({occupant:{kind:'free' as const},groupId:null,replacements:[]})
 workspace.mainPlan.facilities.central.slots=[slot('芬','g','香草')]
 workspace.mainPlan.facilities.room_1_1.slots=[{...slot('断罪者','g','克洛丝'),groupBindings:[{groupId:'h',replacements:[id('克洛丝')]}]}]
 workspace.mainPlan.facilities.room_1_2.slots=[slot('翎羽','h','空爆')]
 workspace.mainPlan.facilities.dormitory_1.slots=[{...slot('琴柳','g','Free'),groupBindings:[{groupId:'h',replacements:['Free']}]},slot('杜林'),free(),free(),free()]
 workspace.mainPlan.facilities.dormitory_2.slots=[slot('桃金娘','g','Free'),slot('流明'),free(),free(),free()]
 workspace.compatibility.backupPlans=[{trigger:"op_data.inventory_count('赤金') >= 10",plan:{dormitory_1:{plans:[{agent:'琴柳',group:'g',replacement:['断罪者'],group_bindings:[{group:'h',replacement:['断罪者']}]},{agent:'Current'},{agent:'Current'},{agent:'Current'},{agent:'Current'}]}}}]
 const schedule=compileRosterSchedule(workspace),config=compiledScheduleToRuntimeConfig(schedule)
 config.mowerAlpha=true
 const state=createRosterRuntime(config),controller=createBackupPlanController(schedule,state),source=getMowerSourceRuntime(state)
 for(const op of Object.values(source.data.operators)){op.currentRoom=op.room;op.currentIndex=op.index;op.mood=24;op.timeStampMicros=0}
 Object.assign(source.data.operators[id('琴柳')]!,{currentRoom:'',currentIndex:-1})
 Object.assign(source.data.operators[id('芬')]!,{currentRoom:'dormitory_2',currentIndex:2,mood:5})
 Object.assign(source.data.operators[id('断罪者')]!,{currentRoom:'dormitory_1',currentIndex:0,mood:6})
 Object.assign(source.data.operators[id('香草')]!,{currentRoom:'central',currentIndex:0})
 Object.assign(source.data.operators[id('克洛丝')]!,{currentRoom:'room_1_1',currentIndex:0})
 source.data.groupShiftState={g:true,h:false}
 const coverBed=source.data.getDormByName(id('断罪者'))![1]
 coverBed.name=id('断罪者');coverBed.timeMicros=toMowerMicros(2)
 const anchorBed=source.data.getDormByName(id('芬'))![1]
 anchorBed.name=id('芬');anchorBed.timeMicros=toMowerMicros(3)
 state.mowerInventoryCounts={赤金:10}
 controller.evaluate('END')
 expect(controller.active).toEqual([true])
 const final=projectMowerArrangements(source.data,(state.mowerBackupGenerated??[]).map(task=>task.plan))
 expect(final.currentOperator('dormitory_1',0)?.name).toBe(id('断罪者'))
 expect(final.operators[id('琴柳')]!.currentRoom).toBe('')
 expect(coverBed.timeMicros).toBe(toMowerMicros(2))
})
