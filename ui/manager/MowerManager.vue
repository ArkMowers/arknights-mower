<script setup>
import PlusIcon from '@vicons/ionicons5/Add'
import CheckIcon from '@vicons/ionicons5/CheckmarkSharp'
import CrossIcon from '@vicons/ionicons5/CloseSharp'
import DotIcon from '@vicons/ionicons5/EllipsisHorizontal'
import PencilIcon from '@vicons/ionicons5/Pencil'
import PlayIcon from '@vicons/ionicons5/Play'
import TrashOutline from '@vicons/ionicons5/TrashOutline'

import { onMounted, ref } from 'vue'

const loading = ref(true)

const instances = ref([])

const editing = ref(-1)

const new_name = ref('')

onMounted(() => {
  window.addEventListener('pywebviewready', async () => {
    instances.value = await pywebview.api.get_instances()
    loading.value = false
  })
})

async function add() {
  instances.value.push({
    name: '新实例',
    path: ''
  })
  await pywebview.api.add('新实例', '')
}

async function remove(idx) {
  instances.value.splice(idx, 1)
  await pywebview.api.remove(idx)
}

function edit_name(idx) {
  editing.value = idx
  new_name.value = instances.value[idx].name
}

async function accept_name() {
  const idx = editing.value
  editing.value = -1
  instances.value[idx].name = new_name.value
  await pywebview.api.rename(idx, new_name.value)
}

function drop_name() {
  editing.value = -1
}

async function select_path(idx) {
  const response = await pywebview.api.select_path(idx)
  if (response) {
    instances.value[idx].path = response
  }
}

async function start(idx) {
  await pywebview.api.start(idx)
}
</script>

<template>
  <div class="mower-list">
    <template v-if="loading">
      <n-card size="small" v-for="i in 3" :key="i">
        <template #header>
          <div class="header">
            <n-skeleton text width="40%" />
          </div>
        </template>
        <n-skeleton text />
      </n-card>
    </template>
    <n-card size="small" v-for="(instance, idx) in instances" :key="idx">
      <template #header>
        <div class="header">
          <div v-if="editing != idx">{{ instance.name }}</div>
          <n-button size="tiny" v-if="editing == -1" @click="edit_name(idx)">
            <template #icon>
              <n-icon>
                <pencil-icon />
              </n-icon>
            </template>
          </n-button>
          <n-button type="error" ghost size="tiny" @click="remove(idx)" v-if="editing == -1">
            <template #icon>
              <n-icon>
                <trash-outline />
              </n-icon>
            </template>
          </n-button>
          <div class="expand" v-if="editing != idx"></div>
          <n-button
            type="primary"
            size="small"
            v-if="editing == -1"
            :disabled="!instance.path"
            @click="start(idx)"
          >
            <template #icon>
              <n-icon>
                <play-icon />
              </n-icon>
            </template>
          </n-button>
          <template v-if="editing == idx">
            <n-input placeholder="实例名称" v-model:value="new_name" />
            <n-button type="primary" size="tiny" circle @click="accept_name">
              <template #icon>
                <n-icon>
                  <check-icon />
                </n-icon>
              </template>
            </n-button>
            <n-button type="error" size="tiny" circle @click="drop_name">
              <template #icon>
                <n-icon>
                  <cross-icon />
                </n-icon>
              </template>
            </n-button>
          </template>
        </div>
      </template>
      <div class="folder">
        <code class="folder-content">{{ instance.path || '请选择该实例配置文件的保存路径' }}</code>
        <n-button size="tiny" @click="select_path(idx)" v-if="editing == -1">
          <template #icon>
            <n-icon>
              <dot-icon />
            </n-icon>
          </template>
        </n-button>
      </div>
    </n-card>
    <n-button size="large" dashed v-if="!loading" @click="add">
      <template #icon>
        <n-icon>
          <plus-icon />
        </n-icon>
      </template>
      添加实例
    </n-button>
  </div>
</template>

<style scoped>
.mower-list {
  box-sizing: border-box;
  width: 100vw;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.header {
  display: flex;
  gap: 6px;
  align-items: center;
  height: 28px;
}

.expand {
  flex-grow: 1;
}

.folder {
  display: flex;
  gap: 6px;
  align-items: center;
}

.folder-content {
  word-break: break-all;
}
</style>
