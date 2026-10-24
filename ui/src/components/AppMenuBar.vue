<template>
  <nav
    ref="menuBar"
    class="app-menu-bar window-titlebar__menus"
    :class="{
      'app-menu-bar--dark': theme === 'dark',
      'app-menu-bar--brand': mode === 'brand'
    }"
    aria-label="连接、档案、视图和帮助"
    @mousedown.stop
    @dblclick.stop
  >
    <n-dropdown
      v-if="mode === 'brand'"
      trigger="click"
      placement="bottom-start"
      scrollable
      :theme-overrides="titlebarDropdownTheme"
      :show="active && openMenu === 'brand'"
      :options="brandOptions"
      :menu-props="(option) => dropdownMenuProps({ key: 'brand', label: 'Mower' }, option)"
      :node-props="dropdownNodeProps"
      @update:show="(show) => setMenuOpen('brand', show)"
      @select="selectMenuItem"
    >
      <button
        type="button"
        class="app-menu-bar__brand-trigger"
        :class="{ 'is-open': openMenu === 'brand' }"
        aria-label="Mower 菜单"
        aria-haspopup="menu"
        :aria-expanded="active && openMenu === 'brand'"
        :aria-controls="`${menuId}-brand`"
        :disabled="!active"
        @keydown.down.prevent="setMenuOpen('brand', true)"
        @keydown.esc="setMenuOpen('brand', false)"
        @keydown.tab="setMenuOpen('brand', false)"
      >
        <span>Mower</span>
        <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
          <path d="m4 6 4 4 4-4" />
        </svg>
      </button>
    </n-dropdown>
    <template v-else>
      <n-dropdown
        v-for="(menu, index) in menus"
        :key="menu.key"
        trigger="click"
        placement="bottom-start"
        scrollable
        :theme-overrides="titlebarDropdownTheme"
        :show="active && openMenu === menu.key"
        :options="menu.options"
        :menu-props="(option) => dropdownMenuProps(menu, option)"
        :node-props="dropdownNodeProps"
        @update:show="(show) => setMenuOpen(menu.key, show)"
        @select="selectMenuItem"
      >
        <button
          type="button"
          class="window-titlebar__menu-trigger"
          :class="{ 'is-open': openMenu === menu.key }"
          aria-haspopup="menu"
          :aria-expanded="openMenu === menu.key"
          :aria-controls="`${menuId}-${menu.key}`"
          @mouseenter="openMenu && setMenuOpen(menu.key, true)"
          @keydown.left="onMenuArrow($event, index, -1)"
          @keydown.right="onMenuArrow($event, index, 1)"
          @keydown.down.prevent="setMenuOpen(menu.key, true)"
          @keydown.esc="openMenu = null"
          @keydown.tab="openMenu = null"
        >
          <span class="window-titlebar__menu-label">{{ menu.label }}</span>
        </button>
      </n-dropdown>
    </template>
  </nav>
</template>

<script setup>
import { NDropdown } from 'naive-ui'
import { computed, h, ref, useId, watch } from 'vue'

const titlebarDropdownTheme = {
  borderRadius: '10px',
  fontSizeMedium: '12px',
  optionHeightMedium: '32px',
  padding: '4px 0'
}

const props = defineProps({
  active: { type: Boolean, default: true },
  mode: { type: String, default: 'bar', validator: (value) => ['bar', 'brand'].includes(value) },
  instanceName: { type: String, default: '默认实例' },
  theme: { type: String, default: 'light' },
  mowerPort: { type: String, default: '' },
  emulatorName: { type: String, default: '' },
  adbPort: { type: String, default: '' },
  managerOwnedDevice: { type: Boolean, default: false },
  connectionTestDisabled: { type: Boolean, default: false },
  profileState: { type: Object, default: null },
  profileWriteDisabled: { type: Boolean, default: true },
  profileReadDisabled: { type: Boolean, default: true },
  sidebarVisible: { type: Boolean, default: true }
})
const emit = defineEmits(['connection-action', 'profile-action', 'view-action', 'help-action'])

const menuBar = ref(null)
const menuId = useId()
const openMenu = ref(null)
const activeBrandMenu = ref(null)
const menus = computed(() => [
  {
    key: 'connection',
    label: '连接',
    options: [
      currentOption(
        props.emulatorName || '尚未选择模拟器',
        props.adbPort ? `ADB 端口 ${props.adbPort}` : '',
        !props.emulatorName
      ),
      { type: 'divider', key: 'connection-divider' },
      ...(props.managerOwnedDevice
        ? [{ label: '连接与启动由多开管理器配置', key: 'managed-connection', disabled: true }]
        : [
            { label: '选择模拟器…', key: 'select-emulator' },
            { label: '测试连接', key: 'test-connection', disabled: props.connectionTestDisabled },
            { label: '连接设置…', key: 'connection-settings' }
          ])
    ]
  },
  {
    key: 'profile',
    label: '档案',
    options: [
      ...(props.profileState?.profiles || []).map((profile) => ({
        ...currentOption(
          profile.name,
          profile.id === props.profileState.active_id ? '当前档案' : ''
        ),
        key: `profile-${profile.id}`,
        profileId: profile.id,
        checked: profile.id === props.profileState.active_id,
        disabled: props.profileWriteDisabled || profile.id === props.profileState.active_id,
        icon: profile.id === props.profileState.active_id ? currentOption('').icon : undefined
      })),
      ...(!props.profileState
        ? [{ key: 'profiles-unavailable', label: '档案列表尚未载入', disabled: true }]
        : []),
      { type: 'divider', key: 'profile-divider' },
      { label: '新建档案…', key: 'add-profile', disabled: props.profileWriteDisabled },
      { label: '复制当前档案…', key: 'copy-profile', disabled: props.profileWriteDisabled },
      { label: '重命名档案…', key: 'rename-profile', disabled: props.profileWriteDisabled },
      { type: 'divider', key: 'profile-transfer-divider' },
      { label: '导入档案…', key: 'import-profile', disabled: props.profileWriteDisabled },
      { label: '导出当前档案…', key: 'export-profile', disabled: props.profileReadDisabled },
      { type: 'divider', key: 'profile-refresh-divider' },
      { label: '刷新档案列表', key: 'reload-profiles' }
    ]
  },
  {
    key: 'view',
    label: '视图',
    options: [
      {
        label: props.sidebarVisible ? '隐藏侧边栏' : '显示侧边栏',
        key: 'view-toggle-sidebar'
      },
      { label: '编辑侧边栏', key: 'view-edit-sidebar' }
    ]
  },
  {
    key: 'help',
    label: '帮助',
    options: [
      { label: '反馈问题', key: 'help-feedback' },
      { label: '文档', key: 'help-documentation' },
      { label: '更新日志', key: 'help-changelog' },
      { label: '关于', key: 'help-about' }
    ]
  }
])

const brandOptions = computed(() => [
  ...menus.value.map((menu) => ({
    key: `brand-${menu.key}`,
    menuKey: menu.key,
    label: menu.label,
    accessibleLabel: `${menu.label}菜单`,
    children: menu.options.map((option) => brandOption(menu.key, option))
  })),
  { type: 'divider', key: 'brand-identity-divider' },
  {
    type: 'render',
    key: 'brand-identity',
    render: () =>
      h('div', { class: 'app-menu-bar__identity', role: 'note', 'aria-label': '当前实例和设备' }, [
        h('div', { class: 'app-menu-bar__identity-name' }, props.instanceName || '默认实例'),
        h('div', props.emulatorName || '未选择设备'),
        (props.mowerPort || props.adbPort) &&
          h(
            'div',
            { class: 'app-menu-bar__identity-ports' },
            [
              props.mowerPort && `服务端口 ${props.mowerPort}`,
              props.adbPort && `ADB 端口 ${props.adbPort}`
            ]
              .filter(Boolean)
              .join(' · ')
          )
      ])
  }
])

function brandOption(menuKey, option) {
  return {
    ...option,
    key: `${menuKey}:${option.key}`,
    commandKey: option.key,
    ...(option.children
      ? { children: option.children.map((child) => brandOption(menuKey, child)) }
      : {})
  }
}

function dropdownMenuProps(menu, option) {
  return {
    id: `${menuId}-${menu.key}${option ? `-${option.key}` : ''}`,
    class: [
      'window-titlebar__dropdown',
      { 'window-titlebar__dropdown--dark': props.theme === 'dark' }
    ],
    'data-dropdown-option': true,
    role: 'menu',
    'aria-label': option?.accessibleLabel || menu.label,
    style: {
      minWidth: props.mode === 'brand' && !option ? '180px' : '200px',
      maxWidth: 'calc(100vw - 32px)',
      maxHeight: 'calc(100dvh - 60px)'
    },
    ...(props.mode === 'brand' && option?.menuKey
      ? {
          onVnodeMounted: () => prepareBrandMenu(option.menuKey),
          onVnodeUnmounted: () => {
            if (activeBrandMenu.value === option.menuKey) activeBrandMenu.value = null
          }
        }
      : {})
  }
}

function dropdownNodeProps(option) {
  const key = option.commandKey || option.key
  return {
    role: key === 'current' || option.profileId ? 'menuitemradio' : 'menuitem',
    'aria-checked': option.profileId
      ? option.checked
      : key === 'current'
        ? !option.disabled
        : undefined,
    'aria-disabled': Boolean(option.disabled),
    'aria-label': option.accessibleLabel,
    'aria-haspopup': option.children ? 'menu' : undefined,
    ...(props.mode === 'brand' && option.menuKey
      ? { onMouseenter: () => prepareBrandMenu(option.menuKey) }
      : {})
  }
}

function prepareBrandMenu(key) {
  if (!props.active || openMenu.value !== 'brand' || activeBrandMenu.value === key) return
  activeBrandMenu.value = key
  prepareMenu(key)
}

function currentOption(label, detail, disabled = false) {
  return {
    key: 'current',
    disabled,
    props: {
      style: {
        height: 'auto',
        minHeight: detail ? '46px' : '32px',
        lineHeight: '18px',
        alignItems: 'center'
      }
    },
    label: () =>
      h('span', { class: 'window-titlebar__menu-current' }, [
        h('span', label),
        detail && h('span', { class: 'window-titlebar__menu-detail' }, detail)
      ]),
    icon: disabled
      ? undefined
      : () =>
          h('svg', { viewBox: '0 0 16 16', width: 16, height: 16, 'aria-hidden': 'true' }, [
            h('path', {
              d: 'm3.5 8 3 3 6-6',
              fill: 'none',
              stroke: 'currentColor',
              'stroke-width': 1.5,
              'stroke-linecap': 'round',
              'stroke-linejoin': 'round'
            })
          ])
  }
}

function prepareMenu(key) {
  if (key === 'profile') emit('profile-action', 'refresh')
}

function setMenuOpen(key, show) {
  if (!props.active) return
  if (show) {
    if (openMenu.value !== key) prepareMenu(key)
    openMenu.value = key
  } else if (openMenu.value === key) {
    openMenu.value = null
    activeBrandMenu.value = null
  }
}

function selectMenuItem(key, option) {
  openMenu.value = null
  activeBrandMenu.value = null
  if (!props.active) return
  key = option?.commandKey || key
  const profileActions = {
    'add-profile': 'create',
    'copy-profile': 'copy',
    'rename-profile': 'rename',
    'import-profile': 'import',
    'export-profile': 'export',
    'reload-profiles': 'refresh'
  }
  if (option?.profileId || profileActions[key]) {
    if (option?.disabled) return
    const action = option?.profileId ? 'activate' : profileActions[key]
    if (
      action !== 'refresh' &&
      (action === 'export' ? props.profileReadDisabled : props.profileWriteDisabled)
    )
      return
    if (
      option?.profileId &&
      !props.profileState?.profiles.some((profile) => profile.id === option.profileId)
    )
      return
    emit('profile-action', action, option?.profileId)
    return
  }
  if (option?.disabled) return
  const viewActions = {
    'view-toggle-sidebar': 'toggle-sidebar',
    'view-edit-sidebar': 'edit-sidebar'
  }
  if (viewActions[key]) {
    emit('view-action', viewActions[key])
    return
  }
  const connectionActions = {
    'select-emulator': 'select',
    'test-connection': 'test',
    'connection-settings': 'settings'
  }
  if (connectionActions[key]) {
    if (props.managerOwnedDevice) return
    if (key === 'test-connection' && props.connectionTestDisabled) return
    emit('connection-action', connectionActions[key])
    return
  }
  const helpActions = {
    'help-feedback': 'feedback',
    'help-documentation': 'documentation',
    'help-changelog': 'changelog',
    'help-about': 'about'
  }
  if (helpActions[key]) {
    emit('help-action', helpActions[key])
    return
  }
}

function onMenuArrow(event, index, offset) {
  event.preventDefault()
  event.stopPropagation()
  focusMenu(index, offset)
}

function focusMenu(index, offset) {
  const next = (index + offset + menus.value.length) % menus.value.length
  menuBar.value?.querySelectorAll('button')[next]?.focus()
  if (openMenu.value) setMenuOpen(menus.value[next].key, true)
}

watch(
  () => [props.active, props.mode],
  () => {
    openMenu.value = null
    activeBrandMenu.value = null
  }
)
</script>

<style scoped>
.window-titlebar__menus {
  --window-titlebar-text: #302e2c;
  --window-titlebar-muted: #817d78;
  --window-titlebar-control: #242220;
  --window-titlebar-hover: rgba(40, 37, 35, 0.07);
  --window-titlebar-pressed: rgba(40, 37, 35, 0.12);
  --window-titlebar-divider: rgba(40, 37, 35, 0.1);
  --window-titlebar-focus: #18a058;
  min-width: 0;
  height: 36px;
  box-sizing: border-box;
  color: var(--window-titlebar-text);
  font-size: 12px;
  font-weight: 400;
  line-height: 22px;
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  gap: 2px;
  padding: 7px 0 0 6px;
}

.window-titlebar__menu-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 22px;
  padding: 0 9px;
  border: 0;
  border-radius: 9px;
  color: var(--window-titlebar-muted);
  background: transparent;
  font: inherit;
  white-space: nowrap;
  cursor: default;
  appearance: none;
}

.window-titlebar__menu-trigger:hover,
.window-titlebar__menu-trigger.is-open {
  color: var(--window-titlebar-text);
  background: var(--window-titlebar-hover);
}

.window-titlebar__menu-trigger:active {
  background: var(--window-titlebar-pressed);
}

.window-titlebar__menu-trigger:focus-visible {
  outline: 2px solid var(--window-titlebar-focus);
  outline-offset: -2px;
}

.app-menu-bar--brand {
  height: auto;
  padding: 0;
  align-items: center;
}

.app-menu-bar__brand-trigger {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 30px;
  margin-left: -8px;
  padding: 2px 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--window-titlebar-text);
  font-family: inherit;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  cursor: pointer;
}

.app-menu-bar__brand-trigger svg {
  fill: none;
  stroke: var(--window-titlebar-muted);
  stroke-width: 1.3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.app-menu-bar__brand-trigger:hover,
.app-menu-bar__brand-trigger.is-open {
  background: var(--window-titlebar-hover);
}

.app-menu-bar__brand-trigger:focus-visible {
  outline: 2px solid var(--window-titlebar-focus);
  outline-offset: -2px;
}

:global(.app-menu-bar__identity) {
  max-width: 280px;
  padding: 5px 14px 7px;
  font-size: 11px;
  line-height: 1.7;
  color: #817d78;
  overflow-wrap: anywhere;
}

:global(.app-menu-bar__identity-name) {
  color: #302e2c;
  font-weight: 500;
}

:global(.app-menu-bar__identity-ports) {
  margin-top: 3px;
  font-size: 10px;
}

:global(.window-titlebar__dropdown--dark .app-menu-bar__identity) {
  color: rgba(255, 255, 255, 0.52);
}

:global(.window-titlebar__dropdown--dark .app-menu-bar__identity-name) {
  color: rgba(255, 255, 255, 0.88);
}

:global(.window-titlebar__menu-current) {
  display: flex;
  flex-direction: column;
  padding: 3px 0;
  white-space: nowrap;
}

:global(.window-titlebar__dropdown.n-dropdown-menu) {
  box-sizing: border-box;
  border: 1px solid rgba(65, 61, 57, 0.14);
  border-radius: 14px;
}

:global(.window-titlebar__dropdown--dark.n-dropdown-menu) {
  border-color: rgba(255, 255, 255, 0.14);
}

:global(.window-titlebar__menu-detail) {
  font-size: 11px;
  opacity: 0.55;
}

:global(.window-titlebar__menu-row) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  white-space: nowrap;
}

:global(.window-titlebar__menu-description) {
  max-width: min(360px, calc(100vw - 64px));
  padding: 8px 14px;
  font-size: 11px;
  line-height: 1.6;
  opacity: 0.6;
  overflow-wrap: anywhere;
}

.app-menu-bar--dark {
  --window-titlebar-text: rgba(255, 255, 255, 0.88);
  --window-titlebar-muted: rgba(255, 255, 255, 0.52);
  --window-titlebar-control: rgba(255, 255, 255, 0.9);
  --window-titlebar-hover: rgba(255, 255, 255, 0.08);
  --window-titlebar-pressed: rgba(255, 255, 255, 0.13);
  --window-titlebar-divider: rgba(255, 255, 255, 0.12);
  --window-titlebar-focus: #63c38a;
}
</style>
