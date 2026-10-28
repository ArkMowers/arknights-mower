<script setup>
import { computed } from 'vue'
import { i18n } from '@/i18n'
import '@/styles/updates.css'

const props = defineProps({
  channel: String,
  channelKey: String,
  version: String,
  notes: String
})
const { t } = i18n.global
const channelLabel = computed(() => {
  const key = `settings.software.${props.channelKey}`
  return props.channelKey && i18n.global.te(key) ? t(key) : props.channel
})
</script>

<template>
  <section class="update-preview" :aria-label="t('updates.previewAria')">
    <div class="update-preview-meta">
      <span v-if="channelLabel" class="update-caption"
        >{{ t('settings.software.updateChannel') }} · {{ channelLabel }}</span
      >
      <strong v-if="version" class="update-version-value">{{ version }}</strong>
    </div>
    <div class="update-preview-notes">
      <span class="update-caption">{{ t('runtime.changelog') }}</span>
      <pre class="update-notes">{{ notes || t('updates.noNotes') }}</pre>
    </div>
  </section>
</template>
