<script setup>
import { computed, inject, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import SearchIcon from '@vicons/fluent/es/Search24Regular'
import { routeLocationKey } from 'vue-router'
import { settingsNavigationKey, settingsSectionKey } from '@/composables/settingsNavigation'
import { matchesSettingsSearch, settingsElementKeywords } from '@/utils/settingsSearch'
import '@/styles/settings.css'

const props = defineProps({
  title: { type: String, required: true },
  description: { type: String, default: '' },
  navLabel: { type: String, required: true },
  // [{ id, title, icon }]
  sections: { type: Array, required: true }
})

const mobile = inject('mobile', ref(false))
const navigation = inject(settingsNavigationKey, null)
const route = inject(routeLocationKey, null)
const active = ref(props.sections[0]?.id)
const currentSection = computed(() => props.sections.find((section) => section.id === active.value))
provide(settingsSectionKey, navigation ? active : null)
let container = null
let scrollTarget = null
let lockUntil = 0
let scrollFallback = null
let indexObserver = null

const query = ref('')
const index = ref([])
const results = computed(() => {
  if (!query.value.trim()) return []
  return index.value
    .filter((entry) => matchesSettingsSearch(query.value, entry.haystack))
    .sort(
      (left, right) =>
        Number(matchesSettingsSearch(query.value, right.label)) -
          Number(matchesSettingsSearch(query.value, left.label)) || left.priority - right.priority
    )
    .slice(0, 30)
})

function text(node) {
  return node?.textContent.replace(/\s+/g, ' ').trim() ?? ''
}

// 从已挂载分区收集字段和选项；条件字段可在所属卡片声明搜索词。
function buildIndex() {
  const entries = []
  const seen = new Set()
  for (const section of props.sections) {
    const root = document.getElementById(section.id)
    if (!root) continue
    entries.push({
      key: section.id,
      label: section.title,
      path: props.title,
      element: root,
      priority: 2,
      haystack: section.title
    })
    for (const card of root.querySelectorAll('.n-card')) {
      const header = card.querySelector(':scope > .n-card-header .n-card-header__main')
      const cardTitle = text(header?.querySelector('.card-title') ?? header) || section.title
      const labels = [
        [cardTitle, card],
        ...[
          ...card.querySelectorAll('.n-form-item-label, .n-checkbox__label, [data-settings-label]')
        ].map((label) => [
          (
            label.getAttribute('data-settings-label') ||
            text(label.querySelector('.settings-row-copy > span') ?? label)
          ).replace(/[?？：:]\s*$/, ''),
          label.closest('.n-form-item, .n-checkbox') ?? label
        ])
      ]
      for (const [label, element] of labels) {
        const key = `${section.id}|${cardTitle}|${label}`
        if (!label || seen.has(key)) continue
        seen.add(key)
        const path = label === cardTitle ? section.title : `${section.title} › ${cardTitle}`
        entries.push({
          key,
          label,
          path,
          element,
          priority: element === card ? 1 : 0,
          haystack: `${label} ${path} ${settingsElementKeywords(element)}`
        })
      }
    }
  }
  index.value = entries
}

// 后续输入也重新收集，包含异步加载和开关切换后新出现的字段。
watch(
  query,
  (value) => {
    if (value.trim()) buildIndex()
  },
  { flush: 'post' }
)

async function reveal(entry) {
  query.value = ''
  const section = entry.element.closest('.settings-section')
  if (section) active.value = section.id
  await nextTick()
  scrollToElement(entry.element)
  entry.element.classList.remove('settings-search-hit')
  void entry.element.offsetWidth
  entry.element.classList.add('settings-search-hit')
  setTimeout(() => entry.element.classList.remove('settings-search-hit'), 1600)
}

function submit() {
  if (results.value.length) reveal(results.value[0])
}
function searchKey(event) {
  if (event.key === 'Escape') query.value = ''
  if (event.key === 'Enter') {
    event.preventDefault()
    submit()
  }
}

async function jump(id) {
  if (!props.sections.some((section) => section.id === id)) return
  clearTimeout(scrollFallback)
  active.value = id
  await nextTick()
  const target = document.getElementById(id)
  if (!target) return
  if (navigation) {
    container = scrollParent(target)
    container.scrollTop = 0
  } else {
    scrollToElement(target)
  }
}

function scrollToElement(target) {
  clearTimeout(scrollFallback)
  // 平滑滚动期间不让滚动监听把高亮拉回途经的分类
  lockUntil = Date.now() + 700
  // 从分区找滚动容器，避免命中卡片内部的局部滚动区域
  container = scrollParent(target.closest('.settings-section') ?? target)
  const frame = container
  const bounds = frame.getBoundingClientRect()
  const scale = frame.offsetHeight ? bounds.height / frame.offsetHeight : 1
  const offset = (target.getBoundingClientRect().top - bounds.top) / (scale || 1)
  // 为移动端顶部返回栏，以及独立布局的吸顶分类导航留出空间。
  const aside = document.querySelector('.settings-aside')
  const content = document.querySelector('.settings-content')
  const stacked =
    aside && content && aside.getBoundingClientRect().right > content.getBoundingClientRect().left
  const mobileHeader = document.querySelector('.mobile-settings-header')
  const top =
    frame.scrollTop +
    offset -
    16 -
    (stacked ? aside.offsetHeight : 0) -
    (mobileHeader?.offsetHeight ?? 0)
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const start = frame.scrollTop
  frame.scrollTo({ top, behavior: reduce ? 'auto' : 'smooth' })
  // 部分 WebView 不执行平滑滚动；短时间内完全没动就直接跳转
  scrollFallback = setTimeout(() => {
    if (frame.scrollTop === start) frame.scrollTop = top
  }, 120)
}

function scrollParent(element) {
  for (let node = element.parentElement; node; node = node.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node
  }
  return document.scrollingElement || document.documentElement
}

function updateActive() {
  if (navigation) return
  if (!container || Date.now() < lockUntil) return
  const bottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 4
  if (bottom) {
    active.value = props.sections.at(-1)?.id
    return
  }
  const bounds = container.getBoundingClientRect()
  const scale = container.offsetHeight ? bounds.height / container.offsetHeight : 1
  const line = bounds.top + 120 * (scale || 1)
  let current = props.sections[0]?.id
  for (const section of props.sections) {
    const element = document.getElementById(section.id)
    if (element && element.getBoundingClientRect().top <= line) current = section.id
  }
  active.value = current
}

const unregister = navigation?.register({
  title: props.title,
  navLabel: props.navLabel,
  sections: props.sections,
  query,
  results,
  active,
  jump,
  reveal
})

async function revealHash(hash) {
  if (!hash) return
  const target = document.getElementById(hash.slice(1))
  const section = target?.closest('.settings-section')
  if (!section || !props.sections.some(({ id }) => id === section.id)) return
  active.value = section.id
  await nextTick()
  scrollToElement(target)
}

watch(() => route?.hash, revealHash)

onMounted(async () => {
  await nextTick()
  const first = document.getElementById(props.sections[0]?.id)
  if (!first) return
  if (typeof MutationObserver !== 'undefined') {
    indexObserver = new MutationObserver(() => {
      if (query.value.trim()) buildIndex()
    })
    for (const section of props.sections) {
      const root = document.getElementById(section.id)
      if (root)
        indexObserver.observe(root, {
          childList: true,
          subtree: true,
          characterData: true,
          attributes: true,
          attributeFilter: ['data-settings-keywords', 'data-settings-label']
        })
    }
  }
  container = scrollParent(first)
  if (!navigation) {
    scrollTarget = container === document.scrollingElement ? window : container
    scrollTarget.addEventListener('scroll', updateActive, { passive: true })
  }
  container.scrollTop = 0
  await revealHash(route?.hash)
  updateActive()
})
onUnmounted(() => {
  clearTimeout(scrollFallback)
  indexObserver?.disconnect()
  scrollTarget?.removeEventListener('scroll', updateActive)
  unregister?.()
})
</script>

<template>
  <div
    class="settings-page"
    :class="{ 'settings-page--mobile': mobile, 'settings-page--shell': navigation }"
  >
    <header class="settings-page-header">
      <h1>{{ navigation ? currentSection?.title : title }}</h1>
      <p v-if="!navigation && description">{{ description }}</p>
    </header>
    <div class="settings-body">
      <aside v-if="!navigation" class="settings-aside">
        <div class="settings-search" role="search">
          <n-input
            v-model:value="query"
            clearable
            size="small"
            :placeholder="`搜索${title}`"
            :input-props="{ 'aria-label': `搜索${title}`, 'aria-controls': `${navLabel}-results` }"
            @keydown="searchKey"
          >
            <template #prefix><n-icon :component="SearchIcon" /></template>
          </n-input>
          <div
            v-if="query.trim()"
            :id="`${navLabel}-results`"
            class="settings-search-results"
            aria-live="polite"
          >
            <button
              v-for="entry in results"
              :key="entry.key"
              type="button"
              class="settings-search-result"
              @click="reveal(entry)"
            >
              <span class="settings-search-result-label">{{ entry.label }}</span>
              <span class="settings-search-result-path">{{ entry.path }}</span>
            </button>
            <div v-if="!results.length" class="settings-search-empty">没有匹配的设置项</div>
          </div>
        </div>
        <nav class="settings-nav" :aria-label="navLabel">
          <a
            v-for="section in sections"
            :key="section.id"
            :href="`#${section.id}`"
            class="settings-nav-item"
            :class="{ 'is-active': active === section.id }"
            :aria-current="active === section.id ? 'true' : undefined"
            @click.prevent="jump(section.id)"
          >
            <n-icon v-if="section.icon" :component="section.icon" size="16" />
            <span>{{ section.title }}</span>
          </a>
        </nav>
      </aside>
      <div class="settings-content">
        <slot />
      </div>
    </div>
  </div>
</template>
