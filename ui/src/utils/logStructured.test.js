import { describe, expect, it } from 'vitest'
import { createLogPresenter } from './logPresentation.js'
import {
  facilityArrangement,
  facilityLifecycle,
  lifecycleKey,
  logLifecycles,
  orderRead,
  productionSwitch,
  rescueStaffing,
  rescueParent,
  rescueGroups,
  idleResetName,
  inventoryItems,
  stageLogMatches,
  trainingPositions
} from './logStructured.js'

const present = createLogPresenter([])
const line = (body, fields = {}) => ({ text: `2026-11-05 12:00:00 INFO ${body}`, ...fields })

describe('explicit log observations', () => {
  const rescue = {
    type: 'rescue-staffing',
    id: 'rescue-1',
    phase: 'queued',
    anchor: true,
    rooms: [
      { room: 'meeting', label: '会客室', agents: ['Current', '', '桑葚'], status: 'pending' }
    ]
  }
  it('validates rescue snapshots and explicit parent scopes without inventing completion', () => {
    expect(rescueStaffing(rescue)).toEqual(rescue)
    for (const fields of [
      { anchor: false },
      { id: ' ' },
      { rooms: [] },
      { rooms: [rescue.rooms[0], rescue.rooms[0]] },
      { phase: 'completed', anchor: false },
      { detail: 'queued cannot fail' }
    ])
      expect(rescueStaffing({ ...rescue, ...fields })).toBeNull()
    const parent = { type: 'rescue-staffing', id: rescue.id, room: 'meeting', attempt: 'a' }
    expect(rescueParent(parent)).toEqual(parent)
    expect(rescueParent({ type: parent.type, id: parent.id })).toEqual({
      type: parent.type,
      id: parent.id
    })
    expect(rescueParent({ ...parent, attempt: undefined })).toBeNull()
  })
  it('keeps the first rescue anchor through failure and a real retry but never revives completed work', () => {
    const status = (phase, state) => ({
      ...rescue,
      phase,
      anchor: false,
      rooms: [{ ...rescue.rooms[0], status: state }]
    })
    const started = status('started', 'active'),
      failed = status('failed', 'unconfirmed'),
      completed = status('completed', 'completed')
    const lines = [rescue, started, failed, started, completed, started].map((event) => ({ event }))
    const result = logLifecycles(lines)
    expect(result.anchors.get(0)).toEqual(completed)
    expect([...result.sourceOnly]).toEqual([1, 2, 3, 4])
    expect(result.pendingKeys.size).toBe(0)
    expect(logLifecycles([{ event: started }]).anchors.size).toBe(0)
    expect(
      logLifecycles([
        { event: rescue },
        { event: { ...started, rooms: [{ ...started.rooms[0], agents: ['陈'] }] } }
      ]).anchors.get(0)
    ).toEqual(rescue)
  })
  it('keeps explicit pre-entry diagnostics with their parent without creating a facility attempt', () => {
    const root = { type: 'rescue-staffing', id: rescue.id },
      scope = { ...root, room: 'meeting', attempt: 'not-entered' }
    const lines = [
      { event: rescue, parent: scope },
      { text: '前置保护未通过', parent: scope },
      { text: '根失败原因', parent: root },
      { text: '未知设施', parent: { ...scope, room: 'train' } },
      { text: '另一任务', parent: { ...scope, id: 'other' } }
    ]
    const state = rescueGroups(lines, logLifecycles(lines))
    expect([...state.members.keys()]).toEqual([1, 2])
    expect(state.groups.get(rescue.id).attempts.size).toBe(0)
    expect(state.groups.get(rescue.id).unanchored.get('meeting')).toEqual([1])
    expect(state.groups.get(rescue.id).roots).toEqual([2])
  })
  it('does not let a terminal record from another parent or an unscoped replay finish a scoped facility attempt', () => {
    const event = {
      type: 'facility-arrangement',
      id: 'same-attempt',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const parent = { type: 'rescue-staffing', id: 'A', room: event.room, attempt: event.id }
    const completed = { ...event, phase: 'completed', anchor: false }
    for (const foreign of [undefined, { ...parent, id: 'B' }]) {
      const result = logLifecycles([
        { event, parent },
        { event: completed, parent: foreign }
      ])
      expect(result.anchors.get(0)).toEqual(event)
      expect(result.sourceOnly.has(1)).toBe(false)
    }
  })
  const orders = {
    type: 'order-read',
    id: 'orders-1',
    phase: 'started',
    anchor: true,
    after_switch: true,
    rooms: [
      { room: 'room_1_1', label: '贸易站 B101', status: 'pending' },
      { room: 'room_2_1', label: '贸易站 B201', status: 'pending' }
    ]
  }
  it('requires a bounded explicit order cohort and status-compatible phases', () => {
    expect(orderRead(orders)).toEqual(orders)
    for (const fields of [
      { id: '' },
      { id: 'x'.repeat(129) },
      { anchor: false },
      { after_switch: 1 },
      { rooms: [] },
      { rooms: Array(33).fill(orders.rooms[0]) },
      { rooms: [orders.rooms[0], orders.rooms[0]] },
      { rooms: [{ ...orders.rooms[0], label: '' }] },
      { rooms: [{ ...orders.rooms[0], status: 'unknown' }] },
      { phase: 'completed', anchor: false },
      { phase: 'started', rooms: [{ ...orders.rooms[0], status: 'read' }] },
      { phase: 'updated', anchor: false, rooms: [{ ...orders.rooms[0], status: 'paused' }] },
      { detail: 'only a failure has detail' }
    ])
      expect(orderRead({ ...orders, ...fields })).toBeNull()
    expect(
      orderRead({
        ...orders,
        phase: 'completed',
        anchor: false,
        rooms: orders.rooms.map((room) => ({ ...room, status: 'paused' }))
      })?.phase
    ).toBe('completed')
    expect(
      orderRead({ ...orders, phase: 'failed', anchor: false, detail: 'x'.repeat(2049) })
    ).toBeNull()
  })
  it('updates only its exact order cohort and keeps partial reads pending', () => {
    const updated = {
      ...orders,
      phase: 'updated',
      anchor: false,
      rooms: [{ ...orders.rooms[0], status: 'read' }, orders.rooms[1]]
    }
    const completed = {
      ...orders,
      phase: 'completed',
      anchor: false,
      rooms: orders.rooms.map((room) => ({ ...room, status: 'read' }))
    }
    const lines = [
      { event: orders },
      { event: updated },
      { event: { ...completed, after_switch: false } },
      { event: { ...completed, rooms: [completed.rooms[0]] } },
      { event: { ...completed, rooms: [...completed.rooms].reverse() } }
    ]
    let result = logLifecycles(lines)
    expect(result.anchors.get(0)).toEqual(updated)
    expect([...result.sourceOnly]).toEqual([1])
    expect(result.latestKey).toBe(lifecycleKey(orders))
    lines.push({ event: completed }, { event: updated })
    result = logLifecycles(lines)
    expect(result.anchors.get(0)).toEqual(completed)
    expect(result.latestKey).toBeNull()
    expect([...result.sourceOnly]).toEqual([1, 5])
    expect(logLifecycles([{ event: completed }]).anchors.size).toBe(0)
  })
  const production = {
    type: 'production-switch',
    id: 'production-1',
    phase: 'started',
    anchor: true,
    room: 'room_1_2',
    label: '制造站 B102',
    facility: 'manufacture',
    product: '赤金'
  }
  it('accepts only bounded typed production observations with matching anchor phases', () => {
    expect(productionSwitch(production)).toEqual(production)
    expect(productionSwitch({ ...production, previous: '中级作战记录' })?.previous).toBe(
      '中级作战记录'
    )
    for (const fields of [
      { type: 'facility-arrangement' },
      { id: ' ' },
      { room: 'x'.repeat(129) },
      { label: '' },
      { facility: 'dormitory' },
      { product: 'x'.repeat(257) },
      { previous: null },
      { previous: '' },
      { anchor: undefined },
      { anchor: false },
      { phase: 'done' },
      { detail: 'not a waiting phase' }
    ])
      expect(productionSwitch({ ...production, ...fields })).toBeNull()
    const wait = {
      ...production,
      phase: 'waiting',
      anchor: false,
      detail: '无人机数量不足，预计 26 秒后可满足整批加速计划'
    }
    expect(productionSwitch(wait)).toEqual(wait)
    expect(productionSwitch({ ...wait, detail: undefined })).toBeNull()
    expect(productionSwitch({ ...wait, detail: 'x'.repeat(2049) })).toBeNull()
  })
  it('keeps production identities separate from facilities and other targets and resumes the first anchor', () => {
    const facility = {
      type: 'facility-arrangement',
      id: production.id,
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const lines = [
      { event: facility },
      { event: production },
      {
        event: {
          ...production,
          phase: 'waiting',
          anchor: false,
          previous: '中级作战记录',
          detail: '真实等待原因'
        }
      },
      { event: { ...production, phase: 'completed', anchor: false, product: '中级作战记录' } },
      { event: { ...production, previous: '赤金' } }
    ]
    let result = logLifecycles(lines)
    expect(result.latestKey).toBe(lifecycleKey(production))
    expect([...result.sourceOnly]).toEqual([2, 4])
    expect(result.anchors.get(1)).toMatchObject({ phase: 'started', previous: '中级作战记录' })
    expect(result.details.size).toBe(0)
    lines.push({ event: { ...production, phase: 'completed', anchor: false } })
    result = logLifecycles(lines)
    expect(result.latestKey).toBe(lifecycleKey(facility))
    expect(result.anchors.get(1)?.phase).toBe('completed')
  })
  it('does not invent an anchor from an orphan result or restart a completed production switch from a late wait', () => {
    const completed = { ...production, phase: 'completed', anchor: false }
    expect(logLifecycles([{ event: completed }]).anchors.size).toBe(0)
    const result = logLifecycles([
      { event: production },
      { event: completed },
      { event: { ...production, phase: 'waiting', anchor: false, detail: '旧等待记录' } }
    ])
    expect(result.anchors.get(0)?.phase).toBe('completed')
    expect(result.latestKey).toBeNull()
    expect([...result.sourceOnly]).toEqual([1])
  })
  it('matches only an explicitly recorded stage code and bounded main-drop names', () => {
    const text = '固源岩库存已达到设定上限，本轮跳过1-7'
    const event = { type: 'stage-inventory-limit', stage: { code: '1-7', drops: ['固源岩'] } }
    expect(stageLogMatches(text, event)).toEqual([
      { type: 'stage', start: 17, end: 20, text: '1-7', code: '1-7', drops: ['固源岩'] }
    ])
    for (const value of [
      null,
      { ...event, type: 'other' },
      { ...event, stage: { code: 'CE-6', drops: ['龙门币'] } },
      { ...event, stage: { code: '1-7', drops: [''] } }
    ])
      expect(stageLogMatches(text, value)).toEqual([])
    expect(stageLogMatches(text + '；1-7', event)).toEqual([])
  })
  it('links only the exact selected-stage suffix of a ratio decision even when its rule repeats the code', () => {
    const message =
      '比例规则「PR-B-1 芯片储备」的刷取比例相同（1:1），优先刷取库存相对不足的材料，本轮选择 PR-B-1'
    const event = {
      type: 'stage-inventory-ratio',
      stage: { code: 'PR-B-1', drops: ['狙击芯片', '术师芯片'] }
    }
    expect(stageLogMatches(message, event)).toEqual([
      {
        type: 'stage',
        start: message.length - 6,
        end: message.length,
        text: 'PR-B-1',
        code: 'PR-B-1',
        drops: ['狙击芯片', '术师芯片']
      }
    ])
    const presented = present(message, null, null, null, null, null, event)
    expect(presented.tokens.filter((token) => token.type === 'stage')).toHaveLength(1)
    expect(presented.tokens.map((token) => token.text).join('')).toBe(message)
    for (const invalid of [message + ' ', message + '。', message.replace(/PR-B-1$/u, 'PR-B-2')])
      expect(stageLogMatches(invalid, event)).toEqual([])
    expect(stageLogMatches(message, { ...event, stage: { code: 'PR-B-1', drops: [''] } })).toEqual(
      []
    )
    expect(stageLogMatches(message, { ...event, type: 'stage-inventory-limit' })).toEqual([])
  })
  it('locates an ordered stage plan without merging duplicates, overlapping codes or virtual aliases', () => {
    const message = '接下来计划依次刷取当期剿灭 → 1-7 → 1-7-HARD → 1-7 → 上次作战'
    const event = {
      type: 'stage-inventory-plan',
      stages: [
        { code: 'Annihilation', label: '当期剿灭', drops: [] },
        { code: '1-7', label: '1-7', drops: ['固源岩'] },
        { code: '1-7-HARD', label: '1-7-HARD', drops: [] },
        { code: '1-7', label: '1-7', drops: ['固源岩'] },
        { code: '', label: '上次作战', drops: [] }
      ]
    }
    expect(
      stageLogMatches(message, event).map(({ start, end, text }) => ({ start, end, text }))
    ).toEqual([
      { start: 16, end: 19, text: '1-7' },
      { start: 22, end: 30, text: '1-7-HARD' },
      { start: 33, end: 36, text: '1-7' }
    ])
    const presented = present(message, null, null, null, null, null, event)
    expect(
      presented.tokens.filter((token) => token.type === 'stage').map((token) => token.code)
    ).toEqual(['1-7', '1-7-HARD', '1-7'])
    expect(presented.tokens.map((token) => token.text).join('')).toBe(message)
    expect(stageLogMatches(message + '。', event)).toEqual([])
    expect(stageLogMatches(message.replace(' → ', ' -> '), event)).toEqual([])
  })
  it('rejects mismatched plan metadata and never invents fixed drops for virtual stages', () => {
    const concrete = { code: 'PR-B-1', label: 'PR-B-1', drops: ['狙击芯片', '术师芯片'] }
    const event = { type: 'stage-inventory-plan', stages: [concrete] }
    expect(stageLogMatches('接下来计划依次刷取PR-B-1', event).map((token) => token.code)).toEqual([
      'PR-B-1'
    ])
    for (const stages of [
      [{ ...concrete, label: 'PR-B-2' }],
      [{ ...concrete, code: 'Annihilation', label: '当期剿灭' }],
      [{ ...concrete, code: '', label: '上次作战' }],
      [{ ...concrete, drops: [''] }],
      Array(129).fill(concrete)
    ])
      expect(
        stageLogMatches('接下来计划依次刷取' + stages.map((stage) => stage.label).join(' → '), {
          ...event,
          stages
        })
      ).toEqual([])
    expect(stageLogMatches('当前没有待刷关卡', { ...event, stages: [] })).toEqual([])
  })
  it('retains trainee and assistant positions only when their source is explicit and unambiguous', () => {
    const event = {
      type: 'training-selection',
      positions: [
        { agent: '夜莺', index: 0 },
        { agent: '艾雅法拉', index: 1 }
      ]
    }
    expect(trainingPositions(event)).toEqual(event.positions)
    for (const value of [
      { ...event, positions: [{ agent: '夜莺', index: 2 }] },
      {
        ...event,
        positions: [
          { agent: '夜莺', index: 0 },
          { agent: '艾雅法拉', index: 0 }
        ]
      },
      { ...event, type: 'facility-arrangement', room: 'meeting' }
    ])
      expect(trainingPositions(value)).toBeNull()
  })
  it('accepts only a bounded explicit facility progress event', () => {
    const event = {
      type: 'facility-arrangement',
      id: 'a'.repeat(32),
      phase: 'started',
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    expect(facilityArrangement(event)).toEqual(event)
    const updated = { ...event, phase: 'updated', anchor: false, agents: ['阿米娅', '陈'] }
    expect(facilityArrangement(updated)).toEqual(updated)
    expect(facilityArrangement({ ...updated, anchor: undefined })).toBeNull()
    expect(facilityArrangement({ ...updated, anchor: true })).toBeNull()
    for (const changed of [
      { phase: 'waiting' },
      { id: ' ' },
      { id: 'a'.repeat(129) },
      { label: null },
      { anchor: 'true' },
      { anchor: false },
      { agents: Array(6).fill('阿米娅') },
      { agents: [''] }
    ])
      expect(facilityArrangement({ ...event, ...changed })).toBeNull()
  })
  it.each(['completed', 'failed'])(
    'updates the matching facility roster without creating an anchor or reviving %s attempts',
    (phase) => {
      const event = {
        type: 'facility-arrangement',
        id: 'recycling-current',
        phase: 'started',
        anchor: true,
        room: 'recycle',
        label: '回收站',
        agents: ['行铃']
      }
      const updated = { ...event, phase: 'updated', anchor: false, agents: ['行铃', '旅骨'] }
      const lines = [{ event }, { event: updated }]
      const pending = facilityLifecycle(lines)
      expect([...pending.anchors]).toEqual([[0, updated]])
      expect([...pending.sourceOnly]).toEqual([1])
      expect([...pending.pendingIds]).toEqual([event.id])
      expect(facilityLifecycle([{ event: updated }]).anchors.size).toBe(0)
      for (const fields of [{ id: 'other' }, { room: 'meeting' }, { label: '另一设施' }]) {
        expect(
          facilityLifecycle([{ event }, { event: { ...updated, ...fields } }]).anchors.get(0)
        ).toEqual(event)
      }
      const terminal = { ...updated, phase }
      const result = facilityLifecycle([...lines, { event: terminal }, { event: updated }])
      expect([...result.anchors]).toEqual([[0, terminal]])
      expect([...result.sourceOnly]).toEqual([1, 2])
      expect(result.latestId).toBeNull()
      expect(result.pendingIds.size).toBe(0)
    }
  )

  it('resumes the pending parent anchor after a nested operation completes', () => {
    const parent = {
      type: 'facility-arrangement',
      id: 'parent',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const child = { ...parent, id: 'child', room: 'dormitory_1', label: '宿舍1' }
    const lines = [
      { event: parent },
      { event: child },
      { event: { ...child, phase: 'completed', anchor: false } }
    ]
    const result = facilityLifecycle(lines)
    expect([...result.anchors]).toEqual([
      [0, parent],
      [1, lines[2].event]
    ])
    expect([...result.sourceOnly]).toEqual([2])
    expect(result.latestId).toBe('parent')
    expect([...result.pendingIds]).toEqual(['parent'])
  })
  it('requires the retained explicit anchor and matching identity before merging a result', () => {
    const event = {
      type: 'facility-arrangement',
      id: 'current',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const lines = [
      { event: { ...event, phase: 'completed', anchor: false } },
      { event },
      { event: { ...event, id: 'other', phase: 'completed', anchor: false } },
      { event: { ...event, room: 'train', phase: 'completed', anchor: false } },
      { event: { ...event, label: '其它设施', phase: 'completed', anchor: false } },
      { event: { ...event, anchor: undefined, phase: 'completed' } },
      { event },
      { event: { ...event, agents: ['陈'], phase: 'completed', anchor: false } }
    ]
    const result = facilityLifecycle(lines)
    expect([...result.anchors]).toEqual([[1, lines[7].event]])
    expect([...result.sourceOnly]).toEqual([6, 7])
    expect(result.latestId).toBeNull()
  })
  it('accepts only the exact depot legacy list in its recorded group', () => {
    const legacy = line('仓库扫描：已识别2种物品\n固源岩：0\n龙门币：7214000', {
      group: 'depot-recognition'
    })
    expect(inventoryItems(legacy, present(legacy.text))).toEqual([
      { name: '固源岩', count: 0 },
      { name: '龙门币', count: 7214000 }
    ])
    for (const changed of [
      { group: 'base-scheduler' },
      { text: legacy.text + '\n别的内容' },
      { text: legacy.text.replace('已识别2', '已识别3') }
    ]) {
      const invalid = { ...legacy, ...changed }
      expect(inventoryItems(invalid, present(invalid.text))).toBeNull()
    }
  })
  it('requires the reset event, exact operator metadata and the unchanged source sentence', () => {
    const reset = line('重设 [[operator:陈]] 至空闲', {
      event: { type: 'operator-reset-idle' },
      agents: ['陈']
    })
    expect(idleResetName(reset, present(reset.text))).toBe('陈')
    for (const level of ['WARNING', 'ERROR', 'CRITICAL']) {
      const invalid = { ...reset, text: reset.text.replace('INFO', level) }
      expect(idleResetName(invalid, present(invalid.text))).toBeNull()
    }
    for (const fields of [{ event: null }, { agents: ['阿米娅'] }, { text: 'INFO 安排陈至空闲' }]) {
      const invalid = { ...reset, ...fields }
      expect(idleResetName(invalid, present(invalid.text))).toBeNull()
    }
  })

  it('keeps every inventory quantity and order and rejects mismatched or invalid metadata', () => {
    const items = [
      { name: '固源岩', count: 0 },
      { name: '龙门币', count: 7214000 }
    ]
    const inventory = line('仓库扫描：已识别2种物品\n固源岩：0\n龙门币：7214000', {
      inventory: { items }
    })
    expect(inventoryItems(inventory, present(inventory.text))).toEqual(items)
    for (const changed of [items.slice(1), [{ name: '固源岩', count: -1 }], [...items].reverse()]) {
      const invalid = { ...inventory, inventory: { items: changed } }
      expect(inventoryItems(invalid, present(invalid.text))).toBeNull()
    }
  })
})
