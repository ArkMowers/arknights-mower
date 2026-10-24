<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { managerCall } from './bridge.js'
import { editedDevicePatch, presetLabels } from '../src/utils/deviceSettings.js'

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
const groups = computed(() => [...new Set(fields.value.map((field) => field.group))])
const changes = computed(() =>
  Object.fromEntries(
    Object.entries(draft.value).filter(([key, value]) => value !== initial.value[key])
  )
)
const disabled = computed(() => pending.value || !original.value)
let disposed = false

async function load() {
  pending.value = true
  original.value = null
  error.value = ''
  try {
    const result = await managerCall(() => props.api.get_device_settings(props.idx, props.target))
    if (disposed) return
    original.value = result.values
    fields.value = result.fields
    const flat = Object.fromEntries(
      result.fields.map(({ key }) => [
        key,
        key.split('.').reduce((value, part) => value?.[part], result.values)
      ])
    )
    initial.value = { ...flat }
    draft.value = { ...flat }
  } catch (reason) {
    error.value = reason?.message || '无法读取设备配置'
  } finally {
    pending.value = false
  }
}

function edit(key, value) {
  if (disabled.value || fields.value.find((field) => field.key === key)?.read_only) return
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
    const result = await managerCall(
      () =>
        props.api.discover_device_settings(
          props.idx,
          { ...changes.value },
          props.target,
          original.value
        ),
      60000
    )
    if (!disposed) discovery.value = result
  } catch (reason) {
    error.value = reason?.message || '无法检测设备'
  } finally {
    pending.value = false
  }
}

function selectCandidate(key) {
  if (disabled.value) return
  const binding = discovery.value?.candidates?.find((candidate) => candidate.key === key)?.binding
  if (!binding) return
  for (const [field, value] of Object.entries(binding)) {
    if (Object.hasOwn(draft.value, `device.${field}`)) draft.value[`device.${field}`] = value
  }
  draft.value['device.last_serial'] = ''
}

async function browse(field) {
  if (disabled.value) return
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
  if (disabled.value || !Object.keys(changes.value).length) return
  pending.value = true
  error.value = ''
  try {
    const result = await managerCall(() =>
      props.api.update_device_settings(
        props.idx,
        { ...changes.value },
        props.target,
        original.value
      )
    )
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
      的设备连接、游戏启动与性能设置，保存后下次启动生效。公共配置中已选中的字段仍会在启动时覆盖单实例值。自定义截图命令会在主机上执行，请确认命令来源。</n-alert
    >
    <n-alert v-if="error" type="error"
      >{{ error
      }}<template #action
        ><n-button :disabled="pending" @click="load">重新加载</n-button></template
      ></n-alert
    >
    <n-skeleton v-if="!original && pending" :height="160" />
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
                v-for="field in fields.filter((item) => item.group === group && !item.read_only)"
                :key="field.key"
                :label="field.label"
                :class="{
                  'device-editor-wide':
                    ['file', 'directory'].includes(field.kind) || field.key.endsWith('.command')
                }"
              >
                <n-switch
                  v-if="field.kind === 'boolean'"
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
      <n-button
        type="primary"
        :loading="pending"
        :disabled="disabled || !Object.keys(changes).length"
        @click="save"
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
