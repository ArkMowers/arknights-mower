<script setup>
import { watch } from 'vue'
import { useMessage } from 'naive-ui'
import { useMowerStore } from '@/stores/mower'

const mower = useMowerStore()
const message = useMessage()
watch(
  () => mower.plan_warnings,
  (warnings) => {
    if (!warnings.length) return
    mower.plan_warnings = []
    for (const warning of warnings) {
      message.warning(warning, { duration: 0, closable: true })
    }
  },
  { immediate: true, flush: 'sync' }
)
</script>

<template><span v-if="false" /></template>
