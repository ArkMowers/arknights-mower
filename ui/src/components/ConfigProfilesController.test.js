import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  createRenderer,
  createSSRApp,
  defineComponent,
  h,
  nextTick,
  ref,
  shallowRef,
  ssrContextKey
} from 'vue'
import { renderToString } from 'vue/server-renderer'
import ConfigProfilesController from './ConfigProfilesController.vue'
import { i18n } from '@/i18n'

const feedback = vi.hoisted(() => ({ success: vi.fn() }))

vi.mock('naive-ui', async (original) => {
  const library = await original()
  const wrapper = defineComponent({
    props: ['show', 'title', 'value', 'checked', 'indeterminate', 'disabled', 'contentStyle'],
    setup(props, { slots }) {
      return () => {
        if (props.show === false) return null
        return h('div', { 'data-value': props.value, 'data-indeterminate': props.indeterminate }, [
          props.title,
          h('main', { style: props.contentStyle }, slots.default?.()),
          slots.footer ? h('footer', slots.footer()) : null,
          slots.action?.()
        ])
      }
    }
  })
  return {
    ...library,
    useMessage: () => feedback,
    ...Object.fromEntries(
      Object.keys(library)
        .filter((name) => /^N[A-Z]/.test(name))
        .map((name) => [name, wrapper])
    )
  }
})

const mounted = []
function mount(controller) {
  const renderer = createRenderer({
    createElement: () => ({}),
    createText: () => ({}),
    createComment: () => ({}),
    setText() {},
    setElementText() {},
    patchProp() {},
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null
  })
  const app = renderer.createApp(
    { ...ConfigProfilesController, render: () => null },
    { controller }
  )
  app.provide(ssrContextKey, { modules: new Set() })
  app.mount({})
  mounted.push(app)
}

beforeEach(() => vi.clearAllMocks())
afterEach(() => {
  i18n.global.locale.value = 'zh-CN'
  for (const app of mounted.splice(0)) app.unmount()
})

function setup(action) {
  const controller = {
    dialog: ref({ action, target: 'second', targetName: '备用账号' }),
    name: ref('新档案'),
    selected: ref(['device']),
    file: shallowRef(null),
    sections: ref([
      {
        label: '连接与运行',
        children: [
          { key: 'device', label: '设备与游戏连接', description: '整组设备身份、截图与触控' },
          { key: 'runtime', label: '运行参数', description: '独立选择性能、采样与等待' }
        ]
      },
      {
        label: '数据',
        children: [{ key: 'inventory', label: '仓库库存', description: '材料数量' }]
      }
    ]),
    busy: ref(false),
    loading: ref(false),
    error: ref(''),
    message: ref(''),
    stale: ref(false),
    pendingReload: ref(false),
    writeDisabled: ref(false),
    selectFile: vi.fn(),
    toggleSection: vi.fn(),
    submit: vi.fn(),
    reloadPage: vi.fn(),
    refresh: vi.fn(),
    state: shallowRef({ active_id: 'first', profiles: [{ id: 'first', name: '主账号' }] })
  }
  return {
    controller,
    render: () => renderToString(createSSRApp(ConfigProfilesController, { controller }))
  }
}

describe('configuration profile dialog', () => {
  it('translates the fixed catalog in English while preserving names, source metadata and selected keys', async () => {
    const { controller, render } = setup('activate')
    i18n.global.locale.value = 'en-US'
    const html = await render()

    expect(html).toContain('Switch Profile')
    expect(html).toContain('Switch to')
    expect(html).toContain('备用账号')
    expect(html).toContain('Connection &amp; Runtime')
    expect(html).toContain('Device &amp; Game Connection')
    expect(html).toContain('Keep device identity, paths, screenshot and touch methods')
    expect(html).not.toContain('整组设备身份、截图与触控')
    expect(html).toContain('data-value="device"')
    expect(html).toContain('data-value="runtime"')
    expect(controller.selected.value).toEqual(['device'])
    expect(controller.sections.value[0]).toMatchObject({
      label: '连接与运行',
      children: [
        { key: 'device', label: '设备与游戏连接', description: '整组设备身份、截图与触控' },
        { key: 'runtime', label: '运行参数', description: '独立选择性能、采样与等待' }
      ]
    })
    expect(controller.submit).not.toHaveBeenCalled()
  })

  it.each(['ja-JP', 'zh-TW'])(
    'translates the fixed catalog in %s while retaining its selection',
    async (locale) => {
      const { controller, render } = setup('activate')
      i18n.global.locale.value = locale
      const html = await render()
      expect(html).toContain(i18n.global.t('settings.profileCatalog.deviceLabel'))
      expect(html).toContain(i18n.global.t('settings.profileCatalog.sectionConnection'))
      expect(html).toContain('data-value="device"')
      expect(html).toContain('备用账号')
      expect(controller.selected.value).toEqual(['device'])
      expect(controller.sections.value[0].children[0].label).toBe('设备与游戏连接')
      expect(controller.submit).not.toHaveBeenCalled()
    }
  )

  it('keeps unknown catalog extensions visible using their original labels and descriptions', async () => {
    const { controller, render } = setup('import')
    controller.sections.value.push({
      key: 'future-section',
      label: '后端新增分类',
      children: [{ key: 'future_group', label: '后端新增项目', description: '后端新增项目说明' }]
    })
    i18n.global.locale.value = 'en-US'
    const html = await render()
    expect(html).toContain('Device &amp; Game Connection')
    expect(html).toContain('后端新增分类')
    expect(html).toContain('后端新增项目说明')
    expect(html).toContain('data-value="future_group"')
    expect(controller.selected.value).toEqual(['device'])
  })

  it('renders backend sections as expandable checkbox groups with one complete device group', async () => {
    const { render } = setup('create')
    const html = await render()
    expect(html.match(/<details /g)).toHaveLength(2)
    expect(html).toContain('data-value="device"')
    expect(html).toContain('data-value="runtime"')
    expect(html).toContain('data-value="inventory"')
    expect(html).toContain('data-indeterminate="true"')
    expect(html).toContain('overflow-y:auto')
    expect(html.slice(html.indexOf('<footer>'))).toContain('创建并切换')
    expect(html).toContain('未勾选的项目使用默认值')
  })

  it.each([
    ['activate', '未勾选的项目使用目标档案'],
    ['import', '其余内容来自 ZIP']
  ])('explains current-content ownership for %s', async (action, expected) => {
    const { render } = setup(action)
    const html = await render()
    expect(html).toContain(expected)
    expect(html).toContain('尚未应用的设备身份和弹窗编辑草稿')
    expect(html).toContain('切换后不会自动开始任务')
  })

  it('renames without presenting snapshot selection', async () => {
    const { render } = setup('rename')
    const html = await render()
    expect(html).toContain('保存名称')
    expect(html).not.toContain('<details')
    expect(html).not.toContain('沿用')
  })

  it('shows reload recovery instead of repeating an operation after an uncertain response', async () => {
    const { controller, render } = setup('activate')
    controller.stale.value = true
    controller.error.value = '操作结果尚未确认，自动保存已暂停'
    const html = await render()
    expect(html).toContain('需要重新加载档案')
    expect(html).toContain('检查当前档案')
    expect(html).toContain('主账号')
    expect(html).not.toContain('<details')
    expect(controller.submit).not.toHaveBeenCalled()
  })

  it('offers a full page reload after failed bootstrap instead of only refreshing the list', async () => {
    const { controller, render } = setup('create')
    controller.dialog.value = null
    controller.error.value = '档案列表读取失败'
    const html = await render()
    expect(html).toContain('档案管理不可用')
    expect(html).toContain('重新加载页面')
    expect(html).not.toContain('重新读取')
    expect(controller.refresh).not.toHaveBeenCalled()
  })

  it.each(['档案已重命名。', '已开始下载档案。'])(
    'keeps completed success %s silent',
    async (message) => {
      const { controller, render } = setup('rename')
      controller.dialog.value = null
      controller.message.value = message
      const html = await render()
      expect(feedback.success).not.toHaveBeenCalled()
      expect(html).not.toContain(message)
      expect(html).not.toContain('profiles-message')
    }
  )

  it('keeps success silent after the operation finishes and its dialog closes', async () => {
    const { controller } = setup('rename')
    controller.busy.value = true
    mount(controller)
    controller.message.value = '档案已重命名。'
    await nextTick()
    expect(feedback.success).not.toHaveBeenCalled()
    controller.dialog.value = null
    await nextTick()
    expect(feedback.success).not.toHaveBeenCalled()
    controller.busy.value = false
    await nextTick()
    expect(feedback.success).not.toHaveBeenCalled()
  })

  it('keeps success feedback out of dialogs, errors and reload recovery', async () => {
    const { controller, render } = setup('rename')
    controller.message.value = '档案已重命名。'
    expect(await render()).not.toContain('档案已重命名。')
    controller.dialog.value = null
    controller.error.value = '读取失败'
    expect(await render()).not.toContain('档案已重命名。')
    controller.error.value = ''
    controller.pendingReload.value = true
    expect(await render()).not.toContain('档案已重命名。')
    expect(feedback.success).not.toHaveBeenCalled()
    expect(controller.message.value).toBe('档案已重命名。')
  })
})
