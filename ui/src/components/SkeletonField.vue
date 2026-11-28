<script setup>
import { h } from 'vue'
import { NInput, NSelect } from 'naive-ui'

// 输入框和选择框读取中的占位：画出与读完后相同的控件框（边框、高度、选择框的下拉箭头），值的
// 位置是一个文字占位块。控件不可操作、不可聚焦，读完后由真实控件在原处替换。页面给的 class
// 和 style 落在控件的根元素上，与真实控件共用同样的布局规则。
const props = defineProps({
  kind: { type: String, default: 'input' },
  // 值占位块的宽度。
  width: { type: String, default: '10em' },
  size: { type: String, default: undefined },
  // 读完后控件处于禁用状态时为 true，占位也画成禁用的外框。
  disabled: Boolean
})
const OPTIONS = [{ label: '', value: 'placeholder' }]
const renderValue = () =>
  h('span', { class: 'skeleton-bone skeleton-text', style: { '--skeleton-w': props.width } })
</script>

<template>
  <n-select
    v-if="kind === 'select'"
    value="placeholder"
    :options="OPTIONS"
    :size="size"
    :render-label="renderValue"
    :disabled="disabled"
    inert
  />
  <n-input v-else value="" placeholder="" readonly :size="size" :disabled="disabled" inert>
    <template #prefix>
      <span class="skeleton-bone skeleton-text" :style="{ '--skeleton-w': width }" />
    </template>
  </n-input>
</template>
