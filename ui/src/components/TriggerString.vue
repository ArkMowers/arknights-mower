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
  x = data.value.match(
    /^op_data\.get_current_room_for_ui\(\s*'(.+?)'\s*(?:,\s*(True|False))?\s*(?:,\s*(None|\d+|'[\d,]+'))?\s*(?:,\s*'(.+?)'\s*)?\)$/
  )
  if (x && x[0] == data.value) {
    let position
    if (!x[3] || x[3] === 'None') {
      position = 'ALL'
    } else if (x[3].startsWith("'")) {
      position = x[3].slice(1, -1)
    } else {
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
  x = data.value.match(
    /^op_data\.get_group_info\(\s*'(.+?)'\s*(?:,\s*(?:'(.+?)'|None)\s*)?\s*(?:,\s*(?:'(.+?)'|None)\s*)?\)$/
  )
  if (x && x[0] == data.value) {
    return {
      type: 'group',
      options: x[1],
      group_name: x[2],
      mode: x[3]
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
  } else if (op_data.value.type == 'group') {
    return 'group'
  } else {
    return 'op'
  }
})

const type_options = [
  { label: '干员属性', value: 'op' },
  // { label: '组属性', value: 'group' },
  { label: '房间干员', value: 'gcr' },
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

const gcr_attribute_options = [
  // 未来可扩展模板
  // {label: '技能',value: 'skill',attribute: 'skill'}
  { label: '干员名称', value: 'position' },
  { label: '心情值', value: 'mood', attribute: 'mood' },
  { label: '是否在高效组', value: 'is_high', attribute: 'is_high' }
]

const group_options = computed(() => {
  const baseOptions = [
    { label: '组内属性', value: 'True' },
    { label: '单人与组', value: 'False,True' },
    { label: '组与组', value: 'True,True' }
  ]
  const isLongPattern =
    op_data.value.options &&
    op_data.value.options.split(',').length >
      Math.max(...baseOptions.map((opt) => opt.value.split(',').length))
  return isLongPattern
    ? [...baseOptions, { label: '太长会坏掉的', value: op_data.value.options }]
    : baseOptions
})

const group_model_options = [
  { label: '心情数据', value: 'mode_mood' },
  { label: '用尽时间', value: 'mode_exhaust_time' },
  { label: '心情消耗速率', value: 'mode_depletion_rate' },
  { label: '数据更新时间', value: 'mode_time_stamp' },
  { label: '最终输出名字', value: 'mode_name' },
  { label: '正向排序', value: 'mode_up' },
  { label: '反向排序', value: 'mode_down' },
  { label: '获取最低', value: 'mode_min' },
  { label: '获取最高', value: 'mode_max' },
  { label: '小于几人', value: 'mode_lt' },
  { label: '大于几人', value: 'mode_gt' },
  { label: '组平均值', value: 'mode_group_avg' },
  { label: '干员平均值', value: 'mode_op_avg' },
  { label: '取消单干员基准', value: 'mode_no_ref' },
  { label: '以最低为基准', value: 'mode_ref_min' },
  { label: '以最高为基准', value: 'mode_ref_max' },
  { label: '最小差值', value: 'mode_diff_min' },
  { label: '最大差值', value: 'mode_diff_max' },
  { label: '与临近干员差值', value: 'mode_diff_adj' },
  { label: '取消自动令夕心情', value: 'mode_no_auto_mood' }
]

function set_op_type(v) {
  data.value = ''
  if (v == 'op') {
    data.value = "op_data.operators['阿米娅'].current_mood()"
  } else if (v == 'impart') {
    data.value = 'op_data.party_time'
  } else if (v == 'gcr') {
    data.value = "op_data.get_current_room_for_ui('dormitory_1')"
  } else if (v == 'group') {
    data.value = "op_data.get_group_info('True')"
  }
}

import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
const plan_store = usePlanStore()
const { operators, groups } = storeToRefs(plan_store)

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
// 位置相关
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
const gcr_position_options = computed(() => {
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

// 组相关
function update_group(options, group_name, mode) {
  const isModeChanged = options && options !== op_data.value.options
  if (isModeChanged) {
    group_name = 'None'
    // mode = 'None'
  }
  const defaultParams = {
    options: 'True',
    group_name: 'None',
    mode: 'None'
  }

  const currentOptions = options || op_data.value.options || defaultParams.options
  const currentGroupName = group_name !== undefined ? group_name : defaultParams.group_name
  const currentModel = mode !== undefined ? mode : defaultParams.mode

  const orderedParams = [
    `'${currentOptions}'`,
    currentGroupName === 'None' ? 'None' : `'${currentGroupName}'`,
    currentModel === 'None' ? 'None' : `'${currentModel}'`
  ]

  // 从右向左移除多余默认值
  let lastNonDefault = orderedParams.length
  while (
    lastNonDefault > 1 &&
    orderedParams[lastNonDefault - 1] ===
      defaultParams[Object.keys(defaultParams)[lastNonDefault - 1]]
  ) {
    lastNonDefault--
  }

  data.value = `op_data.get_group_info(${orderedParams.slice(0, lastNonDefault).join(', ')})`
}

//处理多选变化
function handleModeChange(values) {
  const modeValue = values && values.length > 0 ? values.join(',') : undefined
  update_group(op_data.value.options, op_data.value.group_name, modeValue)
}

const useCustomSelector = computed(() => {
  if (!op_data.value.options) return false
  const parts = op_data.value.options.split(',')
  return parts.length >= 3 && new Set(parts).size === 1
})
// 解析options生成选择器配置
const getSelectorConfig = (options) => {
  const patterns = options.split(',')

  if (useCustomSelector.value) {
    // 自选模式下只返回一个配置项
    return [
      {
        isGroup: patterns[0] === 'True',
        placeholder: `选择${patterns.length}个${patterns[0] === 'True' ? '组' : '干员'}`,
        value: op_data.value.group_name?.split(':').slice(0, patterns.length).join(':') || null,
        isCustom: true,
        count: patterns.length
      }
    ]
  }

  // 正常模式
  return patterns.map((pattern, index) => ({
    isGroup: pattern === 'True',
    placeholder: `${index === 0 ? '选择' : '选择'}${pattern === 'True' ? '组' : '干员'}`,
    value: op_data.value.group_name?.split(':')[index] || null
  }))
}
const getSelectorConfigByType = (isGroup, index, configType, option) => {
  const configMap = {
    options: isGroup ? formattedGroups.value : operators.value,
    renderLabel: isGroup ? render_group_label : render_op_label,
    renderTag: useCustomSelector.value
      ? isGroup
        ? render_group_tag
        : render_op_tag
      : isGroup
        ? render_group_label
        : render_op_label,
    style: isGroup
      ? {
          'min-width': '120px'
        }
      : {
          'min-width': '220px'
        }
  }

  // console.log(useCustomSelector.value);
  if (option) {
    return configMap[configType](option)
  }

  return configMap[configType]
}

// 统一处理选择器更新
const handleSelectorUpdate = (values, index) => {
  if (useCustomSelector.value) {
    const filteredValues = values.filter((v) => v && v.trim() !== '')
    const v = filteredValues.length > 0 ? filteredValues.join(':') : 'None'
    update_group(op_data.value.options, v, op_data.value.mode)
  } else {
    const parts = op_data.value.group_name?.split(':') || []
    parts[index] = values
    update_group(op_data.value.options, parts.join(':'), op_data.value.mode)
  }
}
const selectedItems = ref([])
watch(
  () => op_data.value.group_name,
  (newVal) => {
    if (useCustomSelector.value && newVal && newVal !== 'None') {
      selectedItems.value = newVal.split(':').filter((item) => item && item !== 'None')
    } else {
      selectedItems.value = []
    }
  },
  { immediate: true }
)

const selectedModes = ref([])
watch(
  () => op_data.value.mode,
  (newVal) => {
    selectedModes.value = newVal && newVal !== 'None' ? newVal.split(',') : []
  },
  { immediate: true }
)

import { pinyin_match } from '@/utils/common'
import { render_op_label, render_op_tag } from '@/utils/op_select'
import { formatGroupData, render_group_label, render_group_tag } from '@/utils/group_select'

const formattedGroups = computed(() => {
  return formatGroupData(groups.value)
})

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
  <!-- 第一行：主选择器和组头部 -->
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
  <template v-if="op_type == 'gcr'">
    <n-select
      :value="op_data.room || 'dormitory_1'"
      filterable
      :options="gcr_options"
      :on-update:value="(v) => update_gcr(v, op_data.position, op_data.attribute)"
      :filter="(p, o) => pinyin_match(o.label, p)"
      style="min-width: 120px"
    />
    <n-select
      v-if="gcr_position_options.length > 0"
      :value="op_data.position"
      :options="gcr_position_options"
      :on-update:value="(v) => update_gcr(op_data.room, v, op_data.attribute)"
      style="min-width: 120px"
    />
    <!-- v-if="showAttributeOptions" -->
    <n-select
      :value="op_data.attribute || 'position'"
      :options="gcr_attribute_options"
      :on-update:value="(v) => update_gcr(op_data.room, op_data.position, v)"
      style="min-width: 120px"
    />
  </template>

  <template v-if="op_type == 'group'">
    <n-select
      :value="op_data.options"
      :options="group_options"
      :on-update:value="(v) => update_group(v, op_data.group_name, op_data.mode)"
      style="min-width: 150px"
    />

    <!-- 动态渲染选择器 -->
    <template v-if="op_type === 'group' && op_data.options !== 'custom'">
      <template v-for="(config, index) in getSelectorConfig(op_data.options)" :key="index">
        <n-select
          v-if="!config.isCustom"
          :value="config.value"
          filterable
          :options="getSelectorConfigByType(config.isGroup, index, 'options')"
          :render-label="
            (option) => getSelectorConfigByType(config.isGroup, index, 'renderLabel', option)
          "
          :render-tag="
            ({ option }) => getSelectorConfigByType(config.isGroup, index, 'renderTag', option)
          "
          :filter="(p, o) => pinyin_match(o.label, p)"
          :on-update:value="(v) => handleSelectorUpdate(v, index)"
          :placeholder="config.placeholder"
          :style="getSelectorConfigByType(config.isGroup, index, 'style')"
        />
        <n-select
          v-else
          v-model:value="selectedItems"
          multiple
          filterable
          :options="config.isGroup ? formattedGroups : operators"
          :render-label="getSelectorConfigByType(config.isGroup, index, 'renderLabel')"
          :render-tag="getSelectorConfigByType(config.isGroup, index, 'renderTag')"
          :placeholder="config.placeholder"
          :filter="(p, o) => pinyin_match(o.label, p)"
          :style="getSelectorConfigByType(config.isGroup, index, 'style')"
          @update:value="(vals) => handleSelectorUpdate(vals, index)"
          clearable
        />
      </template>
    </template>
    <!-- <n-select
        :value="op_data.mode"
        :options="group_model_options"
        :on-update:value="(v) => update_group(op_data.options, op_data.group_name, v)"
        style="min-width: 120px"
      /> -->
    <n-select
      v-model:value="selectedModes"
      multiple
      filterable
      :options="group_model_options"
      :render-tag="render_group_tag"
      :filter="(p, o) => pinyin_match(o.label, p)"
      style="min-width: 120px"
      @update:value="handleModeChange"
      clearable
    />
  </template>
</template>
