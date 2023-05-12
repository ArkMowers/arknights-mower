<script setup>
import { useConfigStore } from '@/stores/config'
import { storeToRefs } from 'pinia'

const store = useConfigStore()

const { mail_enable, account, pass_code, maa_enable, maa_path, maa_adb_path, maa_weekly_plan } =
  storeToRefs(store)
</script>

<template>
  <div class="home-container">
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="mail_enable">
          <div class="card-title">邮件提醒</div>
        </n-checkbox>
      </template>
      <template #default>
        <table>
          <tr>
            <td class="table-space">QQ邮箱</td>
            <td class="table-space"><n-input v-model:value="account"></n-input></td>
            <td class="table-space">授权码</td>
            <td><n-input v-model:value="pass_code"></n-input></td>
          </tr>
        </table>
      </template>
    </n-card>
    <n-card>
      <template #header>
        <n-checkbox v-model:checked="maa_enable">
          <div class="card-title">MAA</div>
        </n-checkbox>
      </template>
      <template #default>
        <table>
          <tr>
            <td class="table-space">MAA地址</td>
            <td class="table-space"><n-input v-model:value="maa_path"></n-input></td>
            <td class="table-space">adb地址</td>
            <td><n-input v-model:value="maa_adb_path"></n-input></td>
          </tr>
        </table>
        <n-h3>周计划</n-h3>
        <table>
          <tr v-for="plan in maa_weekly_plan">
            <td class="table-space">
              <n-h4>{{ plan.weekday }}</n-h4>
            </td>
            <td>关卡：</td>
            <td class="table-space">
              <n-input v-model:value="plan.stage"></n-input>
            </td>
            <td>理智药：</td>
            <td>
              <n-input-number v-model:value="plan.medicine"></n-input-number>
            </td>
          </tr>
        </table>
      </template>
    </n-card>
  </div>
</template>

<style scoped>
h4 {
  margin: 0;
}

.card-title {
  font-weight: 500;
  font-size: 16px;
}
</style>
