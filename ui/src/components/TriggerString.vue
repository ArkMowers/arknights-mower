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
  //GCR模式匹配
  x = data.value.match(/^(?!.*current_mood\(\))(\(?op_data\.get_current_room\('(.+?)'(?:,\s*True)?\)(?:\[(\d+)\])?(?:\sor\sNone)?\)?)$/)
  if (x && x[0] == data.value) {
    return {
      type: 'gcr',
      room: x[2],  // 分组索引变化
      position: x[3] ? parseInt(x[3]) : 'ALL',
      attribute: 'position'
    }
  }

  //GCR心情模式
  x = data.value.match(/\(op_data\.get_current_room\('(.+?)'(?:,\s*True)?\)(?:\[(\d+)\])?\sor\sNone\)\sand\sop_data\.operators\[.+\]\.current_mood\(\)/)
  if (x && x[0] == data.value) {
    return {
      type: 'gcr',
      room: x[1],
      position: x[2] ? parseInt(x[2]) : 0,
      attribute: 'mood'
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
    value: 'position',
    buildExpression: (room, pos) => getOperatorExpr(room, pos)
  },
  { 
    label: '心情值', 
    value: 'mood',
    buildExpression: (room, pos) =>{
      if (pos === 'ALL') {
        // return `[op.current_mood() for op in ${getOperatorExpr(room, pos)} if op]`
        return getOperatorExpr(room, pos)
      }
            const expr = getOperatorExpr(room, pos)
      return `${expr} and op_data.operators[${expr}].current_mood()`
    }
  }
  // 未来可以方便地添加新属性
  // {
  //   label: '技能',
  //   value: 'skill',
  //   buildExpression: (room, pos) => `...`
  // }
]

function set_op_type(v) {
  data.value = ''
  if (v == 'op') {
    data.value = "op_data.operators['阿米娅'].current_mood()"
  } else if (v == 'impart') {
    data.value = 'op_data.party_time'
  } else if (v == 'gcr') {
    data.value = "op_data.get_current_room('dormitory_1')"
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
  // const isSinglePos = roomConfig?.positions === 1
  const effectivePos = calculateEffectivePosition(pos, roomConfig, roomConfig?.positions === 1);

  const attributeConfig = gcr_attribute_options.find(opt => opt.value === attribute)
  data.value = attributeConfig?.buildExpression(currentRoom, effectivePos)
            || getOperatorExpr(currentRoom, effectivePos);
}

function getCurrentRoom(room = false) {
  return room || op_data.value.room || 'dormitory_1';
}

function getRoomConfig(room){
  return gcr_options.find(r => r.value === room)
}
//处理位置状态
function calculateEffectivePosition(pos, roomConfig, isSinglePos) {
  // const maxPos = roomConfig ?  roomConfig.positions - 1 : 0
  // const effectivePos = isSinglePos ? 0 : 
  //                    (pos !== undefined ? (pos === 'ALL' ? pos : Math.min(pos, maxPos)) : (op_data.value.position || 'ALL'))
  if (isSinglePos) return 0;
  if (pos === undefined) return op_data.value.position || 'ALL';

  const maxPos = roomConfig ? roomConfig.positions - 1 : 0;
  return pos === 'ALL' ? pos : Math.min(pos, maxPos);
}

//获取干员的基础表达式
function getOperatorExpr(room, pos) {
  const roomExpr = `op_data.get_current_room('${room}'${pos === 'ALL' ? '' : ', True'})`;
  return pos === 'ALL' ? roomExpr : `(${roomExpr}[${pos}] or None)`;
}

//判断是否显示其它选项
const showAttributeOptions = computed(() => {
  const room = getCurrentRoom()
  const roomConfig = getRoomConfig(room)
  return roomConfig && (roomConfig.positions === 1 || op_data.value.position !== 'ALL')
})
//计算当前房间的位置选项
const position_options = computed(() => {
  const room = getCurrentRoom()
  const roomConfig = getRoomConfig(room)
  if (!roomConfig) return []
  
  return roomConfig.positions > 1 ? [
    { label: '全部位置', value: 'ALL' },
    ...Array.from({ length: roomConfig.positions }, (_, i) => ({
      label: `位置 ${i + 1}`,
      value: i
    }))
  ] : []
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
    
    <n-select
      v-if="showAttributeOptions"
      :value="op_data.attribute || 'position'"
      :options="gcr_attribute_options"
      :on-update:value="(v) => update_gcr(op_data.room, op_data.position, v)"
      style="min-width: 100px; margin-left: 8px"
    />
  </template>
</template>
