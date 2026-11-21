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
      params: { branch: 'dev', remote: 'origin' }
    })
    expect(view.reference.value).toBe('dev')
    view.reference.value = 'aaaaaaa'
    await view.checkVersion()
    expect(axios.post).toHaveBeenCalledWith(
      '/software-update/source/check',
      { branch: 'dev', reference: 'aaaaaaa', remote: 'origin' },
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

describe('source remote and PR selection', () => {
  it('ignores responses from a previous repository and checks the selected fork', async () => {
    const histories = []
    const axios = {
      get: vi.fn(() => new Promise((resolve) => histories.push(resolve))),
      post: vi.fn().mockImplementation(async (url) => ({
        data: url.endsWith('/source/remote')
          ? {
              ok: true,
              source_url: 'https://github.com/personal/mower.git',
              remotes: [
                {
                  value: 'https://github.com/personal/mower.git',
                  label: 'https://github.com/personal/mower.git'
                }
              ]
            }
          : { ok: true, check_id: 'fork', source_repo: 'personal/mower' }
      }))
    }
    const view = state(axios)
    const old = view.loadHistory()
    const fork = view.selectRemote('https://github.com/personal/mower')
    await vi.waitFor(() => expect(histories).toHaveLength(2))
    histories[1]({ data: { ok: true, branch: 'main', commits: [], source_repo: 'personal/mower' } })
    await fork
    histories[0]({
      data: { ok: true, branch: 'alpha', commits: [], source_repo: 'official/mower' }
    })
    await old
    expect(view.history.value.source_repo).toBe('personal/mower')
    expect(view.branch.value).toBe('main')
    await view.checkVersion()
    expect(axios.post.mock.calls.find(([url]) => url.endsWith('/source/check'))[1]).toEqual({
      remote: 'https://github.com/personal/mower.git',
      branch: 'main',
      reference: 'main'
    })
  })

  it('lists open PRs and checks selected mergeability without changing saved settings', async () => {
    const axios = {
      get: vi
        .fn()
        .mockResolvedValue({ data: { ok: true, pulls: [{ number: 7, title: 'Feature' }] } }),
      post: vi.fn().mockResolvedValue({
        data: { ok: true, source_pr: 7, check_id: 'pr', sha: 'a'.repeat(40) }
      })
    }
    const view = state(axios)
    await view.selectMode('pr')
    expect(axios.get).toHaveBeenCalledWith('/software-update/source/pulls', {
      params: { remote: 'origin' }
    })
    await view.selectPull(7)
    expect(axios.post).toHaveBeenCalledExactlyOnceWith(
      '/software-update/source/pr/check',
      { remote: 'origin', number: 7 },
      { headers: { 'X-Mower-Update': '1' } }
    )
    expect(view.checked.value.source_pr).toBe(7)
    expect(view.branch.value).toBe('alpha')
  })

  it('rejects stale PR checks after changing mode and cannot install conflicting PRs', async () => {
    let finish
    const axios = {
      get: vi.fn().mockResolvedValue({ data: { ok: true, pulls: [], branch: 'alpha' } }),
      post: vi.fn(
        () =>
          new Promise((resolve) => {
            finish = resolve
          })
      )
    }
    const view = state(axios)
    await view.selectMode('pr')
    const pending = view.selectPull(7)
    await view.selectMode('branch')
    finish({ data: { ok: true, check_id: 'stale' } })
    await pending
    expect(view.checked.value).toBeNull()
    await view.selectMode('pr')
    const conflict = view.selectPull(8)
    finish({ data: { ok: false, message: '该 PR 存在合并冲突' } })
    await conflict
    expect(view.checked.value).toBeNull()
    expect(view.error.value).toContain('合并冲突')
  })
})

describe('single source PR selection', () => {
  it('replaces the selected PR and ignores the previous pending check', async () => {
    const checks = []
    const axios = {
      get: vi.fn().mockResolvedValue({ data: { ok: true, pulls: [] } }),
      post: vi.fn(() => new Promise((resolve) => checks.push(resolve)))
    }
    const view = state(axios)
    await view.selectMode('pr')
    await view.checkVersion()
    expect(axios.post).not.toHaveBeenCalled()
    const first = view.selectPull(7)
    const second = view.selectPull(8)
    expect(view.pullNumber.value).toBe(8)
    expect(axios.post.mock.calls.map((call) => call[1])).toEqual([
      { remote: 'origin', number: 7 },
      { remote: 'origin', number: 8 }
    ])
    checks[1]({ data: { ok: true, check_id: 'second', source_pr: 8 } })
    await second
    checks[0]({ data: { ok: true, check_id: 'first', source_pr: 7 } })
    await first
    expect(view.checked.value.check_id).toBe('second')
    await view.selectPull(null)
    expect(view.checked.value).toBeNull()
    expect(view.canCheckPull.value).toBe(false)
    expect(axios.post).toHaveBeenCalledTimes(2)
  })

  it('clears the PR selection when changing repository', async () => {
    const axios = {
      get: vi.fn().mockResolvedValue({ data: { ok: true, pulls: [] } }),
      post: vi.fn().mockResolvedValue({ data: { ok: true, check_id: 'old' } })
    }
    const view = state(axios)
    await view.selectMode('pr')
    await view.selectPull(7)
    await view.selectRemote('origin')
    expect(view.pullNumber.value).toBeNull()
    expect(view.checked.value).toBeNull()
    await view.checkVersion()
    expect(axios.post).toHaveBeenCalledTimes(1)
  })
})
