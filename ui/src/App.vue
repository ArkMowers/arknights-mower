<template>
  <n-config-provider
    :locale="zhCN"
    :date-locale="dateZhCN"
    class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined"
    :hljs="hljs"
  >
    <n-global-style />
    <n-dialog-provider>
      <n-layout has-sider v-if="!mobile">
        <n-layout-sider
          bordered
          collapse-mode="width"
          :collapsed-width="50"
          :width="240"
          :collapsed="collapsed"
          show-trigger
          @collapse="collapsed = true"
          @expand="collapsed = false"
        >
          <n-menu
            :indent="24"
            :collapsed="collapsed"
            :collapsed-width="64"
            :collapsed-icon-size="22"
            :options="menuOptions"
          />
        </n-layout-sider>
        <n-layout-content>
          <router-view />
        </n-layout-content>
      </n-layout>

      <n-layout v-if="mobile">
        <n-layout-header style="height: 95vh; overflow: auto; position: relative">
          <router-view />
        </n-layout-header>
        <n-layout-footer style="height: 8vh" position="absolute">
          <n-tabs type="line" justify-content="space-evenly">
            <n-tab name="主页" @click="$router.push('/')">
              <div style="display: flex; flex-direction: column; align-items: center">
                <n-icon size="24" style="margin-bottom: 4px" :component="BookOutline" />
                运行日志
              </div>
            </n-tab>
            <n-tab name="排班表" @click="$router.push('/plan')">
              <div style="display: flex; flex-direction: column; align-items: center">
                <n-icon size="24" style="margin-bottom: 4px" :component="Home" />
                排班表
              </div>
            </n-tab>
            <n-tab name="心情" @click="showModal = true">
              <div style="display: flex; flex-direction: column; align-items: center">
                <n-icon size="24" style="margin-bottom: 4px" :component="StatsChart" />
                基建报表
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
                  <n-button @click=";(showModal = false), $router.push('/record-pie')">
                    工作休息比例报表
                  </n-button>
                  <n-button @click=";(showModal = false), $router.push('/record-line')">
                    干员心情折线表
                  </n-button>
                </n-card>
              </n-modal>
            </n-tab>
            <n-tab name="设置" @click="$router.push('/setting/allsetting')">
              <div style="display: flex; flex-direction: column; align-items: center">
                <n-icon size="24" style="margin-bottom: 4px" :component="Settings" />
                设置
              </div>
            </n-tab>
            <n-tab name="帮助" @click="$router.push('/doc')">
              <div style="display: flex; flex-direction: column; align-items: center">
                <n-icon size="24" style="margin-bottom: 4px" :component="HelpCircle" />
                帮助
              </div>
            </n-tab>
          </n-tabs>
        </n-layout-footer>
      </n-layout>
    </n-dialog-provider>
  </n-config-provider>
</template>

<script setup>
import { onMounted, inject, provide } from 'vue'
import { storeToRefs } from 'pinia'

const showModal = ref(false)
import { NIcon } from 'naive-ui'
import {
  BookOutline,
  Home,
  BarChart,
  PieChart,
  StatsChart,
  Settings,
  HelpCircle,
  Hammer,
  MailOpen,
  People,
  Bag,
  Flash
} from '@vicons/ionicons5'
import { DiceD20 } from '@vicons/fa'
const collapsed = ref(false)
function renderIcon(icon) {
  return () => h(NIcon, null, { default: () => h(icon) })
}

import { RouterLink } from 'vue-router'
const menuOptions = computed(() => [
  {
    label: () => h(RouterLink, { to: { path: '/' } }, { default: () => '运行日志' }),
    icon: renderIcon(BookOutline),
    key: 'go-to-log'
  },
  {
    label: () => h(RouterLink, { to: { path: '/plan' } }, { default: () => '排班编辑' }),
    icon: renderIcon(Home),
    key: 'go-to-plan'
  },

  {
    label: () => 'Mower设置',
    icon: renderIcon(Settings),
    key: 'go-to-mowersetting',
    children: [
      {
        label: () =>
          h(RouterLink, { to: { path: '/setting/Advanced' } }, { default: () => '基本设置' }),
        key: 'Advanced',
        icon: renderIcon(Settings)
      },
      {
        label: () =>
          h(RouterLink, { to: { path: '/setting/External' } }, { default: () => '基建设置' }),
        key: 'External',
        icon: renderIcon(Hammer)
      },
      {
        label: () =>
          h(
            RouterLink,
            { to: { path: '/setting/MaaWeeklynew1' } },
            { default: () => '清理智-xiner' }
          ),
        key: 'MaaWeeklynew1',
        icon: renderIcon(Flash)
      }
    ]
  },

  //{ label: () => h(RouterLink, { to: { path: "/setting/sk-land" } }, { default: () => "森空岛签到" }), key: "go-to-skland" },

  {
    label: () =>
      h(RouterLink, { to: { path: '/setting/allsetting' } }, { default: () => '全部设置' }),
    icon: renderIcon(Settings),
    show: mobile.value,
    key: 'go-to-allsetting'
  },
  {
    label: () => '基建报表',
    key: 'building-report',
    icon: renderIcon(StatsChart),
    children: [
      {
        label: () =>
          h(RouterLink, { to: { path: '/record-line' } }, { default: () => '基建报表-折线' }),
        icon: renderIcon(BarChart),
        key: 'go-to-record-line'
      },
      {
        label: () =>
          h(RouterLink, { to: { path: '/record-pie' } }, { default: () => '基建报表-饼图' }),
        icon: renderIcon(PieChart),
        key: 'go-to-record-pie'
      }
    ]
  },
  {
    label: () => h(RouterLink, { to: { path: '/doc' } }, { default: () => '帮助文档' }),
    icon: renderIcon(HelpCircle),
    key: 'go-to-doc'
  }
])
import { zhCN, dateZhCN, darkTheme } from 'naive-ui'

import hljs from 'highlight.js/lib/core'

import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { useMowerStore } from '@/stores/mower'

const config_store = useConfigStore()
const { load_config, load_shop } = config_store
const { start_automatically, theme } = storeToRefs(config_store)

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
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start`)
}

function set_window_height() {
  const vh = window.innerHeight * 0.01
  document.documentElement.style.setProperty('--vh', `${vh}px`)
}

const loaded = ref(false)

const mobile = ref(true)
provide('mobile', mobile)

onMounted(async () => {
  set_window_height()
  mobile.value = window.innerWidth < 500
  window.addEventListener('resize', () => {
    set_window_height()
    mobile.value = window.innerWidth < 500
  })

  const params = new URLSearchParams(document.location.search)
  const token = params.get('token')
  axios.defaults.headers.common['token'] = token
  await Promise.all([load_config(), load_shop(), load_operators(), get_running()])

  const r = RegExp(operators.value.map((x) => "'" + x.value).join('|'))
  loaded.value = true

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
        begin: /[0-9]+:[0-9]+:[0-9]+(\.[0-9]+)?/,
        className: 'time'
      },
      {
        begin: /room_[0-9]_[0-9]|dormitory_[0-9]|central|contact|factory|meeting/,
        className: 'room'
      }
    ]
  }))

  await load_plan()

  if (!ws.value) {
    listen_ws()
  }

  if (start_automatically.value) {
    start()
  }
})
</script>

<style scoped>
.tabs {
  height: 100%;
}

.provider {
  height: 100%;
}
</style>

<style lang="scss">
#app {
  height: calc(var(--vh, 1vh) * 100);
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

.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
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
</style>
