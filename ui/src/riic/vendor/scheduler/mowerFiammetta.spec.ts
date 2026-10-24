import {describe,it,expect} from 'vitest'
import oracle from './fixtures/mower-fia-ready-cache-alpha.json'
import {MowerOperatorState} from './mowerOperatorState'
import {MowerSchedulingData} from './mowerSchedulingData'
import {mowerFiaReadyMicros,selectMowerFiaTarget} from './mowerFiammetta'
describe('actual alpha Fiammetta cached readiness',()=>{
 for(const c of oracle.cases)it(c.id,()=>{
  const op=new MowerOperatorState({name:'Fia',mood:c.mood,timeStampMicros:c.stampMicros??undefined});let reads=0
  const readyMicros=mowerFiaReadyMicros(op,c.nowMicros,()=>{reads++;return c.timerMicros})
  expect({readyMicros,reads}).toEqual(c.output)
 })
})

it('uses ordered candidates below the threshold and the lowest mood only when fool protection is off',()=>{
 const data=new MowerSchedulingData({plan:{},operators:{A:new MowerOperatorState({name:'A',mood:18,timeStampMicros:0}),B:new MowerOperatorState({name:'B',mood:10,timeStampMicros:0})},dorms:[],nowMicros:0})
 expect(selectMowerFiaTarget(data,['A','B'],false,.8)).toBe('A')
 expect(selectMowerFiaTarget(data,['A','B'],false,.4)).toBe('B')
 expect(selectMowerFiaTarget(data,['A','B'],true,.4)).toBeUndefined()
})

 it('excludes shared working followers from group charging priority',()=>{
  const a=new MowerOperatorState({name:'A',group:'g',mood:10,timeStampMicros:0}),f=new MowerOperatorState({name:'F',room:'room_1_1',group:'g',mood:1,timeStampMicros:0,groupBindings:[{group:'g',replacement:['X']},{group:'h',replacement:['X']}]})
  const data=new MowerSchedulingData({plan:{},operators:{A:a,F:f},dorms:[],nowMicros:0})
  expect(selectMowerFiaTarget(data,['A'],true)).toBe('A')
 })


it('retains ordinary single-group priority checks',()=>{
 const data=new MowerSchedulingData({plan:{},operators:{A:new MowerOperatorState({name:'A',group:'g',mood:10,timeStampMicros:0}),B:new MowerOperatorState({name:'B',room:'room_1_1',group:'g',mood:1,timeStampMicros:0})},dorms:[],nowMicros:0})
 expect(selectMowerFiaTarget(data,['A'],true)).toBeUndefined()
})

it('keeps the configured exhaustion-worker fallback while excluding shared followers',()=>{
 const aroma=new MowerOperatorState({name:'阿罗玛',room:'room_3_2',currentRoom:'room_3_2',mood:24,timeStampMicros:0,restInFull:true,exhaustRequire:true})
 const gravel=new MowerOperatorState({name:'砾',mood:22,timeStampMicros:0,workaholic:true})
 const gladiia=new MowerOperatorState({name:'歌蕾蒂娅',room:'central',currentRoom:'central',group:'深海',mood:18,timeStampMicros:0})
 const follower=new MowerOperatorState({name:'乌尔比安',room:'room_2_2',currentRoom:'room_2_2',group:'深海',mood:1,timeStampMicros:0,groupBindings:[{group:'深海',replacement:['苍苔']},{group:'红松',replacement:['苍苔']},{group:'感知',replacement:['苍苔']}]})
 const data=new MowerSchedulingData({plan:{},operators:{阿罗玛:aroma,砾:gravel,歌蕾蒂娅:gladiia,乌尔比安:follower},dorms:[],nowMicros:0})
 const targets=['阿罗玛','砾','歌蕾蒂娅']
 expect(selectMowerFiaTarget(data,targets,false)).toBe('歌蕾蒂娅')
 expect(selectMowerFiaTarget(data,targets,true)).toBe('歌蕾蒂娅')
 for(const op of Object.values(data.operators))op.mood=24
 // The existing disabled-protection fallback retains its configured first target.
 expect(selectMowerFiaTarget(data,targets,false)).toBe('阿罗玛')
 expect(selectMowerFiaTarget(data,targets,true)).toBeUndefined()
})

it('charges the configured recovering exhaustion worker before a lower-mood cover with protection disabled',()=>{
 const aroma=new MowerOperatorState({name:'阿罗玛',group:'用尽',room:'room_3_2',currentRoom:'dormitory_1',mood:10,timeStampMicros:0,restInFull:true,exhaustRequire:true})
 const gravel=new MowerOperatorState({name:'砾',room:'room_2_2',currentRoom:'room_2_2',mood:5,timeStampMicros:0,workaholic:true})
 const gladiia=new MowerOperatorState({name:'歌蕾蒂娅',room:'central',currentRoom:'central',group:'深海',mood:18,timeStampMicros:0})
 const follower=new MowerOperatorState({name:'虎狼丸',group:'用尽',room:'meeting',currentRoom:'meeting',mood:1,timeStampMicros:0,groupBindings:[{group:'感知',replacement:['予愿安洁莉娜']},{group:'用尽',replacement:['伊芙利特']}]})
 const data=new MowerSchedulingData({plan:{},operators:{阿罗玛:aroma,砾:gravel,歌蕾蒂娅:gladiia,虎狼丸:follower},dorms:[],nowMicros:0})
 expect(selectMowerFiaTarget(data,['阿罗玛','砾','歌蕾蒂娅'],false)).toBe('阿罗玛')
 expect(selectMowerFiaTarget(data,['阿罗玛','砾','歌蕾蒂娅'],true)).toBe('阿罗玛')
})
