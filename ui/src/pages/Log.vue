<script setup>
import { useMowerStore } from '@/stores/mower'
import { storeToRefs } from 'pinia'
import { onMounted, inject, nextTick, watch, ref } from 'vue'

const mower_store = useMowerStore()

const { log, running, log_lines, task_list } = storeToRefs(mower_store)
const axios = inject('axios')

const auto_scroll = ref(true)

function scroll_last_line() {
  nextTick(() => {
    document.querySelector('pre:last-child')?.scrollIntoView()
  })
}

function scroll_log() {
  const container = document.querySelector('.n-scrollbar-container')
  const content = document.querySelector('.n-scrollbar-content')
  if (auto_scroll.value) {
    scroll_last_line()
  }
}

watch(log, () => {
  scroll_log()
})

onMounted(() => {
  scroll_last_line()
})

function start() {
  running.value = true
  log_lines.value = []
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start`)
}

function stop() {
  running.value = false
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop`)
}

function refresh() {
  location.reload()
}

import PlayIcon from '@vicons/ionicons5/Play'
import StopIcon from '@vicons/ionicons5/Stop'
import ReloadIcon from '@vicons/ionicons5/Reload'
import CollapseIcon from '@vicons/fluent/PanelTopContract20Regular'
import ExpandIcon from '@vicons/fluent/PanelTopExpand20Regular'

const show_task_table = ref(true)
</script>

<template>
  <div class="home-container">
    <n-table class="task-table" size="small" :single-line="false">
      <thead>
        <tr>
          <th>时间</th>
          <th>任务</th>
        </tr>
      </thead>
      <tbody v-show="show_task_table">
        <template v-for="task in task_list">
          <tr>
            <td :rowspan="task.task.length">{{ task.time }}</td>
            <td>{{ task.task[0] }}</td>
          </tr>
          <tr v-for="i in task.task.length - 1">
            <td>{{ task.task[i] }}</td>
          </tr>
        </template>
      </tbody>
    </n-table>
    <n-log class="log" :log="log" language="mower" style="user-select: text" />
    <div class="action-container">
      <n-button type="error" @click="stop" v-if="running">
        <template #icon>
          <n-icon>
            <stop-icon />
          </n-icon>
        </template>
        立即停止
      </n-button>
      <n-button type="primary" @click="start" v-else>
        <template #icon>
          <n-icon>
            <play-icon />
          </n-icon>
        </template>
        开始执行
      </n-button>
      <div class="expand"></div>
      <n-button @click="refresh" size="small">
        <template #icon>
          <n-icon>
            <reload-icon />
          </n-icon>
        </template>
        刷新
      </n-button>
      <div class="scroll-container">
        <n-switch v-model:value="auto_scroll" />
        <span class="scroll-label">自动滚动</span>
      </div>
    </div>
    <n-button
      class="toggle-table-collapse-btn"
      size="small"
      @click="show_task_table = !show_task_table"
      :focusable="false"
    >
      <template #icon>
        <n-icon>
          <collapse-icon v-if="show_task_table" />
          <expand-icon v-else />
        </n-icon>
      </template>
    </n-button>
  </div>
</template>

<style scoped lang="scss">
.log {
  overflow: hidden;
  flex: 1;
}

.task-table {
  max-width: 600px;

  th {
    padding: 2px 16px;

    &:first-child {
      box-sizing: border-box;
      width: 74px;
    }
  }

  td {
    height: 24px;
    padding: 2px 8px;
  }
}

.action-container {
  display: flex;
  align-items: center;
  gap: 12px;
}

.scroll-container {
  display: flex;
  align-items: center;
  gap: 4px;
}

.expand {
  flex-grow: 1;
}

.toggle-table-collapse-btn {
  position: absolute;
  top: 12px;
  right: 12px;
}
</style>

<style>
.n-log pre {
  word-break: break-all;
}

.hljs-date {
  color: #f0a020 !important;
  font-weight: bold;
}

.hljs-time {
  color: #2080f0 !important;
  font-weight: bold;
}

.hljs-room {
  color: #18a058 !important;
  font-weight: bold;
}

.hljs-operator {
  color: #d03050 !important;
}
</style>
