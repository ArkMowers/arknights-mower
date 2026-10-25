/** Bounded ordinary-shift policy. Times are absolute seconds on an explicit virtual clock. */
export const MOWER_MOOD_CONTROL_VERSION='predictive-mood-control-v1'
export interface MoodControlEvent {time:number;type:'departure-start'|'departure-complete'|'return-start'|'return-complete';group:string;resources:string[]}
export interface MoodControlResult {
 decision:string|null;status:'feasible'|'insufficient'|'budget-exhausted';score:number[];events:MoodControlEvent[]
 candidates:number;enumeratedCandidates:number;processedNodes:number;eventCount:number;maxCandidateNodes:number;nextWake:number|null
}
const compare=(a:readonly number[],b:readonly number[])=>{for(let i=0;i<a.length;i++){if(a[i]!==b[i])return a[i]!-b[i]!}return 0}
export interface MoodControlCandidate {group?:string;start?:number}
export interface MoodControlRollout {complete:boolean;score:number[];exhausted?:boolean;nodes?:number;events?:readonly unknown[]}
/** Both adapters use one stable candidate order, hard-limit exclusion and bounded selection. */
export function selectMoodControlCandidate<R extends MoodControlRollout>(now:number,groups:readonly {id:string;lowerAt:number;softAt:number;exhaust?:boolean;protected?:boolean}[],boundaries:readonly number[],rollout:(candidate:MoodControlCandidate)=>R,maxCandidates=16,maxNodes=64):{best:R;selected?:MoodControlCandidate;candidates:number;enumeratedCandidates:number;processedNodes:number;events:number;maxCandidateNodes:number;exhausted:boolean} {
 const ordered=groups.map((g,index)=>({g,index})).sort((a,b)=>a.g.lowerAt-b.g.lowerAt||a.index-b.index)
 const starts=[...new Set([now,...boundaries])].filter(t=>t>=now).sort((a,b)=>a-b)
 const choices:MoodControlCandidate[]=[];let truncated=false
 for(const {g} of ordered)if(!g.exhaust&&!g.protected)for(const start of starts)if(start<g.softAt){if(choices.length+1<maxCandidates)choices.push({group:g.id,start});else truncated=true}
 const baseline=rollout({});let best=baseline,selected:MoodControlCandidate|undefined,candidates=1,processedNodes=Math.min(maxNodes,baseline.nodes??0),events=baseline.events?.length??0,maxCandidateNodes=baseline.nodes??0,exhausted=!!baseline.exhausted||truncated
 for(const candidate of exhausted?[]:choices){
  const result=rollout(candidate);candidates++;processedNodes+=Math.min(maxNodes,result.nodes??0);events+=result.events?.length??0;maxCandidateNodes=Math.max(maxCandidateNodes,result.nodes??0);exhausted ||= !!result.exhausted
  if(exhausted)break
  if(result.complete&&compare(result.score.slice(0,2),baseline.score.slice(0,2))<0&&compare(result.score,best.score)<0){best=result;selected=candidate}
 }
 if(exhausted){best=baseline;selected=undefined}
 return {best,selected,candidates,enumeratedCandidates:choices.length+1,processedNodes,events,maxCandidateNodes,exhausted}
}
