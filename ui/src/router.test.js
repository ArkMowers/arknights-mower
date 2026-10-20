import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', async (original) => {
  const router = await original()
  return { ...router, createWebHistory: () => router.createMemoryHistory() }
})

vi.mock('@/routes', async (original) => {
  const { routes } = await original()
  function stubPages(records) {
    return records.map((record) => ({
      ...record,
      component: record.component ? { render: () => null } : undefined,
      children: record.children ? stubPages(record.children) : undefined
    }))
  }
  return { routes: stubPages(routes) }
})

describe('frontend navigation credentials', () => {
  let router

  beforeEach(async () => {
    vi.resetModules()
    router = (await import('./router')).default
  })

  it.each([
    ['/plan-editor', 'plan'],
    ['/mowersettings', 'mowersettings'],
    ['/record/report', 'report']
  ])('keeps the session token when navigating to %s', async (path, name) => {
    await router.push('/?token=session-token')
    await router.push(path)

    expect(router.currentRoute.value).toMatchObject({
      path,
      name,
      query: { token: 'session-token' }
    })
  })

  it('keeps an explicit destination token and its other navigation fields', async () => {
    await router.push('/?token=session-token')
    await router.push('/mowersettings?token=destination-token&view=details#software-update')

    expect(router.currentRoute.value).toMatchObject({
      path: '/mowersettings',
      query: { token: 'destination-token', view: 'details' },
      hash: '#software-update'
    })
  })

  it('keeps destination query and fragment when inheriting the session token', async () => {
    await router.push('/?token=session-token&window_shell=1')
    await router.push('/mowersettings?view=details#software-update')

    expect(router.currentRoute.value.query).toEqual({
      token: 'session-token',
      window_shell: '1',
      view: 'details'
    })
    expect(router.currentRoute.value.hash).toBe('#software-update')
  })

  it('does not add credentials to navigation that started without a token', async () => {
    await router.push('/')
    await router.push('/mowersettings?view=details#software-update')

    expect(router.currentRoute.value.query).toEqual({ view: 'details' })
    expect(router.currentRoute.value.hash).toBe('#software-update')
  })

  it('retains the missing-page route and session token for an unknown page', async () => {
    await router.push('/?token=session-token')
    await router.push('/unknown-page')

    expect(router.currentRoute.value.path).toBe('/unknown-page')
    expect(router.currentRoute.value.query.token).toBe('session-token')
    expect(router.currentRoute.value.matched.map((record) => record.path)).toEqual([
      '/:pathMatch(.*)'
    ])
  })
})
