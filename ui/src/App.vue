<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
    :theme-overrides="theme == 'dark' ? mowerDarkThemeOverrides : mowerLightThemeOverrides"
    :hljs="hljs"
    :style="{
      userSelect: 'none',
      ...(theme === 'dark' ? mowerDarkCssVariables : mowerLightCssVariables)
    }"
    :class="{
      'provider--dark': theme === 'dark',
      'provider--window-shell': windowShellActive
    }"
  >
    <n-global-style />
    <WindowTitlebar
      :active="windowShellActive"
      :title="windowShellTitle"
      :version="windowTitleVersion"
      :instance-name="windowShell.metadata.instanceName || '默认实例'"
      :theme="theme"
      :control-side="windowShellControlSide"
      :maximized="windowShellState.maximized"
      :controls="windowShellControls"
      :busy="windowShellBusy"
      :mower-port="mowerPort"
      :emulator-name="emulatorName"
      :adb-port="adbPort"
      :on-control="windowShell.runControl"
      :on-toggle-maximize="windowShell.toggleMaximize"
      :resizable="windowShellPlatform === 'windows' && !windowShellState.maximized"
      :on-resize="windowShell.startResize"
    />
    <n-dialog-provider>
      <n-message-provider>
        <n-loading-bar-provider>
          <n-watermark
            :content="watermarkData"
            cross
            fullscreen
            :font-size="16"
            :line-height="32"
            :width="400"
            :height="384"
            :x-offset="12"
            :y-offset="60"
            :rotate="-15"
          />
          <n-layout
            :has-sider="!mobile"
            class="outer-layout"
            :class="{ 'outer-layout--collapsed': sidebarCollapsed }"
          >
            <n-layout-sider
              v-if="!mobile"
              :bordered="!windowShellActive"
              collapse-mode="width"
              :collapsed-width="64"
              :width="210"
              v-model:collapsed="sidebarCollapsed"
              :show-trigger="!windowShellActive"
            >
              <n-menu
                :indent="24"
                :collapsed-width="64"
                :collapsed-icon-size="22"
                :options="menuOptions"
                @update:value="handleMenuClick"
              />
            </n-layout-sider>
            <n-layout-content class="layout-content-container">
              <router-view v-if="loaded" />
              <GlobalUpdateDrop v-if="loaded" />
              <ChatBot v-if="chatBotMounted" v-model:show="showChatBot" />
              <Feedback />
              <n-modal
                v-model:show="showUpdateNoticeModal"
                preset="card"
                style="width: min(720px, calc(100vw - 32px))"
                title="版本更新"
                :mask-closable="false"
                :close-on-esc="false"
                closable
                @close="handleUpdateNoticeAck"
              >
                <div style="font-size: 18px; font-weight: 600">
                  {{ `已更新到 ${updateNotice.current_version}` }}
                </div>
                <div
                  v-if="updateNotice.previous_version"
                  style="margin-top: 8px; color: var(--n-text-color-3)"
                >
                  {{ `从 ${updateNotice.previous_version} 更新` }}
                </div>
                <div
                  style="margin-top: 16px; max-height: 50vh; overflow: auto; line-height: 1.6"
                  v-html="renderedChangelog"
                ></div>
                <div style="margin-top: 20px; display: flex; justify-content: flex-end">
                  <n-button type="primary" @click="handleUpdateNoticeAck">我知道了</n-button>
                </div>
              </n-modal>
            </n-layout-content>
            <template v-if="windowShellActive && !mobile">
              <div class="sider-fade-zone" @mousedown.stop @click="toggleSidebar">
                <div
                  class="sider-fade-btn"
                  :class="{ 'sider-fade-btn--collapsed': sidebarCollapsed }"
                  aria-hidden="true"
                >
                  <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path
                      d="M5.64645 3.14645C5.45118 3.34171 5.45118 3.65829 5.64645 3.85355L9.79289 8L5.64645 12.1464C5.45118 12.3417 5.45118 12.6583 5.64645 12.8536C5.84171 13.0488 6.15829 13.0488 6.35355 12.8536L10.8536 8.35355C11.0488 8.15829 11.0488 7.84171 10.8536 7.64645L6.35355 3.14645C6.15829 2.95118 5.84171 2.95118 5.64645 3.14645Z"
                      fill="currentColor"
                    />
                  </svg>
                </div>
              </div>
            </template>
            <n-layout-footer v-if="mobile">
              <n-tabs type="line" justify-content="space-evenly" size="small">
                <n-tab name="日志" @click="$router.push('/')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="BookOutline" />
                    日志
                  </div>
                </n-tab>
                <n-tab name="设置" @click="showModal2 = true">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="Settings" />
                    设置
                  </div>
                  <n-modal v-model:show="showModal2">
                    <n-card
                      style="width: 300px"
                      title="全部设置"
                      :bordered="false"
                      size="huge"
                      role="dialog"
                      aria-modal="true"
                    >
                      <div>
                        <n-button @click=";((showModal2 = false), $router.push('/mowersettings'))">
                          mower设置
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";((showModal2 = false), $router.push('/maasettings'))">
                          maa设置
                        </n-button>
                      </div>
                    </n-card>
                  </n-modal>
                </n-tab>
                <n-tab name="排班" @click="$router.push('/plan-editor')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="Home" />
                    排班
                  </div>
                </n-tab>
                <n-tab name="专精推荐" @click="$router.push('/mastery-recommendation')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="SkillLevelAdvanced" />
                    专精
                  </div>
                </n-tab>
                <n-tab name="报表" @click="showModal = true">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="StatsChart" />
                    报表
                  </div>
                  <n-modal v-model:show="showModal">
                    <n-card
                      style="width: 300px"
                      title="基建报表"
                      :bordered="false"
                      size="huge"
                      role="dialog"
                      aria-modal="true"
                    >
                      <div>
                        <n-button @click=";((showModal = false), $router.push('/record/line'))">
                          心情曲线
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";((showModal = false), $router.push('/record/pie'))">
                          心情饼图
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";((showModal = false), $router.push('/record/depot'))">
                          仓库
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";((showModal = false), $router.push('/record/report'))">
                          基建报告
                        </n-button>
                      </div>
                      <div>
                        <n-button
                          @click=";((showModal = false), $router.push('/record/trading_analysis'))"
                        >
                          贸易订单分析
                        </n-button>
                      </div>
                    </n-card>
                  </n-modal>
                </n-tab>
                <n-tab name="帮助" @click="$router.push('/doc')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="HelpCircle" />
                    帮助
                  </div>
                </n-tab>
                <n-tab name="资源" @click="$router.push('/readme')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="Bag" />
                    资源
                  </div>
                </n-tab>
                <n-tab name="Mower AI 助手" @click="handleMenuClick('chatbot')">
                  <div style="display: flex; flex-direction: column; align-items: center">
                    <n-icon size="20" style="margin-bottom: -1px" :component="BulbOutline" />
                    AI助手
                  </div>
                </n-tab>
              </n-tabs>
            </n-layout-footer>
          </n-layout>
        </n-loading-bar-provider>
      </n-message-provider>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup>
import SkillLevelAdvanced from '@vicons/carbon/SkillLevelAdvanced'
import WikipediaW from '@vicons/fa/WikipediaW'
import BulbOutline from '@vicons/ionicons5/BulbOutline'
import Wrench from '@vicons/fa/Wrench'
import Bag from '@vicons/ionicons5/Bag'
import BarChart from '@vicons/ionicons5/BarChart'
import BookOutline from '@vicons/ionicons5/BookOutline'
import HelpCircle from '@vicons/ionicons5/HelpCircle'
import Home from '@vicons/ionicons5/Home'
import PieChart from '@vicons/ionicons5/PieChart'
import ReaderOutline from '@vicons/ionicons5/ReaderOutline'
import Newspaper from '@vicons/ionicons5/Newspaper'
import Settings from '@vicons/ionicons5/Settings'
import StatsChart from '@vicons/ionicons5/StatsChart'
import Storefront from '@vicons/ionicons5/Storefront'
import RoseOutline from '@vicons/ionicons5/RoseOutline'
import Coffee from '@vicons/tabler/Coffee'
import { NIcon } from 'naive-ui'
import { storeToRefs } from 'pinia'
import {
  computed,
  defineAsyncComponent,
  h,
  inject,
  nextTick,
  onBeforeUnmount,
  onMounted,
  provide,
  ref,
  watch
} from 'vue'
import Feedback from '@/components/Feedback.vue'
import GlobalUpdateDrop from '@/components/GlobalUpdateDrop.vue'
import WindowTitlebar from '@/components/WindowTitlebar.vue'
import {
  mowerDarkCssVariables,
  mowerDarkThemeOverrides,
  mowerLightCssVariables,
  mowerLightThemeOverrides
} from '@/theme/mower'
import '@/theme/mower.css'
import { createWindowShellAdapter, formatWindowTitle } from '@/window-shell/adapter.js'
import { installModalDragging } from '@/utils/modal-drag.js'

const ChatBot = defineAsyncComponent(() => import('@/components/ChatBot.vue'))
const windowShell = createWindowShellAdapter()
const {
  active: windowShellActive,
  busy: windowShellBusy,
  controls: windowShellControls,
  controlSide: windowShellControlSide,
  platform: windowShellPlatform,
  state: windowShellState
} = windowShell

let disposeModalDrag = null

const showModal = ref(false)
const showModal2 = ref(false)
const showFeedback = ref(false)
const sidebarCollapsed = ref(false)
provide('show_feedback', showFeedback)
provide('sidebar_collapsed', sidebarCollapsed)
function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
}
function renderIcon(icon) {
  return () => h(NIcon, null, { default: () => h(icon) })
}
const showChatBot = ref(false)
const chatBotMounted = ref(false)
function handleMenuClick(key) {
  if (key === 'chatbot') {
    chatBotMounted.value = true
    showChatBot.value = true
  }
}
import { RouterLink } from 'vue-router'
const menuOptions = [
  {
    label: () => h(RouterLink, { to: { path: '/' } }, { default: () => '运行日志' }),
    icon: renderIcon(BookOutline),
    key: 'go-to-log'
  },
  {
    label: () => '全部设置',
    icon: renderIcon(Settings),
    key: 'allsetting',
    children: [
      {
        label: () =>
          h(RouterLink, { to: { path: '/mowersettings' } }, { default: () => 'mower设置' }),
        icon: renderIcon(Coffee),
        key: 'go-to-mowersetting'
      },
      {
        label: () => h(RouterLink, { to: { path: '/maasettings' } }, { default: () => 'maa设置' }),
        icon: renderIcon(RoseOutline),
        key: 'go-to-maasetting'
      }
    ]
  },
  {
    label: () => h(RouterLink, { to: { path: '/plan-editor' } }, { default: () => '排班编辑' }),
    icon: renderIcon(Home),
    key: 'go-to-plan'
  },
  {
    label: () =>
      h(RouterLink, { to: { path: '/mastery-recommendation' } }, { default: () => '专精推荐' }),
    icon: renderIcon(SkillLevelAdvanced),
    key: 'go-to-mastery-recommendation'
  },
  {
    label: () => '数据图表',
    key: 'building-report',
    icon: renderIcon(StatsChart),
    children: [
      {
        label: () =>
          h(RouterLink, { to: { path: '/record/line' } }, { default: () => '干员心情报表' }),
        icon: renderIcon(BarChart),
        key: 'go-to-record-line'
      },
      {
        label: () =>
          h(RouterLink, { to: { path: '/record/pie' } }, { default: () => '工休比报表' }),
        icon: renderIcon(PieChart),
        key: 'go-to-record-pie'
      },
      {
        label: () => h(RouterLink, { to: { path: '/record/depot' } }, { default: () => '仓库' }),
        icon: renderIcon(Storefront),
        key: 'go-to-record-depot'
      },
      {
        label: () =>
          h(RouterLink, { to: { path: '/record/report' } }, { default: () => '基建报表' }),
        icon: renderIcon(ReaderOutline),
        key: 'go-to-record-report'
      },
      {
        label: () =>
          h(
            RouterLink,
            { to: { path: '/record/trading_analysis' } },
            { default: () => '贸易订单分析' }
          ),
        icon: renderIcon(Newspaper),
        key: 'go-to-trading-analysis'
      }
    ]
  },
  {
    label: () => h(RouterLink, { to: { path: '/doc' } }, { default: () => '帮助文档' }),
    icon: renderIcon(HelpCircle),
    key: 'go-to-doc'
  },
  {
    label: () => h(RouterLink, { to: { path: '/readme' } }, { default: () => '其他资源' }),
    icon: renderIcon(Bag),
    key: 'readme'
  },
  {
    label: () => h(RouterLink, { to: { path: '/BasementSkill' } }, { default: () => '基建技能' }),
    icon: renderIcon(SkillLevelAdvanced),
    key: 'BasementSkill'
  },
  {
    label: () =>
      h(
        'a',
        {
          href: 'https://arkntools.app/ ',
          target: '_blank',
          rel: 'noopenner noreferrer'
        },
        '明日方舟工具箱'
      ),
    key: 'toolbox',
    icon: renderIcon(Wrench)
  },
  {
    label: () =>
      h(
        'a',
        {
          href: 'https://prts.wiki/w/%E9%A6%96%E9%A1%B5',
          target: '_blank',
          rel: 'noopenner noreferrer'
        },
        '明日方舟PRTS'
      ),
    key: 'wiki',
    icon: renderIcon(WikipediaW)
  },
  {
    label: () => 'Mower AI 助手',
    icon: renderIcon(BulbOutline),
    key: 'chatbot'
  }
]

import { darkTheme, dateZhCN, zhCN } from 'naive-ui'

import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'

hljs.registerLanguage('json', json)

import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { usePlanStore } from '@/stores/plan'
import { useUpdateNoticeStore } from '@/stores/updateNotice'
import { useResourceVersionStore } from '@/stores/resourceVersion'

import { usewatermarkStore } from '@/stores/watermark'

const watermarkStore = usewatermarkStore()
const { getwatermarkinfo } = watermarkStore

const watermarkData = ref('mower')

const config_store = useConfigStore()
const { load_config, load_shop, load_item } = config_store
const {
  hot_update_enable,
  hot_update_auto_update,
  simulator,
  start_automatically,
  theme,
  webview,
  adb
} = storeToRefs(config_store)
let activeThemeTransition = null

async function setThemeWithTransition(nextTheme) {
  if (nextTheme === theme.value) return

  const root = document.documentElement
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  root.classList.add('mower-theme-changing')

  if (!reduceMotion && typeof document.startViewTransition === 'function') {
    activeThemeTransition?.skipTransition?.()
    const transition = document.startViewTransition(async () => {
      theme.value = nextTheme
      await nextTick()
    })
    activeThemeTransition = transition
    try {
      await transition.ready.catch(() => {})
    } finally {
      if (activeThemeTransition === transition) {
        root.classList.remove('mower-theme-changing')
      }
    }
    void transition.finished
      .catch(() => {})
      .finally(() => {
        if (activeThemeTransition === transition) activeThemeTransition = null
      })
    return
  }

  const provider = document.querySelector('.provider')
  if (!reduceMotion && provider?.animate) {
    const fadeOut = provider.animate([{ opacity: 1 }, { opacity: 0.84 }], {
      duration: 90,
      easing: 'ease-out',
      fill: 'forwards'
    })
    await fadeOut.finished.catch(() => {})
    fadeOut.cancel()
  }
  theme.value = nextTheme
  await nextTick()
  root.classList.remove('mower-theme-changing')
  provider?.animate?.([{ opacity: 0.84 }, { opacity: 1 }], {
    duration: 130,
    easing: 'ease-out'
  })
}

provide('set_theme_with_transition', setThemeWithTransition)
const windowShellTitle = computed(() =>
  formatWindowTitle({
    version: windowTitleVersion.value,
    instanceName: windowShell.metadata.instanceName
  })
)

// 标题栏副信息：实例@端口 与 模拟器@adb端口。实例名已写进系统窗口标题（formatWindowTitle），
// 这里标题栏内再补两个 @端口：mower 端口 = 前端服务所在端口（webview 与后端同源），
// adb 端口 = ADB 连接地址（形如 127.0.0.1:62001）的端口段。
const mowerPort = computed(() => window.location.port || '')
const emulatorName = computed(() => simulator.value?.name || '')
const adbPort = computed(() => {
  const addr = adb.value || ''
  const idx = addr.lastIndexOf(':')
  return idx === -1 ? '' : addr.slice(idx + 1)
})

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)
const { load_plan, load_operators } = plan_store

const mower_store = useMowerStore()
const { ws, running, log_lines, auto_start_handled } = storeToRefs(mower_store)
const { get_running, listen_ws } = mower_store

const update_notice_store = useUpdateNoticeStore()
const { notice: updateNotice } = storeToRefs(update_notice_store)
const { ackUpdateNotice, loadUpdateNotice } = update_notice_store
const showUpdateNoticeModal = ref(false)

const resource_version_store = useResourceVersionStore()
const { installResource, loadResourceVersion, loadResourceJob } = resource_version_store
// 标题栏版本：软件版固定（取启动快照的前半段），资源版实时取当前生效的资源包展示版本；
// 资源包在别处更新时后端广播 resource_updated → loadResourceVersionLocal 刷新这里。
const windowTitleVersion = computed(() => {
  const snapshot = windowShell.metadata.version
  const sep = snapshot.lastIndexOf(' - ')
  const softVer = sep === -1 ? snapshot : snapshot.slice(0, sep)
  const liveRes = resource_version_store.info.current_display
  return liveRes ? `${softVer} - ${liveRes}` : softVer
})

const axios = inject('axios')

function start() {
  running.value = true
  log_lines.value = []
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start/0`)
}

function actions_on_resize() {
  document.documentElement.style.setProperty(
    '--app-height',
    `${window.innerHeight / webview.value.scale}px`
  )
  document.documentElement.style.setProperty(
    '--app-width',
    `${window.innerWidth / webview.value.scale}px`
  )
  mobile.value = window.innerWidth < 800 * webview.value.scale
}

const mobile = ref(true)
provide('mobile', mobile)

const loaded = inject('loaded')

const renderedChangelog = ref('')
let changelogRendered = false
async function renderChangelog() {
  if (changelogRendered) return
  changelogRendered = true
  const [{ default: markdownit }, { default: externalLink }] = await Promise.all([
    import('markdown-it'),
    import('markdown-it-external-link')
  ])
  const md = markdownit({ html: true, breaks: true }).use(externalLink, {
    externalTarget: '_blank',
    rel: 'noopener noreferrer'
  })
  renderedChangelog.value = md.render(updateNotice.value.changelog)
}

async function handleUpdateNoticeAck() {
  if (!updateNotice.value.current_version) {
    showUpdateNoticeModal.value = false
    return
  }
  try {
    await ackUpdateNotice(updateNotice.value.current_version)
    showUpdateNoticeModal.value = false
  } catch (error) {
    console.error('failed to acknowledge update notice', error)
  }
}

const operators_with_free_current = computed(() => {
  return [
    { value: 'Current', label: 'Current' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

onMounted(async () => {
  void windowShell.initialize()
  disposeModalDrag = installModalDragging()
  actions_on_resize()
  window.addEventListener('resize', () => {
    actions_on_resize()
  })

  const params = new URLSearchParams(document.location.search)
  const token = params.get('token')
  const instanceName = params.get('instance_name')
  provide('token', token)
  axios.defaults.headers.common['token'] = token
  // getwatermarkinfo 独立并行，失败不影响主流程（watermark 仅装饰用途）
  getwatermarkinfo()
    .then((info) => {
      watermarkData.value = info
    })
    .catch(() => {})
  await Promise.all([load_config(), load_shop(), load_item(), load_operators(), get_running()])

  document.title = instanceName
    ? `${instanceName} - arknights-mower`
    : simulator.value?.name
      ? `${simulator.value.name} - arknights-mower`
      : 'arknights-mower'

  axios
    .post(
      `${import.meta.env.VITE_HTTP_URL || ''}/software-update/auto-check`,
      {},
      {
        headers: { 'X-Mower-Update': '1' }
      }
    )
    .catch((error) => console.error('failed to request automatic software check', error))

  await load_plan()

  try {
    const notice = await loadUpdateNotice()
    showUpdateNoticeModal.value = notice.should_show
    if (notice.should_show) {
      renderChangelog()
    }
  } catch (error) {
    console.error('failed to load update notice', error)
    showUpdateNoticeModal.value = false
  }
  // Render settings while updating, but resume automatic tasks only afterwards.
  const resourceUpdateRequest = (async () => {
    try {
      if (await loadResourceJob()) {
        await Promise.all([load_shop(), load_item(), load_operators()])
      }
      if (hot_update_enable.value) {
        const resourceInfo = await loadResourceVersion()
        if (hot_update_auto_update.value && resourceInfo.update_available === true) {
          if (await installResource()) {
            await Promise.all([load_shop(), load_item(), load_operators()])
          }
        }
      }
    } catch (error) {
      console.error('failed to load resource version', error)
    }
  })()

  loaded.value = true

  const r = RegExp(operators_with_free_current.value.map((x) => "'" + x.value).join('|'))
  hljs.registerLanguage('mower', () => ({
    contains: [
      {
        begin: r,
        end: /'/,
        className: 'operator',
        relevance: 0
      },
      {
        begin: /宿舍黑名单|重设上次房间为空/,
        relevance: 10
      },
      {
        begin: /[0-9]+(-[0-9]+)+/,
        className: 'date'
      },
      {
        begin: /[0-9]+:[0-9]+:[0-9]+((\.|,)[0-9]+)?/,
        className: 'time'
      },
      {
        begin: /room_[0-9]_[0-9]|dormitory_[0-9]|central|contact|factory|meeting/,
        className: 'room'
      },
      {
        begin: /INFO/,
        className: 'info'
      },
      {
        begin: /WARNING/,
        className: 'warning'
      },
      {
        begin: /ERROR/,
        className: 'error'
      },
      {
        begin: /Scene [0-9]+:.*/,
        className: 'scene'
      }
    ]
  }))

  if (!ws.value) {
    listen_ws()
  }

  await resourceUpdateRequest
  if (start_automatically.value && !auto_start_handled.value) {
    start()
  }
})

onBeforeUnmount(() => {
  disposeModalDrag?.()
  windowShell.dispose()
  delete document.documentElement.dataset.windowShellTheme
  delete document.documentElement.dataset.mowerTheme
})

watch(
  [theme, loaded, windowShellActive],
  ([currentTheme, appLoaded, shellActive]) => {
    document.documentElement.dataset.mowerTheme = currentTheme === 'dark' ? 'dark' : 'light'
    if (appLoaded && shellActive) {
      document.documentElement.dataset.windowShellTheme = currentTheme === 'dark' ? 'dark' : 'light'
      window.scrollTo(0, 0)
    }
  },
  { immediate: true }
)

watch(
  () => webview.value.scale,
  () => {
    const ele = document.querySelector('#app')
    ele.style.transform = `scale(${webview.value.scale})`
    actions_on_resize()
  }
)
</script>

<style>
.n-avatar {
  pointer-events: none !important;
}

.img {
  pointer-events: none !important;
}
</style>

<style scoped>
.tabs {
  height: 100%;
}

.provider {
  height: 100%;
}

.layout-container {
  height: 100%;
}
</style>

<style lang="scss">
#app {
  height: var(--app-height, 100vh);
  width: var(--app-width, 100vw);
  transform-origin: 0 0;
}

.provider--window-shell {
  --window-shell-frame-surface: #faf9f7;
  --window-shell-content-surface: #fff;
  --window-shell-content-shadow-left: rgba(63, 55, 47, 0.13);
  --window-shell-content-shadow-top: rgba(63, 55, 47, 0.07);
  --window-shell-content-shadow-corner: rgba(63, 55, 47, 0.09);
  --window-shell-scrollbar-thumb: rgba(46, 43, 40, 0.2);
  --window-shell-scrollbar-thumb-hover: rgba(46, 43, 40, 0.34);
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--window-shell-frame-surface);
}

html[data-window-shell-theme='dark'] .provider--window-shell {
  --window-shell-frame-surface: #18181c;
  --window-shell-content-surface: #101014;
  --window-shell-content-shadow-left: rgba(0, 0, 0, 0.34);
  --window-shell-content-shadow-top: rgba(0, 0, 0, 0.2);
  --window-shell-content-shadow-corner: rgba(0, 0, 0, 0.26);
  --window-shell-scrollbar-thumb: rgba(255, 255, 255, 0.18);
  --window-shell-scrollbar-thumb-hover: rgba(255, 255, 255, 0.3);
  background: var(--window-shell-frame-surface);
}

.provider--window-shell .outer-layout {
  flex: 1 1 auto;
  min-height: 0;
  height: auto;
  background: var(--window-shell-frame-surface);
}

.provider--window-shell .n-layout-sider {
  background: var(--window-shell-frame-surface);
}

.provider--window-shell .n-layout-sider__border {
  background: transparent;
}

.provider--window-shell .layout-content-container {
  position: relative;
  z-index: 1;
  overflow: hidden;
  background: var(--window-shell-content-surface);
  border-radius: 10px 0 0 0;
  box-shadow:
    -7px 0 18px -14px var(--window-shell-content-shadow-left),
    0 -6px 16px -14px var(--window-shell-content-shadow-top),
    -5px -5px 20px -16px var(--window-shell-content-shadow-corner);
}

/* shadcn 输入框（n-input / n-input-number）——按 shadcn Input 源码规格：
   h-9(36px) / rounded-md(6px) / 1px border-input / bg-background / px-3 / text-sm
   / placeholder:muted-foreground / focus-visible:ring-2 + ring-offset-2 */
.n-input {
  --n-height: 36px !important;
  --n-border-radius: 6px !important;
  --n-border: 1px solid #e4e4e7 !important;
  --n-border-hover: 1px solid #d4d4d8 !important;
  --n-border-focus: 1px solid #e4e4e7 !important;
  --n-color: #ffffff !important;
  --n-color-hover: #ffffff !important;
  --n-color-focus: #ffffff !important;
  --n-padding-left: 12px !important;
  --n-padding-right: 12px !important;
  --n-padding-vertical: 0 !important;
  --n-text-color: #09090b !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px #ffffff, 0 0 0 4px rgba(24, 160, 88, 0.4) !important;
}
html[data-window-shell-theme='dark'] .n-input {
  --n-border: 1px solid #27272a !important;
  --n-border-hover: 1px solid #3f3f46 !important;
  --n-border-focus: 1px solid #27272a !important;
  --n-color: #101014 !important;
  --n-color-hover: #101014 !important;
  --n-color-focus: #101014 !important;
  --n-text-color: #fafafa !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px #101014, 0 0 0 4px rgba(99, 226, 183, 0.4) !important;
}

/* shadcn 下拉选择框（n-select）：触发器 = 同款输入框盒子 + 菜单 = 圆角浮层/option 高亮 */
.n-base-selection {
  --n-height: 36px !important;
  --n-border-radius: 6px !important;
  --n-border: 1px solid #e4e4e7 !important;
  --n-border-hover: 1px solid #d4d4d8 !important;
  --n-border-focus: 1px solid #e4e4e7 !important;
  --n-color: #ffffff !important;
  --n-color-active: #ffffff !important;
  --n-box-shadow-focus: 0 0 0 2px #ffffff, 0 0 0 4px rgba(24, 160, 88, 0.4) !important;
  --n-text-color: #09090b !important;
  --n-placeholder-color: #71717a !important;
  --n-padding-single: 0 12px !important;
  --n-font-size: 14px !important;
}
.n-base-select-menu {
  --n-color: #ffffff !important;
  --n-border-radius: 6px !important;
  --n-option-font-size: 14px !important;
  --n-option-color-pending: rgba(24, 160, 88, 0.08) !important;
  --n-option-color-active: rgba(24, 160, 88, 0.1) !important;
  --n-option-color-active-pending: rgba(24, 160, 88, 0.14) !important;
}
html[data-window-shell-theme='dark'] .n-base-selection {
  --n-border: 1px solid #27272a !important;
  --n-border-hover: 1px solid #3f3f46 !important;
  --n-border-focus: 1px solid #27272a !important;
  --n-color: #101014 !important;
  --n-color-active: #101014 !important;
  --n-text-color: #fafafa !important;
  --n-placeholder-color: #71717a !important;
  --n-box-shadow-focus: 0 0 0 2px #101014, 0 0 0 4px rgba(99, 226, 183, 0.4) !important;
}
html[data-window-shell-theme='dark'] .n-base-select-menu {
  --n-color: #101014 !important;
  --n-option-color-pending: rgba(99, 226, 183, 0.12) !important;
  --n-option-color-active: rgba(99, 226, 183, 0.16) !important;
  --n-option-color-active-pending: rgba(99, 226, 183, 0.2) !important;
}

html.mower-theme-changing *,
html.mower-theme-changing *::before,
html.mower-theme-changing *::after {
  transition: none !important;
}

::view-transition-old(root),
::view-transition-new(root) {
  animation-duration: 220ms;
  animation-timing-function: cubic-bezier(0.22, 1, 0.36, 1);
  mix-blend-mode: normal;
}

::view-transition-old(root) {
  animation-name: mower-theme-fade-out;
}

::view-transition-new(root) {
  animation-name: mower-theme-fade-in;
}

@keyframes mower-theme-fade-out {
  to {
    opacity: 0;
  }
}

@keyframes mower-theme-fade-in {
  from {
    opacity: 0;
  }
}

/* naive-ui 弹窗 teleport 到 <body>，不在 .provider--window-shell 内，
   所以上面的滚动条样式和 --window-shell-scrollbar-thumb 变量都够不到它。
   mower.css 已让 .n-modal 的卡片/对话框内容节点滚动（.n-card-content / .n-dialog__content），
   这里把同名滚动条样式应用到这些 body 级浮层，并把变量提到 :root 兜底。 */
:root {
  --window-shell-scrollbar-thumb: rgba(46, 43, 40, 0.2);
  --window-shell-scrollbar-thumb-hover: rgba(46, 43, 40, 0.34);
}
html[data-window-shell-theme='dark'] {
  --window-shell-scrollbar-thumb: rgba(255, 255, 255, 0.18);
  --window-shell-scrollbar-thumb-hover: rgba(255, 255, 255, 0.3);
}

.provider--window-shell *,
.n-modal,
.n-modal * {
  scrollbar-color: var(--window-shell-scrollbar-thumb) transparent;
  scrollbar-width: thin;
}

.provider--window-shell *::-webkit-scrollbar,
.n-modal *::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

.provider--window-shell *::-webkit-scrollbar-track,
.provider--window-shell *::-webkit-scrollbar-corner,
.n-modal *::-webkit-scrollbar-track,
.n-modal *::-webkit-scrollbar-corner {
  background: transparent;
}

.provider--window-shell *::-webkit-scrollbar-thumb,
.n-modal *::-webkit-scrollbar-thumb {
  min-height: 36px;
  background: var(--window-shell-scrollbar-thumb);
  background-clip: content-box;
  border: 3px solid transparent;
  border-radius: 999px;
}

.provider--window-shell *::-webkit-scrollbar-thumb:hover,
.n-modal *::-webkit-scrollbar-thumb:hover {
  background: var(--window-shell-scrollbar-thumb-hover);
  background-clip: content-box;
}

.provider--window-shell *::-webkit-scrollbar-button,
.n-modal *::-webkit-scrollbar-button {
  display: none;
  width: 0;
  height: 0;
}

.n-tab-pane {
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.n-card-header__main {
  display: flex;
  align-items: center;
  gap: 6px;
}

td {
  height: 34px;
}

.table-space {
  padding-right: 20px;
}

.external-container {
  max-width: 600px;
  margin: 0 auto;
}

.n-checkbox {
  align-items: center;
}

.n-form-item {
  margin-top: 12px;

  &:first-child {
    margin-top: 0;
  }
}

.dialog-btn {
  /* 与旁边的路径输入框（36px）对齐：高度拉到 36px；间距 8px 给输入框聚焦 ring(外扩4px) 留空档 */
  margin-left: 8px;
  --n-height: 36px !important;
}

.report-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  /* 让内容在水平方向上居中 */
  justify-content: center;
  /* 让内容在垂直方向上居中 */

  width: 300px;
  height: 200px;
  padding: 20px 20px 80px 20px;
  border: 1px solid #ccc;
}

.n-checkbox .n-checkbox__label {
  flex-grow: 1;
  display: flex;
  align-items: center;
  padding-right: 0;
}

.outer-layout {
  position: relative;
  height: 100%;
}

/* 无边框窗口：侧栏折叠触发器，悬挂在侧栏/内容交界线上，鼠标滑到才浮现。图标为 naive 原生
   ChevronRight（arrow-circle 触发器同款）；展开时朝左(旋转180°)、折叠时朝右。 */
.provider--window-shell .sider-fade-zone {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 210px;
  width: 22px;
  transform: translateX(-50%);
  cursor: pointer;
  z-index: 2;
}
.outer-layout--collapsed .sider-fade-zone {
  left: 64px;
}
.sider-fade-btn {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.07);
  background: #fff;
  color: #808080;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
  display: grid;
  place-items: center;
  opacity: 0;
  transition:
    opacity 0.15s ease,
    color 0.15s ease;
}
.sider-fade-zone:hover .sider-fade-btn,
.sider-fade-btn:focus-visible {
  opacity: 1;
  color: #18a058;
}
.sider-fade-btn svg {
  display: block;
  width: 15px;
  height: 15px;
  fill: currentcolor;
  transform: rotate(180deg);
  transition: transform 0.2s ease;
}
.sider-fade-btn--collapsed svg {
  transform: rotate(0deg);
}
html[data-mower-theme='dark'] .sider-fade-btn {
  border-color: rgba(255, 255, 255, 0.18);
  background: rgb(44, 44, 50);
  color: rgba(255, 255, 255, 0.68);
}
html[data-mower-theme='dark'] .sider-fade-zone:hover .sider-fade-btn {
  color: #63e2b7;
}

.outer-layout > .n-layout-scroll-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.layout-content-container > .n-layout-scroll-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: auto;
  gap: 8px;
  align-items: center;
}

.home-container {
  padding: 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: calc(100% - 24px);
  height: calc(100% - 24px);
  position: relative;
}

pre {
  word-break: break-all !important;
  font-family:
    'Cascadia Mono', Consolas, 'Microsoft YaHei', 'SF Mono', 'Menlo', 'PingFang SC', monospace !important;
}

.n-dynamic-input-item__action {
  align-self: center !important;
}

ul,
ol {
  padding-left: 18px;
  margin: 0;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
  white-space: nowrap;
}
</style>
