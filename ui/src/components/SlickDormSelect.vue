<template>
  <slick-list
    v-model:list="dormitoryValue"
    axis="xy"
    appendTo=".n-select"
    :distance="5"
    class="width100"
    group="dormitory"
    :accept="!props.disabled"
    @update:list="deleteRepeat"
  >
    <n-select
      :disabled="props.disabled"
      multiple
      filterable
      :options="dormitories"
      placeholder="选择宿舍位置"
      v-model:value="dormitoryValue"
      :filter="(p, o) => o.label.includes(p)"
      :render-label="render_dorm_label"
      :render-tag="render_dorm_slick_tag"
    />
  </slick-list>
</template>

<script setup>
import { ref, h, computed } from 'vue'
import { SlickList, SlickItem } from 'vue-slicksort'
import { NTag } from 'naive-ui'

const dormitoryValue = defineModel() // 绑定 v-model:value

const props = defineProps({
  disabled: {
    type: Boolean,
    default: false
  }
})

// 生成宿舍列表 dormitory_x_y (x: 1-5, y: 2-5)
const dormitories = computed(() => {
  let options = []
  for (let x = 1; x <= 5; x++) {
    for (let y = 2; y <= 5; y++) {
      const value = `dormitory_${x}_${y}`
      options.push({ label: `宿舍 ${x}-${y}`, value })
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
