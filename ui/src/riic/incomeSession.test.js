import { expect, it, vi } from 'vitest'
import { createIncomeSession } from './incomeSession'
function setup() {
  const workers = [],
    state = {},
    update = vi.fn((patch) => Object.assign(state, patch))
  let now = 0
  const session = createIncomeSession({
    update,
    now: () => now,
    createWorker: () => {
      const worker = { postMessage: vi.fn(), terminate: vi.fn() }
      workers.push(worker)
      return worker
    }
  })
  return {
    workers,
    state,
    update,
    session,
    time: (value) => {
      now = value
    }
  }
}
it('cancels, retains observations and ignores late messages across runs', () => {
  const { workers, state, session, time } = setup(),
    source = { plan1: {} },
    settings = { sampleDays: 28 }
  session.start(source, settings)
  source.plan1.changed = true
  settings.sampleDays = 1
  expect(workers[0].postMessage.mock.calls[0][0]).toEqual({
    plan: { plan1: {} },
    settings: { sampleDays: 28 }
  })
  workers[0].onmessage({
    data: { type: 'progress', progress: { label: '预热19小时', fraction: 0.2 } }
  })
  time(20000)
  session.cancel()
  expect(workers[0].terminate).toHaveBeenCalledOnce()
  expect(state.bottleneck).toMatchObject({
    outcome: 'cancelled',
    progressLabel: '预热19小时',
    silence: { seconds: 20 }
  })
  session.start(source, settings)
  workers[0].onmessage({ data: { type: 'complete', result: { success: true, wrong: true } } })
  expect(state.running).toBe(true)
  expect(state.result).toBeNull()
  workers[1].onmessage({ data: { type: 'complete', result: { success: true, diagnostics: [] } } })
  expect(state.running).toBe(false)
  expect(state.result.success).toBe(true)
  expect(workers[1].terminate).toHaveBeenCalledOnce()
})
it.each(['onerror', 'onmessageerror'])('releases failed workers via %s', (method) => {
  const { session, workers, state } = setup()
  session.start({}, {})
  workers[0][method]({ message: 'failed' })
  expect(state.running).toBe(false)
  expect(state.error).toBeTruthy()
  expect(workers[0].terminate).toHaveBeenCalledOnce()
})
it('handles creation failure and disposes without late updates', () => {
  const update = vi.fn(),
    failed = createIncomeSession({
      createWorker: () => {
        throw Error('unavailable')
      },
      update
    })
  failed.start({}, {})
  expect(update.mock.calls.at(-1)[0]).toMatchObject({ running: false, error: 'unavailable' })
  const { session, workers, state } = setup()
  session.start({}, {})
  session.dispose()
  workers[0].onmessage({ data: { type: 'complete', result: { success: true } } })
  expect(workers[0].terminate).toHaveBeenCalledOnce()
  expect(state.result).toBeNull()
})

it('omits retired training state from new worker and completed-result snapshots', () => {
  const { session, workers, state } = setup()
  const settings = { sampleDays: 28, masteryPlanPresent: true }
  session.start({}, settings)
  expect(workers[0].postMessage.mock.calls[0][0].settings).toEqual({ sampleDays: 28 })
  workers[0].onmessage({ data: { type: 'complete', result: { success: true } } })
  expect(state.input.settings).toEqual({ sampleDays: 28 })
  expect(settings.masteryPlanPresent).toBe(true)
})
