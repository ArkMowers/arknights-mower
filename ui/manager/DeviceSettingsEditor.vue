<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { managerCall } from './bridge.js'
import { editedDevicePatch, presetLabels } from '../src/utils/deviceSettings.js'
import WaitingSceneEditor from './WaitingSceneEditor.vue'

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
const policySupported = ref(false)
const originalPolicy = ref(null)
const sharedKeys = ref([])
const independentConfiguration = ref(false)
const initialIndependentConfiguration = ref(false)
const instanceFields = new Set([
  'device.instance_id',
  'device.instance_name',
  'device.game_package'
])
const derivedIdentityFields = new Set(['device.instance_uuid', 'device.topology_fingerprint'])
const templateFields = [
  'device.preset_id',
  'device.installation_path',
  'device.manager_path',
  'device.config_path'
]
const sharedConfiguration = computed(() => policySupported.value && !independentConfiguration.value)
const editableField = (key) => !sharedConfiguration.value || instanceFields.has(key)
const patchField = (key) => editableField(key) || derivedIdentityFields.has(key)
const visibleFields = computed(() =>
  fields.value.filter((field) => !field.read_only && editableField(field.key))
)
const groups = computed(() => [...new Set(visibleFields.value.map((field) => field.group))])
const policyChanged = computed(
  () =>
    policySupported.value &&
    independentConfiguration.value !== initialIndependentConfiguration.value
)
const changes = computed(() =>
  Object.fromEntries(
    Object.entries(draft.value).filter(
      ([key, value]) =>
        JSON.stringify(value) !== JSON.stringify(initial.value[key]) && patchField(key)
    )
  )
)
const disabled = computed(() => pending.value || !original.value)
const hasChanges = computed(() => policyChanged.value || Object.keys(changes.value).length > 0)
let disposed = false

async function load() {
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
  } catch (reason) {
    error.value = reason?.message || '无法读取设备配置'
  } finally {
    pending.value = false
  }
}

function edit(key, value) {
  const field = fields.value.find((item) => item.key === key)
  if (!field || disabled.value || !editableField(key) || field.read_only) return
  discovery.value = null
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
}

function setIndependent(value) {
  if (disabled.value || !policySupported.value) return
  independentConfiguration.value = value === true
  discovery.value = null
  if (!independentConfiguration.value) {
    for (const field of fields.value) {
      if (!instanceFields.has(field.key))
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

async function detect() {
  if (disabled.value) return
  pending.value = true
  error.value = ''
  discovery.value = null
  try {
    const args = [props.idx, { ...changes.value }, props.target, original.value]
    if (policySupported.value)
      args.push({
        independent_configuration: independentConfiguration.value,
        original_policy: originalPolicy.value
      })
    const result = await managerCall(() => props.api.discover_device_settings(...args), 60000)
    if (!disposed) discovery.value = result
  } catch (reason) {
    error.value = reason?.message || '无法检测设备'
  } finally {
    pending.value = false
  }
}

function selectCandidate(key) {
  if (disabled.value) return
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
  if (
    Object.hasOwn(binding, 'instance_id') &&
    binding.instance_id !== draft.value['device.instance_id']
  )
    draft.value['device.instance_name'] = ''
  draft.value['device.instance_uuid'] = ''
  draft.value['device.topology_fingerprint'] = ''
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
  pending.value = true
  error.value = ''
  try {
    const args = [props.idx, { ...changes.value }, props.target, original.value]
    if (policySupported.value)
      args.push({
        independent_configuration: independentConfiguration.value,
        original_policy: originalPolicy.value
      })
    const result = await managerCall(() => props.api.update_device_settings(...args))
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
    <n-alert type="info" :show-icon="false"
      >修改
      {{ target.name }}
      的模拟器选择与连接配置，保存后下次启动生效。自定义截图命令会在主机上执行，请确认命令来源。
    </n-alert>
    <n-alert v-if="error" type="error"
      >{{ error
      }}<template #action
        ><n-button :disabled="pending" @click="load">重新加载</n-button></template
      ></n-alert
    >
    <n-skeleton v-if="!original && pending" :height="160" />
    <n-form-item v-if="original && policySupported" label="独立配置" :show-feedback="false">
      <n-switch
        :value="independentConfiguration"
        :disabled="disabled"
        aria-label="独立配置"
        @update:value="setIndependent"
      />
    </n-form-item>
    <n-alert
      v-if="original && policySupported && !independentConfiguration"
      type="info"
      :show-icon="false"
    >
      此处仅设置模拟器实例编号、实例名称和游戏包名；模拟器预设、路径、连接、截图、启动、性能和页面等待参数统一使用通用设置。需要手动指定
      ADB
      地址或单独设置页面等待参数时请开启独立配置。关闭独立配置会放弃其他参数的未保存修改，保存后下次启动生效。
    </n-alert>
    <n-text v-else-if="original && policySupported" depth="3">
      连接、截图、启动、性能和页面等待参数仅应用于此实例，下次启动生效；任务设置仍由此实例单独保存。
    </n-text>
    <n-space v-if="original" vertical>
      <n-button :disabled="disabled" :loading="pending" @click="detect">检测可用实例</n-button>
      <n-select
        v-if="discovery?.candidates?.length"
        placeholder="选择明确的模拟器实例"
        :disabled="disabled"
        :options="
          discovery.candidates.map((item) => ({
            value: item.key,
            label: [presetLabels[item.preset_id], item.instance_name, item.instance_id]
              .filter(Boolean)
              .join(' · ')
          }))
        "
        @update:value="selectCandidate"
      />
      <n-text v-if="discovery?.candidates?.length" depth="3"
        >选择后仍需保存；检测与选择不会改写配置或启动模拟器。</n-text
      >
      <n-alert v-if="discovery?.error" type="warning">{{ discovery.error.message }}</n-alert>
      <n-text v-else-if="discovery && !discovery.candidates?.length">{{
        discovery.ok ? '已完成当前设备检测。' : '未找到可选实例，请检查模拟器安装路径。'
      }}</n-text>
    </n-space>
    <div v-if="original" class="device-editor-fields">
      <n-collapse :default-expanded-names="['模拟器与设备']">
        <n-collapse-item v-for="group in groups" :key="group" :title="group" :name="group">
          <n-form label-placement="top" :show-feedback="false">
            <div class="device-editor-grid">
              <n-form-item
                v-for="field in visibleFields.filter((item) => item.group === group)"
                :key="field.key"
                :label="field.label"
                :class="{
                  'device-editor-wide':
                    ['file', 'directory', 'waiting_scene'].includes(field.kind) ||
                    field.key.endsWith('.command')
                }"
              >
                <WaitingSceneEditor
                  v-if="field.kind === 'waiting_scene'"
                  :field="field"
                  :value="draft[field.key]"
                  :disabled="disabled"
                  @update:value="(value) => edit(field.key, value)"
                />
                <n-switch
                  v-else-if="field.kind === 'boolean'"
                  :value="draft[field.key]"
                  :disabled="disabled"
                  :aria-label="field.label"
                  @update:value="(value) => edit(field.key, value)"
                />
                <n-select
                  v-else-if="field.kind === 'select'"
                  :value="draft[field.key]"
                  :options="options(field)"
                  :consistent-menu-width="false"
                  :disabled="disabled"
                  :aria-label="field.label"
                  @update:value="(value) => edit(field.key, value)"
                />
                <n-input-number
                  v-else-if="['integer', 'number'].includes(field.kind)"
                  :value="draft[field.key]"
                  :min="field.min ?? 0"
                  :max="field.max"
                  :precision="field.kind === 'integer' ? 0 : undefined"
                  :disabled="disabled"
                  :aria-label="field.label"
                  @update:value="(value) => edit(field.key, value)"
                />
                <n-input-group v-else>
                  <n-input
                    :value="draft[field.key]"
                    :type="field.key.endsWith('.command') ? 'textarea' : 'text'"
                    :autosize="{ minRows: 1, maxRows: 6 }"
                    placeholder="未设置"
                    :disabled="disabled"
                    :aria-label="field.label"
                    @update:value="(value) => edit(field.key, value)"
                  />
                  <n-button
                    v-if="['file', 'directory'].includes(field.kind)"
                    :disabled="disabled"
                    @click="browse(field)"
                    >选择</n-button
                  >
                </n-input-group>
              </n-form-item>
            </div>
          </n-form>
        </n-collapse-item>
      </n-collapse>
    </div>
    <div class="device-editor-actions">
      <n-button type="primary" :loading="pending" :disabled="disabled || !hasChanges" @click="save"
        >保存连接与启动配置</n-button
      >
    </div>
  </div>
</template>

<style scoped>
.device-editor {
  display: grid;
  gap: 16px;
}
.device-editor-fields {
  max-height: calc(100dvh - 340px);
  min-height: 160px;
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
.device-editor-wide {
  grid-column: 1 / -1;
}
.device-editor-actions {
  display: flex;
  justify-content: flex-end;
}
@media (max-width: 560px) {
  .device-editor-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
