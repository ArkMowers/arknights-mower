<script setup>
import { useMowerStore } from '@/stores/mower'
import { storeToRefs } from 'pinia'
import { onMounted, inject, nextTick, watch } from 'vue'

const mower_store = useMowerStore()

const { log, running, log_lines } = storeToRefs(mower_store)
const axios = inject('axios')

function scroll_last_line() {
  nextTick(() => {
    document.querySelector('pre:last-child')?.scrollIntoView()
  })
}

function scroll_log() {
  const container = document.querySelector('.n-scrollbar-container')
  const content = document.querySelector('.n-scrollbar-content')
  if (container.scrollTop + container.clientHeight < content.clientHeight) {
    return
  }
  scroll_last_line()
}

watch(log, (new_log, old_log) => {
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
</script>

<template>
  <div class="home-container">
    <n-log class="log" :log="log" />
    <div>
      <n-button type="error" @click="stop" v-if="running">立即停止</n-button>
      <n-button type="primary" @click="start" v-else>开始执行</n-button>
    </div>
    <n-button class="down-button" type="primary" @click="scroll_last_line">
      <template #icon>
        <n-icon>
          <svg
            xmlns="http://www.w3.org/2000/svg"
            xmlns:xlink="http://www.w3.org/1999/xlink"
            viewBox="0 0 16 16"
          >
            <g fill="none">
              <path
                d="M11.74 7.7a.75.75 0 1 1 1.02 1.1l-4.25 4a.75.75 0 0 1-1.02 0l-4.25-4a.75.75 0 1 1 1.02-1.1L8 11.226L11.74 7.7zm0-4a.75.75 0 1 1 1.02 1.1l-4.25 4a.75.75 0 0 1-1.02 0l-4.25-4a.75.75 0 1 1 1.02-1.1L8 7.227L11.74 3.7z"
                fill="currentColor"
              ></path>
            </g>
          </svg>
        </n-icon>
      </template>
    </n-button>
  </div>
</template>

<style scoped>
.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.log {
  flex-grow: 1;
  overflow: hidden;
  border: 1px solid rgb(224, 224, 230);
  border-radius: 3px;
  padding: 4px;
}

.config-label {
  width: 108px;
}

.down-button {
  position: absolute;
  right: 30px;
  bottom: 70px;
  opacity: 0.5;
}

.down-button:hover {
  opacity: 1;
}
</style>

<style>
.n-log pre {
  word-break: break-all;
}
</style>
