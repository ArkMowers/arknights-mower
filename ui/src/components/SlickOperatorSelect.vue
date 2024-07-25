<template>
  <slick-list
    v-model:list="operatorValue"
    axis="xy"
    appendTo=".n-select"
    distance="5"
    class="width100"
    group="operator"
    :accept="!props.disabled"
    @update:list="deleteRepeat"
  >
    <n-select
      :disabled="props.disabled"
      multiple
      filterable
      :options="operators"
      :placeholder="props.select_placeholder"
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
  },
  select_placeholder: {
    type: String,
    default: ''
  }
})
const render_op_slick_tag = ({ option, handleClose }) => {
  return h(
    SlickItem,
    {
      key: option.value,
      index: operatorValue.value.findIndex((value) => value == option.value),
      disabled: props.disabled,
      style: 'z-index: 999;display: inline;'
    },
    render_op_tag({ option, handleClose })
  )
}

const deleteRepeat = function (operatorList) {
  for (var i = 0; i < operatorList.length; i++) {
    for (var j = i + 1; j < operatorList.length; j++) {
      if (operatorList[i] == operatorList[j]) {
        operatorList.splice(j--, 1)
      }
    }
  }
}
</script>

<style scoped>
.width100 {
  width: 100%;
}
</style>
