<script setup>
import { computed } from 'vue'
import { NIcon } from 'naive-ui'
import GridOutline from '@vicons/ionicons5/es/GridOutline'
import PeopleOutline from '@vicons/ionicons5/es/PeopleOutline'
import CubeOutline from '@vicons/ionicons5/es/CubeOutline'
import BarChartOutline from '@vicons/ionicons5/es/BarChartOutline'
import RouteOutline from '@vicons/ionicons5/es/GitNetworkOutline'
import HammerOutline from '@vicons/ionicons5/es/HammerOutline'

const props = defineProps({
  modelValue: { type: String, default: 'overview' },
  operatorCount: { type: Number, default: 0 },
  missingKinds: { type: Number, default: 0 },
  readyCount: { type: Number, default: 0 },
  goalCount: { type: Number, default: 0 }
})
const emit = defineEmits(['update:modelValue', 'open-route', 'open-workshop'])

const views = computed(() => [
  { key: 'overview', label: '总览', icon: GridOutline, meta: '' },
  {
    key: 'operators',
    label: '干员',
    icon: PeopleOutline,
    meta: props.operatorCount ? String(props.operatorCount) : ''
  },
  {
    key: 'materials',
    label: '材料',
    icon: CubeOutline,
    meta: props.missingKinds
      ? '缺 ' + props.missingKinds
      : props.readyCount
        ? '备齐 ' + props.readyCount
        : ''
  },
  { key: 'insights', label: '统计', icon: BarChartOutline, meta: '' }
])
</script>

<template>
  <nav class="growth-viewnav" aria-label="养成规划视图">
    <div class="growth-viewnav__tabs" role="tablist">
      <button
        v-for="view in views"
        :key="view.key"
        type="button"
        role="tab"
        class="growth-viewnav__tab"
        :class="{ 'is-active': modelValue === view.key }"
        :aria-selected="modelValue === view.key"
        @click="emit('update:modelValue', view.key)"
      >
        <n-icon :component="view.icon" :size="15" aria-hidden="true" />
        <span>{{ view.label }}</span>
        <span v-if="view.meta" class="growth-viewnav__meta gp-mono">{{ view.meta }}</span>
      </button>
    </div>
    <div class="growth-viewnav__tools">
      <button type="button" class="growth-viewnav__tool" @click="emit('open-route')">
        <n-icon :component="RouteOutline" :size="15" aria-hidden="true" />
        专精路线
      </button>
      <button type="button" class="growth-viewnav__tool" @click="emit('open-workshop')">
        <n-icon :component="HammerOutline" :size="15" aria-hidden="true" />
        加工站
      </button>
    </div>
  </nav>
</template>

<style scoped>
.growth-viewnav {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  padding: 6px 2px;
  background: var(--gp-page);
}

.growth-viewnav__tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: 999px;
  background: var(--gp-surface-2);
}

.growth-viewnav__tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 16px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 13.5px;
  font-weight: 650;
  cursor: pointer;
  transition:
    background 180ms var(--gp-ease),
    color 180ms var(--gp-ease);
}

.growth-viewnav__tab:hover {
  color: var(--gp-ink);
  background: var(--gp-surface-3);
}

.growth-viewnav__tab:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 2px;
}

.growth-viewnav__tab.is-active {
  background: var(--gp-ink);
  color: var(--gp-page);
}

.growth-viewnav__meta {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--gp-surface);
  color: var(--gp-ink-2);
  font-size: 10.5px;
  font-weight: 700;
  line-height: 17px;
}

.growth-viewnav__tab.is-active .growth-viewnav__meta {
  background: rgba(244, 240, 229, 0.16);
  color: var(--gp-page);
}

.growth-viewnav__tools {
  display: flex;
  align-items: center;
  gap: 6px;
}

.growth-viewnav__tool {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border: 1px solid var(--gp-hair-soft);
  border-radius: 999px;
  background: transparent;
  color: var(--gp-muted);
  font: inherit;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition:
    color 160ms var(--gp-ease),
    border-color 160ms var(--gp-ease),
    background 160ms var(--gp-ease);
}

.growth-viewnav__tool:hover {
  color: var(--gp-ink);
  border-color: var(--gp-hair);
  background: var(--gp-surface);
}

.growth-viewnav__tool:focus-visible {
  outline: 2px solid var(--gp-accent);
  outline-offset: 2px;
}

@media (max-width: 720px) {
  .growth-viewnav {
    gap: 8px;
    padding: 4px 0;
    top: 0;
  }
  .growth-viewnav__tabs {
    width: 100%;
    overflow-x: auto;
    justify-content: space-between;
    scrollbar-width: none;
  }
  .growth-viewnav__tabs::-webkit-scrollbar {
    display: none;
  }
  .growth-viewnav__tab {
    flex: 1 0 auto;
    justify-content: center;
    padding: 0 10px;
    height: 32px;
    font-size: 12.5px;
  }
  .growth-viewnav__meta {
    display: none;
  }
  .growth-viewnav__tools {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
