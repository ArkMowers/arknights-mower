<script setup>
import { computed, inject, ref } from 'vue'
import { useDialog } from 'naive-ui'
import { useSourceVersions } from '@/utils/sourceVersions'
import { confirmSourceVersion } from '@/utils/softwareUpdate'

const props = defineProps({
  initialBranch: { type: String, default: 'alpha' },
  initialRemote: { type: String, default: 'origin' },
  remotes: { type: Array, default: () => [] },
  running: Boolean,
  blocked: Boolean,
  forceSupported: Boolean,
  instanceCount: { type: Number, default: 0 }
})
const emit = defineEmits(['install'])
const dialogs = useDialog()
const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
const {
  savedRemotes,
  mode,
  pulls,
  pullNumber,
  canCheckPull,
  selectMode,
  selectPull,
  refresh,
  remote,
  selectRemote,
  branch,
  reference,
  history,
  checked,
  loading,
  checking,
  error,
  selectBranch,
  checkVersion
} = useSourceVersions(inject('axios'), base, props.initialBranch, props.initialRemote)
const force = ref(false)
const remoteOptions = computed(() => {
  const options = [...(savedRemotes.value.length ? savedRemotes.value : props.remotes)]
  if (remote.value && !options.some((item) => item.value === remote.value))
    options.push({ value: remote.value, label: remote.value })
  return options
})
const branchOptions = computed(() =>
  [...new Set([branch.value, ...(history.value?.branches || [])])].filter(Boolean).map((value) => ({
    label: value,
    value
  }))
)
const pullOptions = computed(() =>
  pulls.value.map((pull) => ({
    label: `#${pull.number} · ${pull.title}`,
    value: pull.number
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
  if (names.includes('source') && !history.value && !loading.value) refresh()
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
      <div class="source-versions">
        <p v-if="mode === 'branch'" class="hint">可以选择最近20次提交，或手动输入SHA/tag</p>
        <p v-if="history" class="current version">
          当前检出：{{ history.current_branch || '分离 HEAD' }} ·
          {{ history.current_commit.slice(0, 12) }}
        </p>
        <n-form-item label="远端仓库">
          <n-select
            :value="remote"
            :options="remoteOptions"
            filterable
            tag
            size="small"
            :disabled="running || checking"
            placeholder="选择已填写的仓库，或输入 GitHub 地址后回车"
            :input-props="{ 'aria-label': '源码远端仓库' }"
            @update:value="selectRemote"
          />
        </n-form-item>
        <p class="hint">支持公开 GitHub 仓库地址或 owner/repo，填写后仅记在本机</p>
        <n-form-item label="选择方式">
          <n-radio-group
            :value="mode"
            size="small"
            :disabled="running || checking"
            @update:value="selectMode"
          >
            <n-radio-button value="branch">分支 / 提交</n-radio-button>
            <n-radio-button value="pr">开放 PR</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item v-if="mode === 'branch'" label="远端分支">
          <n-select
            :value="branch"
            :options="branchOptions"
            filterable
            tag
            size="small"
            :disabled="running || checking"
            :input-props="{ 'aria-label': '源码远端分支' }"
            @update:value="selectBranch"
          />
        </n-form-item>
        <n-form-item v-if="mode === 'branch'" label="目标版本">
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
        <n-form-item v-if="mode === 'pr'" label="开放 PR">
          <n-select
            :value="pullNumber"
            :options="pullOptions"
            filterable
            size="small"
            :loading="loading"
            :disabled="running || loading || checking"
            placeholder="选择一个无合并冲突的 PR"
            :input-props="{ 'aria-label': '源码开放 PR' }"
            @update:value="selectPull"
          />
        </n-form-item>
        <p class="hint">
          {{
            mode === 'pr'
              ? '安装 GitHub 生成的目标分支最新版本与所选 PR 的合并结果。后续检查仍跟随原来的仓库、分支和渠道。'
              : '提交切换任务后记住所选仓库和分支，供后续开发版检查使用。'
          }}
        </p>
        <n-checkbox v-model:checked="force" :disabled="running || !forceSupported">
          强制覆盖本地源码改动（不备份）
        </n-checkbox>
        <n-space>
          <n-button size="small" :loading="loading" :disabled="running || checking" @click="refresh"
            >刷新列表</n-button
          >
          <n-button
            size="small"
            :loading="checking"
            :disabled="running || checking || (mode === 'pr' ? !canCheckPull : !reference.trim())"
            @click="checkVersion"
            >检查版本</n-button
          >
          <n-button size="small" type="primary" :disabled="!canInstall" @click="confirm"
            >切换并重启</n-button
          >
        </n-space>
        <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
        <div v-if="checked" class="target" aria-live="polite">
          <p v-if="checked.base_commit" class="version">
            基于 {{ checked.source_branch }} · {{ checked.base_commit.slice(0, 12) }}
          </p>
          <p class="version">
            目标仓库：{{ checked.source_repo
            }}{{ checked.source_pr ? ` · PR #${checked.source_pr}` : '' }}
          </p>
          <a :href="checked.url" target="_blank" rel="noopener noreferrer" class="version">{{
            checked.sha
          }}</a>
          <p class="hint">{{ checked.author }} · {{ checked.date }}</p>
          <pre class="notes">{{ checked.message }}</pre>
        </div>
        <p class="hint">
          提交切换任务时会关闭软件自动更新。配置和数据库不随代码回滚，旧版本兼容性取决于所选提交。
        </p>
      </div>
    </n-collapse-item>
  </n-collapse>
</template>

<style scoped>
.source-versions {
  display: flex;
  flex-direction: column;
  gap: 12px;
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
