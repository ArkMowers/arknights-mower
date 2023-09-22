<template>
  <v-app>
    <n-config-provider
      :locale="zhCN"
      :date-locale="dateZhCN"
      class="provider"
      :theme="theme == 'dark' ? darkTheme : undefined"
      :hljs="hljs"
    >
      <n-global-style />
      <n-dialog-provider>
        <n-layout has-sider v-if="!mobilemode">
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
          <n-layout-content class="main">
            <router-view />
          </n-layout-content>
        </n-layout>
        <n-layout v-else>
          <router-view />
          <!-- <n-menu :options="menuOptions" mode="horizontal"  :collapsed="true" /> -->
          <v-bottom-navigation>
            <v-btn value="recent">
              <v-icon>mdi-history</v-icon>

              Recent
            </v-btn>

            <v-btn value="favorites">
              <v-icon>mdi-heart</v-icon>

              Favorites
            </v-btn>

            <v-btn value="nearby">
              <v-icon>mdi-map-marker</v-icon>

              Nearby
            </v-btn>
          </v-bottom-navigation>
        </n-layout>
      </n-dialog-provider>
    </n-config-provider>
  </v-app>
</template>

<script setup>
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
const mobilemode = ref(true)
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
    label: () => '设置',
    key: 'go-to-settings',
    icon: renderIcon(Settings),
    show: !mobilemode.value,
    children: [
      {
        label: () => 'Mower设置',
        key: 'go-to-mowersetting',
        children: [
          {
            label: () =>
              h(
                RouterLink,
                { to: { path: '/setting/mower-setting' } },
                { default: () => '基本设置' }
              ),
            key: 'go-to-mowersetting',
            icon: renderIcon(Settings)
          },
          {
            label: () =>
              h(
                RouterLink,
                { to: { path: '/setting/basement-setting' } },
                { default: () => '基建设置' }
              ),
            key: 'go-to-basementsetting',
            icon: renderIcon(Hammer)
          },

          {
            label: () =>
              h(RouterLink, { to: { path: '/setting/email' } }, { default: () => '邮件设置' }),
            key: 'go-to-email',
            icon: renderIcon(MailOpen)
          },
          {
            label: () =>
              h(RouterLink, { to: { path: '/setting/recruit' } }, { default: () => '公开招募' }),
            key: 'go-to-recruit',
            icon: renderIcon(People)
          }
        ]
      },

      {
        label: () => 'MAA设置',
        key: 'maa-settings',
        children: [
          {
            label: () =>
              h(RouterLink, { to: { path: '/setting/maa-basic' } }, { default: () => '连接设置' }),
            icon: renderIcon(Settings),
            key: 'go-to-maabasic'
          },
          {
            label: () =>
              h(RouterLink, { to: { path: '/setting/maa-weekly' } }, { default: () => '清理智' }),
            key: 'go-to-maaweekly',
            icon: renderIcon(Flash)
          },
          {
            label: () =>
              h(RouterLink, { to: { path: '/setting/clue' } }, { default: () => '线索/信用商店' }),
            key: 'go-to-clue',
            icon: renderIcon(Bag)
          },
          {
            label: () =>
              h(
                RouterLink,
                { to: { path: '/setting/maahugmission' } },
                { default: () => '肉鸽等' }
              ),
            key: 'go-to-maahugmission',
            icon: renderIcon(DiceD20)
          }
        ]
      }
      //{ label: () => h(RouterLink, { to: { path: "/setting/sk-land" } }, { default: () => "森空岛签到" }), key: "go-to-skland" },
    ]
  },
  {
    label: () =>
      h(RouterLink, { to: { path: '/setting/allsetting' } }, { default: () => '全部设置' }),
    icon: renderIcon(Settings),
    show: mobilemode.value,
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

import { onMounted, inject } from 'vue'
import { storeToRefs } from 'pinia'

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

onMounted(async () => {
  set_window_height()
  window.addEventListener('resize', () => {
    set_window_height()
  })

  if (window.innerWidth > 570) {
    mobilemode.value = false
  }

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

<style>
#app {
  height: calc(var(--vh, 1vh) * 100);
}

.home-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.external-container {
  width: 600px;
  margin: 0 auto;
}

.n-checkbox {
  align-items: center;
}

.no-grow {
  flex-grow: 0;
  width: 900px;
}

.provider {
  height: 100%;
  display: flex;
}

.n-menu {
  flex: 1;
  flex-basis: 20%;
  min-width: 200px;
  overflow-y: auto;
}

.main .n-layout-scroll-container {
  padding: 12px 12px 12px 24px;
}
</style>
