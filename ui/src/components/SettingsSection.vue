<script setup>
import { inject } from 'vue'
import { settingsSectionKey } from '@/composables/settingsNavigation'

defineProps({
  id: { type: String, required: true },
  title: { type: String, required: true },
  description: { type: String, default: '' },
  icon: { type: [Object, Function], default: null }
})

const selected = inject(settingsSectionKey, null)
</script>

<template>
  <section
    v-show="!selected || selected === id"
    :id="id"
    class="settings-section"
    :aria-label="selected ? title : undefined"
    :aria-labelledby="selected ? undefined : `${id}-title`"
  >
    <header v-if="!selected" class="settings-section-header">
      <span v-if="icon" class="settings-section-icon" aria-hidden="true">
        <n-icon :component="icon" size="18" />
      </span>
      <div class="settings-section-heading">
        <h2 :id="`${id}-title`">{{ title }}</h2>
        <p v-if="description">{{ description }}</p>
      </div>
    </header>
    <div class="settings-card-grid">
      <slot />
    </div>
  </section>
</template>
