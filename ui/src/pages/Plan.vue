<script setup>
import { storeToRefs } from 'pinia'
import { usePlanStore } from '@/stores/plan'
import { ref, computed, nextTick, watch } from 'vue'
import pinyinMatch from 'pinyin-match'
import { NAvatar, NTag, NText } from 'naive-ui'
const plan_store = usePlanStore()
const { operators, plan, groups } = storeToRefs(plan_store)
const { facility_operator_limit } = plan_store

const facility_types = [
  { label: '贸易站', value: '贸易站' },
  { label: '制造站', value: '制造站' },
  { label: '发电站', value: '发电站' }
]

const facility = ref('')

const button_type = {
  贸易站: 'info',
  制造站: 'warning',
  发电站: 'primary'
}

const operator_limit = computed(() => {
  if (facility.value.startsWith('room') && plan.value[facility.value].name == '发电站') {
    return 1
  }
  return facility_operator_limit[facility.value] || 0
})

function clear() {
  plan.value[facility.value].name = ''
  nextTick(() => {
    const plans = []
    for (let i = 0; i < operator_limit.value; ++i) {
      plans.push({
        agent: '',
        group: '',
        replacement: []
      })
    }
    plan.value[facility.value].plans = plans
  })
}

watch(
  () => {
    if (facility.value.startsWith('room')) {
      return plan.value[facility.value].name
    }
    return ''
  },
  (new_name, old_name) => {
    if (new_name == '发电站') {
      const plans = plan.value[facility.value].plans
      while (plans.length > operator_limit.value) {
        plans.pop()
      }
    } else if (old_name == '发电站') {
      const plans = plan.value[facility.value].plans
      while (plans.length < operator_limit.value) {
        plans.push({ agent: '', group: '', replacement: [] })
      }
    }
  }
)

const operators_with_free = computed(() => {
  return [
    { value: '', label: '（无）' },
    { value: 'Free', label: 'Free' }
  ].concat(operators.value)
})

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
  } else {
    return '未知'
  }
})

const facility_empty = computed(() => {
  let empty = true
  for (const i of plan.value[facility.value].plans) {
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

function drop_facility(target, event) {
  const source = event.dataTransfer.getData('text/plain')
  const source_plan = plan.value[source]
  plan.value[source] = plan.value[target]
  plan.value[target] = source_plan
  event.preventDefault()
}
const renderMultipleSelectTag = ({ option, handleClose }) => {
  return h(
    NTag,
    {
      style: {
        padding: '0 6px 0 4px'
      },
      round: true,
      closable: true,
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    {
      default: () =>
        h(
          'div',
          {
            style: {
              display: 'flex',
              alignItems: 'center'
            }
          },
          [
            h(NAvatar, {
              src: 'avatar/' + option.value + '.png',
              round: true,
              size: 22,
              style: {
                marginRight: '4px'
              }
            }),
            option.label
          ]
        )
    }
  )
}
const renderLabel = (option) => {
  return h(
    'div',
    {
      style: {
        display: 'flex',
        alignItems: 'center'
      }
    },
    [
      h(NAvatar, {
        src: 'avatar/' + option.value + '.png',
        round: true,
        size: 'small'
      }),
      h(
        'div',
        {
          style: {
            marginLeft: '12px',
            padding: '4px 0'
          }
        },
        [h('div', null, [option.label])]
      )
    ]
  )
}
</script>

<template>
  <div class="plan-container">
    <div class="outer">
      <!-- 左 -->
      <div class="left_box">
        <div class="left_contain">
          <div
            v-for="r in ['room_1_1', 'room_1_2', 'room_1_3']"
            :key="r"
            @click="facility = r"
            :class="[button_type[plan[r].name], r === facility ? 'true' : 'false']"
          >
            <div
              v-show="plan[r].name"
              draggable="true"
              @dragstart="drag_facility(r, $event)"
              @dragover.prevent
              @dragenter.prevent
              @drop="drop_facility(r, $event)"
            >
              <div>
                <div class="facility-name">
                  {{ plan[r].name }}
                </div>
                <div class="avatars">
                  <img
                    v-for="i in plan[r].plans"
                    :src="`avatar/${i.agent}.png`"
                    width="45"
                    height="45"
                    :style="{ 'border-bottom': color_map[i.group] }"
                    draggable="false"
                  />
                </div>
              </div>
            </div>
            <div v-show="!plan[r].name" class="waiting">
              <div>待建造</div>
            </div>
          </div>
        </div>
        <div class="left_contain">
          <div
            v-for="r in ['room_2_1', 'room_2_2', 'room_2_3']"
            :key="r"
            @click="facility = r"
            :class="[button_type[plan[r].name], r === facility ? 'true' : 'false']"
          >
            <div
              v-show="plan[r].name"
              draggable="true"
              @dragstart="drag_facility(r, $event)"
              @dragover.prevent
              @dragenter.prevent
              @drop="drop_facility(r, $event)"
            >
              <div>
                <div class="facility-name">
                  {{ plan[r].name }}
                </div>
                <div class="avatars">
                  <img
                    v-for="i in plan[r].plans"
                    :src="`avatar/${i.agent}.png`"
                    width="45"
                    height="45"
                    :style="{ 'border-bottom': color_map[i.group] }"
                    draggable="false"
                  />
                </div>
              </div>
            </div>
            <div v-show="!plan[r].name" class="waiting">
              <div>待建造</div>
            </div>
            <!-- <n-button
                :dashed="facility != r"
                :ghost="facility == r"
                :type="facility == r ? 'primary' : ''"
                v-if="!plan[r].name"
                @click="facility = r"
                class="facility-3"
              >
                待建造
              </n-button>
              <n-button
                :secondary="facility != r"
                :ghost="facility == r"
                :type="button_type[plan[r].name]"
                v-else
                class="facility-3"
                @click="facility = r"
                tag="div"
                draggable="true"
                @dragstart="drag_facility(r, $event)"
                @dragover.prevent
                @dragenter.prevent
                @drop="drop_facility(r, $event)"
              >
                <div>
                  <div class="facility-name">
                    {{ plan[r].name }}
                  </div>
                  <div class="avatars">
                    <img
                      v-for="i in plan[r].plans"
                      :src="`avatar/${i.agent}.png`"
                      width="45"
                      height="45"
                      :style="{ 'border-bottom': color_map[i.group] }"
                      draggable="false"
                    />
                  </div>
                </div>
              </n-button> -->
          </div>
        </div>
        <div class="left_contain">
          <div
            v-for="r in ['room_3_1', 'room_3_2', 'room_3_3']"
            :key="r"
            @click="facility = r"
            :class="[button_type[plan[r].name], r === facility ? 'true' : 'false']"
          >
            <div
              v-show="plan[r].name"
              draggable="true"
              @dragstart="drag_facility(r, $event)"
              @dragover.prevent
              @dragenter.prevent
              @drop="drop_facility(r, $event)"
            >
              <div>
                <div class="facility-name">
                  {{ plan[r].name }}
                </div>
                <div class="avatars">
                  <img
                    v-for="i in plan[r].plans"
                    :src="`avatar/${i.agent}.png`"
                    width="45"
                    height="45"
                    :style="{ 'border-bottom': color_map[i.group] }"
                    draggable="false"
                  />
                </div>
              </div>
            </div>
            <div v-show="!plan[r].name" class="waiting">
              <div>待建造</div>
            </div>
            <!-- <n-button
                :dashed="facility != r"
                :ghost="facility == r"
                :type="facility == r ? 'primary' : ''"
                v-if="!plan[r].name"
                @click="facility = r"
                class="facility-3"
              >
                待建造
              </n-button>
              <n-button
                :secondary="facility != r"
                :ghost="facility == r"
                :type="button_type[plan[r].name]"
                v-else
                class="facility-3"
                @click="facility = r"
                tag="div"
                draggable="true"
                @dragstart="drag_facility(r, $event)"
                @dragover.prevent
                @dragenter.prevent
                @drop="drop_facility(r, $event)"
              >
                <div>
                  <div class="facility-name">
                    {{ plan[r].name }}
                  </div>
                  <div class="avatars">
                    <img
                      v-for="i in plan[r].plans"
                      :src="`avatar/${i.agent}.png`"
                      width="45"
                      height="45"
                      :style="{ 'border-bottom': color_map[i.group] }"
                      draggable="false"
                    />
                  </div>
                </div>
              </n-button> -->
          </div>
        </div>
      </div>
      <!-- 中 -->
      <div class="mid_box">
        <div class="mid_contain">
          <n-button
            :secondary="facility != 'central'"
            class="facility-5"
            @click="facility = 'central'"
          >
            <div>
              <div class="facility-name">控制中枢</div>
              <div class="avatars">
                <img
                  v-for="i in plan.central.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'dormitory_1'"
          >
            <div>
              <div class="facility-name">宿舍1</div>
              <div class="avatars">
                <img
                  v-for="i in plan.dormitory_1.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'dormitory_2'"
          >
            <div>
              <div class="facility-name">宿舍2</div>
              <div class="avatars">
                <img
                  v-for="i in plan.dormitory_2.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'dormitory_3'"
          >
            <div>
              <div class="facility-name">宿舍3</div>
              <div class="avatars">
                <img
                  v-for="i in plan.dormitory_3.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'dormitory_4'"
          >
            <div>
              <div class="facility-name">宿舍4</div>
              <div class="avatars">
                <img
                  v-for="i in plan.dormitory_4.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'meeting'"
          >
            <div>
              <div class="facility-name">会客室</div>
              <div class="avatars">
                <img
                  v-for="i in plan.meeting.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'factory'"
          >
            <div>
              <div class="facility-name">加工站</div>
              <div class="avatars">
                <img
                  v-for="i in plan.factory.plans"
                  :src="`avatar/${i.agent}.png`"
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
            @click="facility = 'contact'"
          >
            <div>
              <div class="facility-name">办公室</div>
              <div class="avatars">
                <img
                  v-for="i in plan.contact.plans"
                  :src="`avatar/${i.agent}.png`"
                  width="45"
                  height="45"
                  :style="{ 'border-bottom': color_map[i.group] }"
                />
              </div>
            </div>
          </n-button>
        </div>
        <div class="right_contain"><n-button disabled class="facility-2">训练室</n-button></div>
      </div>
    </div>
    <n-space justify="center" v-if="facility">
      <table>
        <tr>
          <td>设施类别：</td>
          <td>
            <n-select
              v-model:value="plan[facility].name"
              :options="facility_types"
              class="type-select"
              v-if="facility.startsWith('room')"
            />
            <span v-else class="type-select">{{ right_side_facility_name }}</span>
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
          <td class="select-label">干员：</td>
          <td class="table-space">
            <n-select
              filterable
              :options="operators_with_free"
              class="operator-select"
              v-model:value="plan[facility].plans[i - 1].agent"
              :filter="(p, o) => pinyinMatch.match(o.label, p)"
              :render-label="renderLabel"
            />
          </td>
          <td class="select-label">组：</td>
          <td class="table-space group">
            <n-input v-model:value="plan[facility].plans[i - 1].group"></n-input>
          </td>
          <td class="select-label">替换：</td>
          <td>
            <n-select
              :disabled="!plan[facility].plans[i - 1].agent"
              multiple
              filterable
              :options="operators_with_free"
              class="replacement-select"
              v-model:value="plan[facility].plans[i - 1].replacement"
              :filter="(p, o) => pinyinMatch.match(o.label, p)"
              :render-label="renderLabel"
              :render-tag="renderMultipleSelectTag"
            />
          </td>
        </tr>
      </table>
    </n-space>
  </div>
</template>

<style scoped>
.w90 {
  width: 90px;
}

.select-label {
  width: 44px;
}

.type-select {
  width: 100px;
  margin-right: 8px;
}

.operator-select {
  width: 150px;
}

.replacement-select {
  min-width: 400px;
}

.plan-container {
  min-width: 980px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.group {
  width: 120px;
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
}

.facility-name {
  margin-bottom: 4px;
  text-align: center;
}

.avatars > img {
  box-sizing: content-box;
  border-radius: 2px;
  background: lightgrey;
}

.outer {
  display: flex;
  gap: 16px;
  margin: 0 auto;
}
.left_box {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.left_box .left_contain {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
}

.left_box .left_contain > div {
  cursor: pointer;
}

.left_box .left_contain .info {
  background-color: rgba(32, 128, 240, 0.16);
  padding: 5px 15px 15px 15px;
  border-radius: 3px;
  border: 1px solid transparent;
  transition: all 0.3s;
}

.left_box .left_contain .info:hover {
  background-color: rgba(32, 128, 240, 0.22);
}

.left_box .left_contain .info.true {
  background-color: #fff;
  border: 1px solid rgb(32, 128, 240);
}

.left_box .left_contain .info .facility-name {
  color: #2080f0;
}

.left_box .left_contain .warning {
  background-color: rgba(240, 160, 32, 0.16);
  padding: 5px 15px 15px 15px;
  border-radius: 3px;
  border: 1px solid transparent;
  transition: all 0.3s;
}

.left_box .left_contain .warning:hover {
  background-color: rgba(240, 160, 32, 0.22);
}

.left_box .left_contain .warning.true {
  background-color: #fff;
  border: 1px solid rgb(240, 160, 32);
}

.left_box .left_contain .warning .facility-name {
  color: #f0a020;
}

.left_box .left_contain .primary {
  background-color: rgba(24, 160, 88, 0.16);
  padding: 5px 15px 15px 15px;
  border-radius: 3px;
  border: 1px solid transparent;
  transition: all 0.3s;
}

.left_box .left_contain .primary:hover {
  background-color: rgba(24, 160, 88, 0.22);
}

.left_box .left_contain .primary.true {
  background-color: #fff;
  border: 1px solid rgb(24, 160, 88);
}

.left_box .left_contain .primary .facility-name {
  color: #18a058;
}

.mid_box {
  display: flex;
  flex-direction: column;
}

.waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgb(51, 54, 57);
  min-height: 93px;
  opacity: 0.6;
  transition: all 0.3s;
  cursor: pointer;
  border-radius: 3px;
}

.waiting:hover {
  opacity: 1;
  border: 1px dashed rgb(54, 173, 106);
  color: rgb(54, 173, 106);
}

.waiting div {
  text-align: center;
}
</style>
