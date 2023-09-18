<template>
  <n-config-provider :locale="zhCN" :date-locale="dateZhCN" class="provider"
    :theme="theme == 'dark' ? darkTheme : undefined" :hljs="hljs">
    <n-global-style />
    <n-menu :options="menuOptions" class="menu" />
    <n-dialog-provider>
      <router-view class="router-view" />
    </n-dialog-provider>
  </n-config-provider>
</template>


<script setup>
import { RouterLink } from 'vue-router'
const menuOptions = ref([
  { label: () => h(RouterLink, { to: { path: "/" } }, { default: () => "运行日志" }), key: "go-to-log" },
  { label: () => h(RouterLink, { to: { path: "/plan" } }, { default: () => "排班编辑" }), key: "go-to-plan" },
  {
    label: () => "设置",
    key: "go-to-settings",
    children: [
      { label: () => h(RouterLink, { to: { path: "/advancedleft/mower-setting" } }, { default: () => "Mower-设置" }), key: "go-to-mowersetting" },
      { label: () => h(RouterLink, { to: { path: "/advancedleft/basement-setting" } }, { default: () => "Mower-基建设置" }), key: "go-to-basementsetting" },
      { label: () => h(RouterLink, { to: { path: "/advancedleft/clue" } }, { default: () => "排班编辑" }), key: "go-to-clue" },
      { label: () => h(RouterLink, { to: { path: "/advancedleft/email" } }, { default: () => "邮件设置" }), key: "go-to-email" },
      {
        label: () => "maa设置",
        key: "maa-settings",
        children: [
          { label: () => h(RouterLink, { to: { path: "/advancedleft/maa-basic" } }, { default: () => "基础设置" }), key: "go-to-maabasic" },
          { label: () => h(RouterLink, { to: { path: "/advancedleft/maa-weekly" } }, { default: () => "清理智" }), key: "go-to-maaweekly" },
          { label: () => h(RouterLink, { to: { path: "/advancedleft/maahugmission" } }, { default: () => "肉鸽/保全/生稀盐酸" }), key: "go-to-maahugmission" }
        ]
      },
      //{ label: () => h(RouterLink, { to: { path: "/advancedleft/sk-land" } }, { default: () => "森空岛签到" }), key: "go-to-skland" },
      { label: () => h(RouterLink, { to: { path: "/advancedleft/recruit" } }, { default: () => "公开招募" }), key: "go-to-recruit" }
    ]
  },
  {
    label: () => "基建报表",
    key: "building-report",
    children: [
      { label: () => h(RouterLink, { to: { path: "/record-line" } }, { default: () => "基建报表-折线" }), key: "go-to-record-line" },
      { label: () => h(RouterLink, { to: { path: "/record-pine" } }, { default: () => "基建报表-饼图" }), key: "go-to-record-pine" }
    ]
  },
  { label: () => h(RouterLink, { to: { path: "/doc" } }, { default: () => "帮助文档" }), key: "go-to-doc" }
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
  padding: 0 12px 12px;
  flex-grow: 1;
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
  overflow-y: auto
}
.router-view {
  flex: 1;
  flex-basis: 80%;
  overflow-y: auto
}
</style>
