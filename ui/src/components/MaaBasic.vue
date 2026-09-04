<script setup>
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
const axios = inject('axios')

const mobile = inject('mobile')

import { useConfigStore } from '@/stores/config'
const store = useConfigStore()

import { storeToRefs } from 'pinia'
const { maa_path, maa_mirrorchyan_token, maa_update_channel, maa_conn_preset, maa_touch_option } =
  storeToRefs(store)

import { folder_dialog } from '@/utils/dialog'

async function select_maa_dir() {
  const folder_path = await folder_dialog()
  if (folder_path) {
    maa_path.value = folder_path
  }
}

const maa_msg = ref('')
const maa_testing = ref(false)

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function test_maa() {
  if (maa_testing.value) return
  maa_testing.value = true
  maa_msg.value = '正在测试……'
  try {
    let response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa`)
    let data = response.data
    if (typeof data === 'string') {
      maa_msg.value = data
      return
    }
    while (data.status === 'running') {
      maa_msg.value = data.message || '正在测试……'
      await sleep(1000)
      response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/check-maa/status`)
      data = response.data
      if (typeof data === 'string') {
        maa_msg.value = data
        return
      }
    }
    maa_msg.value = data.message || '测试失败，请检查Maa日志！'
  } catch (error) {
    maa_msg.value = `测试失败：${error.message}`
  } finally {
    maa_testing.value = false
  }
}

const maa_conn_presets = ref([])

async function get_maa_conn_presets() {
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-conn-preset`)
    maa_conn_presets.value = response.data.map((x) => ({ label: x, value: x }))
  } catch (error) {
    maa_msg.value = `读取连接配置失败：${error.message}`
  }
}

const maa_touch_options = ['maatouch', 'minitouch', 'adb'].map((x) => {
  return { label: x, value: x }
})

const maa_update_supported = ref(false)
const maa_update_platform = ref('')
const maa_update_arch = ref('')
const maa_update_source = ref('github')
let maa_update_source_initialized = false
const maa_latest_version = ref('')
const maa_installed = ref(false)
const maa_installed_version = ref('')
const maa_backup_path = ref('')
const maa_update_info_msg = ref('')
const maa_update_job = ref({
  status: 'idle',
  phase: 'idle',
  message: '',
  progress: null,
  current: 0,
  total: 0,
  version: '',
  operation: '',
  result: null
})
let maa_update_timer = null
let maa_update_info_request_id = 0
const builtin_update_loading = ref(false)
const builtin_update_msg = ref('')
const mirrorchyan_cdk_status = ref({
  loading: false,
  checked_token: '',
  valid: false,
  expired: false,
  code: null,
  expires_at: 0,
  message: ''
})
let mirrorchyan_cdk_timer = null
let mirrorchyan_cdk_request_id = 0

function reset_mirrorchyan_cdk_status(message = '') {
  mirrorchyan_cdk_status.value = {
    loading: false,
    checked_token: '',
    valid: false,
    expired: false,
    code: null,
    expires_at: 0,
    message
  }
}

async function check_mirrorchyan_cdk(token = maa_mirrorchyan_token.value) {
  const normalized_token = String(token || '').trim()
  if (normalized_token.length !== 24) {
    reset_mirrorchyan_cdk_status(normalized_token ? '请输入完整的 24 位 Mirror酱 CDK' : '')
    return false
  }

  const request_id = ++mirrorchyan_cdk_request_id
  mirrorchyan_cdk_status.value = {
    ...mirrorchyan_cdk_status.value,
    loading: true,
    checked_token: normalized_token,
    message: '正在检查 Mirror酱 CDK……'
  }
  try {
    const response = await axios.post(
      `${import.meta.env.VITE_HTTP_URL}/maa-update/mirrorchyan-status`,
      {
        mirror_token: normalized_token,
        channel: maa_update_channel.value
      }
    )
    if (
      request_id !== mirrorchyan_cdk_request_id ||
      normalized_token !== String(maa_mirrorchyan_token.value || '').trim()
    ) {
      return false
    }
    const data = response.data
    mirrorchyan_cdk_status.value = {
      loading: false,
      checked_token: normalized_token,
      valid: Boolean(data.ok && data.valid),
      expired: Boolean(data.expired),
      code: data.code ?? null,
      expires_at: Number(data.expires_at || 0),
      message: data.message || 'Mirror酱 CDK 状态未知'
    }
  } catch (error) {
    if (request_id !== mirrorchyan_cdk_request_id) return false
    mirrorchyan_cdk_status.value = {
      loading: false,
      checked_token: normalized_token,
      valid: false,
      expired: false,
      code: null,
      expires_at: 0,
      message: error.response?.data?.message || `检查 Mirror酱 CDK 失败：${error.message}`
    }
  }
  return mirrorchyan_cdk_status.value.valid
}

function schedule_mirrorchyan_cdk_check(token) {
  if (mirrorchyan_cdk_timer) window.clearTimeout(mirrorchyan_cdk_timer)
  mirrorchyan_cdk_request_id++
  const normalized_token = String(token || '').trim()
  if (!normalized_token) {
    reset_mirrorchyan_cdk_status()
    return
  }
  if (normalized_token.length !== 24) {
    reset_mirrorchyan_cdk_status('请输入完整的 24 位 Mirror酱 CDK')
    return
  }
  reset_mirrorchyan_cdk_status('等待检查 Mirror酱 CDK')
  mirrorchyan_cdk_timer = window.setTimeout(() => check_mirrorchyan_cdk(normalized_token), 500)
}

watch(
  maa_mirrorchyan_token,
  (token, previousToken = '') => {
    if (token.trim() && !previousToken.trim()) maa_update_source.value = 'mirrorchyan'
    if (maa_update_supported.value || maa_update_platform.value === 'windows') {
      schedule_mirrorchyan_cdk_check(token)
    }
  },
  { immediate: true }
)

watch(maa_update_channel, (channel, previous_channel) => {
  if (channel === previous_channel) return
  if (maa_update_supported.value || maa_update_platform.value === 'windows') {
    schedule_mirrorchyan_cdk_check(maa_mirrorchyan_token.value)
  }
  if (maa_update_supported.value) get_maa_update_info()
})

const maa_updating = computed(() => maa_update_job.value.status === 'running')
const maa_path_missing = computed(() => !String(maa_path.value || '').trim())
const maa_managed_operation_label = computed(() => (maa_installed.value ? '更新' : '下载'))
const maa_job_operation_label = computed(() =>
  maa_update_job.value.operation === 'update' ? '更新' : '下载'
)
const maa_update_channel_label = computed(() =>
  maa_update_channel.value === 'beta' ? '公测版' : '正式版'
)
const mirrorchyan_cdk_remaining_days = computed(() => {
  if (!mirrorchyan_cdk_status.value.expires_at) return null
  return (mirrorchyan_cdk_status.value.expires_at * 1000 - Date.now()) / 86_400_000
})
const mirrorchyan_cdk_message = computed(() => {
  const status = mirrorchyan_cdk_status.value
  if (!String(maa_mirrorchyan_token.value || '').trim()) return ''
  if (status.loading) return status.message
  if (!status.valid || !status.expires_at) return status.message
  const remaining_days = Math.max(0, mirrorchyan_cdk_remaining_days.value).toFixed(1)
  const expires_at = new Date(status.expires_at * 1000).toLocaleString('zh-CN', {
    hour12: false
  })
  return `Mirror酱 CDK 还剩 ${remaining_days} 天到期（${expires_at}）`
})
const mirrorchyan_cdk_message_class = computed(() => {
  const status = mirrorchyan_cdk_status.value
  const token = String(maa_mirrorchyan_token.value || '').trim()
  if (token && token.length !== 24) return 'update-error'
  if (status.loading || status.checked_token === '') return 'update-hint'
  if (!status.valid || status.expired) return 'update-error'
  if (mirrorchyan_cdk_remaining_days.value !== null && mirrorchyan_cdk_remaining_days.value <= 7) {
    return 'update-warning'
  }
  return 'update-success'
})
const mirrorchyan_cdk_ready = computed(() => {
  const token = String(maa_mirrorchyan_token.value || '').trim()
  const status = mirrorchyan_cdk_status.value
  return (
    token.length === 24 &&
    !status.loading &&
    status.checked_token === token &&
    status.valid &&
    !status.expired
  )
})
const maa_update_progress_status = computed(() => {
  if (maa_update_job.value.status === 'error') return 'error'
  if (maa_update_job.value.status === 'success') return 'success'
  return 'default'
})

function format_bytes(value) {
  const size = Number(value || 0)
  if (!size) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(Math.floor(Math.log(size) / Math.log(1024)), units.length - 1)
  return `${(size / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

function apply_maa_update_job(job, apply_install_info = true) {
  if (!job) return
  maa_update_job.value = { ...maa_update_job.value, ...job }
  if (apply_install_info) {
    if (job.result?.backup) maa_backup_path.value = job.result.backup
    if (job.status === 'success' && job.result?.installed_version) {
      maa_installed_version.value = job.result.installed_version
    }
  }
}

async function poll_maa_update() {
  if (maa_update_timer) window.clearTimeout(maa_update_timer)
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-update/status`)
    apply_maa_update_job(response.data.job)
    if (maa_update_job.value.status === 'running') {
      maa_update_timer = window.setTimeout(poll_maa_update, 800)
    } else if (maa_update_job.value.status === 'success') {
      await get_maa_update_info()
      await get_maa_conn_presets()
    }
  } catch (error) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message = `读取 Maa ${maa_job_operation_label.value}进度失败：${error.message}`
  }
}

async function get_maa_update_info() {
  const request_id = ++maa_update_info_request_id
  try {
    const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/maa-update/info`, {
      params: { channel: maa_update_channel.value }
    })
    if (request_id !== maa_update_info_request_id) return
    const data = response.data
    maa_update_supported.value = Boolean(data.supported)
    maa_update_platform.value = data.platform || ''
    maa_update_arch.value = data.arch || ''
    maa_installed.value = Boolean(data.installed)
    if (maa_update_supported.value || maa_update_platform.value === 'windows') {
      schedule_mirrorchyan_cdk_check(maa_mirrorchyan_token.value)
    } else {
      reset_mirrorchyan_cdk_status()
    }
    if (!maa_update_source_initialized) {
      maa_update_source.value = data.default_source === 'mirrorchyan' ? 'mirrorchyan' : 'github'
      maa_update_source_initialized = true
    }
    maa_latest_version.value = data.latest?.tag || ''
    maa_installed_version.value = data.installed_version || ''
    maa_backup_path.value = data.backup || ''
    maa_update_info_msg.value = data.ok
      ? ''
      : data.message || `读取 Maa ${maa_managed_operation_label.value}版本失败`
    apply_maa_update_job(data.job, data.job?.result?.target === data.target)
    if (maa_update_job.value.status === 'running') poll_maa_update()
  } catch (error) {
    if (request_id !== maa_update_info_request_id) return
    maa_update_info_msg.value = `读取 Maa ${maa_managed_operation_label.value}版本失败：${error.message}`
  }
}

async function start_maa_update() {
  if (maa_updating.value) return
  maa_update_info_msg.value = ''
  if (maa_path_missing.value) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message = '请先设置 Maa 目录'
    return
  }
  if (maa_update_source.value === 'mirrorchyan') {
    const valid = await check_mirrorchyan_cdk()
    if (!valid) {
      maa_update_job.value.status = 'error'
      maa_update_job.value.message = mirrorchyan_cdk_status.value.message || '请检查 Mirror酱 CDK'
      return
    }
  }
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/maa-update/start`, {
      maa_path: maa_path.value,
      source: maa_update_source.value,
      mirror_token: maa_update_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : '',
      channel: maa_update_channel.value
    })
    if (!response.data.ok) {
      maa_update_job.value.status = 'error'
      maa_update_job.value.message =
        response.data.message || `MAA ${maa_managed_operation_label.value}启动失败`
      return
    }
    apply_maa_update_job(response.data.job)
    poll_maa_update()
  } catch (error) {
    maa_update_job.value.status = 'error'
    maa_update_job.value.message =
      error.response?.data?.message ||
      `MAA ${maa_managed_operation_label.value}启动失败：${error.message}`
  }
}

async function start_builtin_maa_update() {
  if (builtin_update_loading.value) return
  if (maa_path_missing.value) {
    builtin_update_msg.value = '请先设置 Maa 目录'
    return
  }
  builtin_update_loading.value = true
  builtin_update_msg.value = ''
  try {
    const response = await axios.post(`${import.meta.env.VITE_HTTP_URL}/maa-update/builtin`, {
      maa_path: maa_path.value,
      mirror_token: maa_update_source.value === 'mirrorchyan' ? maa_mirrorchyan_token.value : '',
      channel: maa_update_channel.value
    })
    builtin_update_msg.value = response.data.message || ''
    if (!response.data.ok) return
  } catch (error) {
    builtin_update_msg.value =
      error.response?.data?.message || `启动 MAA 自带更新失败：${error.message}`
  } finally {
    builtin_update_loading.value = false
  }
}

onMounted(() => {
  get_maa_conn_presets()
  get_maa_update_info()
})

onUnmounted(() => {
  if (maa_update_timer) window.clearTimeout(maa_update_timer)
  if (mirrorchyan_cdk_timer) window.clearTimeout(mirrorchyan_cdk_timer)
  mirrorchyan_cdk_request_id++
})
</script>

<template>
  <n-card title="Maa设置">
    <template #header>Maa设置<help-text>刷理智、信用相关、领奖励、肉鸽保全等</help-text></template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="96"
      label-align="left"
    >
      <n-form-item label="Maa目录">
        <n-input type="textarea" :autosize="true" v-model:value="maa_path" />
        <n-button @click="select_maa_dir" class="dialog-btn">...</n-button>
      </n-form-item>
      <n-form-item label="连接配置">
        <n-select :options="maa_conn_presets" v-model:value="maa_conn_preset" />
        <n-button @click="get_maa_conn_presets" class="dialog-btn">刷新</n-button>
      </n-form-item>
      <n-form-item label="触控模式">
        <n-select v-model:value="maa_touch_option" :options="maa_touch_options" />
      </n-form-item>
    </n-form>
    <n-divider />
    <div class="misc-container">
      <n-button :loading="maa_testing" :disabled="maa_testing" @click="test_maa">
        测试连接
      </n-button>
      <div>{{ maa_msg }}</div>
    </div>
    <template v-if="maa_update_supported">
      <n-divider />
      <div class="maa-updater">
        <div class="update-title">
          {{
            maa_update_platform === 'windows'
              ? 'Windows 下载 Maa'
              : `${maa_update_platform === 'linux' ? 'Linux' : 'macOS'} ${
                  maa_installed ? '更新 Maa' : '下载 Maa'
                }`
          }}
        </div>
        <div class="update-meta">
          <span>
            可{{ maa_managed_operation_label }}的{{ maa_update_channel_label }}：{{
              maa_latest_version || '待获取'
            }}
          </span>
          <span v-if="maa_update_platform === 'windows'">已安装：未检测到 Maa</span>
          <span v-else>已安装：{{ maa_installed_version || '未知/手动安装' }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{ maa_managed_operation_label }}通道</span>
          <n-radio-group v-model:value="maa_update_channel">
            <n-space>
              <n-radio value="stable">正式版</n-radio>
              <n-radio value="beta">公测版</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <div class="update-option">
          <span class="update-option-label">{{ maa_installed ? '更新源' : '下载源' }}</span>
          <n-radio-group v-model:value="maa_update_source">
            <n-space>
              <n-radio value="github">GitHub</n-radio>
              <n-radio value="mirrorchyan">Mirror酱</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <template v-if="maa_update_source === 'mirrorchyan'">
          <n-input
            v-model:value="maa_mirrorchyan_token"
            type="password"
            show-password-on="mousedown"
            placeholder="Mirror酱 CDK"
            :disabled="maa_updating"
          />
          <div
            v-if="mirrorchyan_cdk_message"
            :class="mirrorchyan_cdk_message_class"
            aria-live="polite"
          >
            {{ mirrorchyan_cdk_message }}
          </div>
          <div class="update-hint">
            CDK 保存在 Mower 配置文件中。
            <n-a href="https://mirrorchyan.com/" target="_blank" rel="noopener noreferrer">
              获取 CDK
            </n-a>
          </div>
          <div v-if="maa_update_platform === 'windows'" class="update-hint">
            未检测到 Maa，将按当前架构下载一份 {{ maa_update_channel_label }} Windows
            {{ maa_update_arch }} 完整包并安装到设定目录。
          </div>
          <div v-else-if="maa_update_platform === 'linux'" class="update-hint">
            {{ maa_installed ? '更新' : '下载' }}时按当前架构取得一份
            {{ maa_update_channel_label }} Linux {{ maa_update_arch }} 完整包，其中已包含
            MaaCore、resource 与 Python。
          </div>
          <div v-else class="update-hint">
            {{ maa_installed ? '更新' : '下载' }}时将取得 {{ maa_update_channel_label }} macOS GUI
            包并从 DMG 分离运行库与 resource，同时下载同版本的 Windows arm64 包提取 Python 文件夹。
          </div>
        </template>
        <div v-else-if="maa_update_platform === 'windows'" class="update-hint">
          未检测到 Maa，将通过 GitHub 按当前架构下载 {{ maa_update_channel_label }} Windows
          {{ maa_update_arch }} 完整包并安装到设定目录。
        </div>
        <div v-else-if="maa_update_platform === 'linux'" class="update-hint">
          GitHub {{ maa_installed ? '更新' : '下载' }}按当前架构取得一份
          {{ maa_update_channel_label }} Linux {{ maa_update_arch }} tar.gz 完整包，其中已包含
          MaaCore、resource 与 Python。
        </div>
        <div v-else class="update-hint">
          GitHub {{ maa_installed ? '更新' : '下载' }}使用 {{ maa_update_channel_label }} macOS
          universal runtime 包；Python API 仅从同版本 Windows arm64 包按需下载 Python 文件夹。
        </div>
        <div v-if="!maa_installed && maa_backup_path" class="update-hint">
          这是 Maa 下载安装，不会作为已有 Maa 的覆盖更新流程。若目标目录已有其他内容，原目录将保存在
          {{ maa_backup_path }}。
        </div>
        <div v-else-if="maa_backup_path" class="update-hint">
          更新成功后原目录保存在 {{ maa_backup_path }}；下一次成功更新时替换该备份，更新失败时保留。
          cache 与 config 会复制到新目录继续使用。
        </div>
        <n-progress
          v-if="maa_update_job.progress !== null"
          type="line"
          :percentage="maa_update_job.progress"
          :status="maa_update_progress_status"
          :indicator-placement="'inside'"
          processing
        />
        <div v-if="maa_update_job.message" class="update-message">
          {{ maa_update_job.message }}
          <template v-if="maa_update_job.total">
            （{{ format_bytes(maa_update_job.current) }} /
            {{ format_bytes(maa_update_job.total) }}）
          </template>
        </div>
        <div v-if="maa_update_info_msg" class="update-error">{{ maa_update_info_msg }}</div>
        <n-button
          type="primary"
          :loading="maa_updating"
          :disabled="
            maa_updating || (maa_update_source === 'mirrorchyan' && !mirrorchyan_cdk_ready)
          "
          @click="start_maa_update"
        >
          {{
            maa_update_platform === 'windows' ? '下载 Maa' : maa_installed ? '更新 Maa' : '下载 Maa'
          }}
        </n-button>
      </div>
    </template>
    <template v-else-if="maa_update_platform === 'linux' && maa_update_info_msg">
      <n-divider />
      <div class="maa-updater">
        <div class="update-title">Linux {{ maa_installed ? '更新 Maa' : '下载 Maa' }}</div>
        <div class="update-error">{{ maa_update_info_msg }}</div>
      </div>
    </template>
    <template v-else-if="maa_update_platform === 'windows'">
      <n-divider />
      <div class="maa-updater">
        <div class="update-title">Maa 自带更新</div>
        <div class="update-meta">
          <span>已安装：{{ maa_installed_version || '已检测到 Maa' }}</span>
        </div>
        <div class="update-option">
          <span class="update-option-label">Mower 下载通道</span>
          <n-radio-group v-model:value="maa_update_channel">
            <n-space>
              <n-radio value="stable">正式版</n-radio>
              <n-radio value="beta">公测版</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <div class="update-option">
          <span class="update-option-label">Mower 下载源</span>
          <n-radio-group v-model:value="maa_update_source">
            <n-space>
              <n-radio value="github">GitHub</n-radio>
              <n-radio value="mirrorchyan">Mirror酱</n-radio>
            </n-space>
          </n-radio-group>
        </div>
        <template v-if="maa_update_source === 'mirrorchyan'">
          <n-input
            v-model:value="maa_mirrorchyan_token"
            type="password"
            show-password-on="mousedown"
            placeholder="Mirror酱 CDK"
            :disabled="builtin_update_loading"
          />
          <div
            v-if="mirrorchyan_cdk_message"
            :class="mirrorchyan_cdk_message_class"
            aria-live="polite"
          >
            {{ mirrorchyan_cdk_message }}
          </div>
          <div class="update-hint">
            CDK 保存在 Mower 配置文件中。
            <n-a href="https://mirrorchyan.com/" target="_blank" rel="noopener noreferrer">
              获取 CDK
            </n-a>
          </div>
        </template>
        <div class="update-hint">
          已检测到 Windows Maa，本次操作只启动 MAA.Updater.exe，Mower 不会替换 Maa
          目录。上方更新源、版本通道和 CDK 只用于 Mower 首次下载，本次更新不会传递给
          MAA.Updater.exe；请在 Maa 内配置正式版/公测版通道、更新源和 Mirror酱 CDK。
        </div>
        <div v-if="builtin_update_msg" class="update-message">{{ builtin_update_msg }}</div>
        <n-button
          type="primary"
          :loading="builtin_update_loading"
          :disabled="builtin_update_loading"
          @click="start_builtin_maa_update"
        >
          启动 MAA.Updater.exe
        </n-button>
      </div>
    </template>
  </n-card>
</template>

<style scoped lang="scss">
p {
  margin: 0 0 10px 0;
}

.misc-container {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.maa-updater {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.update-title {
  font-size: 16px;
  font-weight: 600;
}

.update-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
}

.update-option {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
}

.update-option-label {
  min-width: 72px;
  color: var(--n-text-color-2);
}

.update-hint {
  color: var(--n-text-color-3);
  line-height: 1.6;
}

.update-message {
  line-height: 1.6;
  word-break: break-all;
}

.update-error {
  color: var(--n-color-error);
}

.update-warning {
  color: var(--n-color-warning);
}

.update-success {
  color: var(--n-color-success);
}
</style>
