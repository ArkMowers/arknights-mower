import {expect,it} from 'vitest'
import {MowerOperatorState,restingThresholdFor} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerResting,mowerTryReorder,mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {mowerArrangementGroupTransitions,commitMowerGroupShifts} from './mowerSharedGroups'
import {projectMowerArrangements} from './mowerObservations'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'
import {MowerTaskQueue,toMowerMicros,type MowerTaskPlan} from './mowerTaskQueue'
import {mowerRecallMoodAdmissible,planMowerReplacementHandoff} from './mowerReplacementCoordination'

function fixture(extraEmpty=false,onlyEmpty=false,sameCover=false){
 const operators:Record<string,MowerOperatorState>={}
 for(const [name,room,group,replacement] of [['A','meeting','a',['F']],['F','contact','a',[sameCover?'Y':'X']]] as [string,string,string,string[]][]){
  operators[name]=new MowerOperatorState({name,room,index:0,group,replacement,operatorType:'high',restingPriority:'high',currentRoom:room,currentIndex:0,mood:24,timeStampMicros:0})
 }
 operators.F!.groupBindings=[{group:'a',replacement:[sameCover?'Y':'X']},{group:onlyEmpty?'':'b',replacement:['Y']},...(extraEmpty?[{group:'',replacement:['Z']}]:[])]
 for(const name of ['X','Y','Z'])operators[name]=new MowerOperatorState({name})
 return new MowerSchedulingData({alpha:true,plan:{meeting:['A'],contact:['F'],dormitory_1:Array(5).fill('Free')},operators,dorms:[0,1,2,3,4].map(index=>new MowerDormState(['dormitory_1',index])),nowMicros:0,policy:{groupRestingThresholds:{b:.8}}})
}

it('assigns the unique named resting group independently of the active working swap',()=>{
 const data=fixture(),op=data.operators.F!
 expect(op.group).toBe('b');expect(data.isGroupShiftAnchor(op,'b')).toBe(true);expect(data.isGroupShiftAnchor(op,'a')).toBe(false)
 expect(restingThresholdFor(op,data.policy)).toBe(.8)
 commitMowerGroupShifts(data,{a:true})
 expect(op.group).toBe('b');expect(op.replacement).toEqual(['Y'])
 const projected=projectMowerArrangements(data,[])
 expect(projected.operators.F!.shiftGroup).toBe('b');expect(projected.operators.F).not.toBe(op)
})

it('uses the unique resting primary for ordinary departure and return timing',()=>{
 let data=fixture();data.operators.F!.mood=0
 const queue=new MowerTaskQueue(),plan=mowerResting(data,queue)
 expect(plan.contact).toEqual(['Y']);expect(mowerArrangementGroupTransitions(data,plan)).toEqual({b:true})
 const beds=mowerTryReorder(data,plan)
 data=projectMowerArrangements(data,[plan,...(beds?[beds]:[])])
 const bed=data.getDormByName('F')?.[1];expect(bed).toBeDefined();bed!.timeMicros=toMowerMicros(2)
 const returning=new MowerTaskQueue();planMowerAlphaMetadata(data,returning,[])
 expect(returning.tasks.some(task=>task.plan.contact?.[0]==='F')).toBe(true)
})

for(const sameCover of [false,true])it(`keeps working swaps separate from normal off-shift requests (${sameCover})`,()=>{
 const data=fixture(false,false,sameCover);data.operators.A!.mood=0
 const plan=mowerResting(data,new MowerTaskQueue())
 expect(plan.meeting).toEqual(['F']);expect(plan.contact).toEqual([sameCover?'Y':'X'])
 expect(mowerArrangementGroupTransitions(data,plan)).toEqual({a:true})
 const projected=projectMowerArrangements(data,[plan])
 expect(projected.operators.F!.currentRoom).toBe('meeting');expect(projected.groupIsResting('b')).toBe(false)
})

it('counts an empty binding when deciding whether a named group has a mood anchor',()=>{
 const data=fixture(true)
 expect(data.operators.F!.group).toBe('');expect(data.isGroupShiftAnchor(data.operators.F!,'b')).toBe(false)
})

it('supports an empty binding as the only normal resting group',()=>{
 const data=fixture(false,true);data.operators.F!.mood=0
 expect(data.operators.F!.group).toBe('');expect(data.operators.F!.shiftGroup).toBe('')
 const plan=mowerResting(data,new MowerTaskQueue())
 expect(plan.contact).toEqual(['Y']);expect(mowerArrangementGroupTransitions(data,plan)).toEqual({})
})

it('allows an individually resting primary to cover another working group',()=>{
 let data=fixture(false,true)
 data=projectMowerArrangements(data,[{contact:['Y'],dormitory_1:['F','Free','Free','Free','Free']}])
 data.operators.F!.mood=10;data.getDormByName('F')![1].timeMicros=toMowerMicros(4);data.operators.A!.mood=0
 const plan=mowerResting(data,new MowerTaskQueue())
 expect(plan.meeting).toEqual(['F']);expect(plan.contact).toEqual(['X'])
 data=projectMowerArrangements(data,[plan])
 expect(data.operators.F!.currentRoom).toBe('meeting');expect(data.getDormByName('F')).toBeUndefined()
})

it('retains a unique normal departure until its other working cover is released',()=>{
 let data=fixture();data.operators.A!.mood=0
 const first=mowerResting(data,new MowerTaskQueue()),beds=mowerTryReorder(data,first)
 data=projectMowerArrangements(data,[first,...(beds?[beds]:[])])
 data.operators.F!.mood=0
 for(let n=0;n<2;n++){
  const plan={}
  expect(mowerGetRestingPlan(data,['F'],[],plan)).toBe(false);expect(plan).toEqual({})
  expect(data.groupIsResting('b')).toBe(false)
 }
 data=projectMowerArrangements(data,[{meeting:['A'],contact:['F']}])
 const plan={}
 expect(mowerGetRestingPlan(data,['F'],[],plan)).toBe(true)
 expect(mowerArrangementGroupTransitions(data,plan)).toEqual({b:true})
})

for(const role of ['ordinary','low','standby','workaholic'] as const)for(const sameCover of [false,true])it(`keeps working swaps independent of the covered primary recovery role (${role}, ${sameCover})`,()=>{
 const data=fixture(false,false,sameCover)
 const owner=data.operators.A!
 owner.restingPriority=role==='standby'?'standby':role==='low'?'low':'high'
 owner.workaholic=role==='workaholic'
 data.operators.G=new MowerOperatorState({name:'G',room:'meeting',index:1,group:'a',replacement:['Z'],operatorType:'high',currentRoom:'meeting',currentIndex:1,mood:0,timeStampMicros:0})
 data.plan.meeting!.push('G')
 // An unrelated shared slot must not be replaced merely because F changes workstation.
 data.operators.D=new MowerOperatorState({name:'D',room:'room_1_1',index:0,group:'b',groupBindings:[{group:'b',replacement:['U']},{group:'c',replacement:['V']}],replacement:['U'],operatorType:'high',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0})
 data.operators.H=new MowerOperatorState({name:'H',room:'recycle',index:0,group:'c',replacement:['W'],operatorType:'high',currentRoom:'recycle',currentIndex:0,mood:24,timeStampMicros:0})
 for(const name of ['U','V','W'])data.operators[name]=new MowerOperatorState({name})
 data.plan.room_1_1=['D'];data.plan.recycle=['H']
 const members=data.shiftGroupMembers('a')
 expect(data.shiftRequestGroups(['G'])).toEqual(['a'])
 expect(planMowerReplacementHandoff(data,members,{requestNames:['G']})).toEqual({})
 data.operators.G!.mood=24;data.operators.F!.mood=0
 expect(mowerRecallMoodAdmissible(data,new Set(),members,['G'])).toBe(false)
 data.operators.G!.mood=0;data.operators.F!.mood=24
 const plan=mowerResting(data,new MowerTaskQueue())
 expect(plan.meeting).toEqual(['F','Z'])
 expect(plan.contact).toEqual([sameCover?'Y':'X'])
 expect(plan.room_1_1).toBeUndefined();expect(plan.recycle).toBeUndefined()
 expect(data.groupIsResting('a')).toBe(false);expect(data.groupIsResting('b')).toBe(false)
 const projected=projectMowerArrangements(data,[plan])
 expect(projected.operators.F!.currentRoom).toBe('meeting')
 expect(projected.operators.D!.currentRoom).toBe('room_1_1')
 expect(projected.groupIsResting('a')).toBe(true);expect(projected.groupIsResting('b')).toBe(false)
})

it('retains an independently requested normal group despite its primary also covering another group',()=>{
 const data=fixture();data.operators.A!.restingPriority='standby'
 data.operators.G=new MowerOperatorState({name:'G',room:'meeting',index:1,group:'a',replacement:['Z'],operatorType:'high',currentRoom:'meeting',currentIndex:1,mood:0,timeStampMicros:0})
 data.operators.B=new MowerOperatorState({name:'B',room:'recycle',index:0,group:'b',replacement:['W'],operatorType:'high',currentRoom:'recycle',currentIndex:0,mood:0,timeStampMicros:0})
 data.operators.W=new MowerOperatorState({name:'W'})
 data.plan.meeting!.push('G');data.plan.recycle=['B']
 expect(new Set(data.shiftRequestGroups([...data.shiftGroupMembers('a'),'B']))).toEqual(new Set(['a','b']))
 const plan={}
 expect(mowerGetRestingPlan(data,[...data.shiftGroupMembers('a'),'B'],[],plan)).toBe(false)
 expect(plan).toEqual({});expect(data.groupShiftState).toEqual({})
})

it('preserves the requested binding through consecutive shared working swaps',()=>{
 const data=fixture()
 data.operators.A!.replacement=['F']
 data.operators.A!.mood=0
 data.operators.F!.groupBindings=[{group:'a',replacement:['X']},{group:'b',replacement:['Y']}]
 const middle=new MowerOperatorState({name:'M',room:'meeting',index:1,group:'c',replacement:['Z'],groupBindings:[{group:'a',replacement:['F']},{group:'c',replacement:['Z']}],operatorType:'high',currentRoom:'meeting',currentIndex:1,mood:24,timeStampMicros:0})
 data.operators.A!.replacement=['M'];data.operators.M=middle;data.plan.meeting!.push('M')
 // Rebuild effective normal bindings from configuration, as startup and projections do.
 const rebuilt=new MowerSchedulingData({alpha:true,plan:data.plan,operators:data.operators,dorms:data.dorms,nowMicros:0})
 expect(rebuilt.operators.M!.group).toBe('c');expect(rebuilt.operators.F!.group).toBe('b')
 expect(rebuilt.shiftRequestGroups(['A'])).toEqual(['a'])
 const plan=mowerResting(rebuilt,new MowerTaskQueue())
 expect(plan.meeting).toEqual(['M','F']);expect(plan.contact).toEqual(['X'])
 const projected=projectMowerArrangements(rebuilt,[plan])
 expect(projected.groupIsResting('a')).toBe(true)
 expect(projected.groupIsResting('b')).toBe(false);expect(projected.groupIsResting('c')).toBe(false)
})

it('keeps an independent request after excluding an intermediate working swap group',()=>{
 const data=fixture(false,false,true)
 data.operators.F!.groupBindings=[{group:'a',replacement:['Y']},{group:'b',replacement:['M']}]
 data.operators.M=new MowerOperatorState({name:'M',room:'recycle',index:0,group:'b',replacement:['X'],groupBindings:[{group:'b',replacement:['X']},{group:'c',replacement:['Z']}],operatorType:'high',currentRoom:'recycle',currentIndex:0,mood:0,timeStampMicros:0})
 data.operators.D=new MowerOperatorState({name:'D',room:'room_1_1',index:0,group:'c',replacement:['U'],groupBindings:[{group:'c',replacement:['U']},{group:'d',replacement:['V']}],operatorType:'high',currentRoom:'room_1_1',currentIndex:0,mood:24,timeStampMicros:0})
 data.operators.H=new MowerOperatorState({name:'H',room:'room_2_1',index:0,group:'d',replacement:['W'],operatorType:'high',currentRoom:'room_2_1',currentIndex:0,mood:24,timeStampMicros:0})
 for(const name of ['U','V','W'])data.operators[name]=new MowerOperatorState({name})
 data.plan.recycle=['M'];data.plan.room_1_1=['D'];data.plan.room_2_1=['H']
 const rebuilt=new MowerSchedulingData({alpha:true,plan:data.plan,operators:data.operators,dorms:data.dorms,nowMicros:0})
 const requestNames=['A','M'],members=[...rebuilt.shiftGroupMembers('a'),'M'],plan:MowerTaskPlan={}
 expect(rebuilt.shiftRequestGroups(requestNames)).toEqual(['a','c'])
 expect(mowerGetRestingPlan(rebuilt,members,[],plan,{requestNames})).toBe(true)
 expect(plan.meeting).toEqual(['F']);expect(plan.contact).toEqual(['Y'])
 expect(plan.recycle).toEqual(['Z']);expect(plan.room_1_1).toEqual(['U'])
 const beds=mowerTryReorder(rebuilt,plan);if(beds)Object.assign(plan,beds)
 const projected=projectMowerArrangements(rebuilt,[plan])
 expect(projected.groupIsResting('a')).toBe(true);expect(projected.groupIsResting('c')).toBe(true)
 expect(projected.groupIsResting('b')).toBe(false);expect(projected.operators.D!.isResting()).toBe(true)
})
