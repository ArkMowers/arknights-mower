<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()

const { adb, package_type, free_blacklist, plan_file } = storeToRefs(store)
</script>

<template>
  <div class="home-container">
    <table>
      <tr>
        <td>服务器：</td>
        <td>
          <n-radio-group v-model:value="package_type">
            <n-radio value="official">官服</n-radio>
            <n-radio value="bilibili">BiliBili服</n-radio>
          </n-radio-group>
        </td>
        <td></td>
      </tr>
      <tr>
        <td>adb连接地址：</td>
        <td>
          <n-input v-model:value="adb"></n-input>
        </td>
        <td></td>
      </tr>
      <tr>
        <td>宿舍黑名单：</td>
        <td>
          <n-input v-model:value="free_blacklist"></n-input>
        </td>
        <td></td>
      </tr>
      <tr>
        <td>排班表：</td>
        <td>
          <n-input v-model:value="plan_file"></n-input>
        </td>
        <td>
          <n-button>...</n-button>
        </td>
      </tr>
    </table>
    <n-log class="log" :log="'114514'" />
    <div>
      <n-button type="primary">开始执行</n-button>
    </div>
  </div>
</template>

<style scoped>
.home-container {
  padding: 0 12px 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.log {
  flex-grow: 1;
  border: 1px solid rgb(224, 224, 230);
  border-radius: 3px;
  padding: 4px;
}
</style>
