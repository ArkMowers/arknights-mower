<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
    :hljs="hljs"
    style="user-select: none"
  >
    <n-global-style />
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
          <n-layout :has-sider="!mobile" class="outer-layout">
            <n-layout-sider
              v-if="!mobile"
              bordered
              collapse-mode="width"
              :collapsed-width="64"
              :width="210"
              show-trigger
            >
              <n-menu
                :indent="24"
                :collapsed-width="64"
                :collapsed-icon-size="22"
                :options="menuOptions"
              />
            </n-layout-sider>
            <n-layout-content class="layout-content-container">
              <router-view v-if="loaded" />
            </n-layout-content>
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
                        <n-button @click=";(showModal2 = false), $router.push('/mowersettings')">
                          mower设置
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";(showModal2 = false), $router.push('/maasettings')">
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
                        <n-button @click=";(showModal = false), $router.push('/record/line')">
                          心情曲线
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";(showModal = false), $router.push('/record/pie')">
                          心情饼图
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";(showModal = false), $router.push('/record/depot')">
                          仓库
                        </n-button>
                      </div>
                      <div>
                        <n-button @click=";(showModal = false), $router.push('/record/report')">
                          基建报告
                        </n-button>
                      </div>
                      <div>
                        <n-button
                          @click=";(showModal = false), $router.push('/record/trading_analysis')"
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
import { h, inject, onMounted, provide, ref } from 'vue'

const showModal = ref(false)
const showModal2 = ref(false)
function renderIcon(icon) {
  return () => h(NIcon, null, { default: () => h(icon) })
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
  // {
  //   label: () => h(RouterLink, { to: { path: '/aio' } }, { default: () => 'aio' }),
  //   icon: renderIcon(Settings),
  //   key: 'go-to-aio'
  // },
  {
    label: () => h(RouterLink, { to: { path: '/plan-editor' } }, { default: () => '排班编辑' }),
    icon: renderIcon(Home),
    key: 'go-to-plan'
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
  }
]

import { darkTheme, dateZhCN, zhCN } from 'naive-ui'

import hljs from 'highlight.js/lib/core'
import json from 'highlight.js/lib/languages/json'

hljs.registerLanguage('json', json)

import { useConfigStore } from '@/stores/config'
import { useMowerStore } from '@/stores/mower'
import { usePlanStore } from '@/stores/plan'

import { usewatermarkStore } from '@/stores/watermark'

const watermarkStore = usewatermarkStore()
const { getwatermarkinfo } = watermarkStore

const watermarkData = ref('mower')

const config_store = useConfigStore()
const { load_config, load_shop, load_item } = config_store
const { start_automatically, theme, webview } = storeToRefs(config_store)

const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)
const { load_plan, load_operators } = plan_store

const mower_store = useMowerStore()
const { ws, running, log_lines } = storeToRefs(mower_store)
const { get_running, listen_ws } = mower_store

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

const operators_with_free_current = computed(() => {
  return [
    { value: 'Current', label: 'Current' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

onMounted(async () => {
  actions_on_resize()
  window.addEventListener('resize', () => {
    actions_on_resize()
  })

  const params = new URLSearchParams(document.location.search)
  const token = params.get('token')
  provide('token', token)
  axios.defaults.headers.common['token'] = token
  await Promise.all([load_config(), load_shop(), load_item(), load_operators(), get_running()])

  await load_plan()

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

  if (start_automatically.value) {
    start()
  }

  watermarkData.value = await getwatermarkinfo()
})

watch(
  () => webview.value.scale,
  (scale) => {
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
  margin-left: 4px;
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
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.n-checkbox .n-checkbox__label {
  flex-grow: 1;
  display: flex;
  align-items: center;
  padding-right: 0;
}

.outer-layout {
  height: 100%;
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
  font-family: 'Cascadia Mono', Consolas, 'Microsoft YaHei', 'SF Mono', 'Menlo', 'PingFang SC',
    monospace !important;
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
