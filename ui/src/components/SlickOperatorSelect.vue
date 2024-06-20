<template>
  <slick-list
    v-model:list="operatorValue"
    axis="x"
    appendTo=".n-select"
    distance="5"
    class="width100"
  >
    <n-select
      :disabled="props.disabled"
      multiple
      filterable
      :options="operators"
      v-model:value="operatorValue"
      :filter="(p, o) => match(o.label, p)"
      :render-label="render_op_label"
      :render-tag="render_op_slick_tag"
    />
  </slick-list>
</template>

<script setup>
import { match } from 'pinyin-pro'
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { render_op_label, render_op_tag } from '@/utils/op_select'
import { h } from 'vue'
import { SlickList, SlickItem } from 'vue-slicksort'

const { operators } = storeToRefs(usePlanStore())

const operatorValue = defineModel()
const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  }
})
const render_op_slick_tag = ({ option, handleClose }) => {
  return h(
    SlickItem,
    {
      key: option.value,
      index: operatorValue.value.findIndex((value) => value == option.value),
      disabled: props.disabled,
      style: 'z-index:999'
    },
    render_op_tag({ option, handleClose })
  )
}
</script>

<style scoped>
.width100 {
  width: 100%;
}
</style>
