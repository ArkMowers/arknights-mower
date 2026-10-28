<script setup>
import { i18n } from '@/i18n'
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
    <n-collapse-item
      :title="i18n.global.t('settings.source.sourceVersionManagement')"
      name="source"
    >
      <div class="source-versions">
        <p v-if="mode === 'branch'" class="hint">
          {{ i18n.global.t('settings.source.selectOneOfThe20MostRecent') }}
        </p>
        <p v-if="history" class="current version">
          {{ i18n.global.t('settings.source.checkedOut')
          }}{{ history.current_branch || i18n.global.t('settings.source.detachedHead') }} ·
          {{ history.current_commit.slice(0, 12) }}
        </p>
        <n-form-item :label="i18n.global.t('settings.source.remoteRepository')">
          <n-select
            :value="remote"
            :options="remoteOptions"
            filterable
            tag
            size="small"
            :disabled="running || checking"
            :placeholder="i18n.global.t('settings.source.chooseASavedRepositoryOrEnterA')"
            :input-props="{ 'aria-label': i18n.global.t('settings.source.sourceRemoteRepository') }"
            @update:value="selectRemote"
          />
        </n-form-item>
        <p class="hint">{{ i18n.global.t('settings.source.useAPublicGithubUrlOrOwner') }}</p>
        <n-form-item :label="i18n.global.t('settings.source.selectionMode')">
          <n-radio-group
            :value="mode"
            size="small"
            :disabled="running || checking"
            @update:value="selectMode"
          >
            <n-radio-button value="branch">{{
              i18n.global.t('settings.source.branchCommit')
            }}</n-radio-button>
            <n-radio-button value="pr">{{
              i18n.global.t('settings.source.openPr')
            }}</n-radio-button>
          </n-radio-group>
        </n-form-item>
        <n-form-item
          v-if="mode === 'branch'"
          :label="i18n.global.t('settings.source.remoteBranch')"
        >
          <n-select
            :value="branch"
            :options="branchOptions"
            filterable
            tag
            size="small"
            :disabled="running || checking"
            :input-props="{ 'aria-label': i18n.global.t('settings.source.sourceRemoteBranch') }"
            @update:value="selectBranch"
          />
        </n-form-item>
        <n-form-item
          v-if="mode === 'branch'"
          :label="i18n.global.t('settings.source.targetVersion')"
        >
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
            :placeholder="i18n.global.t('settings.source.chooseACommitOrEnterASha')"
            :input-props="{ 'aria-label': i18n.global.t('settings.source.sourceTargetVersion') }"
          />
        </n-form-item>
        <n-form-item v-if="mode === 'pr'" :label="i18n.global.t('settings.source.openPr')">
          <n-select
            :value="pullNumber"
            :options="pullOptions"
            filterable
            size="small"
            :loading="loading"
            :disabled="running || loading || checking"
            :placeholder="i18n.global.t('settings.source.selectAPrWithNoMergeConflicts')"
            :input-props="{ 'aria-label': i18n.global.t('settings.source.openSourcePr') }"
            @update:value="selectPull"
          />
        </n-form-item>
        <p class="hint">
          {{
            mode === 'pr'
              ? i18n.global.t('settings.source.afterTheCheckSucceedsInstallationMergesThe')
              : i18n.global.t('settings.source.rememberTheSelectedRepositoryAndBranchWhen')
          }}
        </p>
        <n-checkbox v-model:checked="force" :disabled="running || !forceSupported">
          {{ i18n.global.t('settings.source.overwriteLocalSourceChangesWithoutABackup') }}
        </n-checkbox>
        <n-space>
          <n-button
            size="small"
            :loading="loading"
            :disabled="running || checking"
            @click="refresh"
            >{{ i18n.global.t('settings.source.refreshLists') }}</n-button
          >
          <n-button
            size="small"
            :loading="checking"
            :disabled="running || checking || (mode === 'pr' ? !canCheckPull : !reference.trim())"
            @click="checkVersion"
            >{{ i18n.global.t('settings.source.checkVersion') }}</n-button
          >
          <n-button size="small" type="primary" :disabled="!canInstall" @click="confirm">{{
            i18n.global.t('settings.source.switchRestart')
          }}</n-button>
        </n-space>
        <n-alert v-if="error" type="error" role="alert">{{ error }}</n-alert>
        <div v-if="checked" class="target" aria-live="polite">
          <p v-if="checked.base_commit" class="version">
            {{ i18n.global.t('settings.source.basedOn') }} {{ checked.source_branch }} ·
            {{ checked.base_commit.slice(0, 12) }}
          </p>
          <p class="version">
            {{ i18n.global.t('settings.source.targetRepository') }}{{ checked.source_repo
            }}{{ checked.source_pr ? ` · PR #${checked.source_pr}` : '' }}
          </p>
          <p v-if="checked.source_pr" class="hint">
            {{ i18n.global.t('settings.source.selectedPrCommitMergedDuringInstallation') }}
          </p>
          <a :href="checked.url" target="_blank" rel="noopener noreferrer" class="version">{{
            checked.sha
          }}</a>
          <p class="hint">{{ checked.author }} · {{ checked.date }}</p>
          <pre class="notes">{{ checked.message }}</pre>
        </div>
        <p class="hint">
          {{ i18n.global.t('settings.source.submittingAVersionSwitchDisablesAutomaticSoftware') }}
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
