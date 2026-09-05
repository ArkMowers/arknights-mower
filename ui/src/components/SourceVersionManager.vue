<script setup>
import { computed, inject, ref } from 'vue'
import { useDialog } from 'naive-ui'
import { useSourceVersions } from '@/utils/sourceVersions'
import { confirmSourceVersion } from '@/utils/softwareUpdate'

const props = defineProps({
  initialBranch: { type: String, default: 'alpha' },
  running: Boolean,
  blocked: Boolean,
  forceSupported: Boolean,
  instanceCount: { type: Number, default: 0 }
})
const emit = defineEmits(['install'])
const dialogs = useDialog()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
const {
  branch,
  reference,
  history,
  checked,
  loading,
  checking,
  error,
  loadHistory,
  selectBranch,
  checkVersion
} = useSourceVersions(inject('axios'), base, props.initialBranch)
const force = ref(false)
const branchOptions = computed(() =>
  [...new Set([branch.value, ...(history.value?.branches || [])])].map((value) => ({
    label: value,
    value
  }))
)
const commits = computed(() =>
  (history.value?.commits || []).map((commit) => ({
    label: `${commit.sha.slice(0, 7)} · ${commit.message.split('\n')[0]} · ${commit.date.slice(0, 10)}`,
    value: commit.sha
  }))
)
const canInstall = computed(
  () =>
    checked.value &&
    !props.running &&
    !checking.value &&
    (force.value ? props.forceSupported : !props.blocked)
)

function expand(names) {
  if (names.includes('source') && !history.value && !loading.value) loadHistory()
}

function confirm() {
  if (!canInstall.value) return
  const target = { ...checked.value, force: force.value }
  confirmSourceVersion(dialogs, target, props.instanceCount, () => {
    if (!props.running) emit('install', target)
  })
}
</script>

<template>
  <n-collapse @update:expanded-names="expand">
    <n-collapse-item title="源码版本管理" name="source">
      <n-space vertical :size="12" class="source-versions">
        <p class="hint">选择分支和近期提交，或填写 SHA / tag，可更新或切回旧版本。</p>
        <p v-if="history" class="current version">
          当前检出：{{ history.current_branch || '分离 HEAD' }} ·
          {{ history.current_commit.slice(0, 12) }}
        </p>
        <n-form-item label="远端分支">
          <n-select
            :value="branch"
            :options="branchOptions"
            filterable
            size="small"
            :disabled="running || checking"
            :input-props="{ 'aria-label': '源码远端分支' }"
            @update:value="selectBranch"
          />
        </n-form-item>
        <n-form-item label="目标版本">
          <n-select
            v-model:value="reference"
            :options="commits"
            filterable
            tag
            :filter="
              (pattern, option) =>
                option.value.toLowerCase().includes(pattern.trim().toLowerCase()) ||
                option.label.toLowerCase().includes(pattern.trim().toLowerCase())
            "
            size="small"
            :loading="loading"
            :disabled="running || loading || checking"
            placeholder="选择提交，或输入 SHA 后回车"
            :input-props="{ 'aria-label': '源码目标版本' }"
          />
        </n-form-item>
        <n-checkbox v-model:checked="force" :disabled="running || !forceSupported">
          强制覆盖本地源码改动（不备份）
        </n-checkbox>
        <n-space>
          <n-button
            size="small"
            :loading="loading"
            :disabled="running || checking"
            @click="loadHistory"
            >刷新列表</n-button
          >
          <n-button
            size="small"
            :loading="checking"
            :disabled="running || checking || !reference.trim()"
            @click="checkVersion"
            >检查版本</n-button
          >
          <n-button size="small" type="primary" :disabled="!canInstall" @click="confirm"
            >切换并重启</n-button
          >
        </n-space>
        <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
        <div v-if="checked" class="target" aria-live="polite">
          <a :href="checked.url" target="_blank" rel="noopener noreferrer" class="version">{{
            checked.sha
          }}</a>
          <p class="hint">{{ checked.author }} · {{ checked.date }}</p>
          <pre class="notes">{{ checked.message }}</pre>
        </div>
        <p class="hint">
          提交切换任务时会关闭软件自动更新。配置和数据库不随代码回滚，旧版本兼容性取决于所选提交。
        </p>
      </n-space>
    </n-collapse-item>
  </n-collapse>
</template>

<style scoped>
.source-versions {
  width: 100%;
  min-width: 0;
}
.hint {
  font-size: 12px;
  opacity: 0.65;
}
.version {
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.notes {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 200px;
  overflow: auto;
  font: inherit;
  margin: 8px 0 0;
}
p {
  margin: 0;
  text-wrap: pretty;
}
</style>
