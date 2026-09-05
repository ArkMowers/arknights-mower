import { effectScope } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { useSourceVersions } from './sourceVersions'

function state(axios) {
  return effectScope().run(() => useSourceVersions(axios, '/software-update'))
}

describe('source version selection', () => {
  it('requests the selected branch and uses the selected SHA in the check', async () => {
    const axios = {
      get: vi
        .fn()
        .mockResolvedValue({ data: { ok: true, branches: ['alpha', 'dev'], commits: [] } }),
      post: vi
        .fn()
        .mockResolvedValue({ data: { ok: true, sha: 'a'.repeat(40), check_id: 'pinned' } })
    }
    const view = state(axios)
    await view.selectBranch('dev')
    expect(axios.get).toHaveBeenCalledWith('/software-update/source/history', {
      params: { branch: 'dev' }
    })
    expect(view.reference.value).toBe('dev')
    view.reference.value = 'aaaaaaa'
    await view.checkVersion()
    expect(axios.post).toHaveBeenCalledWith(
      '/software-update/source/check',
      { branch: 'dev', reference: 'aaaaaaa' },
      { headers: { 'X-Mower-Update': '1' } }
    )
    expect(view.checked.value.check_id).toBe('pinned')
    view.reference.value = 'v4.1.6-alpha.4'
    expect(view.checked.value).toBeNull()
  })

  it('ignores stale branch history and stale checks after a selection change', async () => {
    const histories = [],
      checks = []
    const axios = {
      get: vi.fn(() => new Promise((resolve) => histories.push(resolve))),
      post: vi.fn(() => new Promise((resolve) => checks.push(resolve)))
    }
    const view = state(axios)
    const first = view.loadHistory()
    const second = view.selectBranch('dev')
    histories[1]({ data: { ok: true, branch: 'dev', commits: [] } })
    await second
    histories[0]({ data: { ok: true, branch: 'alpha', commits: [] } })
    await first
    expect(view.history.value.branch).toBe('dev')
    const oldCheck = view.checkVersion()
    view.reference.value = 'old-commit'
    const currentCheck = view.checkVersion()
    checks[1]({ data: { ok: true, check_id: 'current' } })
    await currentCheck
    checks[0]({ data: { ok: true, check_id: 'stale' } })
    await oldCheck
    expect(view.checked.value.check_id).toBe('current')
  })

  it('displays check failures without retaining an installable target', async () => {
    const view = state({
      post: vi.fn().mockResolvedValue({ data: { ok: false, message: '目标版本不支持恢复' } })
    })
    view.checked.value = { check_id: 'old' }
    await view.checkVersion()
    expect(view.checked.value).toBeNull()
    expect(view.error.value).toBe('目标版本不支持恢复')
    expect(view.checking.value).toBe(false)
  })
})
