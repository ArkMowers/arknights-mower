import {describe,it,expect} from 'vitest'
import {createDefaultConfig,createRoom} from '../domain/defaults'
import {OPERATORS} from '../domain/operators'
import {mowerCoordinationRates} from './mowerCoordinationRates'
import {evaluateDormitoryRecovery} from '../engine/dormitoryRecovery'

const id=(name:string)=>OPERATORS.find(op=>op.name===name)!.charId
function config(){
 const c=createDefaultConfig()
 c.rooms=[];c.controlOperatorIds=[];c.facilities.dormitories=[5]
 c.facilityOperatorIds.dormitories=[['杜林','闪灵','菲亚梅塔','芬'].map(id)]
 c.operatorMorale=Object.fromEntries(c.facilityOperatorIds.dormitories[0]!.map(name=>[name,10]))
 return c
}
describe('isolated coordination rate estimates',()=>{
 it('bounds recovery without single or group bonuses, retaining self penalties and Fiammetta exclusion',()=>{
  const c=config(),before=JSON.stringify(c),r=mowerCoordinationRates(c,[5000])
  expect(r.recovery[id('芬')]).toBeCloseTo(4)
  expect(r.recovery[id('杜林')]).toBeCloseTo(3.9)
  expect(r.recovery[id('菲亚梅塔')]).toBe(2)
  expect(JSON.stringify(c)).toBe(before)
  expect(evaluateDormitoryRecovery(c,0,new Map(Object.entries(c.operatorMorale)),5000,new Map([[id('闪灵'),id('芬')]])).rates.get(id('芬'))).toBeCloseTo(5)
 })
 it('recomputes working consumption from projected providers instead of a cached roster',()=>{
  const c=config(),room=createRoom('room_1_1','manufacture');room.operatorIds=[id('芬')];room.operatorCount=1;c.rooms=[room]
  c.facilityOperatorIds.dormitories=[[]];c.controlOperatorIds=[id('阿米娅')];c.operatorMorale[id('阿米娅')]=24
  expect(mowerCoordinationRates(c,[5000]).work[id('芬')]).toBeCloseTo(.95)
  c.operatorMorale[id('阿米娅')]=0
  expect(mowerCoordinationRates(c,[5000]).work[id('芬')]).toBeCloseTo(1)
 })
 it('uses room atmosphere and explicit test rates without mutating their source',()=>{
  const c=config(),overrides={work:{[id('芬')]:.75},recovery:{[id('菲亚梅塔')]:1.5}}
  expect(mowerCoordinationRates(c,[0],overrides)).toMatchObject({work:{[id('芬')]:.75},recovery:{[id('芬')]:2,[id('杜林')]:1.9,[id('菲亚梅塔')]:1.5}})
  expect(overrides.recovery[id('菲亚梅塔')]).toBe(1.5)
 })
})
