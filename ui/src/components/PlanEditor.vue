<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'
import { usePlanStore } from '@/stores/plan'
import { swap } from '@/utils/common'
import { ref, computed, nextTick, watch, inject } from 'vue'
const config_store = useConfigStore()
const plan_store = usePlanStore()
const { operators, groups, current_plan, plan, workaholic, sub_plan, backup_plans } =
  storeToRefs(plan_store)
const { facility_operator_limit } = plan_store
const { theme } = storeToRefs(config_store)

const outer = ref(null)

const facility_types = [
  { label: '贸易站', value: '贸易站' },
  { label: '制造站', value: '制造站' },
  { label: '发电站', value: '发电站' }
]

const facility = inject('facility')

const button_type = {
  贸易站: 'info',
  制造站: 'warning',
  发电站: 'primary'
}

const operator_limit = computed(() => {
  if (facility.value.startsWith('room') && current_plan.value[facility.value].name == '发电站') {
    return 1
  }
  return facility_operator_limit[facility.value] || 0
})

function clear() {
  current_plan.value[facility.value].name = ''
  nextTick(() => {
    const plans = []
    for (let i = 0; i < operator_limit.value; ++i) {
      plans.push({
        agent: '',
        group: '',
        replacement: []
      })
    }
    current_plan.value[facility.value].plans = plans
  })
}

watch(
  () => {
    if (facility.value.startsWith('room')) {
      return current_plan.value[facility.value].name
    }
    return ''
  },
  (new_name, old_name) => {
    if (new_name == '发电站') {
      const plans = current_plan.value[facility.value].plans
      while (plans.length > operator_limit.value) {
        plans.pop()
      }
    } else if (old_name == '发电站') {
      const plans = current_plan.value[facility.value].plans
      while (plans.length < operator_limit.value) {
        plans.push({ agent: '', group: '', replacement: [] })
      }
    }
  }
)

const operators_with_none = computed(() => {
  return [{ value: '', label: '（无）' }].concat(operators.value)
})

const operators_with_free = computed(() => {
  return [{ value: 'Free', label: 'Free' }].concat(operators.value)
})

const operators_with_none_free = computed(() => {
  return [{ value: 'Free', label: 'Free' }].concat(operators_with_none.value)
})

const operators_with_none_current = computed(() => {
  return [{ value: 'Current', label: 'Current' }].concat(operators_with_none.value)
})

const operators_with_none_free_current = computed(() => {
  return [{ value: 'Current', label: 'Current' }].concat(operators_with_none_free.value)
})

function operator_options(facility) {
  if (sub_plan.value == 'main') {
    return facility.startsWith('dorm') ? operators_with_none_free.value : operators_with_none.value
  } else {
    return facility.startsWith('dorm')
      ? operators_with_none_free_current.value
      : operators_with_none_current.value
  }
}

const right_side_facility_name = computed(() => {
  if (facility.value.startsWith('dormitory')) {
    return '宿舍'
  } else if (facility.value == 'central') {
    return '控制中枢'
  } else if (facility.value == 'contact') {
    return '办公室'
  } else if (facility.value == 'meeting') {
    return '会客室'
  } else if (facility.value == 'factory') {
    return '加工站'
  } else if (facility.value == 'train') {
    return '训练室（仅可安排协助位）'
  } else {
    return '未知'
  }
})

const facility_empty = computed(() => {
  let empty = true
  for (const i of current_plan.value[facility.value].plans) {
    if (i.agent) {
      empty = false
      break
    }
  }
  return empty
})

const color_map = computed(() => {
  const count = groups.value.length
  const result = {}
  for (let i = 0; i < count; ++i) {
    result[groups.value[i]] = `5px solid hsl(${(360 / count) * i}, 80%, 45%)`
  }
  result[''] = 'none'
  return result
})

function drag_facility(room, event) {
  event.dataTransfer.setData('text/plain', room)
  event.dataTransfer.dropEffect = 'move'
}

function updateTrigger(trigger, source, target) {
  for (const key in trigger) {
    if (key === 'left' || key === 'right') {
      if (typeof trigger[key] === 'string') {
        trigger[key] = swapSubstrings(trigger[key], source, target)
      } else if (typeof trigger[key] === 'object' && trigger[key] !== null) {
        updateTrigger(trigger[key], source, target)
      }
    }
  }
}

function swapSubstrings(str, source, target) {
  const placeholder = '__PLACEHOLDER__'
  let newStr = str.replace(new RegExp(source, 'g'), placeholder)
  newStr = newStr.replace(new RegExp(target, 'g'), source)
  newStr = newStr.replace(new RegExp(placeholder, 'g'), target)
  return newStr
}

function swapTask(tasks, source, target) {
  if (tasks) {
    const placeholder = '__PLACEHOLDER__'
    if (tasks.hasOwnProperty(source)) {
      tasks[placeholder] = tasks[source]
      delete tasks[source]
    }
    if (tasks.hasOwnProperty(target)) {
      tasks[source] = tasks[target]
      delete tasks[target]
    }
    if (tasks.hasOwnProperty(placeholder)) {
      tasks[target] = tasks[placeholder]
      delete tasks[placeholder]
    }
  }
}

function drop_facility(target, event) {
  const source = event.dataTransfer.getData('text/plain')

  // 1. 更新当前 current_plan 表
  swap(source, target, current_plan.value)
  console.log(current_plan.value)

  // 2. 更新所有副表和主表（除当前表以外）
  const allPlans = ['main', ...backup_plans.value]

  allPlans.forEach((item, index) => {
    if ((sub_plan.value === 'main' && item === 'main') || sub_plan.value === index) {
      return
    }
    // 执行更新操作
    if (item !== 'main') {
      swap(source, target, item.plan)
      // 副表才需要更新trigger 和 task
      swapTask(item.task, source, target)
      updateTrigger(item.trigger, source, target)
    } else {
      // plan 是主表
      swap(source, target, plan.value)
    }
  })

  event.preventDefault()
}

const avatar_bg = computed(() => {
  return theme.value == 'light' ? 'lightgrey' : 'grey'
})

defineExpose({
  outer
})

import { render_op_label, render_op_tag } from '@/utils/op_select'
import { pinyin_match } from '@/utils/common'

function fill_with_free() {
  for (let i = 0; i < operator_limit.value; ++i) {
    if (current_plan.value[facility.value].plans[i].agent == '') {
      current_plan.value[facility.value].plans[i].agent = 'Free'
    }
  }
}

const trading_products = [
  { label: '赤金订单', value: 'lmd' },
  { label: '合成玉订单', value: 'orundum' }
]

const factory_products = [
  { label: '赤金', value: 'gold' },
  { label: '中级作战记录', value: 'exp3' },
  { label: '源石碎片', value: 'orirock' }
]

import { NAvatar } from 'naive-ui'

const render_product = (option) => {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: '12px'
      }
    },
    [
      h(NAvatar, {
        src: '/product/' + option.value + '.png',
        round: true,
        size: 'small'
      }),
      option.label
    ]
  )
}

const product_bg_opacity = computed(() => {
  return theme.value == 'light' ? 0.6 : 0.7
})

const fia_list = computed(() => {
  for (let i = 1; i <= 4; ++i) {
    for (let j = 0; j < 5; ++j) {
      if (current_plan.value[`dormitory_${i}`].plans[j].agent == '菲亚梅塔') {
        return current_plan.value[`dormitory_${i}`].plans[j].replacement
      }
    }
  }
  return []
})

function set_facility(e) {
  if (facility.value == e) {
    facility.value = ''
  } else {
    facility.value = e
  }
}
</script>

<template>
  <div class="plan-container" ref="outer">
    <div class="outer">
      <!-- 左 -->
      <div class="left_box">
        <div class="left_contain" v-for="row in 3">
          <div
            v-for="r in [`room_${row}_1`, `room_${row}_2`, `room_${row}_3`]"
            :key="r"
            @click="set_facility(r)"
            :class="[button_type[current_plan[r].name], r === facility ? 'true' : 'false']"
          >
            <div
              class="product-bg"
              v-if="['制造站', '贸易站'].includes(current_plan[r].name)"
              :style="{
                'background-image': `url(/product/${current_plan[r].product}.png)`
              }"
            ></div>
            <div
              v-show="current_plan[r].name"
              draggable="true"
              @dragstart="drag_facility(r, $event)"
              @dragover.prevent
              @dragenter.prevent
              @drop="drop_facility(r, $event)"
              class="draggable"
            >
              <div class="facility-name">
                {{ current_plan[r].name }}
              </div>
              <div class="avatars">
                <template v-for="i in current_plan[r].plans">
                  <div class="avatar-wrapper" v-if="i.agent">
                    <img
                      :src="`avatar/${i.agent}.webp`"
                      width="45"
                      height="45"
                      :style="{ 'border-bottom': color_map[i.group] }"
                      draggable="false"
                    />
                    <div
                      class="workaholic"
                      v-if="workaholic.includes(i.agent) && !fia_list.includes(i.agent)"
                    ></div>
                  </div>
                </template>
              </div>
            </div>
            <div v-show="!current_plan[r].name" class="waiting">
              <div>待建造</div>
            </div>
          </div>
        </div>
      </div>
      <!-- 中 -->
      <div class="mid_box">
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'central'"
            class="facility-5"
            @click="set_facility('central')"
          >
            <div>
              <div class="facility-name">控制中枢</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.central.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'dormitory_1'"
            class="facility-5"
            @click="set_facility('dormitory_1')"
          >
            <div>
              <div class="facility-name">宿舍1</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.dormitory_1.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'dormitory_2'"
            class="facility-5"
            @click="set_facility('dormitory_2')"
          >
            <div>
              <div class="facility-name">宿舍2</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.dormitory_2.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'dormitory_3'"
            class="facility-5"
            @click="set_facility('dormitory_3')"
          >
            <div>
              <div class="facility-name">宿舍3</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.dormitory_3.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'dormitory_4'"
            class="facility-5"
            @click="set_facility('dormitory_4')"
          >
            <div>
              <div class="facility-name">宿舍4</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.dormitory_4.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
      </div>
      <!-- 右 -->
      <div class="right_box">
        <div class="right_contain">
          <n-button
            :secondary="facility != 'meeting'"
            class="facility-2"
            @click="set_facility('meeting')"
          >
            <div>
              <div class="facility-name">会客室</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.meeting.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="right_contain">
          <n-button
            :secondary="facility != 'factory'"
            class="facility-2"
            @click="set_facility('factory')"
          >
            <div>
              <div class="facility-name">加工站</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.factory.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="right_contain">
          <n-button
            :secondary="facility != 'contact'"
            class="facility-2"
            @click="set_facility('contact')"
          >
            <div>
              <div class="facility-name">办公室</div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.contact.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <!-- <div class="right_contain"><n-button disabled class="facility-2">训练室</n-button></div> -->
        <div class="right_contain">
          <n-button
            :secondary="facility != 'train'"
            class="facility-2"
            @click="set_facility('train')"
          >
            <div>
              <div class="facility-name">
                <div>协助位</div>
                <div>训练位</div>
              </div>
              <div class="avatars">
                <img
                  v-for="i in current_plan.train.plans"
                  :src="`avatar/${i.agent}.webp`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
      </div>
    </div>
    <n-space justify="center" v-if="facility">
      <table>
        <tr>
          <td>设施类别：</td>
          <td>
            <n-select
              v-model:value="current_plan[facility].name"
              :options="facility_types"
              class="type-select"
              v-if="facility.startsWith('room')"
            />
            <span v-else class="type-select">{{ right_side_facility_name }}</span>
          </td>
          <template v-if="['制造站', '贸易站'].includes(current_plan[facility].name)">
            <td>产物<help-text>切产物功能暂未实装</help-text></td>
            <td>
              <n-select
                v-model:value="current_plan[facility].product"
                :options="
                  current_plan[facility].name == '制造站' ? factory_products : trading_products
                "
                class="product-select"
                :render-label="render_product"
              />
            </td>
          </template>
          <td>
            <n-button
              ghost
              type="primary"
              @click="fill_with_free"
              v-if="facility.startsWith('dorm')"
            >
              此宿舍内空位填充Free
            </n-button>
          </td>
          <td>
            <n-button ghost type="error" @click="clear" :disabled="facility_empty">
              清空此设施内干员
            </n-button>
          </td>
        </tr>
      </table>
    </n-space>
    <n-space justify="center">
      <table>
        <tr v-for="i in operator_limit" :key="i">
          <td class="select-label">
            <template v-if="facility == 'train' && i == 1">协助位</template>
            <template v-else-if="facility == 'train' && i == 2">训练位</template>
            <template v-else>干员：</template>
          </td>
          <td class="table-space">
            <n-select
              filterable
              :options="operator_options(facility)"
              class="operator-select"
              v-model:value="current_plan[facility].plans[i - 1].agent"
              :filter="(p, o) => pinyin_match(o.label, p)"
              :render-label="render_op_label"
            />
          </td>
          <td class="select-label">
            <span>组</span>
            <help-text>可以将有联动基建技能的干员或者心情掉率相等的干员编入同组</help-text>
          </td>
          <td class="table-space group">
            <n-input
              v-model:value="current_plan[facility].plans[i - 1].group"
              :disabled="!current_plan[facility].plans[i - 1].agent"
            />
          </td>
          <td class="select-label">替换：</td>
          <td>
            <n-form-item :show-label="false" :show-feedback="false">
              <slick-operator-select
                :disabled="!current_plan[facility].plans[i - 1].agent"
                v-model="current_plan[facility].plans[i - 1].replacement"
                class="replacement-select"
              />
            </n-form-item>
          </td>
        </tr>
      </table>
    </n-space>
  </div>
</template>

<style scoped lang="scss">
.select-label {
  width: 44px;
}

.type-select {
  width: 100px;
  margin-right: 8px;
}

.product-select {
  width: 180px;
  margin-right: 8px;
}

.operator-select {
  width: 220px;
}

.replacement-select {
  min-width: 400px;
}

.plan-container {
  width: 980px;
  min-width: 980px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group {
  width: 160px;
}

.facility-2 {
  width: 124px;
  height: 76px;
  margin: 2px 3px;
}

.facility-3 {
  width: 175px;
  height: 76px;
  margin: 2px 3px;
}

.facility-5 {
  width: 277px;
  height: 76px;
  margin: 2px 3px;
}

.avatars {
  display: flex;
  gap: 6px;
  z-index: 5;

  & img {
    box-sizing: content-box;
    border-radius: 2px;
    background: v-bind(avatar_bg);
  }
}

.facility-name {
  margin-bottom: 4px;
  text-align: center;
  line-height: 1;
  display: flex;
  justify-content: space-around;
  z-index: 5;
}

.outer {
  display: flex;
  margin: 0 auto;
}

.left_box {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 82px;
  padding-right: 2px;

  .left_contain {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 4px;

    & > div {
      box-sizing: border-box;
      width: 175px;
      height: 76px;
      cursor: pointer;
    }

    .info {
      background-color: rgba(32, 128, 240, 0.16);
      border-radius: 3px;
      border: 1px solid transparent;
      transition: all 0.3s;
      position: relative;

      &:hover {
        background-color: rgba(32, 128, 240, 0.22);
      }

      &.true {
        background-color: var(--n-color);
        border: 1px solid rgb(32, 128, 240);
      }

      .facility-name {
        color: #2080f0;
      }
    }

    .warning {
      background-color: rgba(240, 160, 32, 0.16);
      border-radius: 3px;
      border: 1px solid transparent;
      transition: all 0.3s;
      position: relative;

      &:hover {
        background-color: rgba(240, 160, 32, 0.22);
      }

      &.true {
        background-color: var(--n-color);
        border: 1px solid rgb(240, 160, 32);
      }

      .facility-name {
        color: #f0a020;
      }
    }

    .primary {
      background-color: rgba(24, 160, 88, 0.16);
      border-radius: 3px;
      border: 1px solid transparent;
      transition: all 0.3s;

      &:hover {
        background-color: rgba(24, 160, 88, 0.22);
      }

      &.true {
        background-color: var(--n-color);
        border: 1px solid rgb(24, 160, 88);
      }

      .facility-name {
        color: #18a058;
      }
    }
  }
}

.mid_box {
  display: flex;
  flex-direction: column;
}

.waiting {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgb(51, 54, 57);
  opacity: 0.6;
  transition: all 0.3s;
  cursor: pointer;
  border-radius: 3px;

  &:hover {
    opacity: 1;
    border: 1px dashed rgb(54, 173, 106);
    color: rgb(54, 173, 106);
  }

  div {
    text-align: center;
  }
}

.draggable {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.product-bg {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 173px;
  height: 74px;
  opacity: v-bind(product_bg_opacity);
  background-repeat: no-repeat;
  background-size: 100%;
  background-position: 110px -20px;
  z-index: 3;
  pointer-events: none;
}

.avatar-wrapper {
  position: relative;
}

.workaholic {
  position: absolute;
  content: '';
  top: 0;
  left: 0;
  width: 45px;
  height: 45px;
  opacity: 0.35;
  background-color: red;
  pointer-events: none;
}
</style>

<style>
.n-base-selection-placeholder .n-avatar {
  display: none;
}
</style>
