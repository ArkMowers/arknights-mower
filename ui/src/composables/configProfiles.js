import { i18n } from '@/i18n'
import { computed, ref, shallowRef } from 'vue'
import { createSaveCoordinator } from '@/utils/configPersistence'
import { reloadImportedConfiguration } from '@/utils/configBackup'

export const CONFIG_GENERATION_HEADER = 'X-Mower-Config-Generation'
export const configProfilesKey = Symbol('config-profiles')

const profileSectionGroups = {
  connection: ['device', 'runtime'],
  tasks: [
    'base',
    'runorder',
    'drone',
    'clue',
    'trust',
    'daily',
    'recruit',
    'credit',
    'weekly_plan',
    'maa',
    'long',
    'workshop'
  ],
  plans: ['normal_plan', 'rescue_plan'],
  mower: ['accounts', 'notifications', 'assistant', 'appearance', 'maintenance', 'other_settings'],
  data: ['inventory', 'operators', 'growth', 'mastery', 'mastery_routes', 'recycling'],
  history: [
    'mood_history',
    'trading_history',
    'operation_history',
    'recycling_history',
    'report_history',
    'skland_history',
    'growth_history',
    'other_history'
  ]
}
const profileGroupSections = new Map(
  Object.entries(profileSectionGroups).flatMap(([section, keys]) =>
    keys.map((key) => [key, section])
  )
)

function profileSectionKey(section) {
  return (
    section.key ??
    section.children.map((group) => profileGroupSections.get(group.key)).find(Boolean)
  )
}

export function profileSectionTitle(section) {
  if (i18n.global.locale.value === 'zh-CN') return section.label
  const sectionKey = profileSectionKey(section)
  if (!Object.hasOwn(profileSectionGroups, sectionKey)) return section.label
  const key = `settings.profileCatalog.section${sectionKey[0].toUpperCase()}${sectionKey.slice(1)}`
  return i18n.global.te(key) ? i18n.global.t(key) : section.label
}

export function profileGroupText(group, field) {
  if (i18n.global.locale.value === 'zh-CN') return group[field]
  if (!profileGroupSections.has(group.key)) return group[field]
  const suffix = field === 'description' ? 'Description' : 'Label'
  const key = `settings.profileCatalog.${group.key}${suffix}`
  return i18n.global.te(key) ? i18n.global.t(key) : group[field]
}

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
  return detail?.message || error.message || i18n.global.t('settings.profileDialog.failed')
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
      const label = group.section || i18n.global.t('settings.profileDialog.other')
      if (!result.has(label)) result.set(label, [])
      result.get(label).push(group)
    }
    return [...result].map(([label, children]) => {
      const section = { label, children }
      const key = profileSectionKey(section) ?? `extension:${label}`
      return { key, label: profileSectionTitle({ ...section, key }), children }
    })
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
    error.value = data.message || i18n.global.t('settings.profileDialog.changed')
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
        throw new Error(data.message || i18n.global.t('settings.profileDialog.invalidList'))
      }
      state.value = data
      if (bootstrap && generation === null) {
        generation = String(data.generation)
        axios.defaults.headers.common[CONFIG_GENERATION_HEADER] = generation
      } else if (generation !== null && String(data.generation) !== generation) {
        freeze()
        error.value = i18n.global.t('settings.profileDialog.changedElsewhere')
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
      action === 'rename'
        ? profile.name
        : action === 'copy'
          ? i18n.global.t('settings.profileDialog.copyName', { value0: profile.name })
          : ''
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
      error.value = i18n.global.t('settings.profileDialog.tooLarge')
      return
    }
    if (!/\.zip$/i.test(chosen.name)) {
      error.value = i18n.global.t('settings.profileDialog.missingConfig')
      return
    }
    file.value = chosen
    if (!name.value.trim()) name.value = chosen.name.replace(/\.zip$/i, '')
  }

  function reloadPage() {
    try {
      reload({
        message: message.value || i18n.global.t('settings.profileDialog.reloaded'),
        recovery_path: ''
      })
    } catch (failure) {
      error.value = i18n.global.t('settings.profileDialog.reloadFailed', {
        value0: failure.message || i18n.global.t('settings.profileDialog.retry')
      })
    }
  }

  async function submit() {
    if (!dialog.value || writeDisabled.value) return
    const operation = { ...dialog.value }
    const profileName = name.value.trim()
    if (operation.action !== 'activate' && !profileName) {
      error.value = i18n.global.t('settings.profileDialog.enterName')
      return
    }
    if (operation.action === 'import' && !file.value) {
      error.value = i18n.global.t('settings.profileDialog.chooseProfileBackup')
      return
    }
    const selection = [...selected.value]
    busy.value = true
    error.value = ''
    let attempted = false
    try {
      await saves.pauseAndDrain()
      await beforeChange()
      if (stale.value) throw new Error(i18n.global.t('settings.profileDialog.changed'))
      if (blocked() || state.value.busy)
        throw new Error(i18n.global.t('settings.profileDialog.stopFirst'))
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
        throw new Error(response.data.message || i18n.global.t('settings.profileDialog.incomplete'))
      }
      state.value = { ...state.value, ...response.data }
      dialog.value = null
      if (operation.action === 'rename') {
        saves.resume()
      } else {
        message.value = i18n.global.t('settings.profileDialog.switchedReload')
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
        error.value += i18n.global.t('settings.profileDialog.uncertain')
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
