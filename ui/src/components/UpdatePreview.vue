<script setup>
import '@/styles/updates.css'

defineProps({
  channel: String,
  version: String,
  notes: String
})
</script>

<template>
  <section class="update-preview" aria-label="更新预览">
    <div class="update-preview-meta">
      <span v-if="channel" class="update-caption">更新渠道 · {{ channel }}</span>
      <strong v-if="version" class="update-version-value">{{ version }}</strong>
    </div>
    <div class="update-preview-notes">
      <span class="update-caption">更新日志</span>
      <pre class="update-notes">{{ notes || '此版本未提供更新日志。' }}</pre>
    </div>
  </section>
</template>
