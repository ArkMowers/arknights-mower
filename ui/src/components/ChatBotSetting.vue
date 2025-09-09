<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'
const store = useConfigStore()
const { ai_key, ai_type, ai_api_url, ai_model } = storeToRefs(store)
const type_options = [{ label: 'Deepseek', value: 'deepseek' },{ label: '自定义', value: '自定义' }]
</script>
<template>
  <n-card>
    <template #header>
      <div class="card-title">本地 AI 助手</div>
      <help-text
        ><div>选择自定义可配置API地址和模型</div>
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
      
      <n-form-item label="API 地址" v-if="ai_type === '自定义'">
        <n-input
          v-model:value="ai_api_url"
          placeholder="请输入自定义API地址"
          style="width: 100%"
        />
      </n-form-item>
      
      <n-form-item label="模型名称" v-if="ai_type === '自定义'">
        <n-input
          v-model:value="ai_model"
          placeholder="请输入自定义模型名称"
          style="width: 100%"
        />
      </n-form-item>
    </n-form>
  </n-card>
</template>
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
