import { describe, expect, it } from 'vitest'
import { effectScope, ref } from 'vue'
import { useUpdateProgress } from './useUpdateProgress'

function visit(job) {
  const scope = effectScope()
  const visible = scope.run(() => useUpdateProgress(job))
  return { scope, visible }
}

describe('update progress across settings visits', () => {
  it.each(['success', 'error', 'succeeded', 'failed', 'cancelled'])(
    'hides a previous %s result while retaining its backend data',
    (status) => {
      const job = ref({ id: 'old', status, progress: 100 })
      const page = visit(job)
      expect(page.visible.value).toBe(false)
      job.value = { ...job.value, message: 'previous result' }
      expect(page.visible.value).toBe(false)
      expect(job.value.progress).toBe(100)
      page.scope.stop()
    }
  )

  it('restores a running job and shows completion only for the current visit', () => {
    const job = ref({ id: 'active', status: 'running', progress: 40 })
    const first = visit(job)
    expect(first.visible.value).toBe(true)
    first.scope.stop()
    const second = visit(job)
    expect(second.visible.value).toBe(true)
    job.value = { id: 'active', status: 'success', progress: 100 }
    expect(second.visible.value).toBe(true)
    second.scope.stop()
    const third = visit(job)
    expect(third.visible.value).toBe(false)
    third.scope.stop()
  })

  it('observes immediate validation failure and a fast server completion', () => {
    const job = ref({ status: 'idle' })
    const page = visit(job)
    job.value = { id: '', status: 'running' }
    job.value.status = 'error'
    expect(page.visible.value).toBe(true)
    job.value = { id: '', status: 'running' }
    job.value = { id: 'new', status: 'success', progress: 100 }
    expect(page.visible.value).toBe(true)
    page.scope.stop()
  })

  it('does not display a different task completed elsewhere', () => {
    const job = ref({ id: 'active', status: 'running' })
    const page = visit(job)
    job.value = { id: 'other', status: 'success', progress: 100 }
    expect(page.visible.value).toBe(false)
    job.value = { status: 'idle' }
    job.value = { id: 'active', status: 'success' }
    expect(page.visible.value).toBe(false)
    page.scope.stop()
  })
})
