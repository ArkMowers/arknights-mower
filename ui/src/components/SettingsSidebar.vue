<script setup>
import { computed, inject, nextTick, ref, watch } from 'vue'
import ArrowLeft from '@vicons/fluent/es/ArrowLeft24Regular'
import SearchIcon from '@vicons/fluent/es/Search24Regular'
import { settingsNavigationKey } from '@/composables/settingsNavigation'
import SidebarScroll from './SidebarScroll.vue'
import '@/styles/settings.css'
import '@/styles/sidebar.css'

const emit = defineEmits(['back', 'navigate'])
defineProps({ embedded: Boolean })
const navigation = inject(settingsNavigationKey)
const page = computed(() => navigation.current.value)
const categories = ref(null)
watch(
  [() => page.value?.active.value, categories],
  async () => {
    await nextTick()
    const list = categories.value
    if (!list || list.scrollWidth <= list.clientWidth) return
    list
      .querySelector('[aria-current="true"]')
      ?.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  },
  { flush: 'post' }
)
const query = computed({
  get: () => page.value?.query.value ?? '',
  set: (value) => {
    if (page.value) page.value.query.value = value
  }
})
function jump(id) {
  page.value?.jump(id)
  emit('navigate')
}
function reveal(entry) {
  page.value?.reveal(entry)
  emit('navigate')
}
function submit() {
  const first = page.value?.results.value[0]
  if (first) reveal(first)
}
function searchKey(event) {
  if (event.key === 'Escape') query.value = ''
  if (event.key === 'Enter') {
    event.preventDefault()
    submit()
  }
}
</script>

<template>
  <aside
    class="settings-sidebar"
    :class="{ 'settings-sidebar--embedded': embedded }"
    aria-label="设置导航"
  >
    <button v-if="!embedded" class="settings-sidebar-back" type="button" @click="emit('back')">
      <n-icon :component="ArrowLeft" aria-hidden="true" />
      <span>返回</span>
    </button>
    <div class="settings-sidebar-search settings-search" role="search">
      <n-input
        v-model:value="query"
        clearable
        :disabled="!page"
        :placeholder="`搜索${page?.title ?? '设置'}`"
        :input-props="{ 'aria-label': `搜索${page?.title ?? '设置'}` }"
        @keydown="searchKey"
      >
        <template #prefix><n-icon :component="SearchIcon" /></template>
      </n-input>
    </div>
    <SidebarScroll class="settings-sidebar-scroll sidebar-scroll-fade">
      <template v-if="page">
        <div v-if="query.trim()" class="settings-sidebar-results" aria-live="polite">
          <button
            v-for="entry in page.results.value"
            :key="entry.key"
            type="button"
            class="settings-search-result"
            @click="reveal(entry)"
          >
            <span class="settings-search-result-label">{{ entry.label }}</span>
            <span class="settings-search-result-path">{{ entry.path }}</span>
          </button>
          <p v-if="!page.results.value.length" class="settings-search-empty">没有匹配的设置项</p>
        </div>
        <nav v-else ref="categories" class="settings-nav" :aria-label="page.navLabel">
          <a
            v-for="section in page.sections"
            :key="section.id"
            :href="`#${section.id}`"
            class="settings-nav-item"
            :class="{ 'is-active': page.active.value === section.id }"
            :aria-current="page.active.value === section.id ? 'true' : undefined"
            @click.prevent="jump(section.id)"
          >
            <n-icon v-if="section.icon" :component="section.icon" :size="embedded ? 20 : 14" />
            <span>{{ section.title }}</span>
          </a>
        </nav>
      </template>
    </SidebarScroll>
  </aside>
</template>

<style scoped>
.settings-sidebar {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: 100%;
  min-height: 0;
  box-sizing: border-box;
  padding: 8px;
  color: var(--mower-text);
  --settings-accent-ring: color-mix(in srgb, var(--mower-primary) 28%, transparent);
}
.settings-sidebar-back {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 8px 12px;
  border: 0;
  border-radius: 8px;
  color: inherit;
  background: transparent;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}
.settings-sidebar-back .n-icon,
.settings-sidebar .settings-nav-item .n-icon {
  flex: 0 0 18px;
  font-size: 14px;
}
.settings-sidebar-back:hover {
  background: var(--mower-control-hover);
}
.settings-sidebar-back:focus-visible {
  outline: 2px solid var(--mower-primary);
  outline-offset: -2px;
}
.settings-sidebar-search {
  margin: 0;
}
.settings-sidebar-scroll {
  flex: 1 1 0;
  min-height: 0;
}
.settings-sidebar .settings-nav {
  flex-direction: column;
  gap: 4px;
  overflow: visible;
  padding: 20px 16px 20px 0;
}
.settings-sidebar .settings-nav-item {
  min-height: 36px;
  box-sizing: border-box;
  border-radius: 10px;
  font-size: 13px;
}
.settings-sidebar .settings-nav-item.is-active::before {
  display: block;
  left: 0;
}
.settings-sidebar-results {
  display: grid;
  gap: 4px;
  padding: 20px 16px 20px 0;
}
.settings-sidebar--embedded {
  gap: 14px;
  padding: 0 0 24px;
}

.settings-sidebar--embedded .settings-sidebar-search {
  padding: 0 8px;
}

.settings-sidebar--embedded .settings-nav {
  gap: 4px;
  padding: 0 8px;
}

.settings-sidebar--embedded .settings-nav-item {
  gap: 12px;
  min-height: 44px;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 15px;
  color: var(--mower-text);
}

.settings-sidebar--embedded .settings-nav-item .n-icon {
  font-size: 20px;
}

.settings-sidebar--embedded .settings-nav-item.is-active::before {
  display: none;
}

.settings-sidebar--embedded .settings-nav-item.is-active .n-icon {
  color: inherit;
}

.settings-sidebar--embedded .settings-sidebar-results {
  padding: 0 8px;
}

@container settings-dialog (max-width: 680px) {
  .settings-sidebar--embedded {
    gap: 8px;
    height: auto;
    padding: 0 12px;
  }

  .settings-sidebar--embedded .settings-sidebar-scroll {
    flex: none;
    height: auto;
    max-height: 180px;
  }

  .settings-sidebar--embedded :deep(.n-scrollbar-container) {
    position: static;
    max-height: 180px;
  }

  .settings-sidebar--embedded .settings-nav {
    flex-direction: row;
    gap: 4px;
    overflow-x: auto;
    padding: 0 8px;
    scrollbar-width: none;
  }

  .settings-sidebar--embedded .settings-nav::-webkit-scrollbar {
    display: none;
  }

  .settings-sidebar--embedded .settings-nav-item {
    min-height: 40px;
    padding: 8px 12px;
    font-size: 13px;
    white-space: nowrap;
    scroll-margin-inline: 8px;
  }
}
</style>
