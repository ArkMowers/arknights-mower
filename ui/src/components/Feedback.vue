<script setup>
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
  { label: '功能建议', value: '功能建议' }
]

async function submitFeedback() {
  formRef.value.validate(async (errors) => {
    if (!errors) {
      // Submit logic here
      console.log('表单数据:', feedbackData.value)
      const req = feedbackData.value
      const msg = (await axios.post(`${import.meta.env.VITE_HTTP_URL}/submit_feedback`, req)).data
      if (msg == '邮件发送成功！') {
        alert(msg + '，可在反馈表查看已有记录；邮件内容不会自动写入表格。')
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
  type: [{ required: true, message: '请选择反馈类型', trigger: 'blur' }],
  startTime: [
    {
      validator: (rule, value) => {
        if (feedbackData.value.type === 'Bug' && !value) {
          return new Error('开始时间是必填的')
        }
        return true
      },
      trigger: 'blur'
    }
  ],
  endTime: [
    {
      validator: (rule, value) => {
        if (feedbackData.value.type === 'Bug' && !value) return new Error('结束时间是必填')
        const maxEndDate = new Date(feedbackData.value.startTime + 15 * 60 * 1000)

        if (value > maxEndDate) {
          return new Error('结束时间不能超过开始时间15分钟')
        }
        const curDate = new Date()
        if (value > curDate) {
          return new Error('结束时间不能超过现在时间')
        }
        return true
      },
      trigger: 'blur'
    }
  ],
  description: [
    { required: true, message: '请输入反馈内容', trigger: 'blur' },
    { min: 10, message: '内容至少需要10个字符', trigger: 'blur' }
  ],
  acknowledged1: [
    {
      validator: (rule, value) => {
        if (!value) return new Error('请确认您已阅读相关要求')
        return true
      },
      trigger: 'change'
    }
  ],
  acknowledged2: [
    {
      validator: (rule, value) => {
        if (!value) return new Error('请确认您已阅读相关要求')
        return true
      },
      trigger: 'change'
    }
  ],
  acknowledged3: [
    {
      validator: (rule, value) => {
        if (!value) return new Error('请确认您已阅读相关要求')
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
      alert('复制失败，请手动点击按钮！')
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
        <h3>反馈</h3>
      </template>
      <n-space vertical :size="8" style="margin-bottom: 16px">
        <n-a
          href="https://docs.qq.com/sheet/DUEJ6UWN5VFVRU0dG?tab=BB08J2"
          target="_blank"
          rel="noopener noreferrer"
        >
          打开 Mower 反馈表
        </n-a>
        <n-text depth="3"
          >此处提交通过已配置邮箱发送给开发组；反馈表可单独查阅，填写需相应编辑权限。</n-text
        >
      </n-space>
      <n-form-item path="acknowledged1" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged1">
          我已在 Mower 设置 → 软件更新中检查当前版本，并查看相关更新说明
        </n-checkbox>
      </n-form-item>
      <n-form-item path="acknowledged2" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged2">
          我已查看反馈表和相关讨论，核对是否已有相同问题
        </n-checkbox>
      </n-form-item>
      <n-form-item path="acknowledged3" class="checkbox-wrapper">
        <n-checkbox v-model:checked="feedbackData.acknowledged3">
          我会提供版本、实际现象、期望行为和必要日志，并去除敏感信息
        </n-checkbox>
      </n-form-item>
      <n-form-item label="反馈类型" path="type">
        <n-select v-model:value="feedbackData.type" :options="feedbackTypeOptions" />
      </n-form-item>

      <template v-if="showTimeFields">
        <div class="time-row">
          <n-form-item label="开始时间" path="startTime" v-model:show="showTimeFields">
            <n-date-picker
              v-model:value="feedbackData.startTime"
              type="datetime"
              format="yyyy-MM-dd HH:mm"
            />
          </n-form-item>

          <n-form-item label="结束时间" path="endTime" style="margin-top: 0">
            <n-date-picker
              v-model:value="feedbackData.endTime"
              type="datetime"
              format="yyyy-MM-dd HH:mm"
            />
          </n-form-item>
        </div>
      </template>

      <!-- 反馈内容输入 -->
      <n-form-item label="反馈内容（期望+实际）" path="description">
        <n-input
          type="textarea"
          v-model:value="feedbackData.description"
          :autosize="{ minRows: 2, maxRows: 6 }"
          placeholder="请详描述你期望Mower的操作是什么+实际Mower的操作"
        />
      </n-form-item>

      <!-- 操作按钮 -->
      <div class="button_row">
        <n-button type="warning" @click="submitFeedback">提交</n-button>
        <n-button @click="copy_descrioption">复制反馈内容</n-button>
        <n-button @click="reset">重置</n-button>
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
