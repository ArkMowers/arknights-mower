<script setup>
import { storeToRefs } from 'pinia'
import { onMounted, onUnmounted, inject, nextTick, watch, ref } from 'vue'

import { useMowerStore } from '@/stores/mower'
const mower_store = useMowerStore()
const {
  log,
  log_mobile,
  running,
  plan_condition,
  log_lines,
  task_list,
  waiting,
  get_task_id,
  sc_uri
} = storeToRefs(mower_store)
const { get_tasks, get_running } = mower_store
const axios = inject('axios')
const mobile = inject('mobile')

const auto_scroll = ref(true)
const sc_preview = ref(true)
const sc_blob = ref('')

watch(sc_uri, async (new_value) => {
  if (new_value && sc_preview.value) {
    try {
      const response = await axios.get(
        `${import.meta.env.VITE_HTTP_URL}/screenshots/${sc_uri.value}`,
        {
          responseType: 'blob'
        }
      )
      if (sc_blob.value) {
        URL.revokeObjectURL(sc_blob.value)
      }
      const blob = new Blob([response.data], { type: 'image/jpeg' })
      sc_blob.value = URL.createObjectURL(blob)
    } catch (error) {
      console.error('获取最新截图失败:', error)
      sc_blob.value = ''
    }
  } else {
    if (sc_blob.value) {
      URL.revokeObjectURL(sc_blob.value)
    }
    sc_blob.value = ''
  }
  localStorage.setItem('sc_preview', JSON.stringify(sc_preview.value))
})
function scroll_last_line() {
  nextTick(() => {
    document.querySelector('pre:last-child')?.scrollIntoView()
  })
}

function scroll_log() {
  if (auto_scroll.value) {
    scroll_last_line()
  }
}

watch(
  () => [log, task_list],
  () => {
    scroll_log()
  },
  { deep: true }
)

onMounted(() => {
  get_tasks()
  get_running()
  setInterval(get_running, 5000)
  const savedPreviewState = localStorage.getItem('sc_preview')
  if (savedPreviewState !== null) {
    sc_preview.value = JSON.parse(savedPreviewState)
  }
})

onUnmounted(() => {
  clearTimeout(get_task_id.value)
  if (sc_blob.value) {
    URL.revokeObjectURL(sc_blob.value)
  }
})

function start(value) {
  running.value = true
  log_lines.value = []
  if (value == undefined) {
    value = '0'
  }
  axios.get(`${import.meta.env.VITE_HTTP_URL}/start/${value}`)
  get_tasks()
}

function stop() {
  waiting.value = true
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop`).then((response) => {
    running.value = !response.data
    waiting.value = false
  })
}

const show_feedback = ref(false)

import PlayIcon from '@vicons/ionicons5/Play'
import StopIcon from '@vicons/ionicons5/Stop'
import AddIcon from '@vicons/ionicons5/Add'
import CollapseIcon from '@vicons/fluent/PanelTopContract20Regular'
import ExpandIcon from '@vicons/fluent/PanelTopExpand20Regular'

const show_task_table = ref(true)
const show_task = ref(false)
const add_task = ref(true)
provide('show_task', show_task)
provide('show_feedback', show_feedback)
provide('add_task', add_task)
import { useConfigStore } from '@/stores/config'
const config_store = useConfigStore()
const { theme } = storeToRefs(config_store)

const bg_opacity = computed(() => {
  return theme.value == 'light' ? 0.2 : 0.3
})

function stop_maa() {
  axios.get(`${import.meta.env.VITE_HTTP_URL}/stop-maa`)
}

const stop_options = [
  {
    label: '停止Maa',
    key: 'maa'
  }
]
const start_options = [
  {
    label: '载入心情任务',
    key: '0'
  },
  {
    label: '载入心情数据',
    key: '1'
  },
  {
    label: '缓存清零重启',
    key: '2'
  }
]
</script>

<template>
  <div class="home-container">
    <div class="log-bg"></div>
    <n-image
      v-if="sc_preview"
      width="100%"
      class="sc"
      :src="sc_blob == '' ? '/bg2.webp' : sc_blob"
      object-fit="scale-down"
    />

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
    <div v-if="plan_condition.length > 0" style="display: flex; gap: 10px">
      <span>当前激活的副表为： </span>
      <span v-for="(x, index) in plan_condition" :key="index" style="color: green">
        {{ x }}
      </span>
    </div>
    <n-log
      class="log"
      :log="mobile ? log_mobile : log"
      language="mower"
      style="user-select: text"
    />
    <div class="action-container">
      <drop-down v-if="running" :select="stop_maa" :options="stop_options" type="error" :up="true">
        <n-button type="error" @click="stop" :loading="waiting" :disabled="waiting">
          <template #icon>
            <n-icon>
              <stop-icon />
            </n-icon>
          </template>
          <template v-if="!mobile">立即停止</template>
        </n-button>
      </drop-down>
      <drop-down v-if="!running" :select="start" :options="start_options" type="primary" :up="true">
        <n-button
          v-if="!running"
          type="primary"
          @click="start"
          :loading="waiting"
          :disabled="waiting"
        >
          <template #icon>
            <n-icon>
              <play-icon />
            </n-icon>
          </template>
          <template v-if="!mobile">开始执行</template>
        </n-button>
      </drop-down>
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
        <div>只开放了空任务/专精/加工站任务</div>
        <div>只能增，不能删！！写错了可以【载入心情数据】启动</div>
        <div>如果 mower 休息到 00:30，新增的 00:15 的任务是不会被执行的，因为此时在休息</div>
        <div>添加完任务可以【载入心情任务】启动</div>
        <div>空任务，请确保任务房间名字，干员数量正确（没有判定）</div>
        <div>专精任务，UI有详细说明；新增完毕，UI上面的表会实时反馈</div>
        <div>在Q群或者频道提以上问题，看心情踢人</div>
      </help-text>
      <n-button type="error" @click="show_feedback = true">
        <template #icon>
          <!-- <n-icon>
          <add-icon />
        </n-icon> -->
        </template>
        <template v-if="!mobile">反馈问题</template>
      </n-button>
      <feedback />
      <div class="expand"></div>
      <div class="scroll-container">
        <n-checkbox v-model:checked="sc_preview">
          <template v-if="mobile">截图</template>
          <template v-else>预览截图</template>
        </n-checkbox>
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
  background-position: 65% 50%;
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

.hljs-info {
  font-weight: bold;
}

.hljs-warning {
  color: #f0a020 !important;
  font-weight: bold;
}

.hljs-error {
  color: #d03050 !important;
  font-weight: bold;
}

.hljs-scene {
  font-style: italic;
}
.sc {
  max-width: 480px;
  max-height: 270px;
  border-radius: 6px;
  z-index: 15;
}
</style>
