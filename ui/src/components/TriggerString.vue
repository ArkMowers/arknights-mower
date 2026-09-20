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
import {
  facility_expression,
  facility_product_count_expression,
  facility_product_type_count_expression,
  parse_facility_expression,
  parse_facility_product_count_expression,
  summarize_facility_products
} from '@/utils/trigger_facility'
import { trigger_facility_type_options } from '@/utils/base_facilities'
import { facility_product_labels, facility_product_options } from '@/utils/base_products'

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
  const facility = parse_facility_expression(data.value)
  if (facility) {
    return {
      type: 'facility',
      room: facility.room,
      status: facility.status
    }
  }
  const productCount = parse_facility_product_count_expression(data.value)
  if (productCount) {
    return {
      type: 'facility_stat',
      status: 'product_count',
      product: productCount
    }
  }
  if (data.value == facility_product_type_count_expression) {
    return {
      type: 'facility_stat',
      status: 'product_type_count'
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
  } else if (op_data.value.type == 'facility') {
    return 'facility'
  } else if (op_data.value.type == 'facility_stat') {
    return 'facility_stat'
  } else {
    return 'op'
  }
})

const type_options = [
  { label: '干员属性', value: 'op' },
  { label: '仓库资源', value: 'inventory' },
  { label: '设施状态', value: 'facility' },
  { label: '生产设施统计', value: 'facility_stat' },
  { label: '线索交流结束时间', value: 'impart' },
  { label: '常量/自定义', value: 'custom' }
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
  } else if (v == 'facility') {
    const room = facility_select_options.value[0]?.value || 'room_1_1'
    const status = ['制造站', '贸易站'].includes(plan.value[room]?.name)
      ? 'product'
      : 'operator_count'
    data.value = facility_expression(room, status)
  } else if (v == 'facility_stat') {
    data.value = facility_product_count_expression(facility_product_options[0].value)
  }
}

function update_inventory(item) {
  data.value = inventory_expression(item)
}

function update_facility(room) {
  const supportsProduct = ['制造站', '贸易站'].includes(plan.value[room]?.name)
  const supportsMastery = room == 'train'
  const status =
    (op_data.value.status == 'product' && !supportsProduct) ||
    (['mastery_plan', 'training'].includes(op_data.value.status) && !supportsMastery)
      ? 'operator_count'
      : op_data.value.status
  data.value = facility_expression(room, status)
}

function update_facility_status(status) {
  data.value = facility_expression(op_data.value.room, status)
}

function update_facility_stat(status) {
  data.value =
    status == 'product_type_count'
      ? facility_product_type_count_expression
      : facility_product_count_expression(facility_product_options[0].value)
}

function update_facility_stat_product(product) {
  data.value = facility_product_count_expression(product)
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
import { useFacilityStore } from '@/stores/facility'
import { useMasteryStore } from '@/stores/mastery'
const plan_store = usePlanStore()
const { operators, plan } = storeToRefs(plan_store)
const { left_side_facility } = plan_store
const depot_store = usedepotStore()
const { inventory, inventoryLoaded, inventoryLoadError } = storeToRefs(depot_store)
const facility_store = useFacilityStore()
const {
  states: facility_states,
  loaded: facilityLoaded,
  loadError: facilityLoadError
} = storeToRefs(facility_store)
const mastery_store = useMasteryStore()
const {
  planCount: masteryPlanCount,
  isTraining: masteryIsTraining,
  planSummaryLoaded,
  planSummaryError
} = storeToRefs(mastery_store)

const inventory_select_options = computed(() =>
  inventory_options_with_counts(
    inventory.value,
    inventoryLoadError.value ? 'error' : inventoryLoaded.value ? 'loaded' : 'loading'
  )
)

const facility_product_summary = computed(() =>
  summarize_facility_products(
    plan.value,
    facilityLoaded.value && !facilityLoadError.value ? facility_states.value : {}
  )
)

const facility_select_options = computed(() =>
  [...left_side_facility, { label: '训练室', value: 'train' }].map((option) => {
    if (option.value == 'train') return option
    const facilityName = plan.value[option.value]?.name
    if (!['制造站', '贸易站'].includes(facilityName)) {
      return {
        ...option,
        label: facilityName ? `${option.label}（${facilityName}）` : option.label
      }
    }
    const current =
      facility_product_labels[facility_product_summary.value.products[option.value]] || '未配置'
    return {
      ...option,
      label: `${option.label}（${facilityName}；当前：${current}）`
    }
  })
)

const facility_status_options = computed(() => {
  if (op_data.value.room == 'train') {
    const planCount = planSummaryError.value
      ? '读取失败'
      : planSummaryLoaded.value
        ? `当前 ${masteryPlanCount.value} 条`
        : '读取中'
    const training = planSummaryError.value
      ? '读取失败'
      : planSummaryLoaded.value
        ? `当前：${masteryIsTraining.value ? '是' : '否'}`
        : '读取中'
    return [
      { label: `是否存在专精计划（${planCount}）`, value: 'mastery_plan' },
      { label: `是否正在训练（${training}）`, value: 'training' },
      { label: '当前干员数量', value: 'operator_count' }
    ]
  }
  const facilityName = plan.value[op_data.value.room]?.name
  const options = [
    { label: '设施类型', value: 'type' },
    { label: '当前干员数量', value: 'operator_count' }
  ]
  if (facilityName == '制造站') options.unshift({ label: '当前产物', value: 'product' })
  if (facilityName == '贸易站') options.unshift({ label: '当前订单类型', value: 'product' })
  return options
})

const facility_stat_options = computed(() => [
  { label: '指定产物/订单的设施数', value: 'product_count' },
  {
    label: `产物/订单种类数（${facility_product_summary.value.typeCount} 种）`,
    value: 'product_type_count'
  }
])

const facility_product_stat_options = computed(() =>
  facility_product_options.map((option) => {
    const current = facility_product_summary.value.counts[option.value]
    return { ...option, label: `${option.label}（${current} 站）` }
  })
)

onMounted(() => {
  depot_store.loadInventory().catch(() => {})
  facility_store.load().catch(() => {})
  mastery_store.loadPlanSummary().catch(() => {})
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
  ...facility_product_options.map(({ label, value }) => ({
    label: `${label}（${value}）`,
    value
  })),
  ...trigger_facility_type_options,
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
  <n-select
    v-if="op_type == 'facility'"
    :default-value="op_data.room"
    :options="facility_select_options"
    :on-update:value="update_facility"
    :consistent-menu-width="false"
    class="facility-room-select"
  />
  <n-select
    v-if="op_type == 'facility'"
    :default-value="op_data.status"
    :options="facility_status_options"
    :on-update:value="update_facility_status"
    :consistent-menu-width="false"
    class="facility-status-select"
  />
  <n-select
    v-if="op_type == 'facility_stat'"
    :default-value="op_data.status"
    :options="facility_stat_options"
    :on-update:value="update_facility_stat"
    :consistent-menu-width="false"
    style="min-width: 300px"
  />
  <n-select
    v-if="op_type == 'facility_stat' && op_data.status == 'product_count'"
    :default-value="op_data.product"
    :options="facility_product_stat_options"
    :on-update:value="update_facility_stat_product"
    :consistent-menu-width="false"
    style="min-width: 300px"
  />
</template>

<style scoped>
.facility-room-select {
  flex: 0 0 220px;
  width: 220px;
  min-width: 180px;
  max-width: 220px;
}

.facility-status-select {
  flex: 1 1 360px;
  min-width: 360px;
}
</style>
