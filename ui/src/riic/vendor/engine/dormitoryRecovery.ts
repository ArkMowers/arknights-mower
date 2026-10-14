import { operatorFor } from '../domain/operatorContext'
import { isWanderingMedic, isLaiosSquad } from './supportRecovery'
import { hasRiicTag } from '../domain/riicTags'
import { buildRiicGlobalContext } from './globalContext'
import { matchesRiicFaction, matchesRiicIdentity } from '../domain/riicIdentity'
import type { AppConfig } from '../domain/types'
export interface DormitoryRecoveryResult { rates:Map<string,number>; details:Map<string,string[]>; unquantified:string[] }
/** Actual-room rates; unspecified atmosphere is zero and explicitly diagnosed. Targets are policy input, not a lowest-morale rule. */
export function evaluateDormitoryRecovery(config:AppConfig,roomIndex:number,moraleValues:ReadonlyMap<string,number>,atmosphere?:number,targetByProvider?:ReadonlyMap<string,string>):DormitoryRecoveryResult {
 const rates=new Map<string,number>(),details=new Map<string,string[]>(),unquantified:string[]=[]
 const level=config.facilities.dormitories[roomIndex]
 if(!level)return {rates,details,unquantified:['宿舍等级缺失']}
 if(atmosphere===undefined)unquantified.push('宿舍氛围未指定；当前仅计等级基础，不代表满氛围')
 const base=1.5+level*.1+Math.min(level*1000,Math.max(0,atmosphere??0))*.0004
 const operators=(config.facilityOperatorIds.dormitories[roomIndex]??[]).map(id=>operatorFor(config, id)).filter(o=>o!==undefined)
 // Match runtime endpoint tolerance without moving directional skill thresholds (18/20).
 const mood=(id:string)=>{const value=moraleValues.get(id)??config.operatorMorale[id]??24;return value<=24&&value>=24-1e-8?24:value}
 const global=buildRiicGlobalContext(config,undefined,new Map(moraleValues))
 const centralEffects:{value:number;eliteOnly:boolean;label:string}[]=[]
 for (const id of config.controlOperatorIds) {
  const provider=operatorFor(config, id)
  if (!provider || (moraleValues.get(id)??config.operatorMorale[id]??24)<=0 || config.zeroMoraleOperatorIds.includes(id)) continue
  for (const skill of provider.skills.filter(s=>s.roomType==='CONTROL'&&/所有宿舍|宿舍内所有干员|宿舍内.*精英干员/.test(s.description))) {
   if(/^control_dorm_rec(?:2)?\[/.test(skill.buffId))centralEffects.push({value:.05,eliteOnly:false,label:provider.name+'·'+skill.name})
   else if(skill.buffId==='control_dorm_rec_tag[001]')centralEffects.push({value:.1,eliteOnly:true,label:provider.name+'·'+skill.name})
   else unquantified.push(`${provider.name}·${skill.name} (${skill.buffId})：中枢宿舍恢复未解析`)
  }
 }
 const all=new Map<string,number>(),single=new Map<string,number>(),self=new Map<string,number>()
 const record=(id:string,value:number,kind:'all'|'single'|'self',label:string)=>{const table=kind==='all'?all:kind==='single'?single:self;table.set(id,kind==='self'?(table.get(id)??0)+value:Math.max(table.get(id)??0,value));details.set(id,[...(details.get(id)??[]),`${label}：${kind} ${value}/h`])}
 for(const provider of operators)for(const skill of provider.skills.filter(s=>s.roomType==='DORMITORY')) {
  const d=skill.description,b=skill.buffId,label=`${provider.name}·${skill.name}`
  if(b==='dorm_recExcludeOther[000]'||b==='dorm_exchangeAp[000]'||b==='dorm_rec_all&tired[100]'||b==='dorm_rec_toone[000]')continue
  if(b==='dorm_rec_all&single[000]'){const targets=operators.filter(o=>mood(o.charId)<24);for(const t of targets)record(t.charId,.8/targets.length,targets.length===1?'single':'all',label);continue}
  if(b==='dorm_rec_all&tag[000]'){for(const target of operators)record(target.charId,.15+(isLaiosSquad(target)?.15:0),'all',label);continue}
  let dynamicAll:number|undefined
  if(b==='dorm_rec_all&profession[000]')dynamicAll=.06*Math.min(4,global.presentOperators.filter(isWanderingMedic).length)
  if(b.startsWith('dorm_powToRecAll[')) {
    // User confirmed in-game on 2026-09-12: virtual stations also count for Lumen.
    dynamicAll=(b==='dorm_powToRecAll[010]'?.15:.1)+.05*global.effectivePowerStations.count
  }
  if(b.startsWith('dorm_hireToRecAll['))dynamicAll=(b==='dorm_hireToRecAll[000]'?.15:.1)+(b==='dorm_hireToRecAll[021]'?.1:.05)*Math.max(0,config.facilities.office-1)
  if(b==='dorm_rec_all&unfull[001]')dynamicAll=.2+.01*operators.filter(o=>mood(o.charId)<24).length
  if(b==='dorm_rec_all&lv[100]')dynamicAll=.15+.02*level
  if(b==='dorm_rec_all&bd[000]')dynamicAll=.2+.01*Math.floor(global.silentResonance.effective/5)
  if(b==='dorm_rec_all&group[000]')dynamicAll=.06*Math.min(4,global.presentOperators.filter(o=>matchesRiicFaction(o,'sui')).length)
  if(dynamicAll!==undefined){for(const t of operators)record(t.charId,dynamicAll,'all',label);continue}
  if(b.startsWith('dorm_rec_oneself2[')){record(provider.charId,.7+.05*Math.max(0,operators.length-1),'self',label);continue}
  if(b==='dorm_rec_all&tired[000]'){for(const t of operators)record(t.charId,.15+(mood(t.charId)<=18?.1:0),'all',label);continue}
  const fixed=/^dorm_rec_(?:all|single|oneself)(?:&oneself)?\[/.test(b)||['dorm_rec_bd_n1_n2[000]','dorm_rec_bd_n1_n3[000]','dorm_rec_all&unfull[000]','dorm_rec_all&lv[000]','dorm_rec_single_power[100]','dorm_rec_single_power[000]','dorm_rec_single_power[001]','dorm_rec_single_P[000]','dorm_rec_single_P[001]','dorm_rec_single_P[002]','dorm_rec_single&tag[000]'].includes(b)
  if(!fixed){if(/心情.*恢复|每小时恢复/.test(d))unquantified.push(`${label} (${b})：条件恢复尚未量化`);continue}
  const selfMatch=d.match(/自身心情每小时恢复([+-][\d.]+)/)
  if(selfMatch)record(provider.charId,Number(selfMatch[1]),'self',label)
  const allMatch=d.match(/(?:该宿舍内|宿舍内)(?:所有|除自身以外所有)干员的心情每小时恢复\+([\d.]+)/)
  if(allMatch)for(const t of operators){if(d.includes('除自身以外所有')&&t.charId===provider.charId)continue;const fatigueExtra=provider.skills.some(s=>s.buffId==='dorm_rec_all&tired[100]')&&mood(t.charId)<=20?.1:0;const morganExtra=provider.name==='推进之王'&&operators.some(o=>o.skills.some(s=>s.buffId==='dorm_rec_toone[000]'))&&matchesRiicIdentity(t,'groupId','glasgow')?.3:0;record(t.charId,Number(allMatch[1])+fatigueExtra+morganExtra,'all',label)}
  const singleMatch=d.match(/某个干员(?:的心情)?每小时恢复\+([\d.]+)/)
  if(singleMatch){const candidates=operators.filter(o=>mood(o.charId)<24&&(!d.includes('除自身以外')||o.charId!==provider.charId));const requested=targetByProvider?.get(provider.charId);const target=requested?candidates.find(o=>o.charId===requested):candidates.length===1?candidates[0]:undefined;if(target){
   const named:Record<string,string>={'dorm_rec_single_P[000]':'锡兰','dorm_rec_single_P[001]':'嘉维尔','dorm_rec_single_P[002]':'蓝毒'}
   const extra=(b==='dorm_rec_single&tag[000]'&&(hasRiicTag(target,'monsterHunter')||hasRiicTag(target,'bubbleHunter')))||(named[b]===target.name)||(b==='dorm_rec_single_power[000]'&&matchesRiicIdentity(target,'nationId','sami'))||(b==='dorm_rec_single_power[001]'&&matchesRiicIdentity(target,'nationId','laterano'))
   record(target.charId,Number(singleMatch[1])+(extra?.45:0),'single',label)
  }else if(candidates.length)unquantified.push(`${label} (${b})：${requested?'指定单体目标不满足条件':'未指定单体恢复目标'}`)}
  if(!selfMatch&&!allMatch&&!singleMatch&&/恢复/.test(d))unquantified.push(`${label} (${b})：恢复文案未解析`)
 }
 for(const op of operators){
  const fixed=op.skills.some(s=>s.buffId==='dorm_recExcludeOther[000]')
  const central=fixed?0:Math.max(0,...centralEffects.filter(e=>!e.eliteOnly||matchesRiicIdentity(op,'groupId','elite')).map(e=>e.value))
  if(central>0)details.set(op.charId,[...(details.get(op.charId)??[]),`中枢加成：+${central}/h`])
  const rate=fixed?2:base+central+(all.get(op.charId)??0)+(single.get(op.charId)??0)+(self.get(op.charId)??0)
  rates.set(op.charId,rate)
  details.set(op.charId,fixed?['自律：固定 2/h，排除等级、氛围及其他恢复']:[`等级与氛围基础 ${base}/h`,...(details.get(op.charId)??[])])}
 return {rates,details,unquantified}
}
