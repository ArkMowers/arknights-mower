<script setup>
import FolderIcon from '@vicons/ionicons5/es/FolderOpenOutline'
import { computed, ref } from 'vue'
import HelpText from '../src/components/HelpText.vue'
import WaitingSceneEditor from './WaitingSceneEditor.vue'
import { connectionFields, idleAction, idleActionPatch, idleOptions } from './connectionSettings.js'
import { editDeviceDraft, presetLabels } from '../src/utils/deviceSettings'

const props = defineProps({
  values: { type: Object, required: true },
  fields: { type: Array, required: true },
  disabled: Boolean
})
const emit = defineEmits(['update:values', 'browse'])
const connectionSections = [
  '模拟器模板',
  '程序位置',
  '连接方式',
  '性能',
  '连接恢复',
  '游戏启动与空闲',
  '运行参数',
  '实例启动'
]
const groupName = (field) => (connectionSections.includes(field.group) ? '连接与启动' : field.group)
const groups = computed(() => [...new Set(visibleFields.value.map(groupName))])
const search = ref('')
const visibleFields = computed(() =>
  connectionFields(props.fields, props.values).filter((field) =>
    `${groupName(field)} ${field.group} ${field.label} ${field.searchKeywords || ''} ${field.kind === 'waiting_scene' ? (field.scenes ?? []).flat().join(' ') + ' 截图间隔 等待次数' : ''}`
      .toLowerCase()
      .includes(search.value.trim().toLowerCase())
  )
)
const backendKeys = ['device.screenshot_backend', 'device.touch_backend']
const enabled = (key) =>
  props.fields.some((field) => field.key === key && field.shared_connection) ||
  Object.hasOwn(props.values, key)

function sections(group) {
  const fields = visibleFields.value.filter((field) => groupName(field) === group)
  const names = group === '连接与启动' ? connectionSections : [group]
  return names
    .map((name) => ({ name, fields: fields.filter((field) => field.group === name) }))
    .filter((section) => section.fields.length)
}

function options(field) {
  return field.options.map(([value, label]) => ({
    value,
    label:
      field.key === 'device.preset_id'
        ? `${presetLabels[value] || label} (${value.split('.')[0]})`
        : label
  }))
}

function toggle(field, checked) {
  if (props.disabled || field.read_only || field.shared_connection) return
  const next = { ...props.values }
  for (const key of backendKeys.includes(field.key) ? backendKeys : [field.key]) {
    if (checked)
      next[key] = JSON.parse(JSON.stringify(props.fields.find((item) => item.key === key).default))
    else delete next[key]
  }
  emit('update:values', next)
}

function change(field, value) {
  if (props.disabled || field.read_only || !enabled(field.key)) return
  const next = {
    ...props.values,
    ...(field.kind === 'idle_action' ? idleActionPatch(value) : { [field.key]: value })
  }
  if (backendKeys.includes(field.key)) {
    const device = Object.fromEntries(
      backendKeys.map((key) => [key.split('.')[1], props.values[key]])
    )
    const updated = editDeviceDraft(device, field.key.split('.')[1], value)
    for (const key of backendKeys) next[key] = updated[key.split('.')[1]]
  }
  emit('update:values', next)
}
</script>

<template>
  <details class="common-settings" open>
    <summary>
      <span>通用设置</span>
      <n-tag size="small">{{ Object.keys(values).length }} 项</n-tag>
      <span class="effective-time">实例配置下次启动生效</span>
    </summary>
    <p class="common-description">
      各实例可在“连接与启动”中启用独立配置，单独设置连接、性能和运行参数；未启用时共用此处参数，仅单独设置实例编号、实例名称和游戏包名。MAA
      安装目录、截图保存、启动方式和实例页面打开方式可逐项使用本实例值，本实例值优先于通用值。修改通用设置不会改动已保存的本实例值。实例配置在下次受管理启动时生效；实例页面打开方式在保存后用于“打开实例页面”按钮。
    </p>
    <n-input
      v-model:value="search"
      clearable
      placeholder="搜索通用设置"
      aria-label="搜索通用设置"
    />
    <p v-if="!visibleFields.length" class="common-description">没有匹配的配置项</p>
    <details
      v-for="group in groups"
      :key="group"
      class="common-group"
      :open="!!search || group === '连接与启动'"
    >
      <summary>
        {{ group
        }}<span class="group-count"
          >{{
            fields.filter((field) => groupName(field) === group && enabled(field.key)).length
          }}
          项统一配置</span
        >
      </summary>
      <div v-for="section in sections(group)" :key="section.name" class="common-section">
        <h3 v-if="group === '连接与启动'" class="common-section-title">{{ section.name }}</h3>
        <div class="common-fields">
          <div
            v-for="field in section.fields"
            :key="field.key"
            class="common-field"
            :class="{ 'common-field-wide': field.kind === 'waiting_scene' }"
          >
            <div class="field-label">
              <span v-if="field.shared_connection">{{ field.label }}</span>
              <n-checkbox
                v-else
                :checked="enabled(field.key)"
                :disabled="disabled || field.read_only || field.shared_connection"
                :aria-label="`统一设置${field.label}`"
                @update:checked="(checked) => toggle(field, checked)"
                >{{ field.label }}</n-checkbox
              >
              <help-text v-if="field.help" :label="`${field.label}说明`">{{
                field.help
              }}</help-text>
            </div>
            <div class="field-control">
              <n-select
                v-if="field.kind === 'idle_action'"
                :value="idleAction(values)"
                :options="idleOptions(values)"
                :consistent-menu-width="false"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :aria-label="field.label"
                @update:value="(value) => change(field, value)"
              />
              <WaitingSceneEditor
                v-else-if="field.kind === 'waiting_scene'"
                :field="field"
                :value="values[field.key] ?? field.default"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                @update:value="(value) => change(field, value)"
              />
              <n-input-number
                v-else-if="['integer', 'number'].includes(field.kind)"
                :value="values[field.key] ?? field.default"
                :min="field.min"
                :max="field.max"
                :precision="field.kind === 'integer' ? 0 : undefined"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :aria-label="field.label"
                @update:value="(value) => change(field, value)"
              />
              <n-switch
                v-else-if="field.kind === 'boolean'"
                :value="values[field.key] ?? field.default"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :aria-label="field.label"
                @update:value="(value) => change(field, value)"
              />
              <n-select
                v-else-if="field.kind === 'select'"
                :value="values[field.key] ?? field.default"
                :options="options(field)"
                :consistent-menu-width="false"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :aria-label="field.label"
                @update:value="(value) => change(field, value)"
              />
              <n-input
                v-else
                :value="values[field.key] ?? field.default"
                :type="field.kind === 'password' ? 'password' : 'text'"
                show-password-on="click"
                placeholder="未设置"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :aria-label="field.label"
                @update:value="(value) => change(field, value)"
              />
              <n-button
                v-if="['directory', 'file'].includes(field.kind)"
                :disabled="disabled || field.read_only || !enabled(field.key)"
                :title="`选择${field.label}`"
                :aria-label="`选择${field.label}`"
                @click="emit('browse', field.key)"
                ><template #icon
                  ><n-icon><folder-icon /></n-icon></template
              ></n-button>
            </div>
          </div>
        </div>
      </div>
    </details>
  </details>
</template>

<style scoped>
.common-settings {
  border-bottom: 1px solid #e5e7eb;
  margin-bottom: 16px;
  padding-bottom: 12px;
}
summary {
  cursor: pointer;
  padding: 10px 0;
  min-height: 24px;
}
.common-settings > summary {
  font-weight: 600;
}
summary > * {
  margin-right: 8px;
}
.effective-time {
  font-size: 12px;
  font-weight: 400;
  color: #666;
}
.common-description {
  color: #666;
  line-height: 1.65;
}
.group-count {
  float: right;
  color: #777;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.common-group {
  border-top: 1px solid #eee;
}
.common-section-title {
  margin: 12px 0 4px;
  font-size: 13px;
  font-weight: 500;
  color: #666;
}
.common-section + .common-section {
  border-top: 1px solid #eee;
}
.common-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 20px;
  padding: 8px 0 16px;
}
.common-field {
  min-width: 0;
}
.common-field-wide {
  grid-column: 1 / -1;
}
.field-label {
  display: flex;
  align-items: center;
  gap: 6px;
}
.field-control {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  margin-top: 6px;
}
.field-control > :first-child:not(.n-switch) {
  flex: 1;
  min-width: 0;
}
@media (max-width: 640px) {
  .common-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
