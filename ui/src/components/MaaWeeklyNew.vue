<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_weekly_plan1, maa_enable } = storeToRefs(store)

import { NTag } from 'naive-ui'
import { h, ref } from 'vue'

const currentDay = ref(new Date().getDay())

const updatePlan = (plan1, day) => {
  plan1[day] = plan1[day] === 1 ? 2 : 1
}
const daysOfWeek = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']

function updateStage() {
  maa_weekly_plan.value.slice(0, daysOfWeek.length).forEach((plan, i) => {
    plan.stage = maa_weekly_plan1.value
      .filter((plan) => plan[daysOfWeek[i]] === 2)
      .map((plan) => plan.stage)
      .flat()
  })
}

const showstage = (stage) => {
  const valueMapping = {
    '1-7': '1-7',
    Annihilation: '剿灭',
    'LS-6': '经验书',
    'CE-6': '龙门',
    'AP-5': '红票',
    'SK-6': '碳条',
    'CA-5': '技能书',
    'PR-A-2': '重装医疗',
    'PR-B-2': '狙击术士',
    'PR-C-2': '先锋辅助',
    'PR-D-2': '近卫特种'
  }

  if (stage in valueMapping) {
    return valueMapping[stage]
  } else {
    return stage
  }
}

function render_tag({ option, handleClose }) {
  return h(
    NTag,
    {
      type: option.type,
      closable: true,
      onMousedown: (e) => {
        e.preventDefault()
      },
      onClose: (e) => {
        e.stopPropagation()
        handleClose()
      }
    },
    {
      default: () => {
        if (option.label == '') {
          return '上次作战'
        } else if (option.label == 'Annihilation') {
          return '当期剿灭'
        } else if (option.label.endsWith('-HARD')) {
          return option.label.slice(0, -5) + '磨难'
        } else if (option.label.endsWith('-NORMAL')) {
          return option.label.slice(0, -7) + '标准'
        } else {
          return option.label
        }
      }
    }
  )
}

function create_tag(label) {
  if (label == ' ' || label == '上次作战') {
    return {
      label: '上次作战',
      value: ''
    }
  } else if (label == '当期剿灭') {
    return {
      label: '当期剿灭',
      value: 'Annihilation'
    }
  } else if (label.endsWith('磨难')) {
    return {
      label: label,
      value: label.slice(0, -2) + '-HARD'
    }
  } else if (label.endsWith('标准')) {
    return {
      label: label,
      value: label.slice(0, -2) + '-NORMAL'
    }
  } else {
    return {
      label,
      value: label
    }
  }
}
</script>

<template>
  <n-card>
    <n-checkbox v-model:checked="maa_enable" class="card-title"> Maa周计划 </n-checkbox>

    <help-text>
      <p>理智药的数量表示“每次调用Maa时吃多少”，不是“每天吃多少”。</p>
      <p>48 小时内过期的理智药会自动使用。</p>
      <p>“每天”从凌晨四点开始，与游戏内一致。</p>
      <span>关卡填写说明：</span>
      <ul>
        <li><b>添加关卡</b>：输入关卡名，按回车键确认。文本变为标签，代表输入成功。</li>
        <li>
          <b>上次作战</b>：输入空格或“上次作战”后回车，生成 <n-tag closable>上次作战</n-tag> 标签。
        </li>
        <li><b>主线关卡难度</b>：在关卡末尾添加“标准”或“磨难”以指定难度。例：</li>
        <ul>
          <li><n-tag closable>12-17标准</n-tag> 表示12-17标准难度。</li>
          <li><n-tag closable>12-17磨难</n-tag> 表示12-17磨难难度。</li>
        </ul>
        <li><b>当期剿灭</b>：输入“当期剿灭”后回车，生成 <n-tag closable>当期剿灭</n-tag> 标签。</li>
        <li>
          <b>信用作战</b>：若信用作战选项已开启，且当日计划不包含
          <n-tag closable>上次作战</n-tag>，则自动进行信用作战。
        </li>
        <li>
          <b>多个关卡</b
          >：填入多个关卡时，按顺序依次刷取所有关卡。关卡无法刷取或刷取结束后，继续尝试下一关卡。例：
          <ul>
            <li>
              <n-tag closable class="tag-mr">HE-7</n-tag>
              <n-tag closable>上次作战</n-tag>
              ：刷活动关HE-7，若活动未开放，则刷上一关。
            </li>
            <li>
              <n-tag closable class="tag-mr">AP-5</n-tag>
              <n-tag closable>1-7</n-tag>
              ：刷红票本AP-5，剩余体力刷1-7。
            </li>
          </ul>
        </li>
        <li><b>不刷理智</b>：留空表示不刷理智。</li>
      </ul>
    </help-text>

    <n-table size="small" :single-line="false" style="text-align: center">
      <thead>
        <tr>
          <th>关卡</th>
          <th
            v-for="(day, index) in daysOfWeek"
            :key="index"
            :class="{ today: currentDay === index }"
          >
            {{ day }}{{ currentDay === index + 1 ? ' (今天)' : '' }}
          </th>
        </tr>
      </thead>
      <tbody>
        <td>药</td>
        <td v-for="(day, index) in daysOfWeek" :key="index">
          <n-input-number
            v-model:value="maa_weekly_plan[index].medicine"
            :min="0"
            :max="6"
            :show-button="false"
          />
        </td>
        <tr v-for="(plan1, index) in maa_weekly_plan1" :key="plan1.weekday1">
          <td>
            <n-select
              v-if="index < 3"
              v-model:value="plan1.stage"
              multiple
              filterable
              tag
              :show="false"
              :show-arrow="false"
              :render-tag="render_tag"
              :on-create="create_tag"
            />
            <span v-else>{{ showstage(plan1.stage) }}</span>
          </td>
          <td
            v-for="day in daysOfWeek"
            :class="{
              class2: plan1[day] === 2,
              class1: plan1[day] === 1,
              class0: plan1[day] === 0
            }"
          >
            <template v-if="plan1[day] !== 0">
              <n-checkbox
                @click="updateStage"
                v-model="plan1[day]"
                :checked="plan1[day] === 2"
                @change="updatePlan(plan1, day)"
              />
            </template>
          </td>
        </tr>
      </tbody>
    </n-table>
  </n-card>
</template>

<style scoped lang="scss">
.class0 {
  background-color: hsl(33, 30%, 91%);
}

.class1 {
  background-color: hsl(198, 20%, 21%);
}

.class2 {
  background-color: hsl(356, 50%, 40%);
}

.card-title {
  font-weight: 500;
  font-size: 18px;
  margin-right: 8px;
}
</style>
