// Default init branch of operators.py:547-561, pinned Mower alpha (MIT).
export const MOWER_DORM_ORDER_ERROR='宿舍优先级和当前宿舍不匹配，请清除优先级自动排序或者自己更正'
export function mowerDormOrderError(order:string,ids:string[]):string|undefined{
 const names=order.split(',').filter(Boolean)
 if(!names.length)return undefined
 const configured=new Set(names),current=new Set(ids)
 return configured.size===current.size&&[...current].every(id=>configured.has(id))?undefined:MOWER_DORM_ORDER_ERROR
}
export function orderMowerRecoveryBeds<T extends {id:string;roomId:string;vip:boolean}>(beds:T[],order:string):T[]{
 const names=order.split(',').filter(Boolean)
 if(!names.length)return beds
 const error=mowerDormOrderError(order,beds.map(b=>b.id))
 if(error)throw new Error(error)
 const count=new Set(beds.map(b=>b.roomId)).size
 return [...beds].sort((a,b)=>names.indexOf(a.id)-names.indexOf(b.id)).map((bed,index)=>({...bed,vip:index<count}))
}
