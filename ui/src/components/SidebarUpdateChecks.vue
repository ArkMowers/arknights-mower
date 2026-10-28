<script setup>
import { useDialog, useMessage } from 'naive-ui'
import { i18n } from '@/i18n'
const { t } = i18n.global
import SidebarBrand from '@/components/SidebarBrand.vue'
import { useVersionChecksStore } from '@/stores/versionChecks'
import { useResourceVersionStore } from '@/stores/resourceVersion'
import { showResourceUpdateDialog, showSoftwareUpdateDialog } from '@/utils/updateDialog'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  enabled: { type: Boolean, default: false },
  extraSettingsVisible: { type: Boolean, default: true }
})
const checks = useVersionChecksStore()
const messages = useMessage()
const dialogs = useDialog()
const resources = useResourceVersionStore()
async function checkSoftware() {
  if (!props.enabled || checks.softwareChecking) return
  const pending = messages.loading(t('updates.checkingSoftware'), { duration: 0 })
  try {
    const result = await checks.checkSoftware()
    if (result.available) {
      const info = checks.softwareInfo
      if (!result.check_id || info.blockers?.length) {
        messages.error(info.blockers?.join('；') || t('updates.missingSoftwareTarget'))
        return
      }
      showSoftwareUpdateDialog(dialogs, info, result)
    } else {
      messages.success(t('updates.softwareCurrent'))
    }
  } catch (error) {
    messages.error(
      t('updates.softwareCheckFailed', { message: error.response?.data?.message || error.message })
    )
  } finally {
    pending.destroy()
  }
}

async function checkResource() {
  if (!props.enabled || checks.resourceChecking || checks.resourceDisabled) return
  const pending = messages.loading(t('updates.checkingResources'), { duration: 0 })
  try {
    const result = await checks.checkResource()
    if (!result) return
    if (result.update_available === true) {
      showResourceUpdateDialog(dialogs, resources, result)
    } else if (result.update_available === false) {
      messages.success(t('updates.resourcesCurrent'))
    } else {
      messages.error(t('updates.resourcesCheckIncomplete'))
    }
  } catch (error) {
    messages.error(
      t('updates.resourcesCheckFailed', { message: error.response?.data?.message || error.message })
    )
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
</template>
