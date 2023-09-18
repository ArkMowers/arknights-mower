<script setup>

import {storeToRefs} from "pinia";
import { useConfigStore } from '@/stores/config'
const store = useConfigStore()
const { skland_enable ,skland_info} = storeToRefs(store)

function add_account(){
  return {
    isCheck: true,
    account: '',
    password: ''
  }
}

</script>


<template>
  <n-card>
    <template #header>
      <n-checkbox v-model:checked="skland_enable">
        <div class="card-title">森空岛签到</div>
      </n-checkbox>
    </template>

    <n-dynamic-input v-model:value="skland_info" :on-create="add_account">
      <template #create-button-default> 添加森空岛账号 </template>
      <template #default="{ value }">
        <div style="display: flex; align-items: center; width: 100%">
          <n-checkbox v-model:checked="value.isCheck" style="margin-right: 12px" />
          <n-input style="margin-right: 10px;" v-model:value="value.account" type="text" placeholder="账号"/>

          <n-input v-model:value="value.password" type="password" show-password-on="click" placeholder="密码"/>
        </div>
      </template>
    </n-dynamic-input>
  </n-card>


</template>


<style>
.card-title {
  font-weight: 500;
  font-size: 18px;
}



</style>

