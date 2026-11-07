import {OPERATOR_MAP} from '../domain/operators'

/** User-selected simulation initial condition, independent of saved operator morale. */
export const MOWER_FIAMMETTA_INITIAL_MORALE=16
export const isMowerFiammetta=(name:string)=>(OPERATOR_MAP.get(name)?.name??name)==='菲亚梅塔'
export const mowerInitialMorale=(name:string,fallback=24)=>isMowerFiammetta(name)?MOWER_FIAMMETTA_INITIAL_MORALE:fallback
