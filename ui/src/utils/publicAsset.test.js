import { afterEach, expect, it, vi } from 'vitest'
import { publicAsset } from './publicAsset'

afterEach(() => vi.unstubAllGlobals())

it('uses the selected build for encoded and relative public names', () => {
  const url = 'https://mower.231240092.xyz/files/avatar.webp'
  vi.stubGlobal('window', { __MOWER_PUBLIC_ASSETS__: { '/avatar/阿米娅.webp': url } })
  expect(publicAsset('/avatar/' + encodeURIComponent('阿米娅') + '.webp')).toBe(url)
  expect(publicAsset('avatar/阿米娅.webp')).toBe(url)
})

it('preserves the desktop asset path', () => {
  vi.stubGlobal('window', {})
  expect(publicAsset('/bg.webp')).toBe('/bg.webp')
})
