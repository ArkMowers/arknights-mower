import { OPERATORS, type OperatorRecord, type OperatorSkill } from './operators'

export interface OwnedOperatorInput { operator: string; elitePhase: number; level: number }
export interface InventoryDiagnostic { code: string; message: string; line: number }
export interface OwnedOperator {
  charId: string; name: string; elitePhase: number; level: number
  skills: OperatorSkill[]; matchesMaximumSkills: boolean
}
export interface OperatorInventory {
  valid: boolean; operators: OwnedOperator[]; diagnostics: InventoryDiagnostic[]
}
const byReference = new Map(OPERATORS.flatMap(o => [[o.charId, o], [o.name, o]] as const))
// Supplied v076 character_table.json phases[].maxLevel, indexed by displayed rarity.
const levelCaps: Record<number, readonly number[]> = {1:[30],2:[30],3:[40,55],4:[45,60,70],5:[50,70,80],6:[50,80,90]}

/** No imported library means the full operator catalog is available as idle cards. */
export function fullCatalogIdleInventory(): OwnedOperatorInput[] {
  return OPERATORS.map(operator => {
    const caps=levelCaps[operator.rarity]!
    return {operator:operator.charId,elitePhase:caps.length-1,level:caps[caps.length-1]!}
  })
}

export function selectUnlockedSkills(operator: OperatorRecord, elitePhase: number, level: number): OperatorSkill[] {
  const cap = levelCaps[operator.rarity]?.[elitePhase]
  if (!Number.isInteger(elitePhase) || !Number.isInteger(level) || cap === undefined || level < 1 || level > cap) {
    throw new Error(`${operator.name}：无效精英阶段或等级`)
  }
  if (!operator.skillSlots) throw new Error(`${operator.name}：缺少完整技能槽数据`)
  return operator.skillSlots.flatMap(slot => {
    const unlocked = slot.filter(s => s.unlockPhase < elitePhase || (s.unlockPhase === elitePhase && s.unlockLevel <= level))
      .sort((a,b) => a.unlockPhase-b.unlockPhase || a.unlockLevel-b.unlockLevel)
    const selected = unlocked[unlocked.length-1]
    return selected ? [{...selected}] : []
  })
}

/** A missing row means unowned. No stage defaults or promotion assumptions are applied. */
export function compileOperatorInventory(entries: readonly OwnedOperatorInput[]): OperatorInventory {
  const operators: OwnedOperator[] = [], diagnostics: InventoryDiagnostic[] = [], seen = new Set<string>()
  if (!Array.isArray(entries)) return {valid:false,operators,diagnostics:[{code:'INVALID_INVENTORY',line:0,message:'干员库必须为数组'}]}
  entries.forEach((entry, index) => {
    const line = index+1
    const operator = byReference.get(typeof entry?.operator === 'string' ? entry.operator.trim() : '')
    if (!operator) { diagnostics.push({code:'UNKNOWN_OPERATOR',line,message:`第 ${line} 行：未知干员`}); return }
    if (seen.has(operator.charId)) { diagnostics.push({code:'DUPLICATE_OPERATOR',line,message:`第 ${line} 行：${operator.name} 重复录入`}); return }
    seen.add(operator.charId)
    try {
      const skills = selectUnlockedSkills(operator,entry.elitePhase,entry.level)
      operators.push({charId:operator.charId,name:operator.name,elitePhase:entry.elitePhase,level:entry.level,skills,
        matchesMaximumSkills:JSON.stringify(skills) === JSON.stringify(operator.skills)})
    } catch(error) { diagnostics.push({code:'INVALID_STAGE',line,message:`第 ${line} 行：${error instanceof Error ? error.message : String(error)}`}) }
  })
  return {valid:diagnostics.length===0,operators,diagnostics}
}

/** Text interchange: official name or ID, elite phase (0/1/2), level. */
export function parseOperatorInventory(text: string): OperatorInventory & {entries: OwnedOperatorInput[]} {
  const entries: OwnedOperatorInput[] = [], sourceLines: number[] = [], diagnostics: InventoryDiagnostic[] = []
  text.split(/\r?\n/).forEach((line,index) => {
    if (!line.trim()) return
    const fields = line.split(/[,，\t]/).map(s => s.trim())
    if (fields.length!==3 || !/^\d+$/.test(fields[1]!) || !/^\d+$/.test(fields[2]!)) {
      diagnostics.push({code:'INVALID_ROW',line:index+1,message:`第 ${index+1} 行：请填写“干员代号,精英阶段,等级”`}); return
    }
    entries.push({operator:fields[0]!,elitePhase:Number(fields[1]),level:Number(fields[2])});sourceLines.push(index+1)
  })
  const compiled = compileOperatorInventory(entries)
  diagnostics.push(...compiled.diagnostics.map(d => ({...d,line:sourceLines[d.line-1]!,message:d.message.replace(`第 ${d.line} 行`, `第 ${sourceLines[d.line-1]} 行`)})))
  diagnostics.sort((a,b)=>a.line-b.line)
  return {entries,operators:compiled.operators,diagnostics,valid:diagnostics.length===0}
}
