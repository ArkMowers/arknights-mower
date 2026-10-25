import {describe,it,expect} from 'vitest'
import fixtures from '../../../__tests__/fixtures/predictiveMoodControl.json'
import {predictiveFixture} from '../../../__tests__/fixtures/predictiveMoodControl'
import {planMowerOrdinary} from './mowerOrdinaryPlanning'
import {selectMoodControlCandidate} from './mowerPredictiveMoodControl'
describe('shared production predictive mood trajectories',()=>{
 for(const fixture of fixtures)it(fixture.id,()=>{
  const {data,queue,options,diagnostics}=predictiveFixture(fixture.input)
  planMowerOrdinary(data,queue,options)
  const result=diagnostics[0]!.result!
  expect({decision:result.decision,status:result.status,score:result.score,events:result.events.map(({time,type,group})=>({time,type,group})),nextWake:result.nextWake}).toEqual(fixture.expected)
  expect(result.candidates).toBeLessThanOrEqual(16);expect(result.processedNodes).toBeLessThanOrEqual(16*64)
 })
 it('keeps the baseline when another eligible candidate exceeds the batch limit',()=>{
  let calls=0
  const choice=selectMoodControlCandidate(0,[{id:'A',softAt:100,lowerAt:200}],[1,2,3],candidate=>{calls++;return {complete:true,score:candidate.group?[0,0,0,0]:[10,10,0,0],nodes:1}},2)
  expect(calls).toBe(1);expect(choice.enumeratedCandidates).toBe(2)
  expect(choice.selected).toBeUndefined();expect(choice.exhausted).toBe(true)
 })
 it('stops subsequent candidates immediately after the node budget is exhausted',()=>{
  let calls=0
  const choice=selectMoodControlCandidate(0,[{id:'A',softAt:100,lowerAt:200}],[1,2],candidate=>{calls++;return {complete:!candidate.group,score:candidate.group?[0,0,0,0]:[10,10,0,0],nodes:candidate.group?65:64,exhausted:!!candidate.group}})
  expect(calls).toBe(2);expect(choice.selected).toBeUndefined();expect(choice.maxCandidateNodes).toBe(65)
 })
 it('keeps the baseline on budget exhaustion',()=>{
  const baseline={complete:false,score:[100,100,0,0],nodes:64,exhausted:true}
  let calls=0
  expect(selectMoodControlCandidate(0,[{id:'A',softAt:100,lowerAt:200}],[],()=>{calls++;return baseline}).selected).toBeUndefined()
  expect(calls).toBe(1)
 })
})
