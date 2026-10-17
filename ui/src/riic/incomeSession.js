import { createCalculationBottleneckTracker } from './vendor/workbench/calculationBottlenecks'

// A run owns its worker and observations; completed results keep their input snapshot.
export function createIncomeSession({ createWorker, update, now = () => performance.now() }) {
  let worker = null
  let tracker
  let started = 0
  let input
  const elapsed = () => (now() - started) / 1000
  function finish(outcome, result, error) {
    const active = worker
    worker = null
    active?.terminate()
    update({
      running: false,
      result,
      error,
      input,
      bottleneck: tracker?.finish({
        outcome,
        elapsedSeconds: elapsed(),
        error,
        diagnostics: result?.diagnostics
      })
    })
  }
  return {
    start(plan, settings) {
      if (worker) return false
      input = JSON.parse(JSON.stringify({ plan, settings }))
      delete input.settings.masteryPlanPresent
      tracker = createCalculationBottleneckTracker()
      started = now()
      update({ running: true, result: null, error: null, bottleneck: null, progress: null, input })
      try {
        const current = createWorker()
        worker = current
        current.onmessage = ({ data }) => {
          if (worker !== current) return
          if (data.type === 'progress') {
            tracker.observe(data.progress, elapsed())
            update({ progress: data.progress })
          } else if (data.type === 'complete')
            finish(data.result.success ? 'completed' : 'failed', data.result, data.result.error)
          else if (data.type === 'error') finish('failed', null, data.error)
        }
        current.onerror = (e) => {
          if (worker === current) finish('failed', null, e.message || '后台演算失败')
        }
        current.onmessageerror = () => {
          if (worker === current) finish('failed', null, '演算结果传输失败')
        }
        current.postMessage(input)
      } catch (error) {
        finish('failed', null, error.message || String(error))
      }
      return true
    },
    cancel() {
      if (worker) finish('cancelled', null, '演算已停止，可修改参数后重试')
    },
    dispose() {
      const active = worker
      worker = null
      active?.terminate()
    }
  }
}
