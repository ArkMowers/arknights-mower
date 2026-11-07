// Pydantic Plan1/Task field order, consumed by native model_dump/build_global_plan.
// Source: c6bdbb292fe7fcd84c6dfb66154a12a1a9bc5b88 (MIT, Copyright 2021 Nano).
// Recycle insertion: 9091f2b6b4da2a2fb66c47881a47b82dc0885ad7, plan.py:174-205.
export const MOWER_PLAN_ROOM_ORDER = [
 'central','meeting','factory','contact','train','recycle','gaming_1','gaming_2','gaming_3',
 'dormitory_1','dormitory_2','dormitory_3','dormitory_4',
 'room_1_1','room_1_2','room_1_3','room_2_1','room_2_2','room_2_3','room_3_1','room_3_2','room_3_3',
] as const
const indexes=new Map<string,number>(MOWER_PLAN_ROOM_ORDER.map((room,index)=>[room,index]))
export function mowerPlanEntries<T>(plan:Record<string,T>):[string,T][] {
 return Object.entries(plan).sort(([left],[right])=>(indexes.get(left)??Infinity)-(indexes.get(right)??Infinity))
}
