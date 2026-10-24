import { computed, ref, shallowRef } from 'vue'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { reloadImportedConfiguration } from '@/utils/configBackup'

export const CONFIG_GENERATION_HEADER = 'X-Mower-Config-Generation'

export async function downloadConfiguration(axios, url) {
  const { data } = await axios.get(url, { responseType: 'blob' })
  const objectUrl = URL.createObjectURL(data)
  try {
    const anchor = document.createElement('a')
    anchor.href = objectUrl
    anchor.download = `mower-config-${new Date().toISOString().replace(/[:.]/g, '-')}.zip`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
  }
}

async function errorText(error) {
  let detail = error.response?.data
  if (detail instanceof Blob) {
    try {
      detail = JSON.parse(await detail.text())
      error.response.data = detail
    } catch {
      detail = null
    }
  }
  return detail?.message || error.message || '档案操作失败，请重试'
}

export function createConfigProfiles({
  axios,
  config,
  plan,
  rescuePlan,
  blocked = () => false,
  beforeChange = async () => {},
  reload = reloadImportedConfiguration,
  download = downloadConfiguration
}) {
  const base = `${import.meta.env.VITE_HTTP_URL || ''}/config-profiles`
  const saves = createSaveCoordinator(config, plan, rescuePlan ? [rescuePlan] : [])
  const frozenSaves = createSaveCoordinator(config, plan, rescuePlan ? [rescuePlan] : [])
  const state = shallowRef(null)
  const loading = ref(false)
  const busy = ref(false)
  const error = ref('')
  const message = ref('')
  const stale = ref(false)
  const pendingReload = ref(false)
  const dialog = ref(null)
  const name = ref('')
  const selected = ref([])
  const file = shallowRef(null)
  let generation = null
  const groups = computed(() => state.value?.groups || [])
  const sections = computed(() => {
    const result = new Map()
    for (const group of groups.value) {
      const label = group.section || '其他'
      if (!result.has(label)) result.set(label, [])
      result.get(label).push(group)
    }
    return [...result].map(([label, children]) => ({ label, children }))
  })
  const readDisabled = computed(
    () =>
      !state.value ||
      loading.value ||
      busy.value ||
      saves.paused.value ||
      stale.value ||
      pendingReload.value
  )
  const writeDisabled = computed(
    () => readDisabled.value || blocked() || state.value?.busy === true
  )

  function freeze() {
    stale.value = true
    frozenSaves.pause({ pendingOperation: true })
  }

  async function observeFailure(failure) {
    if (failure.response?.data instanceof Blob) await errorText(failure)
    const data = failure.response?.data
    if ((data?.code || data?.error) !== 'configuration_changed') return false
    error.value = data.message || '当前档案已变更，请重新加载后继续。'
    freeze()
    return true
  }

  async function refresh({ bootstrap = false } = {}) {
    if (loading.value || busy.value) return false
    loading.value = true
    error.value = ''
    try {
      const { data } = await axios.get(base)
      if (
        !data.ok ||
        !Array.isArray(data.profiles) ||
        !Array.isArray(data.groups) ||
        !['string', 'number'].includes(typeof data.generation)
      ) {
        throw new Error(data.message || '档案列表格式不正确')
      }
      state.value = data
      if (bootstrap && generation === null) {
        generation = String(data.generation)
        axios.defaults.headers.common[CONFIG_GENERATION_HEADER] = generation
      } else if (generation !== null && String(data.generation) !== generation) {
        freeze()
        error.value = '当前档案已在其他页面切换，请重新加载后继续。'
      }
      return true
    } catch (failure) {
      error.value = await errorText(failure)
      return false
    } finally {
      loading.value = false
    }
  }

  function open(action, target = null) {
    if (action === 'refresh') return refresh()
    if (action === 'export') return exportCurrent()
    if (writeDisabled.value) return
    if (!['create', 'copy', 'rename', 'import', 'activate'].includes(action)) return
    const profile = state.value.profiles.find(
      (item) => item.id === (target || state.value.active_id)
    )
    if (!profile || (action === 'activate' && profile.id === state.value.active_id)) return
    error.value = ''
    message.value = ''
    name.value =
      action === 'rename' ? profile.name : action === 'copy' ? `${profile.name} 副本` : ''
    selected.value = action === 'copy' ? groups.value.map((group) => group.key) : []
    file.value = null
    dialog.value = { action, target: profile.id, targetName: profile.name }
  }

  function toggleSection(section, checked) {
    const keys = new Set(selected.value)
    for (const group of section.children) {
      if (checked) keys.add(group.key)
      else keys.delete(group.key)
    }
    selected.value = [...keys]
  }

  function selectFile(event) {
    const chosen = event.target.files?.[0]
    event.target.value = ''
    if (!chosen) return
    file.value = null
    error.value = ''
    if (chosen.size > 16 * 1024 * 1024) {
      error.value = '备份文件不能超过 16 MB'
      return
    }
    if (!/\.zip$/i.test(chosen.name)) {
      error.value = '请选择包含 config 文件夹的 ZIP 备份'
      return
    }
    file.value = chosen
    if (!name.value.trim()) name.value = chosen.name.replace(/\.zip$/i, '')
  }

  function reloadPage() {
    try {
      reload({ message: message.value || '已重新加载档案。', recovery_path: '' })
    } catch (failure) {
      error.value = `页面未能重新加载：${failure.message || '请重试'}`
    }
  }

  async function submit() {
    if (!dialog.value || writeDisabled.value) return
    const operation = { ...dialog.value }
    const profileName = name.value.trim()
    if (operation.action !== 'activate' && !profileName) {
      error.value = '请填写档案名称'
      return
    }
    if (operation.action === 'import' && !file.value) {
      error.value = '请选择 ZIP 档案备份'
      return
    }
    const selection = [...selected.value]
    busy.value = true
    error.value = ''
    let attempted = false
    try {
      await saves.pauseAndDrain()
      await beforeChange()
      if (stale.value) throw new Error('当前档案已变更，请重新加载后继续。')
      if (blocked() || state.value.busy) throw new Error('请先停止任务并等待设备或更新操作结束')
      const options = {
        headers: { 'X-Mower-Settings': '1', [CONFIG_GENERATION_HEADER]: generation }
      }
      let response
      attempted = true
      if (operation.action === 'rename') {
        response = await axios.patch(
          `${base}/${encodeURIComponent(operation.target)}`,
          { name: profileName },
          options
        )
      } else if (operation.action === 'activate') {
        response = await axios.post(
          `${base}/${encodeURIComponent(operation.target)}/activate`,
          { keep: selection },
          options
        )
      } else if (operation.action === 'import') {
        const form = new FormData()
        form.append('backup', file.value)
        form.append('name', profileName)
        form.append('keep', JSON.stringify(selection))
        response = await axios.post(`${base}/import`, form, options)
      } else {
        response = await axios.post(base, { name: profileName, inherit: selection }, options)
      }
      if (!response.data.ok) {
        attempted = false
        throw new Error(response.data.message || '档案操作未完成')
      }
      state.value = { ...state.value, ...response.data }
      dialog.value = null
      if (operation.action === 'rename') {
        saves.resume()
      } else {
        message.value = '档案已切换，重新加载后可继续编辑。'
        pendingReload.value = true
        reloadPage()
      }
    } catch (failure) {
      error.value = await errorText(failure)
      if (await observeFailure(failure)) {
        // A full reload is required before the old stores can resume saving.
      } else if (!attempted || (failure.response?.status >= 400 && failure.response.status < 500)) {
        saves.resume()
      } else {
        freeze()
        error.value += '。操作结果尚未确认，自动保存已暂停，请检查当前档案或重新加载。'
      }
    } finally {
      busy.value = false
    }
  }

  async function exportCurrent() {
    if (readDisabled.value) return
    busy.value = true
    error.value = ''
    message.value = ''
    try {
      await saves.drain()
      await download(axios, `${base}/export`)
    } catch (failure) {
      error.value = await errorText(failure)
      await observeFailure(failure)
    } finally {
      busy.value = false
    }
  }

  return {
    state,
    loading,
    busy,
    error,
    message,
    stale,
    pendingReload,
    dialog,
    name,
    selected,
    file,
    groups,
    sections,
    readDisabled,
    writeDisabled,
    refresh,
    observeFailure,
    bootstrap: () => refresh({ bootstrap: true }),
    open,
    toggleSection,
    selectFile,
    submit,
    reloadPage
  }
}
