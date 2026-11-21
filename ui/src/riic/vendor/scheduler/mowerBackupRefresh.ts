import type {MowerSchedulingData} from './mowerSchedulingData'
import type {MowerTask,MowerBackupRefreshRule} from './mowerTaskQueue'

/** Disabled trading refreshes do not turn a restricted room list into a wildcard. */
export function mergeMowerBackupRefreshRule(current:MowerBackupRefreshRule,previous?:MowerBackupRefreshRule):MowerBackupRefreshRule {
 if(!previous)return {drained:current.drained,trading:[current.trading[0],[...current.trading[1]]]}
 const enabled=current.trading[0]||previous.trading[0]
 const wildcard=current.trading[0]&&!current.trading[1].length||previous.trading[0]&&!previous.trading[1].length
 const rooms=wildcard?[]:[...new Set([...(current.trading[0]?current.trading[1]:[]),...(previous.trading[0]?previous.trading[1]:[])])]
 return {drained:current.drained||previous.drained,trading:[enabled,rooms]}
}

/** A coalesced task inherits unfinished refresh obligations without changing live operators. */
export function inheritMowerBackupRefreshRules(task:MowerTask,previous:readonly MowerTask[]):void {
 const rules={...task.backupRefreshRules}
 for(const old of previous)for(const [name,rule] of Object.entries(old.backupRefreshRules??{}))rules[name]=mergeMowerBackupRefreshRule(rule,rules[name])
 if(Object.keys(rules).length)task.backupRefreshRules=rules
}

/** Capture only changed rules at the real activation boundary, never during preview. */
export function captureMowerBackupRefreshRules(task:MowerTask|undefined,before:MowerSchedulingData,after:MowerSchedulingData,oldDrained:readonly string[],newDrained:readonly string[]):void {
 if(!task||!Object.keys(task.plan).length)return
 const rules={...task.backupRefreshRules}
 for(const name of new Set([...Object.keys(before.operators),...Object.keys(after.operators)])){
  const old:MowerBackupRefreshRule={drained:oldDrained.includes(name),trading:before.operators[name]?.refreshOrderRooms??[false,[]]}
  const next:MowerBackupRefreshRule={drained:newDrained.includes(name),trading:after.operators[name]?.refreshOrderRooms??[false,[]]}
  if(JSON.stringify(old)!==JSON.stringify(next))rules[name]=mergeMowerBackupRefreshRule(old,rules[name])
 }
 if(Object.keys(rules).length)task.backupRefreshRules=rules
}
