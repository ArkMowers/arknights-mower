<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_enable, maa_expiring_medicine, exipring_medicine_on_weekend } =
  storeToRefs(store)

import { NTag } from 'naive-ui'
import { computed, h, inject, ref } from 'vue'

const mobile = inject('mobile')

// 关卡开放时间表（索引：周一=0, 周日=6）
const weekdayIndices = { 周一: 0, 周二: 1, 周三: 2, 周四: 3, 周五: 4, 周六: 5, 周日: 6 }
const time_table = {
  CE: [1, 3, 5, 6], // 龙门币：周二、周四、周六、周日
  AP: [0, 3, 5, 6], // 红票：周一、周四、周六、周日
  SK: [0, 2, 4, 5], // 碳本：周一、周三、周五、周六
  CA: [1, 2, 4, 6], // 技能书：周二、周三、周五、周日
  'PR-A': [0, 3, 4, 6], // 医疗重装：周一、周四、周五、周日
  'PR-B': [0, 1, 4, 5], // 狙击术师：周一、周二、周五、周六
  'PR-C': [2, 3, 5, 6], // 先锋辅助：周三、周四、周六、周日
  'PR-D': [1, 2, 5, 6] // 近卫特种：周二、周三、周六、周日
}

// 关卡过滤开关（活动期间可关闭）
const filterStageByAvailability = ref(true)

// 关卡显示名称
const stageDisplayNames = {
  '': '上次作战',
  Annihilation: '当期剿灭',
  'LS-6': '经验书',
  'CE-6': '龙门币',
  'AP-5': '红票',
  'SK-5': '碳本',
  'CA-5': '技能书',
  'PR-A-1': '医疗重装1',
  'PR-A-2': '医疗重装2',
  'PR-B-1': '狙击术师1',
  'PR-B-2': '狙击术师2',
  'PR-C-1': '先锋辅助1',
  'PR-C-2': '先锋辅助2',
  'PR-D-1': '近卫特种1',
  'PR-D-2': '近卫特种2',
  '1-7': '1-7'
}

const presetStages = Object.keys(stageDisplayNames)

const stageOptions = computed(() =>
  presetStages.map((value) => ({
    label: value ? `${stageDisplayNames[value]} (${value})` : stageDisplayNames[value],
    value
  }))
)

// 判断关卡在某天是否开放
function isStageAvailableOnWeekday(stage, weekdayName) {
  const dayIndex = weekdayIndices[weekdayName]
  if (dayIndex === undefined) return true
  // 常驻关卡每天都开放
  if (stage === '' || stage === 'Annihilation' || stage === '1-7' || stage === 'LS-6') return true
  // 根据时间表判断
  for (const [prefix, days] of Object.entries(time_table)) {
    if (stage.startsWith(prefix)) {
      return days.includes(dayIndex)
    }
  }
  return true
}

// 根据开关过滤关卡选项
function filteredStageOptions(weekday) {
  if (!filterStageByAvailability.value) {
    return stageOptions.value
  }
  return stageOptions.value.filter((opt) => isStageAvailableOnWeekday(opt.value, weekday))
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
    <template #header>
      <n-checkbox v-model:checked="maa_enable">
        <div class="card-title">刷理智周计划</div>
      </n-checkbox>
      <help-text>
        <div>支持的常驻关卡：</div>
        <ul>
          <li>第一章、第八章、第十二章主线；</li>
          <li>全部资源收集关卡。</li>
        </ul>
        <div>资源收集关卡按开放时间过滤，活动期间可关闭过滤。</div>
      </help-text>
      <n-button
        text
        tag="a"
        href="https://m.prts.wiki/w/%E5%85%B3%E5%8D%A1%E4%B8%80%E8%A7%88/%E8%B5%84%E6%BA%90%E6%94%B6%E9%9B%86"
        target="_blank"
        type="primary"
        class="prts-wiki-link"
      >
        <div class="prts-wiki-link-text">PRTS.wiki：关卡一览/资源收集</div>
      </n-button>
    </template>
    <n-form
      :label-placement="mobile ? 'top' : 'left'"
      :show-feedback="false"
      label-width="72"
      label-align="left"
    >
      <n-form-item :show-label="false">
        <n-flex vertical :size="8">
          <n-flex>
            <n-checkbox v-model:checked="maa_expiring_medicine">
              自动使用将要过期（约3天）的理智药
            </n-checkbox>
            <n-checkbox
              v-model:checked="exipring_medicine_on_weekend"
              :disabled="!maa_expiring_medicine"
            >
              仅在周末使用
            </n-checkbox>
          </n-flex>
          <n-flex>
            <n-checkbox v-model:checked="filterStageByAvailability">
              只显示当日开放关卡
            </n-checkbox>
          </n-flex>
        </n-flex>
      </n-form-item>
    </n-form>
    <table>
      <tr>
        <th></th>
        <th>关卡</th>
        <th>每次吃药</th>
      </tr>
      <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
        <td>{{ plan.weekday }}</td>
        <td>
          <n-select
            v-model:value="plan.stage"
            multiple
            filterable
            tag
            :show="false"
            :show-arrow="false"
            :options="filteredStageOptions(plan.weekday)"
            :render-tag="render_tag"
            :on-create="create_tag"
          />
        </td>
        <td>
          <n-input-number v-model:value="plan.medicine" :min="0" :show-button="false">
            <template #suffix>支</template>
          </n-input-number>
        </td>
      </tr>
    </table>
  </n-card>
</template>

<style scoped lang="scss">
table {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 40px;
      text-align: left;
    }

    &:nth-child(3) {
      width: 80px;
    }
  }
}

.tag-mr {
  margin-right: 4px;
}

.prts-wiki-link {
  margin: 8px 0;
  flex-shrink: 1;
  min-width: 0;
}

.prts-wiki-link-text {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>