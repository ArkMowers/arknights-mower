<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])

import { ref, watch, computed, onMounted, h } from 'vue'
import { NAvatar } from 'naive-ui'
import {
  inventory_expression,
  inventory_options,
  inventory_options_with_counts,
  parse_inventory_expression
} from '@/utils/trigger_inventory'

const data = ref(props.data)

watch(data, () => {
  emit('update', data.value)
})

const op_data = computed(() => {
  let x = data.value.match(/op_data.operators\['(.+?)'\].is_resting\(\)/)
  if (x && x[0] == data.value) {
    return {
      type: 'in_dorm',
      operator: x[1]
    }
  }
  x = data.value.match(/op_data.operators\['(.+?)'\].is_working\(\)/)
  if (x && x[0] == data.value) {
    return {
      type: 'working',
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
  const inventory = parse_inventory_expression(data.value)
  if (inventory) {
    return {
      type: 'inventory',
      item: inventory
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
  } else if (op_data.value.type == 'inventory') {
    return 'inventory'
  } else {
    return 'op'
  }
})

const type_options = [
  { label: '干员属性', value: 'op' },
  { label: '仓库资源', value: 'inventory' },
  { label: '线索交流结束时间', value: 'impart' },
  { label: '自定义', value: 'custom' }
]

const op_options = [
  { label: '心情', value: 'mood' },
  { label: '当前位置', value: 'room' },
  { label: '在工作', value: 'working' },
  { label: '在休息', value: 'in_dorm' }
]

function set_op_type(v) {
  data.value = ''
  if (v == 'op') {
    data.value = "op_data.operators['阿米娅'].current_mood()"
  } else if (v == 'impart') {
    data.value = 'op_data.party_time'
  } else if (v == 'inventory') {
    data.value = inventory_expression(inventory_options[0].value)
  }
}

function update_inventory(item) {
  data.value = inventory_expression(item)
}

function render_inventory_option(option) {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        width: '100%',
        minWidth: 0
      }
    },
    [
      h(NAvatar, {
        src: `/depot/${option.icon}.webp`,
        round: true,
        size: 'small',
        objectFit: 'contain'
      }),
      h('span', { style: { whiteSpace: 'nowrap' } }, option.name),
      h(
        'span',
        {
          style: {
            marginLeft: 'auto',
            opacity: 0.65,
            whiteSpace: 'nowrap',
            fontVariantNumeric: 'tabular-nums'
          }
        },
        `库存 ${option.inventoryText}`
      )
    ]
  )
}

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { usedepotStore } from '@/stores/depot'
const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)
const depot_store = usedepotStore()
const { inventory, inventoryLoaded, inventoryLoadError } = storeToRefs(depot_store)

const inventory_select_options = computed(() =>
  inventory_options_with_counts(
    inventory.value,
    inventoryLoadError.value ? 'error' : inventoryLoaded.value ? 'loaded' : 'loading'
  )
)

onMounted(() => {
  depot_store.loadInventory().catch(() => {})
})

function build_data(op, type) {
  const x = `op_data.operators['${op}'].`
  if (type == 'in_dorm') {
    data.value = x + 'is_resting()'
  } else if (type == 'working') {
    data.value = x + 'is_working()'
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

import { pinyin_match } from '@/utils/common'
import { render_op_label } from '@/utils/op_select'

const custom_tips = [
  'True',
  'False',
  'None',
  'central',
  'meeting',
  'room_1_1',
  'room_1_2',
  'room_1_3',
  'room_2_1',
  'room_2_2',
  'room_2_3',
  'room_3_1',
  'room_3_2',
  'room_3_3',
  'contact',
  'factory',
  'train',
  'dormitory_1',
  'dormitory_2',
  'dormitory_3',
  'dormitory_4'
]
</script>

<template>
  <n-select
    :default-value="op_type"
    :options="type_options"
    :on-update:value="set_op_type"
    style="min-width: 180px"
  />
  <n-auto-complete
    v-if="op_type == 'custom'"
    v-model:value="data"
    :options="custom_tips"
    blur-after-select
    :get-show="() => true"
  />
  <template v-if="op_type == 'op'">
    <n-select
      :default-value="op_data.operator"
      filterable
      :options="operators"
      :on-update:value="update_op"
      :filter="(p, o) => pinyin_match(o.label, p)"
      :render-label="render_op_label"
      style="min-width: 220px"
    />
    <n-select
      :default-value="op_data.type"
      :options="op_options"
      :on-update:value="update_type"
      style="min-width: 120px"
    />
  </template>
  <n-select
    v-if="op_type == 'inventory'"
    :default-value="op_data.item"
    :options="inventory_select_options"
    :on-update:value="update_inventory"
    :render-label="render_inventory_option"
    style="min-width: 320px"
  />
</template>
