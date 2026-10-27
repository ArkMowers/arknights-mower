<script setup>
import { i18n } from '@/i18n'
const { t } = i18n.global
defineProps({
  select: { type: Function },
  options: { type: Array },
  type: { default: 'default' },
  up: { default: false, type: Boolean },
  menuLabel: { type: String, default: '' },
  disabled: { type: Boolean, default: false }
})

import DropUpIcon from '@vicons/ionicons4/es/MdArrowDropup'
import DropDownIcon from '@vicons/ionicons4/es/MdArrowDropdown'

import { inject, ref } from 'vue'

const mobile = inject('mobile', ref(false))
const menuOpen = ref(false)
</script>

<template>
  <n-button-group v-if="mobile" class="split-dropdown split-dropdown--touch">
    <slot />
    <n-dropdown
      v-model:show="menuOpen"
      trigger="click"
      :options="options"
      :disabled="disabled"
      @select="select"
      :placement="up ? 'top' : 'bottom'"
    >
      <n-button
        class="dropdown"
        :type="type"
        :disabled="disabled"
        :aria-label="menuLabel || t('plans.chooseAction')"
        :title="menuLabel || t('plans.chooseAction')"
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
    v-model:show="menuOpen"
    trigger="hover"
    :options="options"
    :disabled="disabled"
    @select="select"
    :placement="up ? 'top' : 'bottom'"
  >
    <n-button-group class="split-dropdown">
      <slot />
      <n-button
        class="dropdown"
        :type="type"
        :disabled="disabled"
        :aria-label="menuLabel || t('plans.chooseAction')"
        :title="menuLabel || t('plans.chooseAction')"
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
