<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_enable } = storeToRefs(store)

import { NTag } from 'naive-ui'
import { h } from 'vue'

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
    { default: () => (option.label == '' ? '（上次作战）' : option.label) }
  )
}

function create_tag(label) {
  if (label == ' ') {
    return {
      label: '（上次作战）',
      value: ''
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
        <div class="card-title">Maa周计划</div>
      </n-checkbox>
    </template>
    <span>关卡填写说明：</span>
    <ul>
      <li><b>基本操作</b>：输入关卡名，按回车键确认。文本变为标签，代表输入成功。</li>
      <li><b>上次作战</b>：输入空格后回车，生成（上次作战）标签。</li>
      <li>
        <b>多个关卡</b>
        ：填入多个关卡时，按顺序依次刷取所有关卡。关卡无法刷取或刷取结束后，继续尝试下一关卡。例：
        <ul>
          <li>HE-7、（上次作战）：刷活动关HE-7，若活动未开放，则刷上一关。</li>
          <li>AP-5、1-7：刷红票本AP-5，剩余体力刷1-7。</li>
        </ul>
      </li>
      <li><b>不刷理智</b>：留空表示不刷理智。</li>
    </ul>
    <table>
      <tr v-for="plan in maa_weekly_plan" :key="plan.weekday">
        <td>
          <n-h4>{{ plan.weekday }}</n-h4>
        </td>
        <td>关卡</td>
        <td>
          <n-select
            v-model:value="plan.stage"
            multiple
            filterable
            tag
            :show="false"
            :show-arrow="false"
            :render-tag="render_tag"
            :on-create="create_tag"
          />
        </td>
        <td>理智药</td>
        <td>
          <n-input-number v-model:value="plan.medicine" :min="0" />
        </td>
      </tr></table
  ></n-card>
</template>

<style scoped lang="scss">
h4 {
  margin: 0;
}

ul {
  padding-left: 24px;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
}

table {
  width: 100%;

  td {
    &:nth-child(1) {
      width: 40px;
    }

    &:nth-child(2) {
      width: 32px;
    }

    &:nth-child(3) {
      padding-right: 8px;
    }

    &:nth-child(4) {
      width: 50px;
    }

    &:nth-child(5) {
      width: 90px;
    }
  }
}
</style>
