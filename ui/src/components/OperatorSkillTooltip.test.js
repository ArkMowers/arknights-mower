import { renderToString } from '@vue/server-renderer'
import { createSSRApp, h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { useBasementSkill } from '@/stores/basementSkill'
import { render_op_option } from '@/utils/op_select'
import { i18n } from '@/i18n'
import catalog from '../../../arknights_mower/data/building_skill.json'

const tooltip = vi.hoisted(() => ({ show: null }))
vi.mock('axios', () => ({ default: { get: vi.fn() } }))
vi.mock('naive-ui', () => ({
  NAvatar: { render: () => h('span') },
  NTag: {
    props: ['type'],
    setup:
      (props, { slots }) =>
      () =>
        h('span', { 'data-type': props.type }, slots.default())
  },
  NTooltip: {
    setup: (_, { attrs, slots }) => {
      tooltip.show = attrs['onUpdate:show']
      return () => h('div', [slots.trigger(), slots.default()])
    }
  }
}))

const { skill, snapshot, loadOwnedOperators } = useBasementSkill()
const owned = {
  has_data: true,
  operators: [
    {
      name: '能天使',
      owned: true,
      phase: 2,
      level: 20,
      skills: [
        { skill_key: 0, skill_level: 0, status: 'replaced' },
        { skill_key: 0, skill_level: 1, status: 'active' },
        { skill_key: 1, skill_level: 0, status: 'locked' }
      ]
    }
  ]
}

function renderOption(name = '能天使') {
  return renderToString(
    createSSRApp({
      render: () =>
        render_op_option({
          option: { label: name, value: name },
          node: h('span', `选项：${name}`)
        })
    })
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  tooltip.show = null
  snapshot.value = null
  skill.value = [
    {
      name: '能天使',
      child_skill: [
        {
          skill_key: 0,
          skill_level: 0,
          skillname: '企鹅物流·α',
          roomType: '贸易站',
          phase_level: '精英0 1级',
          des: '订单效率<@cc.vup>+20%</>'
        },
        {
          skill_key: 0,
          skill_level: 1,
          skillname: '物流专家',
          roomType: '贸易站',
          phase_level: '精英2 1级',
          des: '订单效率+35%'
        },
        {
          skill_key: 1,
          skill_level: 0,
          skillname: '加工技能',
          roomType: '加工站',
          phase_level: '精英2 1级',
          des: '副产品概率提升'
        }
      ]
    }
  ]
})
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
})

describe('排班选人技能提示', () => {
  it('renders official skill details after a locale change while preserving the raw catalog and operator option', async () => {
    skill.value = [catalog.find((operator) => operator.name === '能天使')]
    const original = JSON.stringify(skill.value)
    expect(await renderOption()).toContain('物流专家')
    i18n.global.locale.value = 'en-US'
    const html = await renderOption()
    expect(html).toContain('Logistics Expert')
    expect(html).toContain('order acquisition efficiency +35%')
    expect(html).toContain('选项：能天使')
    expect(JSON.stringify(skill.value)).toBe(original)
    expect(axios.get).not.toHaveBeenCalled()
  })
  it('展开提示只读本地练度，复用持有、练度及各技能版本状态', async () => {
    const initial = await renderOption()
    expect(initial).toContain('选项：能天使')
    expect(initial).toContain('订单效率+20%')
    expect(initial).not.toMatch(/已拥有|未拥有|已解锁|未解锁|已替换/)
    expect(axios.get).not.toHaveBeenCalled()
    axios.get.mockResolvedValue({ data: owned })
    await tooltip.show(true)
    expect(axios.get).toHaveBeenCalledExactlyOnceWith(
      expect.stringContaining('/basement-skill/operators')
    )
    const html = await renderOption()
    expect(html).toContain('已拥有')
    expect(html).toContain('精2 20级')
    expect(html).toMatch(/企鹅物流·α<\/span>.*?已替换/)
    expect(html).toMatch(/物流专家<\/span>.*?data-type="success".*?已解锁/)
    expect(html).toMatch(/加工技能<\/span>.*?未解锁/)
    expect(html).toContain('贸易站 · 精英2 1级')
    await tooltip.show(false)
    expect(axios.get).toHaveBeenCalledOnce()
  })

  it('共享快照更新后提示随之更新，同名形态沿用相同状态', async () => {
    snapshot.value = owned
    expect(await renderOption('能天使（测试形态）')).toContain('已解锁')
    axios.get.mockResolvedValue({
      data: { has_data: true, operators: [{ name: '能天使', owned: false }] }
    })
    await loadOwnedOperators()
    const html = await renderOption('能天使（测试形态）')
    expect(html.match(/未拥有/g)).toHaveLength(4)
    expect(html).not.toMatch(/已拥有|精2 20级|已解锁|未解锁|已替换/)
  })

  it.each([null, { has_data: false, operators: owned.operators }])(
    '缺少可信练度时不推断持有或解锁状态',
    async (data) => {
      snapshot.value = data
      const html = await renderOption()
      expect(html).toContain('物流专家')
      expect(html).not.toMatch(/已拥有|未拥有|已解锁|未解锁|已替换/)
    }
  )

  it('并发展开共用请求，读取失败可继续查看说明并在再次展开时重试', async () => {
    await renderOption()
    axios.get.mockRejectedValueOnce(new Error('连接失败'))
    await Promise.all([tooltip.show(true), tooltip.show(true)])
    expect(axios.get).toHaveBeenCalledOnce()
    expect(await renderOption()).toContain('订单效率+35%')
    expect(snapshot.value).toBeNull()
    axios.get.mockResolvedValue({ data: owned })
    await tooltip.show(true)
    expect(await renderOption()).toContain('已拥有')
    axios.get.mockRejectedValueOnce(new Error('连接失败'))
    await tooltip.show(true)
    expect(await renderOption()).toContain('已拥有')
  })

  it('没有技能的占位选项保留原节点', async () => {
    expect(await renderOption('Free')).toContain('选项：Free')
    expect(tooltip.show).toBeNull()
    expect(axios.get).not.toHaveBeenCalled()
  })
})
