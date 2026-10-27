<script setup>
import { h, nextTick, ref, shallowRef } from 'vue'
import { useDialog, useMessage } from 'naive-ui'
import SidebarBrand from '@/components/SidebarBrand.vue'
import { useVersionChecksStore } from '@/stores/versionChecks'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { confirmSoftwareInstall } from '@/utils/softwareUpdate'
import UpdatePreview from './UpdatePreview.vue'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  enabled: { type: Boolean, default: false },
  extraSettingsVisible: { type: Boolean, default: true }
})
const checks = useVersionChecksStore()
const messages = useMessage()
const dialogs = useDialog()
const resources = useResourceVersionStore()
const updateComponent = shallowRef(null)
const updateProps = ref({})
const updater = ref(null)
const showUpdater = ref(false)
const updaterTitle = ref('')

function previewDialog(preview, showImpact = false) {
  return {
    warning(options) {
      return dialogs.warning({
        ...options,
        style: { width: 'min(560px, calc(100vw - 32px))' },
        content: () =>
          h('div', [
            h(UpdatePreview, preview),
            h('details', { class: 'update-confirm-impact', open: showImpact }, [
              h('summary', '更新影响'),
              h('p', options.content)
            ])
          ])
      })
    }
  }
}

async function installSoftware(selection, preview) {
  if (!props.enabled) return
  try {
    updateComponent.value = (await import('./SoftwareUpdate.vue')).default
    updateProps.value = { compact: true, preview }
    updaterTitle.value = '软件更新'
    showUpdater.value = true
    await nextTick()
    await updater.value.installCheckedUpdate(selection)
  } catch (error) {
    messages.error(`软件更新未完成：${error.response?.data?.message || error.message}`)
  }
}

async function installResource(selection, preview) {
  if (!props.enabled || resources.installing) return
  try {
    const component = (await import('./ResourceUpdate.vue')).default
    if (resources.info.remote_version !== selection.remote_version) {
      messages.error('资源更新目标已改变，请重新检查更新。')
      return
    }
    updateComponent.value = component
    updateProps.value = { skipInitialCheck: true, compact: true, preview }
    updaterTitle.value = '资源更新'
    showUpdater.value = true
    await nextTick()
    void updater.value.installCheckedUpdate().catch((error) => {
      messages.error(`资源更新未完成：${error.response?.data?.message || error.message}`)
    })
  } catch (error) {
    messages.error(`资源更新未完成：${error.response?.data?.message || error.message}`)
  }
}

async function checkSoftware() {
  if (!props.enabled || checks.softwareChecking) return
  const pending = messages.loading('正在检查软件更新…', { duration: 0 })
  try {
    const result = await checks.checkSoftware()
    if (result.available) {
      const info = checks.softwareInfo
      if (!result.check_id || info.blockers?.length) {
        messages.error(info.blockers?.join('；') || '未取得更新目标，请重新检查更新。')
        return
      }
      const channel = result.channel || info.settings.channel
      const preview = {
        channel: info.channels?.find((item) => item.value === channel)?.label || channel,
        version: result.version,
        notes: result.notes
      }
      confirmSoftwareInstall(
        previewDialog(preview, result.downgrade === true || result.force === true),
        info.version,
        { ...result, confirm_positive_text: '立即更新' },
        info.instances.length,
        (selection) => installSoftware(selection, preview)
      )
    } else {
      messages.success('软件已与所选渠道一致。')
    }
  } catch (error) {
    messages.error(`软件检查未完成：${error.response?.data?.message || error.message}`)
  } finally {
    pending.destroy()
  }
}

async function checkResource() {
  if (!props.enabled || checks.resourceChecking || checks.resourceDisabled) return
  const pending = messages.loading('正在检查资源更新…', { duration: 0 })
  try {
    const result = await checks.checkResource()
    if (!result) return
    if (result.update_available === true) {
      const target = result.remote_display || result.remote_version
      const preview = { version: target }
      previewDialog(preview).warning({
        title: '是否更新资源？',
        content: `将下载并安装资源包${target ? ` ${target}` : ''}。同一套 Mower 的全部实例共用资源包，空闲时自动加载，无需重启 Mower。`,
        positiveText: '立即更新',
        negativeText: '取消',
        autoFocus: false,
        onPositiveClick: () => installResource(result, preview)
      })
    } else if (result.update_available === false) {
      messages.success('资源已是最新版本。')
    } else {
      messages.error('资源检查未完成，请稍后重试。')
    }
  } catch (error) {
    messages.error(`资源检查未完成：${error.response?.data?.message || error.message}`)
  } finally {
    pending.destroy()
  }
}
</script>

<template>
  <SidebarBrand
    v-bind="$attrs"
    :updates-enabled="enabled"
    :software-checking="checks.softwareChecking"
    :resource-checking="checks.resourceChecking"
    :resource-disabled="checks.resourceDisabled"
    @check-software="checkSoftware"
    @check-resource="checkResource"
  >
    <template v-if="$slots.home" #home><slot name="home" /></template>
  </SidebarBrand>
  <n-modal
    v-model:show="showUpdater"
    preset="card"
    :title="updaterTitle"
    style="width: min(560px, calc(100vw - 32px)); max-height: 85dvh; overflow: auto"
  >
    <component :is="updateComponent" v-bind="updateProps" ref="updater" />
  </n-modal>
</template>
