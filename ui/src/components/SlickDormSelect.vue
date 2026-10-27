<template>
  <slick-list
    v-model:list="dormitoryValue"
    axis="xy"
    append-to="body"
    :distance="5"
    :transition-duration="dragAnimation"
    :dragged-settling-duration="dragAnimation"
    helper-class="mower-drag-fallback"
    class="width100"
    group="dormitory"
    :accept="!props.disabled"
    @update:list="deleteRepeat"
    @sort-start="({ node }) => normalizeSortablePreview({ item: node })"
    @dragstart.prevent
  >
    <n-select
      :disabled="props.disabled"
      multiple
      filterable
      :options="dormitories"
      :placeholder="t('plans.chooseDormPosition')"
      v-model:value="dormitoryValue"
      :filter="(p, o) => o.label.includes(p)"
      :render-label="render_dorm_label"
      :render-tag="render_dorm_slick_tag"
    />
  </slick-list>
</template>

<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
import { h, computed } from 'vue'
import { SlickList, SlickItem } from 'vue-slicksort'
import { NTag } from 'naive-ui'
import '@/styles/drag.css'
import { normalizeSortablePreview } from '@/utils/sortablePreview'

const dragAnimation =
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    ? 0
    : 180
const dormitoryValue = defineModel() // 绑定 v-model:value

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  },
  includeLow: {
    type: Boolean,
    default: false
  },
  roomOnly: {
    type: Boolean,
    default: false
  }
})

// 生成宿舍列表 dormitory_x_y (x: 1-4, y: 2-5)
const dormitories = computed(() => {
  let options = []
  for (let x = 1; x <= 4; x++) {
    if (props.roomOnly) {
      options.push({ label: t('plans.dormNumber', { number: x }), value: `dormitory_${x}` })
      if (props.includeLow) {
        options.push({
          label: t('plans.dormLowNumber', { number: x }),
          value: `dormitory_${x}_low`
        })
      }
      continue
    }
    for (let y = 1; y <= 4; y++) {
      const value = `dormitory_${x}_${y}`
      options.push({ label: t('plans.dormPosition', { room: x, position: y + 1 }), value })
    }
  }
  return options
})

// 渲染宿舍标签
const render_dorm_label = (option) => {
  return h('div', {}, option.label)
}

// 渲染拖拽排序的标签
const render_dorm_slick_tag = ({ option, handleClose }) => {
  return h(
    SlickItem,
    {
      key: option.value,
      index: dormitoryValue.value.findIndex((value) => value == option.value),
      disabled: props.disabled,
      class: 'mower-drag-tag',
      'aria-disabled': props.disabled,
      style: 'z-index: 999; display: inline;'
    },
    () =>
      h(
        NTag,
        {
          closable: !props.disabled,
          onClose: () => handleClose()
        },
        { default: () => option.label }
      )
  )
}

// 去除重复选择
const deleteRepeat = function (dormList) {
  for (let i = 0; i < dormList.length; i++) {
    for (let j = i + 1; j < dormList.length; j++) {
      if (dormList[i] === dormList[j]) {
        dormList.splice(j--, 1)
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
