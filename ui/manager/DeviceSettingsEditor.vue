<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { managerCall } from './bridge.js'
import {
  deviceSettingsState,
  deviceDetectionDraft,
  editedDevicePatch,
  presetLabels
} from '../src/utils/deviceSettings.js'
import DeviceProfileField from '../src/components/DeviceProfileField.vue'
import HelpText from '../src/components/HelpText.vue'
import WaitingSceneEditor from './WaitingSceneEditor.vue'
import { connectionFields, idleAction, idleActionPatch, idleOptions } from './connectionSettings.js'

const props = defineProps({
  api: { type: Object, required: true },
  idx: { type: Number, required: true },
  target: { type: Object, required: true }
})
const emit = defineEmits(['saved'])
const original = ref(null)
const draft = ref({})
const initial = ref({})
const fields = ref([])
const pending = ref(false)
const error = ref('')
const discovery = ref(null)
const testResult = ref(null)
const testing = ref(false)
const confirmedSerial = ref(null)
const manualConfirmation = ref(null)
const advanced = ref(false)
const selectedKey = ref(null)
const confirmShared = ref(false)
const preflightResult = computed(() => discovery.value?.kind === 'preflight')
const candidateOptions = computed(() =>
  (discovery.value?.candidates || []).map((item) =>
    preflightResult.value
      ? { value: item.serial, label: [item.serial, item.state].filter(Boolean).join(' · ') }
      : {
          value: item.key,
          label: [presetLabels[item.preset_id], item.instance_name, item.instance_id]
            .filter(Boolean)
            .join(' · ')
        }
  )
)
const policySupported = ref(false)
const originalPolicy = ref(null)
const sharedKeys = ref([])
const overrideKeys = ref([])
const instanceOverride = ref({ local_keys: [], manager_values: {} })
const initialOverride = ref({ local_keys: [], manager_values: {} })
const managerOnlyKeys = new Set(['startup_mode', 'instance_page_mode'])
const usesLocalValue = (key) =>
  instanceOverride.value.local_keys.includes(key) ||
  Object.hasOwn(instanceOverride.value.manager_values, key)
const independentConfiguration = ref(false)
const initialIndependentConfiguration = ref(false)
const instanceFields = new Set([
  'device.instance_id',
  'device.instance_name',
  'device.mumu_manual_serial',
  'device.game_package'
])
const derivedIdentityFields = new Set([
  'device.instance_uuid',
  'device.topology_fingerprint',
  'device.mumu_created_timestamp'
])
const templateFields = [
  'device.preset_id',
  'device.installation_path',
  'device.manager_path',
  'device.config_path'
]
const sharedConfiguration = computed(() => policySupported.value && !independentConfiguration.value)
const editableField = (key) =>
  overrideKeys.value.includes(key)
    ? usesLocalValue(key)
    : !sharedConfiguration.value || instanceFields.has(key)
const patchField = (key) => editableField(key) || derivedIdentityFields.has(key)
const profile = computed(() =>
  Object.fromEntries(
    Object.entries(draft.value)
      .filter(([key]) => key.startsWith('device.'))
      .map(([key, value]) => [key.slice(7), value])
  )
)
const deviceState = computed(() =>
  deviceSettingsState({
    profile: profile.value,
    result:
      testResult.value ||
      (discovery.value ? { ...discovery.value, kind: discovery.value.kind || 'discovery' } : null),
    busy: pending.value,
    advanced: true,
    selectedKey: selectedKey.value,
    confirmedPackage: profile.value.game_package
  })
)
const profileKeys = computed(
  () =>
    new Set(
      [...deviceState.value.fields, ...deviceState.value.connectionFields].map(
        ({ key }) => `device.${key}`
      )
    )
)
function fieldSource(key) {
  if (!policySupported.value) return ''
  if (overrideKeys.value.includes(key)) return usesLocalValue(key) ? '本实例值' : '来自通用设置'
  return !editableField(key) ? '来自通用设置' : '本实例值'
}
const profileFields = computed(() =>
  deviceState.value.fields.flatMap((field) => {
    const definition = fields.value.find(({ key }) => key === `device.${field.key}`)
    if (!definition || definition.read_only) return []
    const repair = testResult.value?.error?.fields || discovery.value?.error?.fields || []
    if (!advanced.value && !['preset_id', ...repair].includes(field.key)) return []
    return [
      {
        ...field,
        value: profile.value[field.key] ?? '',
        options: field.key === 'preset_id' ? options(definition) : field.options,
        source: fieldSource(definition.key),
        disabled: disabled.value || !editableField(definition.key)
      }
    ]
  })
)
const backendFields = computed(() =>
  deviceState.value.connectionFields
    .filter((field) => fields.value.some(({ key }) => key === `device.${field.key}`))
    .map((field) => ({
      ...field,
      source: fieldSource(`device.${field.key}`),
      disabled: disabled.value || !editableField(`device.${field.key}`)
    }))
)
const visibleFields = computed(() =>
  connectionFields(fields.value, draft.value).filter((field) => !field.read_only)
)
const additionalFields = computed(() =>
  visibleFields.value.filter(
    (field) =>
      !profileKeys.value.has(field.key) &&
      ![
        'device.instance_id',
        'device.instance_name',
        'device.config_path',
        'device.manager_path'
      ].includes(field.key)
  )
)
const groups = computed(() => [...new Set(additionalFields.value.map((field) => field.group))])
const discardedFields = computed(() =>
  fields.value
    .filter(
      (field) =>
        !instanceFields.has(field.key) &&
        !overrideKeys.value.includes(field.key) &&
        JSON.stringify(draft.value[field.key]) !==
          JSON.stringify(
            originalPolicy.value?.shared_values?.[field.key] ?? initial.value[field.key]
          )
    )
    .map((field) => field.label || field.key)
)
function confirmIndependentChange() {
  setIndependent(false)
  confirmShared.value = false
}
function requestIndependent(value) {
  if (!value && discardedFields.value.length) confirmShared.value = true
  else setIndependent(value)
}
function editProfile(key, value) {
  edit(`device.${key}`, value)
}
function browseProfile(key) {
  const field = fields.value.find((item) => item.key === `device.${key}`)
  if (field) return browse(field)
}
const policyChanged = computed(
  () =>
    policySupported.value &&
    (independentConfiguration.value !== initialIndependentConfiguration.value ||
      JSON.stringify(instanceOverride.value) !== JSON.stringify(initialOverride.value))
)
const changes = computed(() =>
  Object.fromEntries(
    Object.entries(draft.value).filter(([key, value]) => {
      const baseline =
        instanceOverride.value.local_keys.includes(key) &&
        Object.hasOwn(originalPolicy.value?.local_values ?? {}, key)
          ? originalPolicy.value.local_values[key]
          : initial.value[key]
      return (
        patchField(key) &&
        (JSON.stringify(value) !== JSON.stringify(baseline) ||
          (key === 'device.last_serial' && confirmedSerial.value === value))
      )
    })
  )
)
const disabled = computed(() => pending.value || !original.value)
const hasChanges = computed(() => policyChanged.value || Object.keys(changes.value).length > 0)
let disposed = false

async function load() {
  testResult.value = null
  selectedKey.value = null
  pending.value = true
  original.value = null
  error.value = ''
  try {
    const result = await managerCall(() => props.api.get_device_settings(props.idx, props.target))
    if (disposed) return
    if (!result?.values || !Array.isArray(result.fields))
      throw new Error('设备配置格式不正确，请重新加载')
    policySupported.value = Object.hasOwn(result, 'independent_configuration')
    if (
      policySupported.value &&
      (typeof result.independent_configuration !== 'boolean' ||
        !Array.isArray(result.shared_keys) ||
        !result.original_policy ||
        typeof result.original_policy !== 'object')
    )
      throw new Error('连接配置的继承信息不完整，请更新管理器后重新加载')
    originalPolicy.value = result.original_policy ?? null
    sharedKeys.value = result.shared_keys ?? []
    overrideKeys.value = result.override_keys ?? []
    instanceOverride.value = copyValue(
      result.instance_override ?? { local_keys: [], manager_values: {} }
    )
    initialOverride.value = copyValue(instanceOverride.value)
    independentConfiguration.value = result.independent_configuration === true
    initialIndependentConfiguration.value = independentConfiguration.value
    const flat = Object.fromEntries(
      result.fields.map(({ key }) => [
        key,
        key.split('.').reduce((value, part) => value?.[part], result.values)
      ])
    )
    original.value = result.values
    fields.value = result.fields
    initial.value = structuredClone(flat)
    draft.value = structuredClone(flat)
    discovery.value = null
    confirmedSerial.value = null
  } catch (reason) {
    error.value = reason?.message || '无法读取设备配置'
  } finally {
    pending.value = false
  }
}

function edit(key, value) {
  testResult.value = null
  const field = fields.value.find((item) => item.key === key)
  if (!field || disabled.value || !editableField(key) || field.read_only) return
  discovery.value = null
  selectedKey.value = null
  const targetChanged =
    [...templateFields, 'device.instance_id', 'device.instance_name'].includes(key) &&
    draft.value[key] !== value
  if (targetChanged) {
    confirmedSerial.value = null
    if (key === 'device.instance_name') {
      draft.value['device.last_serial'] = ''
      draft.value['device.instance_uuid'] = ''
      draft.value['device.topology_fingerprint'] = ''
    }
  }
  if (key === 'device.last_serial') confirmedSerial.value = value
  if (key.startsWith('device.')) {
    const profile = Object.fromEntries(
      Object.entries(draft.value)
        .filter(([field]) => field.startsWith('device.'))
        .map(([field, current]) => [field.slice(7), current])
    )
    for (const [field, next] of Object.entries(editedDevicePatch(profile, key.slice(7), value))) {
      if (Object.hasOwn(draft.value, `device.${field}`)) draft.value[`device.${field}`] = next
    }
  } else draft.value[key] = value
  if (managerOnlyKeys.has(key) && usesLocalValue(key))
    instanceOverride.value.manager_values[key] = value
}

function editIdleAction(value) {
  for (const [key, selected] of Object.entries(idleActionPatch(value))) edit(key, selected)
}

function setIndependent(value) {
  testResult.value = null
  if (disabled.value || !policySupported.value) return
  independentConfiguration.value = value === true
  discovery.value = null
  confirmedSerial.value = null
  if (!independentConfiguration.value) {
    for (const field of fields.value) {
      if (!instanceFields.has(field.key) && !overrideKeys.value.includes(field.key))
        draft.value[field.key] = copyValue(initial.value[field.key])
    }
    for (const key of sharedKeys.value) {
      if (Object.hasOwn(originalPolicy.value.shared_values ?? {}, key))
        draft.value[key] = copyValue(originalPolicy.value.shared_values[key])
    }
    if (
      templateFields.some((key) => draft.value[key] !== initial.value[key]) ||
      draft.value['device.instance_id'] !== initial.value['device.instance_id']
    ) {
      draft.value['device.last_serial'] = ''
      draft.value['device.instance_uuid'] = ''
      draft.value['device.topology_fingerprint'] = ''
    }
  }
}

function setLocalValue(key, local) {
  testResult.value = null
  if (disabled.value || !overrideKeys.value.includes(key)) return
  if (managerOnlyKeys.has(key)) {
    if (local) instanceOverride.value.manager_values[key] = draft.value[key]
    else delete instanceOverride.value.manager_values[key]
  } else {
    instanceOverride.value.local_keys = local
      ? [...new Set([...instanceOverride.value.local_keys, key])].sort()
      : instanceOverride.value.local_keys.filter((item) => item !== key)
  }
  if (
    local &&
    !managerOnlyKeys.has(key) &&
    Object.hasOwn(originalPolicy.value.local_values ?? {}, key)
  )
    draft.value[key] = copyValue(originalPolicy.value.local_values[key])
  if (!local) {
    const defaultValue = managerOnlyKeys.has(key)
      ? (fields.value.find((field) => field.key === key)?.default ?? initial.value[key])
      : initial.value[key]
    draft.value[key] = copyValue(originalPolicy.value.shared_values[key] ?? defaultValue)
  }
}

function requestPolicy() {
  const result = {
    independent_configuration: independentConfiguration.value,
    original_policy: originalPolicy.value
  }
  if (overrideKeys.value.length) result.instance_override = copyValue(instanceOverride.value)
  return result
}

function copyValue(value) {
  return value && typeof value === 'object' ? JSON.parse(JSON.stringify(value)) : value
}

function options(field) {
  return field.options.map(([value, label]) => ({
    value,
    label:
      field.key === 'device.preset_id'
        ? `${presetLabels[value] || label} (${value.split('.')[0]})`
        : field.key === 'device.game_package'
          ? value.endsWith('bilibili')
            ? 'Bilibili 服'
            : '官服'
          : label
  }))
}

async function testConnection() {
  if (disabled.value || typeof props.api.test_device_settings !== 'function') return
  pending.value = true
  testing.value = true
  error.value = ''
  testResult.value = null
  try {
    const args = [props.idx, { ...changes.value }, props.target, original.value]
    if (policySupported.value) args.push(requestPolicy())
    const result = await managerCall(() => props.api.test_device_settings(...args), 60000)
    if (!disposed) testResult.value = result
  } catch (reason) {
    error.value = reason?.message || '无法测试设备连接'
  } finally {
    pending.value = false
    testing.value = false
  }
}

async function detect() {
  if (disabled.value) return
  testResult.value = null
  selectedKey.value = null
  pending.value = true
  error.value = ''
  discovery.value = null
  try {
    const args = [props.idx, { ...changes.value }, props.target, original.value]
    if (policySupported.value) args.push(requestPolicy())
    const result = await managerCall(() => props.api.discover_device_settings(...args), 60000)
    if (!disposed) discovery.value = result
  } catch (reason) {
    error.value = reason?.message || '无法检测设备'
  } finally {
    pending.value = false
  }
}

function selectCandidate(key) {
  testResult.value = null
  if (disabled.value) return
  if (preflightResult.value) {
    if (!discovery.value.candidates.some((item) => item.serial === key)) return
    if (!editableField('device.last_serial')) {
      error.value = '选择 ADB 连接地址需要开启独立配置，请开启后重新检测。'
      return
    }
    const profile = Object.fromEntries(
      Object.entries(draft.value)
        .filter(([field]) => field.startsWith('device.'))
        .map(([field, value]) => [field.slice(7), value])
    )
    const selected = {
      ...deviceDetectionDraft(profile, discovery.value),
      ...discovery.value.profile_patch,
      ...(discovery.value.adb_path ? { adb_path: discovery.value.adb_path } : {}),
      last_serial: key
    }
    confirmedSerial.value = key
    for (const [field, value] of Object.entries(selected)) {
      if (Object.hasOwn(draft.value, `device.${field}`) && patchField(`device.${field}`))
        draft.value[`device.${field}`] = value
    }
    error.value = ''
    return
  }
  const candidate = discovery.value?.candidates?.find((candidate) => candidate.key === key)
  const binding = candidate?.binding
  if (!binding) return
  if (
    sharedConfiguration.value &&
    (candidate.shared_template_matches === false ||
      (candidate.preset_id && candidate.preset_id !== draft.value['device.preset_id']) ||
      templateFields.some(
        (field) =>
          Object.hasOwn(binding, field.slice(7)) && binding[field.slice(7)] !== draft.value[field]
      ))
  ) {
    error.value = '此实例的模拟器预设或路径与通用设置不同，请修改通用设置或开启独立配置后重新检测。'
    return
  }
  error.value = ''
  selectedKey.value = key
  confirmedSerial.value = null
  if (
    Object.hasOwn(binding, 'instance_id') &&
    binding.instance_id !== draft.value['device.instance_id']
  )
    draft.value['device.instance_name'] = ''
  draft.value['device.instance_uuid'] = ''
  draft.value['device.topology_fingerprint'] = ''
  if (Object.hasOwn(draft.value, 'device.mumu_manual_serial'))
    draft.value['device.mumu_manual_serial'] = ''
  if (Object.hasOwn(draft.value, 'device.mumu_created_timestamp'))
    draft.value['device.mumu_created_timestamp'] = ''
  for (const [field, value] of Object.entries(binding)) {
    if (Object.hasOwn(draft.value, `device.${field}`) && patchField(`device.${field}`))
      draft.value[`device.${field}`] = value
  }
  draft.value['device.last_serial'] = ''
}

async function browse(field) {
  if (disabled.value || !editableField(field.key) || field.read_only) return
  pending.value = true
  error.value = ''
  try {
    const value = await props.api.select_device_path(field.key, draft.value[field.key] || '')
    if (!disposed && value) {
      pending.value = false
      edit(field.key, value)
    }
  } catch (reason) {
    error.value = reason?.message || '无法选择路径'
  } finally {
    pending.value = false
  }
}

async function save() {
  if (disabled.value || !hasChanges.value) return
  if (changes.value['device.mumu_manual_serial']?.trim()) {
    manualConfirmation.value = JSON.stringify({ changes: changes.value, policy: requestPolicy() })
    return
  }
  await performSave()
}

async function confirmManual() {
  const previous = manualConfirmation.value
  manualConfirmation.value = null
  if (
    !previous ||
    disabled.value ||
    previous !== JSON.stringify({ changes: changes.value, policy: requestPolicy() })
  ) {
    error.value = '设备配置已变化，请重新确认手动地址。'
    return
  }
  await performSave()
}

async function performSave() {
  pending.value = true
  error.value = ''
  try {
    const args = [props.idx, { ...changes.value }, props.target, original.value]
    if (policySupported.value) args.push(requestPolicy())
    // A frontend timeout cannot cancel an in-flight save; keep editing locked
    // until the manager reports the actual outcome.
    const result = await props.api.update_device_settings(...args)
    if (result?.ok === false) throw new Error(result.message)
    if (!disposed) emit('saved')
  } catch (reason) {
    error.value = reason?.message || '无法保存设备配置'
  } finally {
    pending.value = false
  }
}

onMounted(load)
onUnmounted(() => {
  disposed = true
})
</script>

<template>
  <div class="device-editor">
    <div class="device-summary" v-if="original">
      <div class="device-title-row">
        <strong>{{ deviceState.presetTitle }}</strong>
        <n-tag size="small" :type="deviceState.statusTagType">{{
          selectedKey && !preflightResult && !testResult
            ? '已选择，未测试连接'
            : deviceState.statusDisplayLabel
        }}</n-tag>
        <n-tag v-if="hasChanges" size="small" type="warning">未保存</n-tag>
      </div>
      <p>
        {{ target.name }} ·
        {{ profile.instance_name || profile.instance_id || '尚未选择模拟器实例' }}
      </p>
      <n-text depth="3"
        >ADB 地址：{{ testResult?.serial || profile.last_serial || '待连接验证' }}</n-text
      >
    </div>
    <n-text depth="3">配置保存后下次启动生效。检测与选择不会启动模拟器，也不会自动保存。</n-text>
    <n-alert v-if="draft['device.mumu_manual_serial']" type="warning" :show-icon="false">
      请确认手动地址属于当前 MuMu
      实例。端口可能变化或被其他实例复用，地址错误时任务可能操作其他账号。管理器未提供或复用创建时间时，无法识别同名实例被替换；手动地址不能使用
      MuMu IPC。
    </n-alert>
    <n-alert v-if="error" type="error"
      >{{ error
      }}<template #action
        ><n-button :disabled="pending" @click="load">重新加载</n-button></template
      ></n-alert
    >
    <n-skeleton v-if="!original && pending" :height="160" />
    <n-form-item
      v-if="original && policySupported"
      label="独立配置"
      label-placement="left"
      :show-feedback="false"
    >
      <n-switch
        :value="independentConfiguration"
        :disabled="disabled"
        aria-label="独立配置"
        @update:value="requestIndependent"
      />
    </n-form-item>
    <n-alert
      v-if="original && policySupported && !independentConfiguration"
      type="info"
      :show-icon="false"
    >
      连接参数来自通用设置。开启独立配置后，可为此实例单独设置。
    </n-alert>
    <n-text v-else-if="original && policySupported" depth="3">
      连接参数仅应用于此实例，下次启动生效。
    </n-text>
    <div v-if="original" class="device-editor-fields">
      <section class="device-primary-fields" aria-label="设备连接">
        <n-grid cols="2" :x-gap="16" :y-gap="4">
          <n-gi v-for="field in profileFields" :key="field.key" :span="field.span || 1"
            ><DeviceProfileField :field="field" @edit="editProfile" @browse="browseProfile"
          /></n-gi>
        </n-grid>
        <n-alert
          v-if="testResult"
          :type="testResult.ok ? 'success' : 'warning'"
          :show-icon="true"
          role="status"
        >
          {{
            testResult.ok
              ? `连接测试通过。设备、游戏包与截图检查正常。${hasChanges ? '修改仍需手动保存。' : ''}`
              : ['instance_stopped', 'start_confirmation_required'].includes(testResult.error?.code)
                ? '所选模拟器实例尚未启动，请在模拟器中启动后再测试连接。'
                : testResult.error?.message || '连接测试未通过，请检查所选设备。'
          }}
        </n-alert>
        <n-space vertical>
          <n-space align="center">
            <n-button type="primary" :disabled="disabled" :loading="pending" @click="detect"
              >检测可用实例</n-button
            >
            <n-button
              :disabled="disabled || typeof api.test_device_settings !== 'function'"
              :loading="testing"
              @click="testConnection"
              >测试连接</n-button
            >
            <n-button quaternary :aria-expanded="advanced" @click="advanced = !advanced">{{
              advanced ? '收起高级设置' : '高级设置'
            }}</n-button>
          </n-space>
          <n-select
            v-if="candidateOptions.length"
            :value="preflightResult ? confirmedSerial : selectedKey"
            aria-label="选择实例"
            :placeholder="preflightResult ? '选择明确的 ADB 连接地址' : '选择明确的模拟器实例'"
            :disabled="disabled"
            :options="candidateOptions"
            @update:value="selectCandidate"
          />
          <n-text v-if="discovery?.candidates?.length" depth="3"
            >选择后仍需保存；检测与选择不会改写配置或启动模拟器。</n-text
          >
          <n-alert v-if="discovery?.error" type="warning">{{ discovery.error.message }}</n-alert>
          <n-text v-else-if="discovery && !discovery.candidates?.length">{{
            discovery.ok ? '已完成当前设备检测。' : '未找到可选实例，请检查模拟器安装路径。'
          }}</n-text>
          <n-alert v-if="discovery?.guidance" type="info" :show-icon="false">{{
            discovery.guidance
          }}</n-alert>
        </n-space>

        <n-divider title-placement="left">截图与触控</n-divider>
        <n-grid cols="2" :x-gap="16" :y-gap="4">
          <n-gi v-for="field in backendFields" :key="field.key" :span="field.span || 1"
            ><DeviceProfileField :field="field" @edit="editProfile"
          /></n-gi>
        </n-grid>
      </section>
      <n-collapse :default-expanded-names="['截图与触控', '游戏启动与空闲', '实例启动']">
        <n-collapse-item
          v-for="group in groups.filter(
            (name) => advanced || !['模拟器与设备', '连接恢复', '性能', '运行参数'].includes(name)
          )"
          :key="group"
          :title="group === '截图与触控' ? '更多截图与连接选项' : group"
          :name="group"
        >
          <n-form label-placement="top" :show-feedback="false">
            <div class="device-editor-grid">
              <n-form-item
                v-for="field in additionalFields.filter((item) => item.group === group)"
                :key="field.key"
                :class="{
                  'device-editor-wide':
                    ['file', 'directory', 'waiting_scene'].includes(field.kind) ||
                    field.key.endsWith('.command')
                }"
              >
                <template #label
                  ><span>{{ field.label }}</span
                  ><HelpText v-if="field.help">{{ field.help }}</HelpText></template
                >
                <div class="device-editor-field-value">
                  <n-text v-if="fieldSource(field.key)" depth="3" class="field-source">{{
                    fieldSource(field.key)
                  }}</n-text>
                  <n-select
                    v-if="overrideKeys.includes(field.key)"
                    :value="usesLocalValue(field.key) ? 'local' : 'common'"
                    :options="[
                      { value: 'common', label: '使用通用设置' },
                      { value: 'local', label: '使用本实例值' }
                    ]"
                    :disabled="disabled"
                    :aria-label="`${field.label}配置来源`"
                    @update:value="(value) => setLocalValue(field.key, value === 'local')"
                  />
                  <n-select
                    v-if="field.kind === 'idle_action'"
                    :value="idleAction(draft)"
                    :options="idleOptions(draft)"
                    :consistent-menu-width="false"
                    :disabled="disabled || !editableField(field.key)"
                    :aria-label="field.label"
                    @update:value="editIdleAction"
                  />
                  <WaitingSceneEditor
                    v-else-if="field.kind === 'waiting_scene'"
                    :field="field"
                    :value="draft[field.key]"
                    :disabled="disabled || !editableField(field.key)"
                    @update:value="(value) => edit(field.key, value)"
                  />
                  <n-switch
                    v-else-if="field.kind === 'boolean'"
                    :value="draft[field.key]"
                    :disabled="disabled || !editableField(field.key)"
                    :aria-label="field.label"
                    @update:value="(value) => edit(field.key, value)"
                  />
                  <n-select
                    v-else-if="field.kind === 'select'"
                    :value="draft[field.key]"
                    :options="options(field)"
                    :consistent-menu-width="false"
                    :disabled="disabled || !editableField(field.key)"
                    :aria-label="field.label"
                    @update:value="(value) => edit(field.key, value)"
                  />
                  <n-input-number
                    v-else-if="['integer', 'number'].includes(field.kind)"
                    :value="draft[field.key]"
                    :min="field.min ?? 0"
                    :max="field.max"
                    :precision="field.kind === 'integer' ? 0 : undefined"
                    :disabled="disabled || !editableField(field.key)"
                    :aria-label="field.label"
                    @update:value="(value) => edit(field.key, value)"
                  />
                  <n-input-group v-else>
                    <n-input
                      :value="draft[field.key]"
                      :type="field.key.endsWith('.command') ? 'textarea' : 'text'"
                      :autosize="{ minRows: 1, maxRows: 6 }"
                      placeholder="未设置"
                      :disabled="disabled || !editableField(field.key)"
                      :aria-label="field.label"
                      @update:value="(value) => edit(field.key, value)"
                    />
                    <n-button
                      v-if="['file', 'directory'].includes(field.kind)"
                      :disabled="disabled || !editableField(field.key)"
                      @click="browse(field)"
                      >选择</n-button
                    >
                  </n-input-group>
                </div>
              </n-form-item>
            </div>
          </n-form>
        </n-collapse-item>
      </n-collapse>
    </div>
    <div class="device-editor-actions">
      <n-text depth="3" role="status"
        >{{ hasChanges ? '有未保存的修改' : '当前显示已保存的配置' }} · 下次启动生效</n-text
      >
      <n-button type="primary" :loading="pending" :disabled="disabled || !hasChanges" @click="save"
        >保存连接与启动配置</n-button
      >
    </div>
    <n-modal
      :show="!!manualConfirmation"
      preset="dialog"
      title="确认手动填写 MuMu 地址"
      positive-text="我已了解"
      negative-text="取消"
      @positive-click="confirmManual"
      @negative-click="manualConfirmation = null"
      @close="manualConfirmation = null"
    >
      Mower
      无法自动确认手动地址是否属于所选实例。地址错误或被其他实例复用时，任务可能操作其他账号；模拟器重启后也请检查端口。管理器未提供或复用创建时间时，无法识别同名实例被替换。启停仍按所选实例执行，手动地址不能使用
      MuMu IPC。
    </n-modal>
    <n-modal
      :show="confirmShared"
      preset="dialog"
      title="改用通用连接配置？"
      positive-text="放弃这些修改并切换"
      negative-text="保留独立配置"
      @positive-click="confirmIndependentChange"
      @negative-click="confirmShared = false"
      @close="confirmShared = false"
      @update:show="(value) => (confirmShared = value)"
    >
      <p>以下设置将恢复通用值，其他本实例设置保留：</p>
      <ul>
        <li v-for="label in discardedFields" :key="label">{{ label }}</li>
      </ul>
    </n-modal>
  </div>
</template>

<style scoped>
.device-summary {
  padding: 16px 20px;
  border-radius: 12px;
  background: var(--mower-control-surface);
}
.device-summary p {
  margin: 6px 0;
}
.device-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.device-title-row strong {
  font-size: 18px;
}
.device-primary-fields {
  padding: 0 12px;
}
.field-source {
  font-size: 12px;
}
.device-editor {
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 150px);
  gap: 12px;
}
.device-editor-fields {
  flex: 1;
  min-height: 140px;
  overflow: auto;
}
.device-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  padding: 4px 2px 16px;
}
.device-editor-grid :deep(.n-input-group > .n-input) {
  flex: 1;
  min-width: 0;
}
.device-editor-grid :deep(.n-input-number) {
  width: 100%;
}
.device-editor-field-value {
  display: grid;
  gap: 8px;
  width: 100%;
}
.device-editor-wide {
  grid-column: 1 / -1;
}
.device-editor > :not(.device-editor-fields) {
  flex-shrink: 0;
}
.device-editor-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--mower-divider);
}
@media (max-width: 560px) {
  .device-editor-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
