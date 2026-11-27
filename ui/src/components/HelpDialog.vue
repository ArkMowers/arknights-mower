<script setup>
import { computed, ref, watch } from 'vue'
import { useThemeVars } from 'naive-ui'
import LoadingSkeleton from '@/components/LoadingSkeleton.vue'
import { useRetainedDialogContent } from '@/composables/retainedDialogContent'

const props = defineProps({
  section: { type: String, default: '' },
  version: { type: String, default: '' },
  resourceVersion: { type: String, default: '' }
})
const emit = defineEmits(['update:section'])
const themeVars = useThemeVars()
// 关闭时 section 立即清空，弹窗淡出期间仍显示关闭前的标题和内容。
const shownSection = useRetainedDialogContent(() => props.section)
const dialogStyle = computed(() => ({
  width: 'min(760px, calc(100vw - 32px))',
  '--mower-primary': themeVars.value.primaryColor
}))
// 更新日志读取中、读取失败和读完后都占同样的高度，弹窗打开后不会再变大。
const changelogContentStyle = { height: '65dvh' }
const changelogPlaceholderLines = [92, 74, 86, 60, 80, 70, 88, 64]
const title = computed(() => (shownSection.value === 'changelog' ? '更新日志' : '关于 Mower'))
const changelog = ref('')
const loading = ref(false)
const error = ref('')

async function loadChangelog() {
  if (changelog.value || loading.value) return
  loading.value = true
  error.value = ''
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
    error.value = '更新日志加载失败，请重试。'
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
    :content-style="shownSection === 'changelog' ? changelogContentStyle : undefined"
    @update:show="(show) => !show && emit('update:section', '')"
  >
    <template v-if="shownSection === 'about'">
      <h2 class="help-about-name">Arknights Mower</h2>
      <p>明日方舟基建自动化工具</p>
      <dl class="help-about-versions">
        <dt>软件版本</dt>
        <dd>{{ version || '未知' }}</dd>
        <dt>资源版本</dt>
        <dd>{{ resourceVersion || '未载入' }}</dd>
      </dl>
      <n-a
        href="https://github.com/ArkMowers/arknights-mower"
        target="_blank"
        rel="noopener noreferrer"
        >项目源码</n-a
      >
    </template>
    <template v-else-if="shownSection === 'changelog'">
      <LoadingSkeleton v-if="loading" class="help-changelog" label="正在加载更新日志">
        <h1><span class="skeleton-bone skeleton-text" style="--skeleton-w: 6em" /></h1>
        <h2><span class="skeleton-bone skeleton-text" style="--skeleton-w: 11em" /></h2>
        <h3><span class="skeleton-bone skeleton-text" style="--skeleton-w: 3em" /></h3>
        <ul>
          <li v-for="(width, index) in changelogPlaceholderLines" :key="index">
            <span class="skeleton-bone skeleton-text" :style="{ '--skeleton-w': `${width}%` }" />
          </li>
        </ul>
      </LoadingSkeleton>
      <n-alert v-else-if="error" type="error">
        {{ error }}
        <template #action><n-button @click="loadChangelog">重试</n-button></template>
      </n-alert>
      <div v-else class="help-changelog help-changelog--document" v-html="changelog"></div>
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

/* 更新日志有几千个节点，一次排完整份会在弹窗淡入时卡住一百多毫秒。滚动范围外的段落跳过
   排版和绘制，按估计高度占位，显示过一次后记住实际高度。 */
.help-changelog--document > :deep(*) {
  content-visibility: auto;
  contain-intrinsic-size: auto 2em;
}

.help-changelog--document > :deep(:is(ul, ol)) {
  contain-intrinsic-size: auto 15em;
}
</style>
