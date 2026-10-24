import type { OperatorRecord } from '../domain/operators'
import terms from '../data/riic-term-evidence.json'
// character_table.json v076, SHA256 a060285f7894cc2ec9cebd2e3e5b44211f029b5c57ca3182bb160bf2ccf3ee05.
// Exact subProfessionId=wandermedic; medical profession and faction identity are not substitutes.
const wanderingMedicIds=new Set(['char_4041_chnut','char_473_mberry','char_449_glider','char_4114_harold','char_1016_agoat2'])
export const isWanderingMedic=(op:Pick<OperatorRecord,'charId'>)=>wanderingMedicIds.has(op.charId)
const termTable=terms.terms as Record<string,{description:string}>
const dungeonMembers=new Set(termTable['cc.tag.dungeon']!.description.replace(/^包含以下干员\n/,'').split(/[、\n]/))
export const isLaiosSquad=(op:Pick<OperatorRecord,'name'>)=>dungeonMembers.has(op.name)
