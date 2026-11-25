<script setup>
import { computed, inject, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useConfigStore } from '@/stores/config'

const props = defineProps({ scripts: Array, library: Array, selected: String })
const axios = inject('axios')
const message = useMessage()
const store = useConfigStore()
const mode = ref('list')
const chosen = ref([])
const times = ref(1)
const submitting = ref(false)
const options = computed(() =>
  props.scripts.map((entry, index) => {
    const script = props.library.find((item) => item.id === entry.id)
    return {
      value: index,
      label: `${index + 1}. ${script?.title || entry.id} · ${entry.is_raid ? '突袭' : '普通'}`
    }
  })
)
watch(
  () => props.scripts.slice(),
  (rows, previous) => {
    const selectedRows = new Set(chosen.value.map((index) => previous?.[index]))
    chosen.value = rows.flatMap((row, index) =>
      !previous?.length || selectedRows.has(row) ? [index] : []
    )
  },
  { immediate: true }
)
const canRun = computed(() =>
  mode.value === 'single'
    ? props.selected && Number.isInteger(times.value) && times.value >= 1 && times.value <= 9999
    : chosen.value.length > 0
)
async function submit() {
  if (submitting.value || !canRun.value) return
  const copilot =
    mode.value === 'single'
      ? { mode: 'single', id: props.selected, loop_times: times.value }
      : {
          mode: 'list',
          scripts: props.scripts
            .filter((_, i) => chosen.value.includes(i))
            .map((item) => ({ ...item }))
        }
  submitting.value = true
  try {
    await store.flush_config_saves()
    const { data } = await axios.post(`${import.meta.env.VITE_HTTP_URL || ''}/task`, {
      task: {
        time: new Date().toISOString(),
        task_type: '手动作业 (MAA)',
        plan: {},
        meta_data: '',
        copilot
      }
    })
    if (data !== '添加任务成功！') throw new Error(typeof data === 'string' ? data : '添加任务失败')
    message.success('手动作业已加入调度')
  } catch (error) {
    message.error(error.response?.data?.message || error.message)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <n-form-item label="手动执行">
    <n-flex vertical style="width: 100%">
      <n-radio-group v-model:value="mode">
        <n-radio value="list">执行勾选列表</n-radio>
        <n-radio value="single">当前关卡作业</n-radio>
      </n-radio-group>
      <template v-if="mode === 'list'">
        <n-select
          v-model:value="chosen"
          multiple
          :options="options"
          placeholder="选择队列中的作业"
        />
        <n-text depth="3">请先在游戏中打开关卡地图，MAA 将按队列顺序定位并执行勾选项。</n-text>
      </template>
      <template v-else>
        <n-text depth="3"
          >请在“已有作业”中选择文件，并在游戏中打开对应关卡。当前关卡模式禁用理智药。</n-text
        >
        <n-input-number
          v-model:value="times"
          :min="1"
          :max="9999"
          :precision="0"
          aria-label="执行次数"
        >
          <template #prefix>执行次数</template>
        </n-input-number>
      </template>
      <n-button :disabled="!canRun" :loading="submitting" @click="submit"
        >执行一次手动任务</n-button
      >
    </n-flex>
  </n-form-item>
</template>
