import { readFile } from 'node:fs/promises'
import { afterEach, expect, it, vi } from 'vitest'
import { h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import SklandRewardIcon from './SklandRewardIcon.vue'

afterEach(() => vi.unstubAllGlobals())

it.each([
  ['初级认知载体', 'item_expcard_stage2_low'],
  ['中级作战记录', 'item_expcard_stage1_mid'],
  ['武器检查装置', 'item_weapon_expcard_mid']
])('renders the bundled icon for %s', async (item, file) => {
  const iconPath = `/skland-icons/endfield/${file}.webp`
  const html = await renderToString(h(SklandRewardIcon, { game: '终末地', item }))

  expect(html).toContain(`<img src="${iconPath}"`)
  const image = await readFile(new URL(`../../public${iconPath}`, import.meta.url))
  expect(image.toString('ascii', 8, 12)).toBe('WEBP')
})

it.each([
  ['明日方舟', '龙门币', '/depot/龙门币.webp'],
  ['终末地', '折金票', '/skland-icons/endfield/item_gold.webp']
])('uses the relay build URL for %s reward icons', async (game, item, iconPath) => {
  const url = 'https://assets.example.com/reward.webp'
  vi.stubGlobal('window', { __MOWER_PUBLIC_ASSETS__: { [iconPath]: url } })

  const html = await renderToString(h(SklandRewardIcon, { game, item }))

  expect(html).toContain(`<img src="${url}"`)
})
