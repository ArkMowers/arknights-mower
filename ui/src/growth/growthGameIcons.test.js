import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { describe, expect, it } from 'vitest'
import iconSources from '../assets/growth/sources.json'
import moduleColors from '../assets/growth/module-colors.json'
import { growthGameIcon, moduleBadge } from './growthGameIcons'

describe('养成规划游戏图标', () => {
  it('使用八大职业、精英阶段和各专精等级的本地图标', () => {
    for (const profession of [
      'PIONEER',
      'WARRIOR',
      'TANK',
      'SNIPER',
      'CASTER',
      'MEDIC',
      'SUPPORT',
      'SPECIAL'
    ]) {
      expect(growthGameIcon('profession', profession).src).toBeTruthy()
    }
    for (const elite of [0, 1, 2]) expect(growthGameIcon('elite', elite).src).toBeTruthy()
    for (const mastery of [0, 1, 2, 3]) expect(growthGameIcon('mastery', mastery).src).toBeTruthy()
  })

  it('不同干员模组使用通用的 X、Y、Δ 字标，兼容三角符号写法', () => {
    expect(moduleBadge('LOR-X').label).toBe('X')
    expect(moduleBadge('SUM-X').label).toBe('X')
    expect(moduleBadge('EXE-Y').label).toBe('Y')
    for (const type of [' LOR-D ', 'LOR-Δ', 'LOR-∆']) {
      expect(moduleBadge(type).label).toBe('Δ')
    }
  })

  it('按模组 ID 使用游戏颜色，保留同型号不同干员的差异', () => {
    expect(moduleBadge('SUM-X', 'uniequip_002_mgllan').color).toBe('#8e8e8e')
    expect(moduleBadge('SUM-X', 'uniequip_002_lasher').color).toBe('#de3129')
    expect(moduleBadge('BEA-X', 'uniequip_002_myrtle').color).toBe('#8e8e8e')
    expect(moduleBadge('BEA-X', 'uniequip_002_jcinta').color).toBe('#e88522')
    expect(moduleBadge('EXE-X', 'uniequip_002_phatom').color).toBe('#8e8e8e')
    expect(moduleBadge('EXE-X', 'uniequip_002_acspec').color).toBe('#de3129')
    expect(moduleBadge('SUM-X', 'unknown').color).toBe('#8e8e8e')
  })

  it('特限模组直接显示希腊字母，并保留未知型号的字母', () => {
    for (const type of ['ISW-A', 'RA-A', 'SO-A', 'ISW-α']) {
      expect(moduleBadge(type).label).toBe('α')
    }
    expect(moduleBadge('SO-B').label).toBe('β')
    expect(moduleBadge('SO-β').label).toBe('β')
    expect(moduleBadge('SO-γ').label).toBe('γ')
    expect(moduleBadge('NEW-Ω').label).toBe('Ω')
    expect(moduleBadge('ORIGINAL').label).toBe('基础')
    expect(moduleBadge(null).label).toBe('模组')
  })

  it('模组颜色快照记录固定来源，每个模组颜色均可在调色板中解析', () => {
    expect(moduleColors.source_url).toContain(moduleColors.source_commit)
    expect(Object.keys(moduleColors.colors).length).toBeGreaterThan(900)
    for (const color of Object.values(moduleColors.colors)) {
      expect(moduleColors.palette[color]).toMatch(/^#[0-9a-f]{6}$/)
    }
    for (const [color, source] of Object.entries(moduleColors.palette_sources)) {
      expect(source.page).toMatch(/^https:\/\/prts\.wiki\/w\//)
      expect(source.url).toMatch(/^https:\/\/media\.prts\.wiki\//)
      expect(source.sha256).toMatch(/^[0-9a-f]{64}$/)
      const sampledRgb =
        '#' +
        source.rgba
          .slice(0, 3)
          .map((value) => value.toString(16).padStart(2, '0'))
          .join('')
      expect(moduleColors.palette[color]).toBe(sampledRgb)
    }
  })

  it('使用 Wiki 的 96×87 专精徽记，避免误用 tiny 点状图标', () => {
    for (const level of [0, 1, 2, 3]) {
      const png = readFileSync(new URL(`../assets/growth/mastery-${level}.png`, import.meta.url))
      expect([png.readUInt32BE(16), png.readUInt32BE(20)]).toEqual([96, 87])
    }
  })

  it('本地 PNG 与记录的 Wiki 原图散列一致，来源链接指向 PRTS 文件页', () => {
    expect(Object.keys(iconSources)).toHaveLength(15)
    for (const [filename, source] of Object.entries(iconSources)) {
      const png = readFileSync(new URL('../assets/growth/' + filename, import.meta.url))
      expect(source.page).toMatch(/^https:\/\/prts\.wiki\/w\//)
      expect(source.url).toMatch(/^https:\/\/media\.prts\.wiki\//)
      expect(createHash('sha256').update(png).digest('hex')).toBe(source.sha256)
    }
  })
})
