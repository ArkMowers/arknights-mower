import { describe, expect, it } from 'vitest'
import { createLogRowPresenter } from './logPresentation'
import { normalizeLogSource } from './logSource'
import { analyzeLogTimeline, buildLogTimeline } from './logTimeline'

function renderTimeline(records) {
  const lines = records.map(normalizeLogSource)
  const facilityPlan = {}
  const { present, presentLines } = createLogRowPresenter([], facilityPlan)
  return buildLogTimeline(analyzeLogTimeline(lines), {
    rows: presentLines(lines),
    present,
    facilityPlan,
    running: true,
    detailsVisible: () => false,
    waitDurations: new Map(),
    interruptedLifecycleKeys: new Set(),
    interruptedRecruitmentIds: new Set(),
    animatedLineKeys: new Set()
  })
}

describe('running log timeline', () => {
  it('updates the original facility heading and shows an ordinary row if the anchor is evicted', () => {
    const arrangement = {
      type: 'facility-arrangement',
      id: 'meeting-entry',
      phase: 'started',
      anchor: true,
      room: 'meeting',
      label: '会客室',
      agents: ['阿米娅']
    }
    const start = { id: 1, text: '17:47:22 INFO 会客室', event: arrangement }
    const end = {
      id: 3,
      text: '17:48:07 INFO 已安排阿米娅进驻会客室',
      event: { ...arrangement, phase: 'completed', anchor: false }
    }
    const completed = renderTimeline([start, { id: 2, text: 'INFO 中间记录' }, end])
    expect(completed.items.find((item) => item.arrangement)).toMatchObject({
      key: 'id:1',
      headingStamp: { time: '17:47:22' },
      arrangement: { phase: 'completed', inProgress: false }
    })
    expect(completed.items.find((item) => item.key === 'id:3').sourceOnly).toBe(true)

    const retained = renderTimeline([end])
    expect(retained.blocks[0].items[0]).toMatchObject({
      key: 'id:3',
      row: { text: end.text }
    })
    expect(retained.items[0].sourceOnly).toBeUndefined()
    expect(retained.items[0].arrangement).toBeUndefined()
  })

  it('keeps source order for a folded rescue task and includes only explicitly associated records', () => {
    const parent = { type: 'rescue-staffing', id: 'rescue-meeting' }
    const start = {
      id: 1,
      text: 'INFO 已生成救急换班任务',
      event: {
        ...parent,
        phase: 'queued',
        anchor: true,
        rooms: [{ room: 'meeting', label: '会客室', agents: ['阿米娅'], status: 'pending' }]
      }
    }
    const unrelated = { id: 2, text: 'INFO 会客室独立记录', room: 'meeting' }
    const warning = { id: 3, text: 'WARNING 救急换班明细', parent }
    const { blocks } = renderTimeline([start, unrelated, warning])
    const rescue = blocks.find((block) => block.parent)
    expect(rescue.sources).toEqual([
      { key: 'id:1', index: 0, text: start.text },
      { key: 'id:3', index: 2, text: warning.text }
    ])
    expect(rescue.items).toEqual([
      expect.objectContaining({ key: 'rescue-display:id:3', sourceKey: 'id:3' })
    ])
    expect(blocks.find((block) => block.key === 'id:2').items[0].row.text).toBe(unrelated.text)
  })
})
