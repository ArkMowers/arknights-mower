<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
import { inject, ref } from 'vue'

const store = useConfigStore()
const axios = inject('axios')
const mobile = inject('mobile')

const testPushResult = ref('')

const { pushplus_enable, pushplus_token } = storeToRefs(store)

async function test_push() {
  testPushResult.value = '正在发送……'
  const response = await axios.get(`${import.meta.env.VITE_HTTP_URL}/test-pushplus-push`)
  testPushResult.value = response.data
}
</script>

<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="pushplus_enable" class="serverpush-title">
        <div class="card-title-wrapper">
          <span class="card-title">PushPlus推送通知</span>
          <help-text class="card-title-tip">
            什么是PushPlus？参考：
            <n-button text tag="a" href="https://www.pushplus.plus" target="_blank" type="primary">
              https://www.pushplus.plus
            </n-button>
          </help-text>
        </div>
      </n-checkbox>
    </template>

    <template #default>
      <n-form
        :label-placement="mobile ? 'top' : 'left'"
        :show-feedback="false"
        label-width="96"
        label-align="left"
      >
        <n-form-item label="Push Plus Token">
          <n-input v-model:value="pushplus_token" show-password-on="click" type="password" />
        </n-form-item>
      </n-form>
      <n-divider v-if="pushplus_enable" />
      <div v-if="pushplus_enable" class="push-test mt-16">
        <n-button @click="test_push">发送测试通知</n-button>
        <div>{{ testPushResult }}</div>
      </div>
    </template>
  </n-card>
</template>

<style scoped>
.card-title-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  font-weight: 500;
  font-size: 18px;
}

.serverpush-title {
  width: 100%;
}

.push-test {
  display: flex;
  align-items: center;
  gap: 16px;
}

.mt-16 {
  margin-top: 16px;
}
</style>
