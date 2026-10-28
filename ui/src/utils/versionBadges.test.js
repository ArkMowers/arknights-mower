import { afterEach, describe, expect, it } from 'vitest'
import { resourceVersionBadge, resourceVersionHint, softwareVersionBadge } from './versionBadges'
import { i18n } from '@/i18n'

afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

const start = Date.parse('2026-10-10T00:00:00+08:00')
const end = Date.parse('2026-10-20T00:00:00+08:00')
const activity = { name: '昨日海', time: start / 1000, endTime: end / 1000 }

describe('software version badges', () => {
  it.each([
    ['4.1.6-alpha.12+unknown', 'alpha'],
    ['4.1.6-alpha.12+deadbee', 'alpha'],
    ['v4.1.6-alpha.12.gdeadbeef', 'nightly'],
    ['4.1.6-alpha.12.gdeadbeef+windows', 'nightly'],
    ['4.1.6-alpha.12.gdeadbee', 'alpha'],
    ['4.1.6-beta.1', ''],
    ['4.1.6', 'stable'],
    ['v4.1.6+deadbee', 'stable'],
    ['4.1.6+build.42-foo', 'stable'],
    ['4.1.6+unknown', 'stable'],
    ['4.1.6-rc.2', ''],
    ['4.1.6-dev', ''],
    ['unknown', ''],
    ['prefix4.1.6', ''],
    ['4.1.6 suffix', ''],
    ['4.1.6.1', ''],
    ['4.1.6+', ''],
    ['', '']
  ])('identifies the installed version %s as %s', (version, badge) => {
    expect(softwareVersionBadge(version)).toBe(badge)
  })

  it.each(['4.1.6-alpha.12+deadbee', '4.1.6-alpha.12.gdeadbeef', '4.1.6+deadbeef', ''])(
    'gives actual source deployment priority over the version suffix %s',
    (version) => {
      expect(softwareVersionBadge(version, 'source')).toBe('source')
    }
  )

  it.each([
    ['4.1.6-alpha.12.gdeadbeef+deadbee', 'nightly'],
    ['4.1.6-alpha.12+deadbee', 'alpha'],
    ['4.1.6+deadbeef', 'stable']
  ])(
    'keeps release deployment classification for %s without treating a SHA as source',
    (version, badge) => {
      expect(softwareVersionBadge(version, 'release')).toBe(badge)
    }
  )

  it.each([undefined, null, '', 'nightly', 'Source', true, {}])(
    'falls back to the version for unknown deployment metadata %j',
    (deployment) => {
      expect(softwareVersionBadge('4.1.6-alpha.12.gdeadbeef', deployment)).toBe('nightly')
      expect(softwareVersionBadge('4.1.6+deadbeef', deployment)).toBe('stable')
    }
  )
})

describe('installed resource badges', () => {
  it.each([
    ['en-US', 'Beijing time', '2h 30m'],
    ['ja-JP', '北京時間', '2時間 30分'],
    ['zh-TW', '北京時間', '2 小時 30 分鐘']
  ])(
    'translates hints in %s while preserving the selected event and China-server timestamps',
    (locale, timezone, duration) => {
      const badge = resourceVersionBadge({ activity }, end - 9000000)
      const original = structuredClone(badge)
      i18n.global.locale.value = locale
      const hint = resourceVersionHint('原资源版本', badge)
      expect(hint).toContain('昨日海')
      expect(hint).toContain('原资源版本')
      expect(hint).toContain(timezone)
      expect(hint).toContain(duration)
      expect(badge).toEqual(original)
      expect(badge.end).toBe(end)
    }
  )

  it('moves from green through yellow to red across the selected activity interval', () => {
    expect(resourceVersionBadge({ activity }, start)).toMatchObject({ state: 'active', hue: 140 })
    expect(resourceVersionBadge({ activity }, start + (end - start) / 2)).toMatchObject({
      state: 'active',
      hue: 70
    })
    expect(resourceVersionBadge({ activity }, end)).toMatchObject({
      state: 'ended',
      hue: 0,
      refresh: false
    })
    expect(resourceVersionBadge({ activity }, end + 86400000).hue).toBe(0)
    expect(resourceVersionBadge({ activity }, start - 86400000)).toMatchObject({
      state: 'upcoming',
      hue: 140
    })
  })

  it('uses the same later-start entry as the resource label, preferring activity on a tie', () => {
    const gacha = { name: '海渊巡游', time: activity.time, endTime: activity.endTime + 86400 }
    expect(resourceVersionBadge({ activity, gacha }, start).name).toBe('昨日海')
    expect(
      resourceVersionBadge({ activity, gacha: { ...gacha, time: gacha.time + 60 } }, start)
    ).toMatchObject({ name: '海渊巡游', kind: '卡池', end: end + 86400000 })
  })

  it('does not borrow an earlier activity end when the displayed gacha has no end time', () => {
    const gacha = { name: '海渊巡游', time: activity.time + 60 }
    expect(resourceVersionBadge({ activity, gacha }, start)).toEqual({
      name: '海渊巡游',
      kind: '卡池',
      state: 'unknown',
      refresh: false
    })
  })

  it.each([
    {},
    { last_updated: '26-10-09-10-00-00_deadbee' },
    { activity: { ...activity, endTime: null } },
    { activity: { ...activity, endTime: '1792425600' } },
    { activity: { ...activity, endTime: activity.time } },
    { activity: { ...activity, endTime: activity.time - 1 } },
    { activity: { ...activity, time: Number.NaN } },
    { activity: { ...activity, endTime: 1e99 } }
  ])('keeps missing or invalid lifecycle metadata neutral: %j', (metadata) => {
    expect(resourceVersionBadge(metadata, start)).toMatchObject({
      state: 'unknown',
      refresh: false
    })
    expect(resourceVersionBadge(metadata, start).hue).toBeUndefined()
  })

  it('states the actual event end in the game timezone and remaining time without claiming resource expiry', () => {
    const badge = resourceVersionBadge({ activity }, end - 9000000)
    expect(resourceVersionHint('当前资源', badge)).toBe(
      '资源版本 当前资源\n活动「昨日海」结束：2026/10/20 00:00（北京时间）\n距结束还有 2 小时 30 分钟'
    )
    expect(resourceVersionHint('当前资源', resourceVersionBadge({ activity }, end))).toContain(
      '活动已结束'
    )
    expect(resourceVersionHint('当前资源', resourceVersionBadge({}))).toContain(
      '未提供有效的活动或卡池结束时间'
    )
  })
})
