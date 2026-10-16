import { describe,it,expect } from 'vitest'
import { createDefaultConfig } from '../domain/defaults'
import { OPERATORS } from '../domain/operators'
import { evaluateDormitoryRecovery } from './dormitoryRecovery'
import { compileOperatorInventory } from '../domain/operatorInventory'
import { inventoryOperatorRecords } from '../domain/operatorContext'
const id=(n:string)=>OPERATORS.find(o=>o.name===n)!.charId
function dorm(names:string[]){const config=createDefaultConfig();config.controlOperatorIds=[];config.facilities.dormitories=[5];config.facilityOperatorIds.dormitories=[names.map(id)];return config}
describe('dormitory recovery source contract',()=>{
 it('takes the highest all-room recovery and retains a separate self penalty',()=>{const c=dorm(['杜林','安比尔','芬']);const r=evaluateDormitoryRecovery(c,0,new Map(c.facilityOperatorIds.dormitories[0]!.map(i=>[i,10])),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.25);expect(r.rates.get(id('杜林'))).toBeCloseTo(4.15)})
})
 it('single recovery takes highest for the explicit same target, and reports unspecified ambiguity',()=>{const c=dorm(['闪灵','Lancet-2','芬','香草']);const moods=new Map(c.facilityOperatorIds.dormitories[0]!.map(i=>[i,10]));const targets=new Map([[id('闪灵'),id('芬')],[id('Lancet-2'),id('芬')]]);expect(evaluateDormitoryRecovery(c,0,moods,5000,targets).rates.get(id('芬'))).toBeCloseTo(4.75);expect(evaluateDormitoryRecovery(c,0,moods,5000).unquantified.length).toBe(2)})
 it('Fiammetta excludes every recovery source including level and atmosphere',()=>{const c=dorm(['菲亚梅塔','杜林','闪灵']);const r=evaluateDormitoryRecovery(c,0,new Map([[id('菲亚梅塔'),8]]),5000,new Map([[id('闪灵'),id('菲亚梅塔')]]));expect(r.rates.get(id('菲亚梅塔'))).toBe(2)})
 it('redistributes Coldshots shared pool and changes max category at one unfinished occupant',()=>{const c=dorm(['冰酿','芬','杜林']);const r=evaluateDormitoryRecovery(c,0,new Map([[id('冰酿'),24],[id('芬'),10],[id('杜林'),10]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.4);const alone=evaluateDormitoryRecovery(c,0,new Map([[id('冰酿'),24],[id('芬'),10],[id('杜林'),24]]),5000);expect(alone.rates.get(id('芬'))).toBeCloseTo(5.05)})
 it('applies room-level and unfinished-person recovery before the same-category maximum',()=>{const c=dorm(['响石','波卜','芬']);const r=evaluateDormitoryRecovery(c,0,new Map([[id('响石'),24],[id('波卜'),24],[id('芬'),12]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.25);expect(r.unquantified).toEqual([])})
import { buildRiicGlobalContext } from './globalContext'
it('zero-morale dormitory residents retain dream and bar perception while exhausted office workers do not',()=>{const c=createDefaultConfig();c.controlOperatorIds=[];c.rooms.forEach(r=>r.operatorIds=[]);c.rooms.find(r=>r.type==='manufacture')!.operatorIds=[id('迷迭香')];c.facilities.dormitories=[1,3];c.facilityOperatorIds.dormitories=[[id('爱丽丝')],[id('车尔尼')]];c.dormitoryOccupantCount=2;c.facilities.office=3;c.facilityOperatorIds.office=[id('絮雨')];c.zeroMoraleOperatorIds=['爱丽丝','车尔尼','絮雨'].map(id);const ctx=buildRiicGlobalContext(c,new Set([id('迷迭香')]));expect(ctx.thoughtChain.effective).toBe(6)})
it.each([['斥罪',1,4.15],['斥罪',3,4.25],['隐德来希',1,4.1],['隐德来希',3,4.3]] as const)('uses actual extra recruitment slots for %s at office %s',(name,l,expected)=>{const c=dorm([name,'芬']);c.facilities.office=l;expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(expected)})
it('Lumen scales with the number of physical stations when there are no virtual providers',()=>{const c=dorm(['流明','芬']);const power=c.rooms.find(r=>r.type==='power')!;c.rooms=c.rooms.filter(r=>r.type!=='power');expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.15);c.rooms.push(power);expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.2)})
it.each([['黑','锡兰',5],['黑','芬',4.55],['深靛','蓝毒',5],['特米米','嘉维尔',5],['新约能天使','送葬人',5],['新约能天使','能天使',4.55],['寒檀','远山',5],['寒檀','芬',4.55],['新约能天使','芬',4.55]] as const)('applies conditional single recovery %s to %s',(provider,target,expected)=>{const c=dorm([provider,target]);const r=evaluateDormitoryRecovery(c,0,new Map([[id(target),10]]),5000,new Map([[id(provider),id(target)]]));expect(r.rates.get(id(target))).toBeCloseTo(expected)})
it('Indigo cannot target herself even when her raw skill omits self exclusion',()=>{const c=dorm(['深靛','芬']);expect(evaluateDormitoryRecovery(c,0,new Map([[id('深靛'),10]]),5000,new Map([[id('深靛'),id('深靛')]])).rates.get(id('深靛'))).toBeCloseTo(4)})
it('does not misclassify Gladiia self recovery as a control-to-dorm buff',()=>{const c=dorm(['芬']);c.controlOperatorIds=[id('歌蕾蒂娅')];expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).unquantified).toEqual([])})
it('Lumen includes Eunectes virtual stations confirmed by the user',()=>{const c=dorm(['流明','芬']);c.rooms=c.rooms.filter(r=>r.type!=='power');const power=createDefaultConfig().rooms.find(r=>r.type==='power')!;power.operatorIds=[id('Lancet-2')];c.rooms.push(power);c.controlOperatorIds=[id('森蚺')];const r=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.3);expect(r.unquantified).toEqual([]);c.zeroMoraleOperatorIds=[id('森蚺')];expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.2)})

it('Lumen also includes the virtual station from active Greyy Alter',()=>{const c=dorm(['流明','芬']);const power=createDefaultConfig().rooms.find(r=>r.type==='power')!;power.operatorIds=[id('承曦格雷伊')];c.rooms=[power];const r=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.25);expect(r.unquantified).toEqual([])})
it('treats roundoff below full morale as full for shared recovery category and unfinished counts',()=>{const c=dorm(['冰酿','杜林','芬']);const nearFull=new Map([[id('冰酿'),24],[id('杜林'),23.99999999999],[id('芬'),10]]);expect(evaluateDormitoryRecovery(c,0,nearFull,5000).rates.get(id('芬'))).toBeCloseTo(5.05);const p=dorm(['波卜','芬']);expect(evaluateDormitoryRecovery(p,0,new Map([[id('波卜'),23.99999999999],[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.21)})
it('does not give a single-target bonus to a roundoff-full target, and preserves genuine subfull morale',()=>{const c=dorm(['闪灵','芬']);const evaluate=(m:number)=>evaluateDormitoryRecovery(c,0,new Map([[id('芬'),m]]),5000,new Map([[id('闪灵'),id('芬')]]));expect(evaluate(23.99999999999).rates.get(id('芬'))).toBe(4);expect(evaluate(23.999999).rates.get(id('芬'))).toBe(4.75)})
it('keeps the simulator directional offset across eighteen rather than snapping it to the threshold',()=>{const c=dorm(['刺玫','芬']);const evaluate=(m:number)=>evaluateDormitoryRecovery(c,0,new Map([[id('芬'),m]]),5000).rates.get(id('芬'));expect(evaluate(18-2e-8)).toBeCloseTo(4.25);expect(evaluate(18+2e-8)).toBeCloseTo(4.15)})
it('adds Perfumer Alter conditional recovery after the all-room maximum',()=>{const c=dorm(['撷英调香师','杜林','芬']);const run=(m:number)=>evaluateDormitoryRecovery(c,0,new Map([[id('芬'),m]]),5000);expect(run(20).rates.get(id('芬'))).toBeCloseTo(4.35);expect(run(20).unquantified).toEqual([]);c.facilityOperatorIds.dormitories[0]=[id('撷英调香师'),id('芬')];expect(run(20.1).rates.get(id('芬'))).toBeCloseTo(4.15);expect(run(20).rates.get(id('芬'))).toBeCloseTo(4.25)})
it('counts actual wandering medics across base including exhausted residents, excludes regular medics and caps four',()=>{const c=dorm(['纯烬艾雅法拉','芬']);c.facilityOperatorIds.reception=['褐果','桑葚','蜜莓','哈洛德','闪灵'].map(id);c.zeroMoraleOperatorIds=['褐果','桑葚','蜜莓','哈洛德'].map(id);expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.24);c.facilityOperatorIds.reception=[id('闪灵')];expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.06)})
it('Senshi applies the Laios tooltip bonus to the exact target set',()=>{const c=dorm(['森西','莱欧斯','芬']);const r=evaluateDormitoryRecovery(c,0,new Map([[id('莱欧斯'),10],[id('芬'),10]]),5000);expect(r.rates.get(id('莱欧斯'))).toBeCloseTo(4.3);expect(r.rates.get(id('芬'))).toBeCloseTo(4.15)})
it('Morgan augments Siege provider only for Glasgow members before all-room maximum',()=>{const c=dorm(['摩根','推进之王','芬']);const r=evaluateDormitoryRecovery(c,0,new Map([[id('摩根'),10],[id('芬'),10]]),5000);expect(r.rates.get(id('摩根'))).toBeCloseTo(4.5);expect(r.rates.get(id('芬'))).toBeCloseTo(4.2);c.facilityOperatorIds.dormitories[0]=[id('摩根'),id('芬')];expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBe(4)})
it.each([['麒麟R夜刀',5],['焰狐龙梓兰',5],['芬',4.55]] as const)('the hunting squad single bonus follows exact tags: %s',(target,expected)=>{const c=dorm(['罗德岛隐秘队',target]);expect(evaluateDormitoryRecovery(c,0,new Map([[id(target),10]]),5000,new Map([[id('罗德岛隐秘队'),id(target)]])).rates.get(id(target))).toBeCloseTo(expected)})
it('quantifies central dorm recovery when no room-wide provider competes, taking the central maximum',()=>{const c=dorm(['芬']);c.controlOperatorIds=['焰影苇草','妮芙'].map(id);const r=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.05);expect(r.unquantified).toEqual([]);c.zeroMoraleOperatorIds=[...c.controlOperatorIds];expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBe(4)})
it('stacks central dorm recovery with room-wide provider without unquantified warnings',()=>{const c=dorm(['杜林','芬']);c.controlOperatorIds=[id('焰影苇草')];const r=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000);expect(r.rates.get(id('芬'))).toBeCloseTo(4.3);expect(r.unquantified).toEqual([])})

it.each([['刺玫',18],['撷英调香师',20]] as const)('adds %s fatigue recovery separately from Durin up to threshold %s',(provider,threshold)=>{
 const c=dorm([provider,'杜林','芬'])
 for(const [m,expected] of [[threshold-2e-8,4.35],[threshold,4.35],[threshold+2e-8,4.25]]){
  const result=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),m!]]),5000)
  expect(result.rates.get(id('芬'))).toBeCloseTo(expected!,8)
  expect(result.unquantified).toEqual([])
 }
})
it.each([[10,4.35],[18,4.35],[19,4.35],[20,4.35],[20.1,4.25]])('takes only one fatigue extra with both providers at morale %s',(m,expected)=>{
 const c=dorm(['刺玫','撷英调香师','杜林','芬','菲亚梅塔'])
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),m],[id('菲亚梅塔'),m]]),5000)
 expect(result.rates.get(id('芬'))).toBeCloseTo(expected,8)
 expect(result.rates.get(id('菲亚梅塔'))).toBe(2)
})
it.each(['刺玫','撷英调香师'])('keeps only the base all-room recovery before %s elite two',provider=>{
 const c=dorm([provider,'芬'])
 c.operatorRecords=inventoryOperatorRecords(compileOperatorInventory([{operator:provider,elitePhase:0,level:1}]))
 expect(evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000).rates.get(id('芬'))).toBeCloseTo(4.15)
})

it.each([[10,5.15,'all'],[24,5.05,'single']] as const)('Coldshot uses the unfinished Fiammetta count at morale %s and the correct recovery category',(fiaMood,expected,kind)=>{
 const c=dorm(['冰酿','菲亚梅塔','杜林','闪灵','芬'])
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('菲亚梅塔'),fiaMood],[id('芬'),10]]),5000,new Map([[id('闪灵'),id('芬')]]))
 expect(result.rates.get(id('芬'))).toBeCloseTo(expected,8)
 expect(result.rates.get(id('菲亚梅塔'))).toBe(2)
 expect(result.details.get(id('芬'))).toContain(`冰酿·小酌怡情：${kind} ${kind==='all'?.4:.8}/h`)
})
it('Coldshot with only one unfinished Free recipient uses the single maximum',()=>{
 const c=dorm(['冰酿','杜林','闪灵','芬'])
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('芬'),10]]),5000,new Map([[id('闪灵'),id('芬')]]))
 expect(result.rates.get(id('芬'))).toBeCloseTo(5.05,8)
})


it('reassigns a locked single-provider recipient when another unfinished resident arrives',()=>{
 const c=dorm(['闪灵','深靛','芬'])
 const targets=new Map([[id('闪灵'),id('深靛')]])
 const moods=new Map([[id('深靛'),1],[id('芬'),24]])
 expect(evaluateDormitoryRecovery(c,0,moods,5000,targets).rates.get(id('深靛'))).toBeCloseTo(4.75)
 moods.set(id('芬'),15)
 const result=evaluateDormitoryRecovery(c,0,moods,5000,targets)
 expect(result.rates.get(id('深靛'))).toBe(4)
 expect(result.rates.get(id('芬'))).toBeCloseTo(4.75)
 expect(result.unquantified).toEqual([])
})
it('sole unfinished providers receive each other’s single recovery but never their own',()=>{
 const c=dorm(['闪灵','深靛'])
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('闪灵'),1],[id('深靛'),2]]),5000)
 expect(result.rates.get(id('闪灵'))).toBeCloseTo(4.55)
 expect(result.rates.get(id('深靛'))).toBeCloseTo(4.75)
})
it('Coldshot never applies her sole-recipient single bonus to herself',()=>{
 const c=dorm(['冰酿','芬'])
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('冰酿'),1]]),5000)
 expect(result.rates.get(id('冰酿'))).toBe(4)
})
it('uses only unlocked single skills when deciding recipient eligibility',()=>{
 const c=dorm(['闪灵','蜜莓','芬'])
 c.operatorRecords=inventoryOperatorRecords(compileOperatorInventory([{operator:'蜜莓',elitePhase:0,level:1}]))
 const result=evaluateDormitoryRecovery(c,0,new Map([[id('蜜莓'),1],[id('芬'),10]]),5000,new Map([[id('闪灵'),id('蜜莓')]]))
 expect(result.rates.get(id('蜜莓'))).toBeCloseTo(4.75)
})
