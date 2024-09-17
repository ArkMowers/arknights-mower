<script setup>
import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()
const { maa_weekly_plan, maa_enable, maa_expiring_medicine, exipring_medicine_on_weekend } =
  storeToRefs(store)

import { NTag } from 'naive-ui'
import { h, inject } from 'vue'

const mobile = inject('mobile')

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
