import { afterEach, describe, expect, it, vi } from 'vitest'
import { readProcessActionStatus, submitProcessAction } from './processAction.js'

describe('shared process action request', () => {
  afterEach(() => vi.unstubAllGlobals())

  function setup() {
    const trace = []
    const session = new Map()
    vi.stubGlobal('sessionStorage', {
      setItem: (key, value) => session.set(key, value)
    })
    const saves = {
      pauseAndDrain: vi.fn(async () => trace.push('drain')),
      resume: vi.fn()
    }
    const axios = {
      post: vi.fn(async () => {
        trace.push('post')
        return { data: { ok: true, id: 'job-1', message: '已提交' } }
      })
    }
    const request = () =>
      submitProcessAction({
        axios,
        saves,
        action: 'stop',
        base: '/process-control',
        pendingKey: 'mower-process-control:/process-control'
      })
    return { trace, session, saves, axios, request }
  }

  it('drains config before submitting stop through existing endpoint', async () => {
    const env = setup()
    const { pending } = await env.request()
    expect(env.trace).toEqual(['drain', 'post'])
    expect(env.axios.post).toHaveBeenCalledWith(
      '/process-control/action',
      { action: 'stop' },
      { headers: { 'X-Mower-Control': '1' } }
    )
    expect(JSON.parse(env.session.get('mower-process-control:/process-control')).id).toBe(
      pending.id
    )
  })

  it('resumes autosave only after an explicit rejection', async () => {
    const env = setup()
    env.axios.post.mockResolvedValueOnce({
      data: { ok: false, message: '已拒绝' }
    })
    await expect(env.request()).rejects.toThrow('已拒绝')
    expect(env.saves.resume).toHaveBeenCalledOnce()
  })

  it('reads the status of the accepted process job from the shared endpoint', async () => {
    const axios = { get: vi.fn(async () => ({ data: { ok: true, status: 'running' } })) }
    const data = await readProcessActionStatus({
      axios,
      base: '/process-control',
      pending: { id: 'job-1' }
    })
    expect(data.status).toBe('running')
    expect(axios.get).toHaveBeenCalledWith('/process-control/status', {
      params: { id: 'job-1' },
      timeout: 3000
    })
  })

  it('rejects a failed process status response without reporting exit success', async () => {
    const axios = { get: vi.fn(async () => ({ data: { ok: false, message: 'job failed' } })) }
    await expect(
      readProcessActionStatus({
        axios,
        base: '/process-control',
        pending: { id: 'job-1' }
      })
    ).rejects.toThrow('job failed')
  })

  it('does not unpause saves when the response was lost', async () => {
    const env = setup()
    env.axios.post.mockRejectedValueOnce(new Error('offline'))
    await expect(env.request()).rejects.toThrow('offline')
    expect(env.saves.resume).not.toHaveBeenCalled()
  })
})
