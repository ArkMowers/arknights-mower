import {OPERATOR_MAP} from '../domain/operators'
import type {RuntimeEvent,RuntimeState} from '../scheduler/rosterRuntime'

export interface SimulationActivityFinding {
  code:string
  kind:'constraint'|'activity'
  message:string
  operatorIds:string[]
}
const diagnosticLabels:Record<string,string>={
  'group-blocked':'可用替班或床位不足，原在岗安排保留',
  'mower-shift-bed-conflict':'强制宿舍任务等待有效恢复床位',
  'mower-backup-cycle':'副表预演循环',
  'mower-backup-deferred':'副表切换暂缓',
  'mower-task-exception':'任务异常',
  'mower-plan-solver-exception':'排班规划异常',
  'mower-planning-exception':'调度规划异常',
}
export const simulationOperatorName=(state:RuntimeState,id:string)=>OPERATOR_MAP.get(id)?.name??state.mowerSource?.data.operators[id]?.nativeName??id
const span=(events:readonly RuntimeEvent[])=>{
  const times=events.map(event=>event.time).filter(Number.isFinite)
  return times.length?`，模拟时间跨度 ${Number(((Math.max(...times)-Math.min(...times))*60).toFixed(2))} 分钟`:''
}

/** Bounded evidence summaries. Diagnostic records carry no resolved/unresolved status. */
export function simulationActivityFindings(state:RuntimeState,recent:readonly RuntimeEvent[]):SimulationActivityFinding[]{
  const findings:SimulationActivityFinding[]=[],seen=new Set<string>()
  const add=(finding:SimulationActivityFinding)=>{
    const key=finding.code+'\0'+finding.message
    if(findings.length<6&&!seen.has(key)){findings.push(finding);seen.add(key)}
  }
  const named=(ids:string[])=>ids.map(id=>simulationOperatorName(state,id)).join('、')
  const available=new Map<string,Set<string>>()
  for(const [id,op] of OPERATOR_MAP)available.set(op.name,new Set([id]))
  for(const op of Object.values(state.mowerSource?.data.operators??{})){
    const ids=available.get(op.nativeName)??new Set<string>();ids.add(op.name);available.set(op.nativeName,ids)
  }
  for(const diagnostic of state.diagnostics.slice(-64).reverse()){
    const label=Object.prototype.hasOwnProperty.call(diagnosticLabels,diagnostic.code)?diagnosticLabels[diagnostic.code]:undefined;if(!label)continue
    let ids:string[]=[],detail=diagnostic.message
    if(diagnostic.code==='group-blocked'){
      const key=/^(group|slot):(.+): insufficient available candidates or beds; original occupants retained$/.exec(detail)
      if(key){
        // Membership is current configuration evidence; the diagnostic may predate that configuration.
        ids=[...new Set(state.config.positions.filter(p=>!p.dormitory&&!p.permanent&&(key[1]==='group'?p.group===key[2]:p.id===key[2])).map(p=>p.primary))]
        detail=`${key[1]==='group'?'绑组':'岗位'} ${key[2]}${ids.length?`；当前关联干员：${named(ids)}`:''}`
      }
    }else if(diagnostic.code==='mower-shift-bed-conflict'){
      const names=/^(.+): forced dorm task waits for valid recovery beds$/.exec(detail)?.[1]?.split('、')??[]
      ids=names.flatMap(name=>{const matches=available.get(name);return matches?.size===1?[...matches]:[]})
      if(names.length)detail=names.join('、')
    }
    // Explicit IDs are unambiguous; short Chinese names inside free-form text are not evidence.
    detail=detail.replace(/\bchar_\d+_[a-zA-Z0-9_]+\b/g,id=>{
      if(diagnostic.code!=='group-blocked'&&(OPERATOR_MAP.has(id)||state.mowerSource?.data.operators[id])){ids.push(id);return simulationOperatorName(state,id)}
      return id
    })
    add({code:diagnostic.code,kind:'constraint',message:`曾报告${label}：${detail.slice(0,400)}。此记录不表示当前仍未解决。`,operatorIds:[...new Set(ids)]})
  }
  const events=recent.slice(-256)
  const shifts=new Map<string,{on:number;off:number;events:RuntimeEvent[]}>()
  for(const event of events)if((event.type==='shift-on'||event.type==='shift-off')&&event.reason!=='position-correction'){
    for(const id of new Set(event.operators)){
      const count=shifts.get(id)??{on:0,off:0,events:[]}
      if(event.type==='shift-on')count.on++;else count.off++
      count.events.push(event);shifts.set(id,count)
    }
  }
  for(const [id,count] of [...shifts].sort((a,b)=>b[1].on+b[1].off-a[1].on-a[1].off))if(count.on>=2&&count.off>=2){
    add({code:'repeated-shifts',kind:'activity',message:`近期记录 ${named([id])} 上班 ${count.on} 次、下班 ${count.off} 次${span(count.events)}；仅描述活动，原因未确定。`,operatorIds:[id]})
  }
  const backups=new Map<string,RuntimeEvent[]>()
  for(const event of events)if(event.type==='backup-plan'){
    const key=event.backupIndex!==undefined?String(event.backupIndex):event.backupName
    if(key!==undefined){const group=backups.get(key)??[];group.push(event);backups.set(key,group)}
  }
  for(const group of [...backups.values()].sort((a,b)=>b.length-a.length))if(group.length>=3){
    const label=group[0]!.backupName??`副表 ${group[0]!.backupIndex!+1}`
    add({code:'repeated-backup-switches',kind:'activity',message:`近期记录 ${label} 切换 ${group.length} 次${span(group)}；仅描述活动，原因未确定。`,operatorIds:[...new Set(group.flatMap(event=>event.operators))]})
  }
  const charges=events.filter(event=>event.type==='fiammetta')
  if(charges.length>=3)add({code:'repeated-fiammetta',kind:'activity',message:`近期记录菲亚充能 ${charges.length} 次${span(charges)}；仅描述活动，原因未确定。`,operatorIds:[...new Set(charges.flatMap(event=>event.operators))]})
  const small=charges.flatMap(event=>{
    const id=event.operators[1],before=event.moraleBefore?.[1],after=event.moraleAfter?.[1]
    return id&&before!==undefined&&after!==undefined&&Number.isFinite(before)&&Number.isFinite(after)&&before>=0&&after>=before&&after<=24&&after-before<=1?[{id,before,after}]:[]
  })
  if(small.length){
    const latest=small[small.length-1]!
    add({code:'small-fiammetta-charge',kind:'activity',message:`近期 ${small.length} 次菲亚充能的目标心情增量不超过 1；最近一次 ${named([latest.id])}：${Number(latest.before.toFixed(3))} → ${Number(latest.after.toFixed(3))}，增加 ${Number((latest.after-latest.before).toFixed(3))}。此数值不表示充能无效或解释演算变慢。`,operatorIds:[...new Set(small.map(item=>item.id))]})
  }
  return findings
}
