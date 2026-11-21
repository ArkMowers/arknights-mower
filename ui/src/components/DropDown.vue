<script setup>
const props = defineProps({
  select: { type: Function },
  options: { type: Array },
  type: { default: 'default' },
  up: { default: false, type: Boolean },
  menuLabel: { type: String, default: '选择操作' },
  disabled: { type: Boolean, default: false },
  glassMenu: { type: Boolean, default: false }
})

import DropUpIcon from '@vicons/ionicons5/es/ChevronUpOutline'
import DropDownIcon from '@vicons/ionicons5/es/ChevronDownOutline'

import { inject, ref } from 'vue'
import '@/styles/logGlassSurface.css'

const mobile = inject('mobile', ref(false))
const menuOpen = ref(false)
const buttonGroup = ref(null)
const menuWidth = ref(undefined)
const glassMenuProps = () => ({ class: 'mower-log-glass-menu' })
const glassMenuTheme = { color: 'transparent', borderRadius: '12px' }

function updateMenuOpen(show) {
  if (show && props.glassMenu) {
    const group = buttonGroup.value?.$el ?? buttonGroup.value
    const width = group?.getBoundingClientRect?.().width
    menuWidth.value = width > 0 ? width : undefined
  }
  menuOpen.value = show
}
</script>

<template>
  <n-button-group v-if="mobile" ref="buttonGroup" class="split-dropdown split-dropdown--touch">
    <slot />
    <n-dropdown
      :show="menuOpen"
      @update:show="updateMenuOpen"
      trigger="click"
      :options="options"
      :disabled="disabled"
      :menu-props="glassMenu ? glassMenuProps : undefined"
      :theme-overrides="glassMenu ? glassMenuTheme : undefined"
      :width="glassMenu ? menuWidth : undefined"
      @select="select"
      :placement="glassMenu ? (up ? 'top-end' : 'bottom-end') : up ? 'top' : 'bottom'"
    >
      <n-button
        class="dropdown"
        :type="type"
        :disabled="disabled"
        :aria-label="menuLabel"
        :title="menuLabel"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        ghost
      >
        <template #icon>
          <n-icon><drop-up-icon v-if="up" /><drop-down-icon v-else /></n-icon>
        </template>
      </n-button>
    </n-dropdown>
  </n-button-group>
  <n-dropdown
    v-else
    :show="menuOpen"
    @update:show="updateMenuOpen"
    trigger="hover"
    :options="options"
    :disabled="disabled"
    :menu-props="glassMenu ? glassMenuProps : undefined"
    :theme-overrides="glassMenu ? glassMenuTheme : undefined"
    :width="glassMenu ? menuWidth : undefined"
    @select="select"
    :placement="glassMenu ? (up ? 'top-end' : 'bottom-end') : up ? 'top' : 'bottom'"
  >
    <n-button-group ref="buttonGroup" class="split-dropdown">
      <slot />
      <n-button
        class="dropdown"
        :type="type"
        :disabled="disabled"
        :aria-label="menuLabel"
        :title="menuLabel"
        aria-haspopup="menu"
        :aria-expanded="menuOpen"
        ghost
      >
        <template #icon>
          <n-icon><drop-up-icon v-if="up" /><drop-down-icon v-else /></n-icon>
        </template>
      </n-button>
    </n-button-group>
  </n-dropdown>
</template>

<style scoped>
.dropdown {
  padding-inline: 6px;
}
.split-dropdown--touch .dropdown {
  width: 44px;
  min-height: 44px;
  padding-inline: 10px;
}
</style>

<style>
.n-dropdown-menu.mower-log-glass-menu {
  --n-option-text-color: #30343a;
  --n-option-text-color-hover: #171b20;
  --n-option-text-color-active: #171b20;
  --n-option-text-color-child-active: #171b20;
  --n-option-color-hover: rgba(40, 50, 62, 0.06);
  --n-option-color-active: rgba(40, 50, 62, 0.18);
  --n-prefix-color: #454c56;
  --n-suffix-color: #454c56;
  --n-group-header-text-color: #5b626d;
  --n-divider-color: rgba(48, 52, 58, 0.16);
}

.n-dropdown-menu.mower-log-glass-menu .n-dropdown-option .n-dropdown-option-body {
  height: auto;
  min-height: var(--n-option-height);
  line-height: 1.5;
}

.n-dropdown-menu.mower-log-glass-menu
  .n-dropdown-option
  .n-dropdown-option-body
  .n-dropdown-option-body__label {
  min-width: 0;
  padding-block: 6px;
  white-space: normal;
  overflow-wrap: anywhere;
}

html[data-mower-theme='dark'] .n-dropdown-menu.mower-log-glass-menu,
html[data-window-shell-theme='dark'] .n-dropdown-menu.mower-log-glass-menu {
  --n-option-text-color: #e4e7ec;
  --n-option-text-color-hover: #ffffff;
  --n-option-text-color-active: #ffffff;
  --n-option-text-color-child-active: #ffffff;
  --n-option-color-hover: rgba(224, 230, 240, 0.08);
  --n-option-color-active: rgba(224, 230, 240, 0.22);
  --n-prefix-color: #d2d7df;
  --n-suffix-color: #d2d7df;
  --n-group-header-text-color: #b0b7c2;
  --n-divider-color: rgba(228, 231, 236, 0.18);
}
</style>
