<template>
  <Advanced />
  <External />
</template>

<script setup>
const Advanced = defineAsyncComponent(() => import('@/pages/Advanced.vue'))
const External = defineAsyncComponent(() => import('@/pages/External.vue'))
</script>
