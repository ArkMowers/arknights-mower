<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global

import { computed, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'

const props = defineProps({
  section: { type: String, default: '' },
  version: { type: String, default: '' },
  resourceVersion: { type: String, default: '' }
})
const emit = defineEmits(['update:section'])
const themeVars = useThemeVars()
const dialogStyle = computed(() => ({
  width: 'min(760px, calc(100vw - 32px))',
  '--mower-primary': themeVars.value.primaryColor
}))
const title = computed(() =>
  props.section === 'changelog' ? t('runtime.changelog') : t('runtime.aboutMower')
)
const changelog = ref('')
const loading = ref(false)
const failed = ref(false)
const error = computed(() => (failed.value ? t('runtime.changelogFailed') : ''))

async function loadChangelog() {
  if (changelog.value || loading.value) return
  loading.value = true
  failed.value = false
  try {
    const [{ default: source }, { default: markdownit }, { default: externalLink }] =
      await Promise.all([
        import('virtual:mower-changelog'),
        import('markdown-it'),
        import('markdown-it-external-link')
      ])
    changelog.value = markdownit({ html: false, breaks: true })
      .use(externalLink, { externalTarget: '_blank', rel: 'noopener noreferrer' })
      .render(source)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}

watch(
  () => props.section,
  (section) => {
    if (section === 'changelog') void loadChangelog()
  },
  { immediate: true }
)
</script>

<template>
  <n-modal
    :show="Boolean(section)"
    preset="card"
    :title="title"
    class="help-dialog"
    :style="dialogStyle"
    :content-style="section === 'changelog' ? { maxHeight: '65dvh' } : undefined"
    @update:show="(show) => !show && emit('update:section', '')"
  >
    <template v-if="section === 'about'">
      <h2 class="help-about-name">Arknights Mower</h2>
      <p>{{ t('runtime.mowerDescription') }}</p>
      <dl class="help-about-versions">
        <dt>{{ t('runtime.softwareVersion') }}</dt>
        <dd>{{ version || t('runtime.unknown') }}</dd>
        <dt>{{ t('runtime.resourceVersion') }}</dt>
        <dd>{{ resourceVersion || t('runtime.notLoaded') }}</dd>
      </dl>
      <n-a
        href="https://github.com/ArkMowers/arknights-mower"
        target="_blank"
        rel="noopener noreferrer"
        >{{ t('runtime.projectSource') }}</n-a
      >
    </template>
    <template v-else-if="section === 'changelog'">
      <p v-if="loading" role="status">{{ t('runtime.loadingChangelog') }}</p>
      <n-alert v-else-if="error" type="error">
        {{ error }}
        <template #action
          ><n-button @click="loadChangelog">{{ t('runtime.retry') }}</n-button></template
        >
      </n-alert>
      <div v-else class="help-changelog" v-html="changelog"></div>
    </template>
  </n-modal>
</template>

<style scoped>
.help-about-name {
  margin-top: 0;
}

.help-about-versions {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px 20px;
}

.help-about-versions dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.help-changelog {
  overflow-wrap: anywhere;
  line-height: 1.7;
  user-select: text;
}

.help-changelog :deep(a) {
  color: var(--mower-primary);
}

.help-changelog :deep(h1:first-child) {
  margin-top: 0;
}
</style>
