<script setup>
import { ref, useAttrs } from 'vue'
import { NInputNumber as NaiveInputNumber } from 'naive-ui'

defineOptions({ inheritAttrs: false })
const attrs = useAttrs()
const control = ref(null)
let pointerType = 'mouse'

function rememberPointer(event) {
  pointerType = event.pointerType
}

function preventTouchButtonFocus(event) {
  // Naive UI focuses the input from mousedown, including on its step buttons.
  // Keep click for arithmetic; preserve mouse long press and keyboard behavior.
  const button = event.target.closest?.('button')
  if (
    (pointerType === 'touch' || pointerType === 'pen') &&
    attrs.showButton !== false &&
    attrs['show-button'] !== false &&
    button?.parentElement?.matches('.n-input__prefix, .n-input__suffix') &&
    !button.closest('.n-input-number-prefix, .n-input-number-suffix')
  ) {
    event.preventDefault()
    event.stopPropagation()
  }
}

defineExpose({
  focus: () => control.value?.focus(),
  blur: () => control.value?.blur(),
  select: () => control.value?.select()
})
</script>

<template>
  <NaiveInputNumber
    ref="control"
    v-bind="attrs"
    :input-props="{ inputmode: 'decimal', ...(attrs.inputProps || attrs['input-props']) }"
    @pointerdown.capture="rememberPointer"
    @mousedown.capture="preventTouchButtonFocus"
  >
    <template v-for="(_, name) in $slots" #[name]="slotProps">
      <slot :name="name" v-bind="slotProps || {}" />
    </template>
  </NaiveInputNumber>
</template>
