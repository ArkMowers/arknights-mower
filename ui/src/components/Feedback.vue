<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

defineOptions({ name: 'MowerFeedback' })

import { inject, ref, computed } from 'vue'
import axios from 'axios'
const show = inject('show_feedback')

const feedbackData = ref({
  acknowledged1: false,
  acknowledged2: false,
  acknowledged3: false,
  type: 'Bug',
  startTime: null,
  endTime: null,
  description: ''
})
const formRef = ref(null)
const feedbackTypeOptions = [
  { label: 'Bug', value: 'Bug' },
  {
    get label() {
      return t('runtime.featureSuggestion')
    },
    value: '功能建议'
  }
]

async function submitFeedback() {
  formRef.value.validate(async (errors) => {
    if (!errors) {
      // Submit logic here
      console.log('表单数据:', feedbackData.value)
      const req = feedbackData.value
      const msg = (await axios.post(`${import.meta.env.VITE_HTTP_URL}/submit_feedback`, req)).data
      if (msg == '邮件发送成功！') {
        alert(msg + t('runtime.feedbackAfterSend'))
        copy_descrioption()
      } else {
        alert(msg)
      }
    } else {
      console.log('验证失败:', errors)
    }
  })
}

// 表单验证规则
const rules = {
  type: [
    {
      required: true,
      get message() {
        return t('runtime.selectFeedbackType')
      },
      trigger: 'blur'
    }
  ],
  startTime: [
    {
      validator: (rule, value) => {
        if (feedbackData.value.type === 'Bug' && !value) {
          return new Error(t('runtime.startTimeRequired'))
        }
        return true
      },
      trigger: 'blur'
    }
  ],
  endTime: [
    {
      validator: (rule, value) => {
        if (feedbackData.value.type === 'Bug' && !value)
          return new Error(t('runtime.endTimeRequired'))
        const maxEndDate = new Date(feedbackData.value.startTime + 15 * 60 * 1000)

        if (value > maxEndDate) {
          return new Error(t('runtime.feedback15Minutes'))
        }
        const curDate = new Date()
        if (value > curDate) {
          return new Error(t('runtime.feedbackFutureEnd'))
        }
        return true
      },
      trigger: 'blur'
    }
  ],
  description: [
    {
      required: true,
      get message() {
        return t('runtime.feedbackContentRequired')
      },
      trigger: 'blur'
    },
    {
      min: 10,
      get message() {
        return t('runtime.feedbackMinimumLength')
      },
      trigger: 'blur'
    }
  ],
  acknowledged1: [
    {
      validator: (rule, value) => {
        if (!value) return new Error(t('runtime.feedbackReadAcknowledgment'))
        return true
      },
      trigger: 'change'
    }
  ],
  acknowledged2: [
    {
      validator: (rule, value) => {
        if (!value) return new Error(t('runtime.feedbackReadAcknowledgment'))
        return true
      },
      trigger: 'change'
    }
  ],
  acknowledged3: [
    {
      validator: (rule, value) => {
        if (!value) return new Error(t('runtime.feedbackReadAcknowledgment'))
        return true
      },
      trigger: 'change'
    }
  ]
}
const showTimeFields = computed(() => feedbackData.value.type === 'Bug')
function reset() {
  feedbackData.value.type = 'Bug'
  feedbackData.value.startTime = null
  feedbackData.value.endTime = null
  feedbackData.value.description = ''
  feedbackData.value.acknowledged1 = false
  feedbackData.value.acknowledged2 = false
  feedbackData.value.acknowledged3 = false
}
function copy_descrioption() {
  navigator.clipboard
    .writeText(feedbackData.value.description)
    .then(() => {})
    .catch((err) => {
      console.error('复制失败：', err)
      alert(t('runtime.feedbackCopyFailed'))
    })
}
</script>

<template>
  <n-modal v-model:show="show" preset="card" transform-origin="center" style="width: auto">
    <n-form
      :model="feedbackData"
      label-width="100px"
      @submit.prevent="submitFeedback"
      :rules="rules"
      ref="formRef"
    >
      <template #header>
        <h3>{{ t('runtime.feedback') }}</h3>
      </template>
      <n-space vertical :size="8" style="margin-bottom: 16px">
        <n-a
          href="https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2"
          target="_blank"
          rel="noopener noreferrer"
          >{{ t('runtime.feedbackSheet') }}</n-a
        >
        <n-text depth="3">{{ t('runtime.feedbackDeliveryHelp') }}</n-text>
      </n-space>
      <n-form-item path="acknowledged1" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged1">{{
          t('runtime.feedbackVersionAcknowledgment')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item path="acknowledged2" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged2">{{
          t('runtime.feedbackDuplicateAcknowledgment')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item path="acknowledged3" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged3">{{
          t('runtime.feedbackDetailsAcknowledgment')
        }}</n-checkbox>
      </n-form-item>
      <n-form-item :label="t('runtime.feedbackType')" path="type">
        <n-select v-model:value="feedbackData.type" :options="feedbackTypeOptions" />
      </n-form-item>

      <template v-if="showTimeFields">
        <div class="time-row">
          <n-form-item
            :label="t('runtime.startTime')"
            path="startTime"
            v-model:show="showTimeFields"
          >
            <n-date-picker
              v-model:value="feedbackData.startTime"
              type="datetime"
              format="yyyy-MM-dd HH:mm"
            />
          </n-form-item>

          <n-form-item :label="t('runtime.endTime')" path="endTime" style="margin-top: 0">
            <n-date-picker
              v-model:value="feedbackData.endTime"
              type="datetime"
              format="yyyy-MM-dd HH:mm"
            />
          </n-form-item>
        </div>
      </template>

      <!-- 反馈内容输入 -->
      <n-form-item :label="t('runtime.feedbackDescription')" path="description">
        <n-input
          type="textarea"
          v-model:value="feedbackData.description"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :placeholder="t('runtime.feedbackPlaceholder')"
        />
      </n-form-item>

      <!-- 操作按钮 -->
      <div class="button_row">
        <n-button type="warning" @click="submitFeedback">{{ t('runtime.submit') }}</n-button>
        <n-button @click="copy_descrioption">{{ t('runtime.copyFeedback') }}</n-button>
        <n-button @click="reset">{{ t('runtime.reset') }}</n-button>
      </div>
    </n-form>
  </n-modal>
</template>

<style scoped lang="scss">
.button_row {
  margin-top: 8px;
}

.checkbox-wrapper {
  display: flex;
  /* 让复选框与内容水平对齐 */
  align-items: center;
  /* 垂直对齐 */
  gap: 8px;
  /* 控制复选框与文字的间距 */
}

.time-row {
  display: flex;
  /* 横向排列 */
  gap: 16px;
  /* 设置开始和结束时间之间的间距 */
  align-items: center;
}
</style>
