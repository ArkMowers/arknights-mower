<template>
  <MowerSettings />
  <BasementSettings />
  <Email />
  <Recruit />

  <MaaBasic />
  <MaaWeekly />
  <Clue />
  <Maahugmission />
</template>

<script setup>
const BasementSettings = defineAsyncComponent(() => import('@/components/BasementSettings.vue'))
const Clue = defineAsyncComponent(() => import('@/components/Clue.vue'))
const Email = defineAsyncComponent(() => import('@/components/Email.vue'))
const MaaBasic = defineAsyncComponent(() => import('@/components/MaaBasic.vue'))
const Maahugmission = defineAsyncComponent(() => import('@/components/Maahugmission.vue'))
const MaaWeekly = defineAsyncComponent(() => import('@/components/MaaWeekly.vue'))
const MowerSettings = defineAsyncComponent(() => import('@/components/MowerSettings.vue'))
const Recruit = defineAsyncComponent(() => import('@/components/Recruit.vue'))
</script>
