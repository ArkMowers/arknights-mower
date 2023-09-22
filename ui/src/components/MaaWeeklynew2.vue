<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_weekly_plan1, maa_enable } = storeToRefs(store)

import { NTag } from 'naive-ui'
import { h, ref } from 'vue'

const currentDay = ref(new Date().getDay());
const daysOfWeek = ['周一', '周二', '周三', '周四', '周五', '周六', '周日',];
const updatePlan = (plan1, day) => {
  // 根据勾选状态更新值
  if (plan1[day] === 1) {
    plan1[day] = 2;
  } else {
    plan1[day] = 1;
  }
};

const event_set = ref()

watch(event_set, (newVal) => {
  maa_weekly_plan.value.forEach(plan => {
    plan.medicine = newVal ? plan.medicine_default : plan.medicine_event;
    plan.stage = newVal ? plan.stage_default : plan.stage_event;
  });
});


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
        <div class="card-title">Maa周计划
        </div>
      </n-checkbox><help-text>
        <p>理智药的数量表示“每次调用Maa时吃多少”，不是“每天吃多少”。</p>
        <p>48 小时内过期的理智药会自动使用。</p>
        <p>“每天”从凌晨四点开始，与游戏内一致。</p>
        <span>关卡填写说明：</span>
        <ul>
          <li><b>添加关卡</b>：输入关卡名，按回车键确认。文本变为标签，代表输入成功。</li>
          <li>
            <b>上次作战</b>：输入空格或“上次作战”后回车，生成
            <n-tag closable>上次作战</n-tag> 标签。
          </li>
          <li><b>主线关卡难度</b>：在关卡末尾添加“标准”或“磨难”以指定难度。例：</li>
          <ul>
            <li><n-tag closable>12-17标准</n-tag> 表示12-17标准难度。</li>
            <li><n-tag closable>12-17磨难</n-tag> 表示12-17磨难难度。</li>
          </ul>
          <li>
            <b>当期剿灭</b>：输入“当期剿灭”后回车，生成 <n-tag closable>当期剿灭</n-tag> 标签。
          </li>
          <li>
            <b>信用作战</b>：若信用作战选项已开启，且当日计划不包含
            <n-tag closable>上次作战</n-tag>，则自动进行信用作战。
          </li>
          <li>
            <b>多个关卡</b>：填入多个关卡时，按顺序依次刷取所有关卡。关卡无法刷取或刷取结束后，继续尝试下一关卡。例：
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
    </template>


    <table>
      <tr>
        <td></td>
        <td><n-tooltip placement="top-start" trigger="click">
            <template #trigger>
              <n-button @click="event_set = true">使用默认配置</n-button>
            </template>
            <span> 成了！</span>
          </n-tooltip></td>
        <td>理智药</td>
        <td><n-tooltip placement="top-start" trigger="click">
            <template #trigger><n-button @click="event_set = false">使用活动配置</n-button>
            </template>
            <span> 成了！</span>
          </n-tooltip></td>
        <td>理智药</td>
      </tr>
      <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
        <td><n-h4>{{ plan.weekday }}</n-h4></td>
        <td>
          <n-select v-model:value="plan.stage_default" multiple filterable tag :show="false" :show-arrow="false"
            :render-tag="render_tag" :on-create="create_tag" />
        </td>
        <td><n-input-number v-model:value="plan.medicine_default" :min="0" /></td>
        <td>
          <n-select v-model:value="plan.stage_event" multiple filterable tag :show="false" :show-arrow="false"
            :render-tag="render_tag" :on-create="create_tag" />
        </td>
        <td><n-input-number v-model:value="plan.medicine_event" :min="0" /></td>
      </tr>
    </table>

  </n-card>
</template>


<style scoped lang="scss">
.newtaskstyle {
  table {
    width: 100%;
    text-align: center;

    td {
      min-width: 35px;
      line-height: 2;

      &:nth-child(1) {
        width: 30%;
      }

      &:nth-child(n + 2) {
        width: 10%;

      }
    }
  }
}


hide-span {
  display: none;
}

.old-task-style {
  flex: 1;
  padding: 0 10px;

  >table {
    width: 100%;

    td {
      &:nth-child(1) {
        width: 10%;
        min-width: 45px;
      }

      &:nth-child(2) {
        width: 35%;
      }

      &:nth-child(3) {
        width: 10%;
        min-width: 100px;
      }

      &:nth-child(4) {
        width: 35%;
      }

      &:nth-child(5) {
        width: 10%;
        min-width: 100px;
      }
    }
  }
}

h4 {
  margin: 0;
}

ul {
  padding-left: 24px;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
  margin-right: 8px;
}


.big-table {
  margin-top: 10px;
  width: 400px;

  th {
    text-align: center;
  }

  td {
    height: 24px;

    &:nth-child(1) {
      width: 70px;
      text-align: center;
    }

    &:nth-child(2) {
      padding-left: 18px;
    }
  }
}

.tag-mr {
  margin-right: 4px;
}
</style>
