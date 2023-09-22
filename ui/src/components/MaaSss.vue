<script setup>
import { inject } from 'vue'

const mobile_mode = inject('mobile_mode')
</script>

<template>
  <n-form :label-placement="mobile ? 'top' : 'left'">
    <n-form-item>
      <template #label> wuhu </template>
      <template #default> takeoff </template>
    </n-form-item>
  </n-form>
</template>
