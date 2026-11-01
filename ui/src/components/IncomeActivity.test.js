import { expect, it, vi } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import IncomeActivity from './IncomeActivity.vue'

vi.mock('vue', async (original) => ({
  ...(await original()),
  useSSRContext: () => ({ modules: new Set() })
}))
const activity = () => ({
  message: '演算推进较慢。',
  status: 'slow',
  findings: [
    {
      code: 'mower-task-exception',
      message: '副表：替补干员 斯卡蒂 必须为同一非空组内的其他主力或未在岗的替补。'
    }
  ],
  task: { label: '下班', metadata: '公招', source: 'queued', dueHours: 12, rooms: ['room_1_2'] },
  operators: [
    {
      id: 'char_263_skadi',
      name: '斯卡蒂',
      morale: 16.2,
      upperLimit: 24,
      room: 'room_1_2',
      groups: ['深海']
    }
  ],
  recentEvents: [{ label: '副表切换：鸿雪下班', count: 2 }]
})
const render = (value, historical = false) =>
  renderToString(createSSRApp({ render: () => h(IncomeActivity, { activity: value, historical }) }))
it('does not label a finished observation as still running', async () => {
  const value = { ...activity(), message: '演算正在推进。' }
  expect(await render(value)).toContain('演算正在推进')
  const html = await render(value, true)
  expect(html).not.toContain('演算正在推进')
  expect(html).toContain('替补干员 斯卡蒂')
})
it('renders actual findings, task labels, operators and events in the live and historical observation view', async () => {
  const html = await render(activity())
  expect(html).toContain('替补干员 斯卡蒂')
  expect(html).toContain('最近待执行任务：下班')
  expect(html).toContain('计划时刻 T+12 小时')
  expect(html).toContain('16.2 / 24')
  expect(html).toContain('深海')
  expect(html).toContain('副表切换：鸿雪下班 2 次')
  expect(html).toContain('历史校验记录不表示当前仍未解决')
})
it('labels active tasks and explicitly identifies missing observation details', async () => {
  const value = activity()
  value.task.source = 'active'
  expect(await render(value)).toContain('当前任务：下班')
  const empty = await render({ message: '演算正在推进。', operators: [], recentEvents: [] })
  expect(empty).toContain('当前观测没有具体干员或任务信息')
})
