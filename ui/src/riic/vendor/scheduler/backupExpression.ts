// Mower logic_expression.py serializes (left operator right) before evaluation.
// This interpreter preserves that syntax without evaluating imported Python/JS.
import { OPERATOR_MAP } from '../domain/operators'
import { MOWER_INVENTORY_ITEMS } from '../domain/simulationInventory'
import { resolveOperatorCharId } from '../domain/operatorIdentifiers'
import type { RuntimeState } from './rosterRuntime'
import type {MowerDateTimeValue} from './mowerSchedulingData'
import {toMowerMicros} from './mowerTaskQueue'

type Value = string | number | boolean | null | MowerDateTimeValue
type Expression = (state: RuntimeState) => Value
type Token = { text: string; kind: 'operator' | 'value' | 'worker' | 'external' | 'query'; value?: Value; name?: string; member?: string }
const roomName = /^(?:room_[1-3]_[1-3]|dormitory_[1-4]|central|meeting|factory|contact|train|recycle)$/
// Inventory queries: Mower 3de2b2ac; facility-product counts: 3ad69f15 Operators (MIT).
const inventoryNames = new Set<string>(MOWER_INVENTORY_ITEMS.map(item => item.name))
const facilityProducts = new Set(['gold', 'exp3', 'orirock', 'orirock_device', 'lmd', 'orundum'])
const facilityRoomName = /^(?:room_[1-3]_[1-3]|dormitory_[1-4]|gaming_[1-3]|central|meeting|factory|contact|train|recycle)$/
const fail = (message: string): never => { throw new Error(`副表：${message}`) }

export function actualRoom(state: RuntimeState, id: string): string {
  const position = state.config.positions.find(p => state.occupants[p.id] === id)
  return position?.roomId ?? state.config.beds.find(b => state.bedOccupants[b.id] === id)?.roomId ?? ''
}

function serialize(source: unknown, depth = 0, budget = { nodes: 0 }): string {
  if (depth > 32 || ++budget.nodes > 512) return fail('条件树超过限制')
  if (typeof source === 'string') {
    if (source.length > 20000) return fail('条件文本超过限制')
    return source
  }
  if (typeof source === 'boolean') return source ? 'True' : 'False'
  if (typeof source === 'number' && Number.isFinite(source)) return String(source)
  if (!source || typeof source !== 'object' || Array.isArray(source)) return fail('条件必须为表达式树')
  const node = source as Record<string, unknown>
  if ('function' in node) {
    const name = String(node.function)
    if (!['max', 'min', 'sum', 'any', 'all', 'abs'].includes(name) || !Array.isArray(node.args) || !node.args.length) return fail('不支持的函数或参数为空')
    if (name === 'abs' && node.args.length !== 1) return fail('abs 条件只接受一项参数')
    let args = node.args.map(arg => serialize(arg, depth + 1, budget)).join(', ')
    if (['sum', 'any', 'all'].includes(name) || (['max', 'min'].includes(name) && node.args.length === 1)) args = `[${args}]`
    const text = `${name}(${args})`
    if (text.length > 20000) return fail('条件文本超过限制')
    return text
  }
  const text = `(${serialize(node.left ?? '', depth + 1, budget)} ${serialize(node.operator ?? '', depth + 1, budget)} ${serialize(node.right ?? '', depth + 1, budget)})`
  if (text.length > 20000) return fail('条件文本超过限制')
  return text
}

function tokenize(text: string): Token[] {
  const tokens: Token[] = []
  for (let rest = text.trim(); rest; rest = rest.trimStart()) {
    if (tokens.length >= 1024) return fail('条件文本超过限制')
    const worker = /^op_data\.operators\[['"]([^'"\[\]]+)['"]\]\.(is_resting\(\)|is_working\(\)|current_mood\(\)|current_room|current_index|room|index|mood|upper_limit|lower_limit|group|workaholic|exhaust_require|rest_in_full|operator_type|resting_priority)\b/.exec(rest) ?? /^op_data\.operators\[['"]([^'"\[\]]+)['"]\]\.(is_resting\(\)|is_working\(\)|current_mood\(\))/.exec(rest)
    const query = /^op_data\.(group_min_mood|group_max_mood|facility_has_mastery_plan|facility_is_training|inventory_count|facility_product_count|facility_product_type_count|facility_product)\b/.exec(rest)
    const external = /^op_data\.(?:party_time\b|major_maintenance_remaining_hours\(\))/.exec(rest)
    const quoted = /^(['"])((?:\\.|(?!\1)[^\\])*)\1/.exec(rest)
    const number = /^(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?/.exec(rest)
    const word = /^(?:and|or|not|is|in|True|False|None)\b/.exec(rest)
    const symbol = /^(?:==|!=|<=|>=|[<>+*/(),\[\]\-])/.exec(rest)
    const aggregate = /^(?:max|min|sum|any|all|abs)\b/.exec(rest)
    const room = /^(?:room_[1-3]_[1-3]|dormitory_[1-4]|gaming_[1-3]|central|meeting|factory|contact|train|recycle)\b/.exec(rest)
    const product = /^(?:orirock_device|orirock|orundum|gold|exp3|lmd)\b/.exec(rest)
    let token: Token
    if (worker) token = { text: worker[0], kind: 'worker', name: worker[1], member: worker[2] }
    else if (query) token = { text: query[0], kind: 'query', member: query[1] }
    else if (external) token = { text: external[0], kind: 'external' }
    else if (quoted) token = { text: quoted[0], kind: 'value', value: quoted[2]!.replace(/\\(['"\\nrt])/g, (_, c: string) => ({ n: '\n', r: '\r', t: '\t' }[c] ?? c)) }
    else if (number && Number.isFinite(Number(number[0]))) token = { text: number[0], kind: 'value', value: Number(number[0]) }
    else if (word) token = ['True', 'False', 'None'].includes(word[0])
      ? { text: word[0], kind: 'value', value: word[0] === 'None' ? null : word[0] === 'True' }
      : { text: word[0], kind: 'operator' }
    else if (symbol) token = { text: symbol[0], kind: 'operator' }
    else if (aggregate) token = { text: aggregate[0], kind: 'operator' }
    else if (product) token = { text: product[0], kind: 'value', value: product[0] }
    else if (room) token = { text: room[0], kind: 'value', value: room[0] }
    else return fail(`不支持的条件 ${rest.slice(0, 120)}`)
    tokens.push(token); rest = rest.slice(token.text.length)
  }
  return tokens
}

export function compileBackupExpression(source: unknown, participants: Set<string>): { evaluate: Expression; usesCurrentMood: boolean; usesMajorMaintenance: boolean; usesMasteryPlan: boolean; usesInventory: boolean; usesFacilityProduct: boolean; observedOperatorDependenciesOnly: boolean; skipped?: string } {
  const tokens = tokenize(serialize(source))
  let cursor = 0, nesting = 0
  const peek = () => tokens[cursor]?.text
  const take = (text: string) => peek() === text ? (++cursor, true) : false
  const numeric = (value: Value) => typeof value === 'number' ? value : typeof value === 'boolean' ? Number(value) : fail('比较/算术运算需要数字')
  const binary = (left: Expression, right: Expression, op: string): Expression => state => {
    const a = left(state)
    if (op === 'and') return a ? right(state) : a
    if (op === 'or') return a ? a : right(state)
    const b = right(state)
    if (op === 'is' || op === 'is not') return op === 'is' ? a === b : a !== b
    if (op === '==' || op === '!=') {
      const numbers=(typeof a==='boolean'||typeof a==='number')&&(typeof b==='boolean'||typeof b==='number')
      const dates=a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'
      const equal=numbers?numeric(a)===numeric(b):dates?a.timeMicros===b.timeMicros:a===b
      return op==='=='?equal:!equal
    }
    if (op === 'in' || op === 'not in') {
      if (typeof a !== 'string' || typeof b !== 'string') return fail('成员比较仅支持字符串')
      return op === 'in' ? b.includes(a) : !b.includes(a)
    }
    const x = numeric(a), y = numeric(b)
    if (op === '<') return x < y
    if (op === '<=') return x <= y
    if (op === '>') return x > y
    if (op === '>=') return x >= y
    const value = op === '+' ? x + y : op === '-' ? x - y : op === '*' ? x * y : x / y
    if (!Number.isFinite(value)) return fail('条件运算结果不是有限数')
    return value
  }
  function atom(): Expression {
    if (++nesting > 64) return fail('条件嵌套超过限制')
    try {
      if (['max', 'min', 'sum', 'any', 'all', 'abs'].includes(peek() ?? '')) {
        const name = tokens[cursor++]!.text
        if (!take('(')) return fail(`${name} 缺少参数括号`)
        const list = ['sum', 'any', 'all'].includes(name) || (['max', 'min'].includes(name) && peek() === '[')
        if (list && !take('[')) return fail(`${name} 需要参数列表`)
        const args = [logicalOr()]
        while (take(',')) args.push(logicalOr())
        if (list && !take(']')) return fail(`${name} 参数列表不完整`)
        if (['max', 'min'].includes(name) && !list && args.length < 2) return fail(`${name} 需要至少两项参数`)
        if (name === 'abs' && args.length !== 1) return fail('abs 条件只接受一项参数')
        if (!take(')')) return fail(`${name} 参数括号不完整`)
        if (name === 'abs') return state => Math.abs(numeric(args[0]!(state)))
        if (['sum', 'any', 'all'].includes(name)) return state => {
          const values = args.map(arg => arg(state))
          if (name === 'any') return values.some(Boolean)
          if (name === 'all') return values.every(Boolean)
          const result = values.reduce<number>((sum, value) => sum + numeric(value), 0)
          if (!Number.isFinite(result)) return fail('条件运算结果不是有限数')
          return result
        }
        return state => args.map(arg => arg(state)).reduce((a, b) => {
          if (typeof a === 'string' && typeof b === 'string') return (name === 'max' ? a >= b : a <= b) ? a : b
          const x = numeric(a), y = numeric(b)
          return (name === 'max' ? x >= y : x <= y) ? a : b
        })
      }
      if (take('(')) {
        if (take(')')) return () => false // Mower's empty tuple is false.
        const expr = logicalOr()
        if (!take(')')) return fail('条件括号不完整')
        return expr
      }
      if (take('+')) { const expr = atom(); return state => numeric(expr(state)) }
      if (take('-')) { const expr = atom(); return state => -numeric(expr(state)) }
      const token = tokens[cursor++]
      if (token?.kind === 'value') return () => token.value!
      if (token?.kind === 'query') {
        if (!take('(')) return fail(`${token.member} 缺少参数括号`)
        if (token.member === 'facility_product_type_count') {
          if (!take(')')) return fail('facility_product_type_count 不接受参数')
          return state => {
            const products = state.mowerFacilityProducts
            if (!products) return fail('缺少设施产物状态')
            return new Set(Object.values(products).filter(product => product !== null && facilityProducts.has(product))).size
          }
        }
        const argument = tokens[cursor++]
        if (argument?.kind !== 'value' || typeof argument.value !== 'string' || !take(')')) return fail(`${token.member} 需要一个字符串参数`)
        const name = argument.value
        if (token.member === 'inventory_count') {
          if (!inventoryNames.has(name)) return fail(`不支持的副表仓库资源：${name}`)
          return state => {
            const inventory = state.mowerInventoryCounts
            if (!inventory) return fail('缺少库存状态；请预设初始物品数量')
            const count = Object.prototype.hasOwnProperty.call(inventory, name) ? inventory[name]! : 0
            if (!Number.isFinite(count) || count < 0) return fail(`库存数量必须为非负有限数：${name}`)
            return count
          }
        }
        if (token.member === 'facility_product_count') {
          if (!facilityProducts.has(name)) return fail(`不支持的产物或订单类型：${name}`)
          return state => {
            const products = state.mowerFacilityProducts
            if (!products) return fail('缺少设施产物状态')
            return Object.values(products).filter(product => product === name).length
          }
        }
        if (token.member === 'facility_product') {
          if (!facilityRoomName.test(name)) return fail(`不支持的设施位置：${name}`)
          return state => {
            const products = state.mowerFacilityProducts
            if (!products) return fail('缺少设施产物状态')
            return Object.prototype.hasOwnProperty.call(products, name) ? products[name] ?? null : null
          }
        }
        if (token.member === 'facility_has_mastery_plan' || token.member === 'facility_is_training') {
          if (name !== 'train') return fail(`不支持的训练室位置：${name}`)
          // Local simulation assumes no unfinished training plan or active training.
          return () => false
        }
        // Alpha _group_moods uses the current effective group and only fixed work anchors.
        return state => {
          const data = state.mowerSource?.data
          if (!data) return fail('缺少绑组心情观测状态')
          const members = name ? data.group(name) : []
          if (!members.length) return fail(`不存在的绑组：${name}`)
          const anchors = members.map(member => data.operators[member]!).filter(op => data.isGroupShiftAnchor(op))
          if (!anchors.length) return fail(`绑组内没有可统计心情的干员：${name}`)
          const moods = anchors.map(op => op.currentMood(toMowerMicros(state.time)))
          return token.member === 'group_max_mood' ? Math.max(...moods) : Math.min(...moods)
        }
      }
      if (token?.kind === 'external') {
        if (token.text === 'op_data.major_maintenance_remaining_hours()') return state => {const remaining=(state.config.majorMaintenanceStartHours??Infinity)-state.time;return remaining>0?remaining:Infinity}
        return state => state.mowerSource?.data.partyTime ?? null
      }
      if (token?.kind === 'worker') {
        const id = resolveOperatorCharId(token.name!)
        if (!OPERATOR_MAP.has(id)) return fail(`未知干员 ${token.name}`)
        participants.add(id)
        return state => {
          const observed=state.mowerSource?.data.operators[id]
          const room = observed?.currentRoom??actualRoom(state, id)
          if (token.member === 'is_resting()') return room.startsWith('dormitory_')
          if (token.member === 'is_working()') return roomName.test(room) && !room.startsWith('dormitory_')
          if (token.member === 'current_room') return room
          if(token.member==='room')return observed?.room??state.config.positions.find(p=>p.primary===id)?.roomId??''
          if(token.member==='index'){const parts=state.config.positions.find(p=>p.primary===id)?.id.split('_');return observed?.index??Number(parts?.[parts.length-1]??-1)}
          if(token.member==='current_index')return observed?.currentIndex??-1
          if(token.member==='mood')return observed?.mood??state.morale[id]??24
          if(token.member==='upper_limit')return observed?.upperLimit??24
          if(token.member==='lower_limit')return observed?.lowerLimit??0
          if(token.member==='group')return observed?.group??''
          if(token.member==='workaholic')return observed?.workaholic??false
          if(token.member==='exhaust_require')return observed?.exhaustRequire??false
          if(token.member==='rest_in_full')return observed?.restInFull??false
          if(token.member==='operator_type')return observed?.operatorType??'low'
          if(token.member==='resting_priority')return observed?.restingPriority??'low'
          if(observed)return observed.currentMood(toMowerMicros(state.time))
          return state.morale[id] ?? fail(`缺少 ${token.name} 的心情`)
        }
      }
      return fail(`不支持的条件 ${token?.text ?? '空操作数'}`)
    } finally { nesting-- }
  }
  function product(): Expression {
    let expr = atom()
    while (peek() === '*' || peek() === '/') { const op = tokens[cursor++]!.text; expr = binary(expr, atom(), op) }
    return expr
  }
  function sum(): Expression {
    let expr = product()
    while (peek() === '+' || peek() === '-') { const op = tokens[cursor++]!.text; expr = binary(expr, product(), op) }
    return expr
  }
  function comparison(): Expression {
    const operands = [sum()], operators: string[] = []
    while (['==', '!=', '<', '<=', '>', '>=', 'is', 'in', 'not'].includes(peek() ?? '')) {
      let op = tokens[cursor++]!.text
      if (op === 'is' && take('not')) op = 'is not'
      else if (op === 'not') { if (!take('in')) return fail('not 后缺少 in'); op = 'not in' }
      operators.push(op); operands.push(sum())
    }
    if (!operators.length) return operands[0]!
    return state => {
      let left = operands[0]!(state)
      for (let i = 0; i < operators.length; i++) {
        const right = operands[i + 1]!(state)
        if (!binary(() => left, () => right, operators[i]!)(state)) return false
        left = right
      }
      return true
    }
  }
  function negation(): Expression {
    let count = 0
    while (take('not')) count++
    const expr = comparison()
    return count ? state => count % 2 ? !expr(state) : Boolean(expr(state)) : expr
  }
  function logicalAnd(): Expression { let expr = negation(); while (take('and')) expr = binary(expr, negation(), 'and'); return expr }
  function logicalOr(): Expression { let expr = logicalAnd(); while (take('or')) expr = binary(expr, logicalAnd(), 'or'); return expr }
  const evaluate = tokens.length ? logicalOr() : () => false
  if (cursor !== tokens.length) return fail(`条件存在未解析内容 ${peek()}`)
  const usesMajorMaintenance = tokens.some(token => token.kind === 'external' && token.text === 'op_data.major_maintenance_remaining_hours()')
  return {
    evaluate, usesMajorMaintenance,
    observedOperatorDependenciesOnly:tokens.some(token=>token.kind==='worker')&&tokens.every(token=>token.kind==='operator'||token.kind==='value'||token.kind==='worker'&&['is_working()','is_resting()','current_room','current_index','room','index','current_mood()','mood'].includes(token.member!)),
    usesInventory: tokens.some(token=>token.kind==='query'&&token.member==='inventory_count'),
    usesFacilityProduct: tokens.some(token=>token.kind==='query'&&['facility_product','facility_product_count','facility_product_type_count'].includes(token.member!)),
    usesMasteryPlan: tokens.some(token=>token.kind==='query'&&['facility_has_mastery_plan','facility_is_training'].includes(token.member!)),
    usesCurrentMood: tokens.some(token=>token.kind==='worker'&&token.member==='current_mood()'||token.kind==='query'&&['group_min_mood','group_max_mood'].includes(token.member!)),
  }
}
