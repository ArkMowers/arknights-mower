/** Neutral identities for otherwise unused Free beds in income simulations. */
const PREFIX='mower-dorm-filler:'
export const MOWER_DORM_FILLER_NAME='填充干员'
export const mowerDormFillerId=(room:string,index:number)=>PREFIX+room+':'+index
export const isMowerDormFiller=(name:string)=>name.startsWith(PREFIX)
