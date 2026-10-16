import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-dorm-recovery-alpha.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {MowerTask,MowerTaskQueue,toMowerMicros} from './mowerTaskQueue'
import {ensureMowerDormRecovery,mowerRecoveryTarget,mowerConfirmedRecoveryTarget,mowerConfirmedRecoveryTargets,mowerRecoveryManagers} from './mowerDormRecovery'
function fixture(groupHole=false,padding='known'){
 const room='dormitory_1',fixed=['M0','M1',groupHole?'Resident':'Free','Free','Free']
 const agents=groupHole?['M0','M1','Cover','H','Q']:['M0','M1','H','R','Q'],operators:Record<string,MowerOperatorState>={}
 for(const [index,name] of agents.entries()){
  const nativeRoom=['M0','M1'].includes(name)?room:name==='H'?'room_work':''
  operators[name]=new MowerOperatorState({name,room:nativeRoom,index:nativeRoom===room?index:0,operatorType:nativeRoom?'high':'low',mood:name==='H'?8:['R','Q','Cover'].includes(name)?3:24,currentRoom:room,currentIndex:index,timeStampMicros:0})
 }
 if(groupHole){
  operators.Resident=new MowerOperatorState({name:'Resident',room,index:2,group:'g',replacement:['Cover'],operatorType:'high'})
  if(padding!=='absent')operators.Padding=new MowerOperatorState({name:'Padding',mood:24,timeStampMicros:padding==='known'?0:undefined})
 }
 operators.M0!.singleRecoveryManager=true
 const data=new MowerSchedulingData({plan:{[room]:fixed},operators,dorms:agents.flatMap((name,index)=>fixed[index]==='Free'?[new MowerDormState([room,index],name,toMowerMicros(3))]:[]),nowMicros:0})
 const task=new MowerTask({plan:{[room]:agents}}),queue=new MowerTaskQueue(),trace:{intermediate:string[]}[]=[]
 queue.tasks.push(task)
 let physical=[...data.currentRoom(room,true)!]
 const observe=()=>{
  for(const op of Object.values(operators))if(op.currentRoom===room&&!physical.includes(op.name)){op.currentRoom='';op.currentIndex=-1}
  for(const [index,name] of physical.entries())if(name){operators[name]!.currentRoom=room;operators[name]!.currentIndex=index}
 }
 const ensure=()=>ensureMowerDormRecovery(data,queue,task,room,agents,{
  arrangeTemporary:names=>{physical=[...names,...Array(fixed.length-names.length).fill('')];trace.push({intermediate:[...physical]});observe()}
 })
 const marker=()=>{const op=operators.H!;return {position:op.dormRecoveryRoom&&op.currentRoom===op.dormRecoveryRoom&&op.currentIndex===op.dormRecoveryIndex?[op.dormRecoveryRoom,op.dormRecoveryIndex]:null,fixed:op.dormRecoveryFixed,version:op.dormPositionVersion}}
 return {room,agents,data,task,queue,operators,trace,ensure,marker,restore:()=>{physical=[...agents];observe()}}
}
describe('actual alpha default dorm recovery ordering',()=>{
 it.each([false,true])('never proactively targets a single-recovery provider, sole unfinished recipient=%s',sole=>{
  const f=fixture();f.ensure();f.restore();f.operators.H!.singleRecoveryManager=true
  if(sole)for(const name of ['R','Q'])f.operators[name]!.mood=24
  f.task.dormRecoveryRestore=[];f.trace.length=0
  expect(mowerRecoveryTarget(f.data,f.room,f.agents)).toBeUndefined()
  expect(f.ensure()).toBe(false)
  expect(f.trace).toEqual([])
  expect(mowerConfirmedRecoveryTarget(f.data,f.room,'M0')).toBeUndefined()
  expect(mowerConfirmedRecoveryTargets(f.data).size).toBe(0)
 })
 it('confirms a fourth-slot manager and keeps only the first provider in the confirmation',()=>{
  const f=fixture();f.operators.M0!.singleRecoveryManager=false
  const manager=new MowerOperatorState({name:'琴柳',room:f.room,index:3,currentRoom:f.room,currentIndex:3,operatorType:'high',mood:12,timeStampMicros:0,singleRecoveryManager:true})
  delete f.operators.R;f.operators['琴柳']=manager;f.agents[3]='琴柳';f.data.plan[f.room]![3]='琴柳'
  f.operators.Q!.singleRecoveryManager=true
  expect(f.ensure()).toBe(true)
  expect(f.marker().fixed).toEqual([['琴柳',3,2]])
  expect(f.trace).toEqual([{intermediate:['M0','M1','H','琴柳','']}])
  f.restore()
  expect(mowerConfirmedRecoveryTargets(f.data).get(f.room)).toEqual(new Map([['琴柳','H']]))
  expect(mowerConfirmedRecoveryTarget(f.data,f.room,'Q')).toBeUndefined()
 })
 it('selects only the earlier of two providers even when both occupy the first two slots',()=>{
  const f=fixture();f.operators.M1!.singleRecoveryManager=true
  expect(f.ensure()).toBe(true)
  expect(f.marker().fixed).toEqual([['M0',0,2]])
  f.restore()
  expect(mowerConfirmedRecoveryTargets(f.data).get(f.room)).toEqual(new Map([['M0','H']]))
 })
 it('skips the selected provider in a recovery bed and confirms the next eligible resident',()=>{
  const f=fixture();f.operators.M0!.singleRecoveryManager=false;f.operators.H!.singleRecoveryManager=true
  expect(mowerRecoveryTarget(f.data,f.room,f.agents)?.name).toBe('R')
  expect(f.ensure()).toBe(true)
  expect(f.operators.R!.dormRecoveryFixed).toEqual([['H',2,2]])
  expect(f.operators.H!.dormRecoveryRoom).toBe('')
 })
 it('keeps a fifth-slot manager at its final position while filling the temporary gap',()=>{
  const f=fixture();f.operators.M0!.singleRecoveryManager=false;f.operators.Q!.singleRecoveryManager=true
  f.operators.Padding=new MowerOperatorState({name:'Padding',mood:24,timeStampMicros:0})
  expect(f.ensure()).toBe(true)
  expect(f.marker().fixed).toEqual([['Q',4,2]])
  expect(f.trace).toEqual([{intermediate:['M0','M1','H','Padding','Q']}])
 })
 it('does not recognize a manager from an incomplete final roster',()=>{
  const f=fixture()
  expect(mowerRecoveryManagers(f.data,f.room,f.agents.slice(0,4))).toEqual([])
 })
 it('matches establishing, reusing and manager-away-and-back native markers',()=>{
  const f=fixture(),cases=oracle.cases
  expect({ordered:f.ensure(),marker:f.marker(),pending:f.task.dormRecoveryRestore,intermediate:f.trace,bedTimerCleared:f.data.getDormByName('H')![1].timeMicros===undefined}).toEqual(cases[0]!.output)
  f.restore();f.task.dormRecoveryRestore=[]
  expect({ordered:f.ensure(),marker:f.marker()}).toEqual(cases[1]!.output)
  const manager=f.operators.M0!;manager.currentRoom='';manager.currentIndex=-1;manager.currentRoom=f.room;manager.currentIndex=0
  expect({ordered:f.ensure(),marker:f.marker()}).toEqual(cases[2]!.output)
 })
 for(const [index,label] of ['no-manager','manager-only-index3','target-full-cached','target-static-native-dorm','upcoming-vip-overwrite'].entries())it(label,()=>{
  const f=fixture()
  if(label==='no-manager')f.operators.M0!.singleRecoveryManager=false
  if(label==='manager-only-index3'){
   f.operators.M0!.singleRecoveryManager=false;f.operators.R!.singleRecoveryManager=true
   expect(f.ensure()).toBe(true)
   expect(f.marker().fixed).toEqual([['R',3,2]])
   expect(f.trace).toEqual([{intermediate:['M0','M1','H','R','']}])
   return
  }
  if(label==='target-full-cached')f.operators.H!.mood=24
  if(label==='target-static-native-dorm')f.operators.H!.room=f.room
  if(label==='upcoming-vip-overwrite')f.queue.tasks.push(new MowerTask({time:.5/3600,plan:{[f.room]:['Current','Current','Other','Current','Current']}}))
  expect({ordered:f.ensure(),marker:f.marker(),intermediate:f.trace}).toEqual(oracle.cases[index+3]!.output)
 })
 for(const [index,padding] of ['known','unknown','absent'].entries())it('group cover hole '+padding,()=>{
  const f=fixture(true,padding)
  expect({ordered:f.ensure(),marker:f.marker(),intermediate:f.trace}).toEqual(oracle.cases[index+8]!.output)
 })
 it('keeps the full task array and reuses pending recovery after UI observation retry',()=>{
  const f=fixture(),before=[...f.agents];expect(f.ensure()).toBe(true);expect(f.agents).toEqual(before)
  f.operators.H!.mood=24;expect(f.ensure()).toBe(true)
 })
 it('requires actual target and manager coordinates and movement version for confirmed physical targeting',()=>{
  const f=fixture();f.ensure();f.restore()
  expect(mowerConfirmedRecoveryTarget(f.data,'dormitory_1','M0')).toBe('H')
  expect(mowerConfirmedRecoveryTargets(f.data).get('dormitory_1')?.get('M0')).toBe('H')
  f.operators.M0!.currentIndex=1
  expect(mowerConfirmedRecoveryTarget(f.data,'dormitory_1','M0')).toBeUndefined()
  expect(mowerConfirmedRecoveryTargets(f.data).get('dormitory_1')?.get('M0')).toBeUndefined()
  expect(mowerRecoveryTarget(f.data,'dormitory_1',f.agents)?.name).toBe('H')
 })
})
