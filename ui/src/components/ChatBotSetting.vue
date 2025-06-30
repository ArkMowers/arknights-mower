<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { ai_key, ai_type } = storeToRefs(store)
const type_options = [{ label: 'Deepseek', value: 'deepseek' }]
</script>
<template>
  <n-card>
    <template #header>
      <div class="card-title">本地 AI 助手</div>
      <help-text
        ><div>目前仅支持Deepseek</div>
        <div>
          Deepseek 密钥请前往
          <a href="https://platform.deepseek.com/api_keys" target="_blank">Deepseek 官网</a> 获取，
          充值1元即可使用很久
        </div>
      </help-text>
    </template>
    <n-form label-placement="left" label-width="auto">
      <n-form-item label="AI 类型">
        <n-select v-model:value="ai_type" :options="type_options" />
      </n-form-item>
      <n-form-item label="API 密钥">
        <n-input
          type="password"
          v-model:value="ai_key"
          placeholder="请输入API密钥"
          show-password-on="click"
        />
      </n-form-item>
    </n-form>
  </n-card>
</template>
<<<<<<< HEAD
<style scoped>
a {
  color: #f5f5f5; /* 或你喜欢的浅色 */
  text-decoration: underline;
}
a:visited {
  color: #f5f5f5;
}
a:hover {
  color: #ffd700;
}
</style>
======= >>>>>>> 43db50353535c87d4eb6fd690fb9ac168a4abd55
