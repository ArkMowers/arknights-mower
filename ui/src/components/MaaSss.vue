<script setup>
import { inject } from 'vue'

const mobile = inject('mobile')

import { storeToRefs } from 'pinia'
import { useConfigStore } from '@/stores/config'

const store = useConfigStore()

const { sss } = storeToRefs(store)

import { file_dialog } from '@/utils/dialog'

async function select_copilot_path() {
  const file_path = await file_dialog()
  if (file_path) {
    sss.value.copilot = file_path
  }
}
</script>

<template>
  <n-form
    :label-placement="mobile ? 'top' : 'left'"
    :show-feedback="false"
    label-width="72"
    label-align="left"
  >
    <n-form-item>
      <template #label>
        <span>关卡</span>
        <help-text>
          <n-image src="/help/sss-type.png" />
        </help-text>
      </template>
      <n-radio-group v-model:value="sss.type">
        <n-space>
          <n-radio :value="i" v-for="i in 2" :key="i">{{ i }}</n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
    <n-form-item label="导能单元">
      <n-radio-group v-model:value="sss.ec">
        <n-space>
          <n-radio :value="i" v-for="i in 3" :key="i">{{ i }}</n-radio>
        </n-space>
      </n-radio-group>
    </n-form-item>
    <n-form-item label="作业路径">
      <n-input type="textarea" :autosize="true" v-model:value="sss.copilot" />
      <n-button @click="select_copilot_path" class="dialog-btn">...</n-button>
    </n-form-item>
    <n-form-item label="循环次数">
      <n-input-number v-model:value="sss.loop">
        <template #suffix>次</template>
      </n-input-number>
    </n-form-item>
  </n-form>
</template>
