<script setup>
const props = defineProps({
  field: { type: Object, required: true },
  value: { type: Object, required: true },
  disabled: Boolean
})
const emit = defineEmits(['update:value'])

function edit(scene, index, value) {
  if (
    props.disabled ||
    props.field.read_only ||
    !Object.hasOwn(props.value, scene) ||
    ![0, 1].includes(index) ||
    !Number.isInteger(value)
  )
    return
  emit('update:value', {
    ...props.value,
    [scene]: props.value[scene].map((previous, position) => (position === index ? value : previous))
  })
}
</script>

<template>
  <div class="waiting-scene-scroll" tabindex="0" role="region" :aria-label="field.label">
    <n-table size="small">
      <thead>
        <tr>
          <th>场景</th>
          <th>截图间隔（秒）</th>
          <th>等待次数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="[scene, label] in field.scenes" :key="scene">
          <td>{{ label }}</td>
          <td v-for="index in [0, 1]" :key="index">
            <n-input-number
              :value="value[scene]?.[index]"
              :precision="0"
              :show-button="false"
              :disabled="disabled || field.read_only"
              :input-props="{
                'aria-label': `${label}${index === 0 ? '截图间隔（秒）' : '等待次数'}`
              }"
              @update:value="(next) => edit(scene, index, next)"
            />
          </td>
        </tr>
      </tbody>
    </n-table>
  </div>
</template>

<style scoped>
.waiting-scene-scroll {
  width: 100%;
  overflow-x: auto;
}
.waiting-scene-scroll :deep(table) {
  min-width: 540px;
}
.waiting-scene-scroll :deep(.n-input-number) {
  min-width: 120px;
}
</style>
