<script setup>
const props = defineProps(['data'])
const emit = defineEmits(['update'])

import { ref, watch, computed } from 'vue'

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
  x = data.value.match(/op_data.operators\['(.+?)'\].name/)
  if (x && x[0] == data.value) {
    return {
      type: 'name',
      operator: x[1]
    }
  }
  //GCR模式匹配
  x = data.value.match(
    /^op_data\.get_current_room_for_ui\(\s*'(.+?)'\s*(?:,\s*(True|False))?\s*(?:,\s*(None|\d+|'[\d,]+'))?\s*(?:,\s*'(.+?)'\s*)?\)$/
  )
  if (x && x[0] == data.value) {
    let position
    if (!x[3] || x[3] === 'None') {
      position = 'ALL'
    } else if (x[3].startsWith("'")) {
      // 去掉引号后直接使用（如 '0,1' → '0,1'）
      position = x[3].slice(1, -1)
    } else {
      // 单个数字（如 0）
      position = parseInt(x[3])
    }
    return {
      type: 'gcr',
      room: x[1],
      bypass: x[2] === 'True',
      // position: x[3] ? parseInt(x[3]) : 'ALL',
      position: position,
      attribute: x[4] || 'position'
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
  } else if (op_data.value.type == 'gcr') {
    return 'gcr'
  } else {
    return 'op'
  }
})

const type_options = [
  { label: '干员属性', value: 'op' },
  { label: '获取指定房间干员', value: 'gcr' },
  { label: '线索交流结束时间', value: 'impart' },
  { label: '自定义', value: 'custom' }
]

const op_options = [
  { label: '名称', value: 'name' },
  { label: '心情', value: 'mood' },
  { label: '当前位置', value: 'room' },
  { label: '在工作', value: 'working' },
  { label: '在休息', value: 'in_dorm' }
]

//GCR房间选项
const gcr_options = [
  { label: '宿舍1', value: 'dormitory_1', positions: 5 },
  { label: '宿舍2', value: 'dormitory_2', positions: 5 },
  { label: '宿舍3', value: 'dormitory_3', positions: 5 },
  { label: '宿舍4', value: 'dormitory_4', positions: 5 },
  { label: 'B101', value: 'room_1_1', positions: 3 },
  { label: 'B102', value: 'room_1_2', positions: 3 },
  { label: 'B103', value: 'room_1_3', positions: 3 },
  { label: 'B201', value: 'room_2_1', positions: 3 },
  { label: 'B202', value: 'room_2_2', positions: 3 },
  { label: 'B203', value: 'room_2_3', positions: 3 },
  { label: 'B301', value: 'room_3_1', positions: 3 },
  { label: 'B302', value: 'room_3_2', positions: 3 },
  { label: 'B303', value: 'room_3_3', positions: 3 },
  { label: '控制中枢', value: 'central', positions: 5 },
  { label: '会客室', value: 'meeting', positions: 2 },
  { label: '加工站', value: 'factory', positions: 1 },
  { label: '办公室', value: 'contact', positions: 1 },
  { label: '训练室', value: 'train', positions: 1 } //暂时不支持训练位
]

//GCR属性选项
const gcr_attribute_options = [
  {
    label: '干员名称',
    value: 'position'
  },
  {
    label: '心情值',
    value: 'mood',
    attribute: 'mood'
  },
  {
    label: '是否在高效组',
    value: 'is_high',
    attribute: 'is_high'
  }
  // 未来可扩展模板
  // {
  //   label: '技能',
  //   value: 'skill',
  //   attribute: 'skill'
  // }
]

function set_op_type(v) {
  data.value = ''
  if (v == 'op') {
    data.value = "op_data.operators['阿米娅'].current_mood()"
  } else if (v == 'impart') {
    data.value = 'op_data.party_time'
  } else if (v == 'gcr') {
    data.value = "op_data.get_current_room_for_ui('dormitory_1')"
  }
}

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
const plan_store = usePlanStore()
const { operators } = storeToRefs(plan_store)

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
  } else if (type == 'name') {
    data.value = x + 'name'
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

//更新GCR房间
function update_gcr(room, pos, attribute = 'position') {
  const currentRoom = getCurrentRoom(room)
  const roomConfig = getRoomConfig(currentRoom)
  const effectivePos = calculateEffectivePosition(pos, roomConfig, roomConfig?.positions === 1)
  const bypass = op_data.value.bypass || false

  // 获取选中的属性配置
  const attributeConfig = gcr_attribute_options.find((opt) => opt.value === attribute) || {}

  data.value = getOperatorExpr({
    room: currentRoom,
    room_index: effectivePos !== 'ALL' ? effectivePos : undefined,
    bypass,
    attribute: attributeConfig.attribute // 自动从配置读取
  })
}

function getCurrentRoom(room = false) {
  return room || op_data.value.room || 'dormitory_1'
}

function getRoomConfig(room) {
  return gcr_options.find((r) => r.value === room)
}
//处理位置状态
function calculateEffectivePosition(pos, roomConfig, isSinglePos) {
  if (isSinglePos) return undefined
  if (pos === undefined) return op_data.value.position || 'ALL'

  const maxPos = roomConfig ? roomConfig.positions - 1 : 0
  return pos === 'ALL' ? pos : Math.min(pos, maxPos)
}

//获取干员的基础表达式
function getOperatorExpr({ room, room_index, bypass = false, attribute = null }) {
  if (!room) throw new Error('room is required')

  // 参数默认值
  const defaultParams = {
    bypass: 'False',
    room_index: 'None',
    attribute: 'None'
  }

  // 实际要传递的参数
  const passedParams = {
    room: `'${room}'`,
    ...(bypass !== false && { bypass: bypass ? 'True' : 'False' }),
    ...(room_index !== undefined && { room_index }),
    ...(attribute !== null && { attribute: `'${attribute}'` })
  }

  // 合并参数，确保顺序正确
  const orderedParams = [
    passedParams.room,
    passedParams.bypass !== undefined ? passedParams.bypass : defaultParams.bypass,
    passedParams.room_index !== undefined ? passedParams.room_index : defaultParams.room_index,
    passedParams.attribute !== undefined ? passedParams.attribute : defaultParams.attribute
  ]

  // 移除多余的默认参数（从右向左）
  let lastNonDefault = orderedParams.length
  while (
    lastNonDefault > 1 &&
    orderedParams[lastNonDefault - 1] ===
      defaultParams[Object.keys(defaultParams)[lastNonDefault - 2]]
  ) {
    lastNonDefault--
  }

  return `op_data.get_current_room_for_ui(${orderedParams.slice(0, lastNonDefault).join(', ')})`
}
//判断是否显示其它选项
// const showAttributeOptions = computed(() => {
//   const room = getCurrentRoom()
//   const roomConfig = getRoomConfig(room)
//   return roomConfig && (roomConfig.positions === 1 || op_data.value.position !== 'ALL')
// })
//计算当前房间的位置选项
const position_options = computed(() => {
  const room = getCurrentRoom()
  const roomConfig = getRoomConfig(room)
  if (!roomConfig) return []

  return roomConfig.positions > 1
    ? [
        { label: '全部位置', value: 'ALL' },
        ...Array.from({ length: roomConfig.positions }, (_, i) => ({
          label: `位置 ${i + 1}`,
          value: i
        }))
      ]
    : []
})

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
  <!--GCR模板 -->
  <template v-if="op_type == 'gcr'">
    <n-select
      :value="op_data.room || 'dormitory_1'"
      :options="gcr_options"
      :on-update:value="(v) => update_gcr(v, op_data.position, op_data.attribute)"
      style="min-width: 220px"
    />

    <n-select
      v-if="position_options.length > 0"
      :value="op_data.position"
      :options="position_options"
      :on-update:value="(v) => update_gcr(op_data.room, v, op_data.attribute)"
      style="min-width: 100px; margin-left: 8px"
    />

    <!-- v-if="showAttributeOptions" -->
    <n-select
      :value="op_data.attribute || 'position'"
      :options="gcr_attribute_options"
      :on-update:value="(v) => update_gcr(op_data.room, op_data.position, v)"
      style="min-width: 100px; margin-left: 8px"
    />
  </template>
</template>
