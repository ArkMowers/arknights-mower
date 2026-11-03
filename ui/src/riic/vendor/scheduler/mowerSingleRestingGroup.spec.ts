import {expect,it} from 'vitest'
import {MowerOperatorState,restingThresholdFor} from './mowerOperatorState'
import {MowerSchedulingData,MowerDormState} from './mowerSchedulingData'
import {mowerResting,mowerTryReorder,mowerGetRestingPlan} from './mowerOrdinaryPlanning'
import {mowerArrangementGroupTransitions,commitMowerGroupShifts} from './mowerSharedGroups'
import {projectMowerArrangements} from './mowerObservations'
import {planMowerAlphaMetadata} from './mowerAlphaMetadata'
import {MowerTaskQueue,toMowerMicros} from './mowerTaskQueue'

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
