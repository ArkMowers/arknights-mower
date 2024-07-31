<script setup>
defineProps(['select', 'options'])
import DropDownIcon from '@vicons/ionicons4/MdArrowDropdown'
</script>

<template>
  <n-dropdown
    trigger="hover"
    placement="bottom-start"
    width="trigger"
    :options="options"
    @select="select"
  >
    <n-button-group>
      <slot />
      <n-button class="dropdown">
        <template #icon>
          <n-icon><drop-down-icon /></n-icon>
        </template>
      </n-button>
    </n-button-group>
  </n-dropdown>
</template>

<style scoped>
.dropdown {
  padding: 0 6px;
}
</style>
