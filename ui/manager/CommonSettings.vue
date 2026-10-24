<script setup>
import { FolderOpenOutline as FolderIcon } from '@vicons/ionicons5'
import { computed, ref } from 'vue'
import HelpText from '../src/components/HelpText.vue'
import { editDeviceDraft } from '../src/utils/deviceSettings'

const props = defineProps({
  values: { type: Object, required: true },
  fields: { type: Array, required: true },
  disabled: Boolean
})
const emit = defineEmits(['update:values', 'browse'])
const groups = computed(() => [...new Set(visibleFields.value.map((field) => field.group))])
const search = ref('')
const visibleFields = computed(() =>
  props.fields.filter((field) =>
    `${field.group} ${field.label}`.toLowerCase().includes(search.value.trim().toLowerCase())
  )
)
const backendKeys = ['device.screenshot_backend', 'device.touch_backend']
const enabled = (key) => Object.hasOwn(props.values, key)

function toggle(field, checked) {
  const next = { ...props.values }
  for (const key of backendKeys.includes(field.key) ? backendKeys : [field.key]) {
    if (checked) next[key] = props.fields.find((item) => item.key === key).default
    else delete next[key]
  }
  emit('update:values', next)
}

function change(field, value) {
  const next = { ...props.values, [field.key]: value }
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
      <span>公共配置</span>
      <n-tag size="small">{{ Object.keys(values).length }} 项</n-tag>
      <span class="effective-time">下次启动生效</span>
    </summary>
    <p class="common-description">勾选后统一覆盖，下次受管理启动生效；未勾选的项目保留实例设置。</p>
    <n-input
      v-model:value="search"
      clearable
      placeholder="搜索公共配置"
      aria-label="搜索公共配置"
    />
    <p v-if="!visibleFields.length" class="common-description">没有匹配的配置项</p>
    <details
      v-for="group in groups"
      :key="group"
      class="common-group"
      :open="!!search || group === '实例启动'"
    >
      <summary>
        {{ group
        }}<span class="group-count"
          >{{
            fields.filter((field) => field.group === group && enabled(field.key)).length
          }}
          项已启用</span
        >
      </summary>
      <div class="common-fields">
        <div
          v-for="field in visibleFields.filter((item) => item.group === group)"
          :key="field.key"
          class="common-field"
        >
          <div class="field-label">
            <n-checkbox
              :checked="enabled(field.key)"
              :disabled="disabled"
              :aria-label="`统一设置${field.label}`"
              @update:checked="(checked) => toggle(field, checked)"
              >{{ field.label }}</n-checkbox
            >
            <help-text v-if="field.help" :label="`${field.label}说明`">{{ field.help }}</help-text>
          </div>
          <div class="field-control">
            <n-input-number
              v-if="['integer', 'number'].includes(field.kind)"
              :value="values[field.key] ?? field.default"
              :min="field.min"
              :max="field.max"
              :precision="field.kind === 'integer' ? 0 : undefined"
              :disabled="disabled || !enabled(field.key)"
              :aria-label="field.label"
              @update:value="(value) => change(field, value)"
            />
            <n-switch
              v-else-if="field.kind === 'boolean'"
              :value="values[field.key] ?? field.default"
              :disabled="disabled || !enabled(field.key)"
              :aria-label="field.label"
              @update:value="(value) => change(field, value)"
            />
            <n-select
              v-else-if="field.kind === 'select'"
              :value="values[field.key] ?? field.default"
              :options="field.options.map(([value, label]) => ({ value, label }))"
              :consistent-menu-width="false"
              :disabled="disabled || !enabled(field.key)"
              :aria-label="field.label"
              @update:value="(value) => change(field, value)"
            />
            <n-input
              v-else
              :value="values[field.key] ?? field.default"
              :type="field.kind === 'password' ? 'password' : 'text'"
              show-password-on="click"
              placeholder="未设置"
              :disabled="disabled || !enabled(field.key)"
              :aria-label="field.label"
              @update:value="(value) => change(field, value)"
            />
            <n-button
              v-if="['directory', 'file'].includes(field.kind)"
              :disabled="disabled || !enabled(field.key)"
              :title="`选择${field.label}`"
              :aria-label="`选择${field.label}`"
              @click="emit('browse', field.key)"
              ><template #icon
                ><n-icon><folder-icon /></n-icon></template
            ></n-button>
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
.common-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px 20px;
  padding: 8px 0 16px;
}
.common-field {
  min-width: 0;
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
