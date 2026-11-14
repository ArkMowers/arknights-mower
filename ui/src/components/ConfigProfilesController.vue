<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ controller: { type: Object, required: true } })
const {
  dialog,
  name,
  selected,
  file,
  sections,
  busy,
  loading,
  error,
  stale,
  pendingReload,
  writeDisabled,
  selectFile,
  toggleSection,
  submit,
  reloadPage,
  refresh
} = props.controller
const input = ref(null)
const title = computed(
  () =>
    ({
      create: '新建档案',
      copy: '复制当前档案',
      rename: '重命名档案',
      import: '导入档案',
      activate: '切换档案'
    })[dialog.value?.action] || '档案'
)
const confirmLabel = computed(
  () =>
    ({
      create: '创建并切换',
      copy: '复制并切换',
      rename: '保存名称',
      import: '导入并切换',
      activate: '切换档案'
    })[dialog.value?.action]
)
const isReload = computed(() => stale.value || pendingReload.value)
function checked(section) {
  return section.children.every((group) => selected.value.includes(group.key))
}
function partial(section) {
  return !checked(section) && section.children.some((group) => selected.value.includes(group.key))
}
</script>

<template>
  <n-alert
    v-if="error && !dialog && !isReload"
    type="error"
    title="档案管理不可用"
    class="profiles-error"
  >
    {{ error }}
    <template #action><n-button @click="reloadPage">重新加载页面</n-button></template>
  </n-alert>
  <n-modal
    :show="Boolean(dialog) && !isReload"
    preset="card"
    :title="title"
    class="profiles-dialog"
    :style="{
      width: 'min(640px, calc(100vw - 32px))',
      display: 'flex',
      flexDirection: 'column'
    }"
    :content-style="{ overflowY: 'auto', minHeight: 0 }"
    :mask-closable="!busy"
    :closable="!busy"
    :close-on-esc="!busy"
    @update:show="
      (show) => {
        if (!show && !busy) dialog = null
      }
    "
  >
    <n-space vertical :size="18">
      <n-alert v-if="error" type="error" :show-icon="false">{{ error }}</n-alert>
      <n-form-item v-if="dialog?.action !== 'activate'" label="档案名称" :show-feedback="false">
        <n-input
          v-model:value="name"
          :disabled="busy"
          placeholder="例如：主账号、备用账号"
          :input-props="{ 'aria-label': '档案名称' }"
          autofocus
        />
      </n-form-item>
      <template v-if="dialog?.action === 'import'">
        <n-space align="center">
          <n-button :disabled="busy" @click="input.click()">选择 ZIP 备份</n-button>
          <n-text>{{ file?.name || '尚未选择文件' }}</n-text>
        </n-space>
        <input
          ref="input"
          type="file"
          hidden
          accept=".zip,application/zip"
          aria-label="选择档案 ZIP 备份"
          @change="selectFile"
        />
      </template>
      <template v-if="dialog?.action !== 'rename'">
        <p class="profiles-copy">
          <template v-if="dialog?.action === 'activate'"
            >切换到「{{
              dialog.targetName
            }}」。勾选的项目保留当前档案的内容，并写入目标档案；未勾选的项目使用目标档案。</template
          >
          <template v-else-if="dialog?.action === 'import'"
            >导入 ZIP 备份会创建一份新档案。勾选的项目使用当前档案的内容，其余内容来自
            ZIP。</template
          >
          <template v-else>勾选要沿用的当前档案内容，未勾选的项目使用默认值。</template>
        </p>
        <details v-for="section in sections" :key="section.label" class="profiles-section" open>
          <summary>
            <n-checkbox
              :checked="checked(section)"
              :indeterminate="partial(section)"
              :disabled="busy"
              @click.stop.prevent
              @update:checked="(value) => toggleSection(section, value)"
              ><strong>{{ section.label }}</strong></n-checkbox
            >
          </summary>
          <n-checkbox-group v-model:value="selected" :disabled="busy"
            ><div class="profiles-options">
              <n-checkbox
                v-for="group in section.children"
                :key="group.key"
                :value="group.key"
                :disabled="busy"
              >
                <span class="profiles-option"
                  ><span>{{ group.label }}</span
                  ><small>{{ group.description }}</small></span
                >
              </n-checkbox>
            </div></n-checkbox-group
          >
        </details>
        <n-text depth="3"
          >操作前会保存已应用的修改。尚未应用的设备身份和弹窗编辑草稿会在重新加载时丢弃；切换后不会自动开始任务。</n-text
        >
      </template>
    </n-space>
    <template #footer
      ><n-space justify="end">
        <n-button :disabled="busy" @click="dialog = null">取消</n-button>
        <n-button type="primary" :loading="busy" :disabled="writeDisabled" @click="submit">{{
          confirmLabel
        }}</n-button>
      </n-space></template
    >
  </n-modal>
  <n-modal
    :show="isReload"
    preset="card"
    title="需要重新加载档案"
    :style="{ width: 'min(480px, calc(100vw - 32px))' }"
    :closable="false"
    :mask-closable="false"
    :close-on-esc="false"
  >
    <n-space vertical :size="16">
      <n-text>{{ error || '档案已切换。旧页面的自动保存保持暂停，重新加载后可继续编辑。' }}</n-text>
      <n-text v-if="stale && controller.state.value" depth="3"
        >当前档案：{{
          controller.state.value.profiles.find(
            (item) => item.id === controller.state.value.active_id
          )?.name
        }}</n-text
      >
      <n-space justify="end">
        <n-button :loading="loading" @click="refresh()">检查当前档案</n-button>
        <n-button type="primary" @click="reloadPage">重新加载</n-button>
      </n-space>
    </n-space>
  </n-modal>
</template>

<style scoped>
.profiles-error {
  margin: 12px;
}
.profiles-copy {
  margin: 0;
  line-height: 1.7;
}
.profiles-section + .profiles-section {
  margin-top: 18px;
}
.profiles-options {
  display: grid;
  gap: 12px;
  padding: 12px 0 0 24px;
}
.profiles-option {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.profiles-option small {
  opacity: 0.65;
  font-size: 12px;
  line-height: 1.5;
}
</style>
