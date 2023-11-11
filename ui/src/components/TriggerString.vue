<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])

import { ref, watch, computed } from 'vue'

const data = ref(props.data)

watch(data, () => {
  emit('update', data.value)
})

const op_data = computed(() => {
  let x = data.value.match(/op_data.operators\['(.+?)'\].current_room.startswith\('dorm'\)/)
  if (x && x[0] == data.value) {
    return {
      type: 'in_dorm',
      operator: x[1]
    }
  }
  x = data.value.match(/op_data.operators\['(.+?)'\].current_room/)
  if (x && x[0] == data.value) {
    return {
      type: 'room',
      operator: x[1]
    }
  }
  x = data.value.match(/op_data.operators\['(.+?)'\].current_mood\(\)/)
  if (x && x[0] == data.value) {
    return {
      type: 'mood',
      operator: x[1]
    }
  }
  if (data.value == 'op_data.party_time') {
    return {
      type: 'impart'
    }
  }
  return {
    type: 'custom'
  }
})

const op_type = computed(() => {
  if (op_data.value.type == 'custom') {
    return 'custom'
  } else if (op_data.value.type == 'impart') {
    return 'impart'
  } else {
    return 'op'
  }
})

const type_options = [
  { label: '干员属性', value: 'op' },
  { label: '线索交流结束时间', value: 'impart' },
  { label: '自定义', value: 'custom' }
]

const op_options = [
  { label: '心情', value: 'mood' },
  { label: '当前位置', value: 'room' },
  { label: '在宿舍', value: 'in_dorm' }
]

function set_op_type(v) {
  data.value = ''
  if (v == 'op') {
    data.value = "op_data.operators['阿米娅'].current_mood()"
  } else if (v == 'impart') {
    data.value = 'op_data.party_time'
  }
}

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

function build_data(op, type) {
  const x = `op_data.operators['${op}'].`
  if (type == 'in_dorm') {
    data.value = x + "current_room.startswith('dorm')"
  } else if (type == 'room') {
    data.value = x + 'current_room'
  } else if (type == 'mood') {
    data.value = x + 'current_mood()'
  } else {
    data.value = ''
  }
}

function update_op(op) {
  build_data(op, op_data.value.type)
}

function update_type(type) {
  build_data(op_data.value.operator, type)
}
</script>

<template>
  <n-select :default-value="op_type" :options="type_options" :on-update:value="set_op_type" />
  <n-input v-if="op_type == 'custom'" v-model:value="data" />
  <template v-if="op_type == 'op'">
    <n-select
      :default-value="op_data.operator"
      filterable
      :options="operators"
      :on-update:value="update_op"
    />
    <n-select :default-value="op_data.type" :options="op_options" :on-update:value="update_type" />
  </template>
</template>
