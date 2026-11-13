import { describe, expect, it } from 'vitest'
import {
  resourceActivityBadges,
  resourceActivityHint,
  resourceVersionBadge,
  resourceVersionHint,
  softwareVersionBadge
} from './versionBadges'

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
  it('colors by the earliest closing active activity despite a newer permanent resource label', () => {
    const permanent = { name: '卫戍协议:规程', time: 1794124800, endTime: 4092580799 }
    const metadata = {
      activity: permanent,
      gacha: { name: '将雪投火', time: 1793487600, endTime: 1794686399 },
      activities: [
        permanent,
        { name: '较晚关闭', time: activity.time - 864000, endTime: activity.endTime + 864000 },
        activity,
        {
          name: '尚未开始',
          time: (start + 6 * 86400000) / 1000,
          endTime: (start + 7 * 86400000) / 1000
        },
        { name: '已经关闭', time: activity.time - 86400, endTime: activity.time }
      ]
    }
    expect(resourceVersionBadge(metadata, start + 5 * 86400000)).toMatchObject({
      name: '昨日海',
      state: 'active',
      hue: 70
    })
    expect(resourceVersionBadge(metadata, end)).toMatchObject({
      name: '较晚关闭',
      state: 'active',
      hue: 47
    })
  })

  it('keeps permanent-only metadata neutral without a countdown clock or a 2099 deadline', () => {
    const permanent = { name: '卫戍协议:规程', time: 1794124800, endTime: 4092580799 }
    const now = Date.parse('2026-11-13T12:00:00+08:00')
    for (const metadata of [
      { activity: permanent },
      { activity: permanent, activities: [permanent] },
      { activity: permanent, activities: [] }
    ]) {
      const badge = resourceVersionBadge(metadata, now)
      expect(badge).toMatchObject({ state: 'unknown', refresh: false })
      expect(badge.hue).toBeUndefined()
      expect(resourceVersionHint('卫戍协议:规程', badge)).toContain('长期开放')
      expect(resourceVersionHint('卫戍协议:规程', badge)).not.toContain('2099')
      expect(resourceVersionHint('卫戍协议:规程', badge)).not.toContain('距作战关闭还有')
    }
    const finite = { name: '时间啊，向前！', time: 1793487600, endTime: 1795291199 }
    expect(resourceVersionBadge({ activity: permanent, activities: [finite] }, now)).toMatchObject({
      name: '时间啊，向前！',
      state: 'active',
      hue: 58
    })
  })

  it('does not color by an upcoming activity or an open gacha, but keeps their hints refreshing', () => {
    const metadata = {
      activities: [{ ...activity, time: activity.time + 60 }],
      gacha: { name: '卡池', time: activity.time - 60, endTime: activity.endTime }
    }
    const badge = resourceVersionBadge(metadata, start)
    expect(badge).toMatchObject({ state: 'unknown', refresh: true })
    expect(badge.hue).toBeUndefined()
    expect(resourceVersionHint('当前资源', badge)).toContain('活动开始')
    expect(resourceVersionHint('当前资源', badge)).toContain('卡池「卡池」结束')
    expect(resourceVersionBadge(metadata, start + 60000)).toMatchObject({
      state: 'active',
      hue: 140
    })
  })

  it('lists every unfinished battle activity, including an older event and an upcoming event', () => {
    const metadata = {
      activity,
      activities: [
        activity,
        { name: '较早活动', time: activity.time - 86400, endTime: activity.endTime + 86400 },
        { name: '商店仍开放', time: activity.time - 172800, endTime: activity.time },
        { name: '尚未开启', time: activity.endTime + 1, endTime: activity.endTime + 86400 },
        { name: '无效时间', time: activity.time, endTime: null }
      ]
    }
    const badges = resourceActivityBadges(metadata, start)
    expect(badges.map((badge) => badge.name)).toEqual(['昨日海', '较早活动', '尚未开启'])
    expect(resourceActivityHint(badges[0])).toContain('作战关闭：2026/10/20 00:00（北京时间）')
    expect(resourceActivityHint(badges[2])).toContain('活动开始：2026/10/20 00:00')
    const hint = resourceVersionHint('当前资源', resourceVersionBadge(metadata, start))
    expect(hint).toContain('较早活动')
    expect(hint).toContain('尚未开启')
    expect(hint).not.toContain('商店仍开放')
    expect(resourceActivityBadges(metadata, end).map((badge) => badge.name)).toEqual([
      '较早活动',
      '尚未开启'
    ])
  })

  it('keeps refreshing while an older activity remains open after the version event ends', () => {
    const metadata = {
      activity,
      activities: [
        { name: '较早活动', time: activity.time - 86400, endTime: activity.endTime + 86400 }
      ]
    }
    expect(resourceVersionBadge(metadata, end).refresh).toBe(true)
    const closed = resourceVersionBadge(metadata, end + 86400000)
    expect(closed.refresh).toBe(false)
    expect(resourceVersionHint('当前资源', closed)).toContain('当前资源中没有未结束的活动')
    expect(resourceVersionHint('当前资源', closed)).not.toContain('较早活动')
  })

  it('falls back to the single activity for older server responses', () => {
    expect(resourceActivityBadges({ activity }, start).map((badge) => badge.name)).toEqual([
      '昨日海'
    ])
    expect(resourceActivityBadges({ activity, activities: [] }, start)).toEqual([])
  })

  it('moves from green through yellow to red and becomes neutral when the activity closes', () => {
    expect(resourceVersionBadge({ activity }, start)).toMatchObject({ state: 'active', hue: 140 })
    expect(resourceVersionBadge({ activity }, start + (end - start) / 2)).toMatchObject({
      state: 'active',
      hue: 70
    })
    expect(resourceVersionBadge({ activity }, end - 1).hue).toBe(0)
    expect(resourceVersionBadge({ activity }, end)).toMatchObject({
      state: 'unknown',
      refresh: false
    })
    expect(resourceVersionBadge({ activity }, end + 86400000).hue).toBeUndefined()
    expect(resourceVersionBadge({ activity }, start - 86400000)).toMatchObject({
      state: 'unknown',
      refresh: true
    })
  })

  it('keeps gacha deadlines in the hint without letting them determine activity color', () => {
    const gacha = { name: '海渊巡游', time: activity.time, endTime: activity.endTime + 86400 }
    expect(resourceVersionBadge({ activity, gacha }, start).name).toBe('昨日海')
    expect(
      resourceVersionBadge({ activity, gacha: { ...gacha, time: gacha.time + 60 } }, start)
    ).toMatchObject({ name: '昨日海', kind: '活动', end })
    expect(
      resourceVersionHint('当前资源', resourceVersionBadge({ activity, gacha }, start))
    ).toContain('卡池「海渊巡游」结束')
  })

  it('keeps an invalid gacha neutral while the valid activity still controls color', () => {
    const gacha = { name: '海渊巡游', time: activity.time + 60 }
    expect(resourceVersionBadge({ activity, gacha }, start)).toMatchObject({
      name: '昨日海',
      state: 'active',
      hue: 140,
      gacha: { name: '海渊巡游', kind: '卡池', state: 'unknown', refresh: false }
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
      '资源版本 当前资源\n活动「昨日海」作战关闭：2026/10/20 00:00（北京时间）\n距作战关闭还有 2 小时 30 分钟'
    )
    expect(resourceVersionHint('当前资源', resourceVersionBadge({ activity }, end))).toContain(
      '当前资源中没有未结束的活动'
    )
    expect(resourceVersionHint('当前资源', resourceVersionBadge({}))).toContain(
      '当前资源中没有未结束的活动'
    )
  })
})
