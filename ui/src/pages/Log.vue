<script setup>
import { storeToRefs } from 'pinia'
import { onMounted, onUnmounted, inject, nextTick, watch, ref } from 'vue'

import { useMowerStore } from '@/stores/mower'
const mower_store = useMowerStore()
const { log, running, log_lines, task_list, waiting, get_task_id } = storeToRefs(mower_store)
const { get_tasks } = mower_store
const axios = inject('axios')
const mobile = inject('mobile')

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
  get_tasks()
})

onUnmounted(() => {
  clearTimeout(get_task_id.value)
})

function start() {
  running.value = true
  log_lines.value = []
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start`)
}

function stop() {
  waiting.value = true
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop`).then((response) => {
    running.value = !response.data
    waiting.value = false
  })
}

function refresh() {
  location.reload()
}

import PlayIcon from '@vicons/ionicons5/Play'
import StopIcon from '@vicons/ionicons5/Stop'
import AddIcon from '@vicons/ionicons5/Add'
import ReloadIcon from '@vicons/ionicons5/Reload'
import CollapseIcon from '@vicons/fluent/PanelTopContract20Regular'
import ExpandIcon from '@vicons/fluent/PanelTopExpand20Regular'

const show_task_table = ref(true)
const show_task = ref(false)
const add_task = ref(true)
provide('show_task', show_task)
provide('add_task', add_task)
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { theme } = storeToRefs(config_store)

const bg_opacity = computed(() => {
  return theme.value == 'light' ? 0.2 : 0.3
})
</script>

<template>
  <div class="home-container">
    <div class="log-bg"></div>
    <n-table class="task-table" size="small" :single-line="false">
      <thead>
        <tr>
          <th>时间</th>
          <th :colspan="2">任务</th>
        </tr>
      </thead>
      <tbody v-show="!mobile || show_task_table">
        <template v-for="task in task_list">
          <template v-if="Object.keys(task.plan).length">
            <tr v-for="(value, key, idx) in task.plan">
              <!-- <td :rowspan="Object.entries(task.plan).length">{{ task.time }}</td> -->
              <td v-if="idx == 0" :rowspan="Object.keys(task.plan).length">
                {{ task.time.split('T')[1].split('.')[0] }}
              </td>
              <td>{{ key }}</td>
              <td>
                {{ value.map((x) => x || '_').join(', ') }}
              </td>
            </tr>
          </template>
          <tr v-else>
            <td>
              {{ task.time.split('T')[1].split('.')[0] }}
            </td>
            <td :colspan="2">{{ task.meta_data }}{{ task.type.display_value }}</td>
          </tr>
        </template>
      </tbody>
    </n-table>
    <n-log class="log" :log="log" language="mower" style="user-select: text" />
    <div class="action-container">
      <n-button type="error" @click="stop" v-if="running" :loading="waiting" :disabled="waiting">
        <template #icon>
          <n-icon>
            <stop-icon />
          </n-icon>
        </template>
        <template v-if="!mobile">立即停止</template>
      </n-button>
      <n-button type="primary" @click="start" v-else :loading="waiting" :disabled="waiting">
        <template #icon>
          <n-icon>
            <play-icon />
          </n-icon>
        </template>
        <template v-if="!mobile">开始执行</template>
      </n-button>
      <task-dialog />
      <n-button type="warning" @click="show_task = true">
        <template #icon>
          <n-icon>
            <add-icon />
          </n-icon>
        </template>
        <template v-if="!mobile">新增任务</template>
      </n-button>
      <help-text v-if="!mobile">
        <div>目前只糊了一个勉强能用的版本，其他功能敬请期待</div>
        <div>只开放了空任务/专精任务</div>
        <div>只能增，不能删！！谨慎填写任务</div>
        <div>如果 mower 休息到 00:30，新增的 00:15 的任务是不会被执行的，因为此时在休息</div>
        <div>所以最好在 00:00 mower运行的时候添加 00:15 的任务了，考验手速的时候到了</div>
        <div>空任务，请确保任务房间名字，干员数量正确（没有判定）</div>
        <div>专精任务，UI有详细说明；新增完毕，UI上面的表会实时反馈</div>
        <div>以下为房间名:</div>
        <div>contact（办公室），meeting（会议室），train（训练室），central（中枢）</div>
        <div>在Q群或者频道提以上问题，看心情踢人</div>
      </help-text>
      <div class="expand"></div>
      <n-button @click="refresh" size="small">
        <template #icon>
          <n-icon>
            <reload-icon />
          </n-icon>
        </template>
        <template v-if="!mobile">刷新</template>
      </n-button>
      <div class="scroll-container">
        <n-switch v-model:value="auto_scroll" />
        <span class="scroll-label" v-if="!mobile">自动滚动</span>
      </div>
    </div>
    <n-button
      class="toggle-table-collapse-btn"
      size="small"
      @click="show_task_table = !show_task_table"
      :focusable="false"
      v-if="mobile"
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
  }

  td {
    height: 24px;
    padding: 2px 8px;

    &:last-child {
      width: 100%;
    }
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

.log-bg {
  content: '';
  width: 100%;
  height: 100%;
  position: absolute;
  top: 0;
  left: 0;
  opacity: v-bind(bg_opacity);
  background-image: url(/bg.webp);
  background-repeat: no-repeat;
  background-size: cover;
  background-position: 30% 75%;
  pointer-events: none;
}
</style>

<style>
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
