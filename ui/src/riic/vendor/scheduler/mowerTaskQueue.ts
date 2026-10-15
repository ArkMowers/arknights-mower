import type {MowerTaskFailureSnapshot} from './mowerTaskFailure'
// Port of ArkMowers/arknights-mower scheduler_task.py and base_schedule.py handle_error.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
export interface MowerTaskType {readonly key:string;readonly value:string;readonly displayValue:string;readonly priority:1|2}
const kind=(key:string,value:string,displayValue:string,priority:1|2=2):MowerTaskType=>Object.freeze({key,value,displayValue,priority})
export const MOWER_TASK_TYPES={
 RUN_ORDER:kind('RUN_ORDER','run_order','跑单',1),SWITCH_PRODUCT:kind('SWITCH_PRODUCT','switch_product','切换产物/订单'),
 FIAMMETTA:kind('FIAMMETTA','菲亚梅塔','肥鸭'),SHIFT_OFF:kind('SHIFT_OFF','shifit_off','下班'),SHIFT_ON:kind('SHIFT_ON','shifit_on','上班'),
 EXHAUST_OFF:kind('EXHAUST_OFF','exhaust_on','用尽下班'),SELF_CORRECTION:kind('SELF_CORRECTION','self_correction','纠错'),
 CLUE_PARTY:kind('CLUE_PARTY','Impart','趴体'),CLUE:kind('CLUE','clue','线索任务'),MAA_MALL:kind('MAA_MALL','maa_Mall','MAA信用购物'),
 NOT_SPECIFIC:kind('NOT_SPECIFIC','','空任务'),RECRUIT:kind('RECRUIT','recruit','公招'),SKLAND:kind('SKLAND','skland','森空岛签到'),
 RE_ORDER:kind('RE_ORDER','宿舍排序','宿舍排序'),RELEASE_DORM:kind('RELEASE_DORM','释放宿舍空位','释放宿舍空位'),FILL_DORM:kind('FILL_DORM','宿舍补位','宿舍补位'),
 REFRESH_TIME:kind('REFRESH_TIME','强制刷新任务时间','强制刷新任务时间'),SKILL_UPGRADE:kind('SKILL_UPGRADE','技能专精','技能专精'),
 SWAP_SUPPORT:kind('SWAP_SUPPORT','换协助位','换协助位'),DEPOT:kind('DEPOT','仓库扫描','仓库扫描'),WORKSHOP:kind('WORKSHOP','加工材料','加工材料'),FURNITURE:kind('FURNITURE','分解所有重复家具','分解所有重复家具'),
} as const
const MICROSECONDS_PER_HOUR=3_600_000_000
export const roundMowerMicros=(micros:number)=>{const base=Math.floor(micros),fraction=micros-base;return fraction===.5?(base%2===0?base:base+1):Math.round(micros)}
/** Python datetime/timedelta resolution. Do not use the morale epsilon for task ordering. */
export const toMowerMicros=(hours:number)=>{const value=roundMowerMicros(hours*MICROSECONDS_PER_HOUR);if(!Number.isSafeInteger(value))throw new Error('Invalid Mower task time: '+String(hours));return value}
export const fromMowerMicros=(micros:number)=>micros/MICROSECONDS_PER_HOUR
export function setMowerTaskType(value:MowerTaskType|string|null|undefined):MowerTaskType {
 if(value&&typeof value==='object'&&Object.values(MOWER_TASK_TYPES).includes(value))return value
 if(typeof value==='string')return Object.values(MOWER_TASK_TYPES).find(t=>t.displayValue.toUpperCase()===value.toUpperCase())??MOWER_TASK_TYPES.NOT_SPECIFIC
 return MOWER_TASK_TYPES.NOT_SPECIFIC
}
export type MowerTaskPlan=Record<string,string[]>
export interface MowerBackupRefreshRule {drained:boolean;trading:[boolean,string[]]}
export interface MowerTaskOptions {time?:number;type?:MowerTaskType|string|null;plan?:MowerTaskPlan;metadata?:string;adjusted?:boolean;strictMoodLimit?:boolean;moodLimit?:number}
export class MowerTask {
 timeMicros:number;type:MowerTaskType;plan:MowerTaskPlan;metadata:string;adjusted:boolean;strictMoodLimit:boolean;moodLimit:number|undefined
 observedOrderDueMicros?:number;wakeOnlyCompletion=false
 executionFailure?:{reason:string;rooms:string[];snapshot:MowerTaskFailureSnapshot}
 executionRetained=false
 get retainsExecution():boolean{return !!this.executionFailure||this.executionRetained}
 groupShiftTransitions:Record<string,boolean>={}
 productShiftLocked=false
 /** A complete physical arrangement must finish before backup/return replanning. */
 backupShiftActive=false
 /** Old rules remain available only while this physical backup arrangement is unfinished. */
 backupRefreshRules?:Record<string,MowerBackupRefreshRule>
 backupExplicitSlots:Set<string>=new Set()
 backupShiftIntent?:MowerTaskPlan;backupShiftConditions?:boolean[];dormFillPlan:MowerTaskPlan={};simpleDormFill=false;arrangementRetryDueMicros?:number
 dormRecoveryRestore:string[]=[]
 arrangementRetryRoom?:string;arrangementRetryCount?:number
 dormMoodResidents:string[]=[];idleDormSearchNames:Record<string,string[]>={};idleDormShiftGroups?:Record<string,string[]>
 releaseTargets?:Record<string,[string,number]>;releaseStartMicros?:number
 moodLimitDeadlineMicros?:number;advanceSupportSwap=false
 productLockNames:Set<string>=new Set();productLockSlots:Set<string>=new Set()
 constructor(options:MowerTaskOptions={},now=0){this.timeMicros=toMowerMicros(options.time??now);this.type=setMowerTaskType(options.type);this.plan=options.plan??{};this.metadata=options.metadata??'';this.adjusted=options.adjusted??false;this.strictMoodLimit=options.strictMoodLimit??false;this.moodLimit=options.moodLimit}
 get time(){return fromMowerMicros(this.timeMicros)}
 set time(value:number){this.timeMicros=toMowerMicros(value)}
 releaseDormTargets():Record<string,[string,number]> {
  if(this.type!==MOWER_TASK_TYPES.RELEASE_DORM)return {}
  let targets=this.releaseTargets
  if(!targets){const slots=Object.entries(this.plan).flatMap(([room,row])=>row.flatMap((name,index)=>name==='Free'?[[room,index] as [string,number]]:[]));if(slots.length!==1||!this.metadata||this.metadata.includes(','))return {};targets={[this.metadata]:slots[0]!}}
  return Object.fromEntries(Object.entries(targets).filter(([, [room,index]])=>this.plan[room]?.[index]==='Free'))
 }
 removeReleaseDormOperator(name:string):void {
  const targets=this.releaseDormTargets(),position=targets[name];delete targets[name]
  if(position){const [room,index]=position;this.plan[room]![index]='Current';if(this.plan[room]!.every(n=>n==='Current'))delete this.plan[room]}
  this.releaseTargets=targets;this.metadata=Object.keys(targets).join(',')
 }
 equals(other:MowerTask):boolean {const keys=Object.keys(this.plan);return this.type===other.type&&Math.abs(this.timeMicros-other.timeMicros)<1_500_000&&keys.length===Object.keys(other.plan).length&&keys.every(k=>other.plan[k]?.length===this.plan[k]!.length&&this.plan[k]!.every((name,i)=>other.plan[k]![i]===name))}
}
/** Order countdown refreshes share the same ideal scheduling boundary as orders. */
export function isMowerRunOrderTask(task:MowerTask):boolean {return task.type===MOWER_TASK_TYPES.RUN_ORDER||task.type===MOWER_TASK_TYPES.REFRESH_TIME}
export interface MowerTaskQuery {time?:number;type?:MowerTaskType;comparison?:'<'|'='|'>';metadata?:string;ignoreRunOrders?:boolean}
export class MowerTaskQueue {
 tasks:MowerTask[]=[]
 /** The no-run-order default scheduling path uses stable time sorting, not type priority. */
 sort():void {this.tasks.sort((a,b)=>Number(!!a.executionFailure)-Number(!!b.executionFailure)||a.timeMicros-b.timeMicros)}
 find(query:MowerTaskQuery={}):MowerTask|undefined {
  const time=query.time===undefined?undefined:toMowerMicros(query.time),comparison=query.comparison??'<'
  return this.tasks.find(task=>!task.executionFailure&&(!query.ignoreRunOrders||!isMowerRunOrderTask(task))&&(comparison==='='?time!==undefined&&Math.abs(task.timeMicros-time)<1_500_000:time===undefined||(comparison==='>'?task.timeMicros>time:task.timeMicros<time))&&(!query.type||task.type===query.type)&&(!query.metadata||task.metadata.includes(query.metadata)))
 }
 /** infra_main removes every reference to the completed object, not every equal task. */
 consume(task:MowerTask):void {this.tasks=this.tasks.filter(t=>t!==task);delete task.backupRefreshRules}
 /** plan_metadata rebuilds these types; active arrangements and experimental locks retain identity. */
 removeDerived(experimental=false):void {this.tasks=this.tasks.filter(t=>t.retainsExecution||t.backupShiftActive||![MOWER_TASK_TYPES.SHIFT_ON,MOWER_TASK_TYPES.RELEASE_DORM].includes(t.type)||experimental&&t.productShiftLocked)}
 /** Default handle_error branch: any queued task strictly inside 2.5h suppresses a fallback. */
 ensureFallback(now:number,options:{adjustForRunOrders?:boolean}={}):MowerTask|undefined {
  if(this.find({time:now+2.5,ignoreRunOrders:options.adjustForRunOrders===false}))return undefined
  if(options.adjustForRunOrders===false&&this.tasks.some(task=>!isMowerRunOrderTask(task)&&task.timeMicros===toMowerMicros(now+2.5)))return undefined
  const task=new MowerTask({time:now+2.5});this.tasks.push(task);return task
 }
}
