<script setup>
import { useMessage } from 'naive-ui'
import SidebarBrand from '@/components/SidebarBrand.vue'
import { useVersionChecksStore } from '@/stores/versionChecks'

defineOptions({ inheritAttrs: false })
const props = defineProps({ enabled: { type: Boolean, default: false } })
const checks = useVersionChecksStore()
const messages = useMessage()

async function checkSoftware() {
  if (!props.enabled || checks.softwareChecking) return
  const pending = messages.loading('正在检查软件更新…', { duration: 0 })
  try {
    const result = await checks.checkSoftware()
    if (result.available) {
      const target = result.version ? ` ${result.version}` : ''
      messages.info(
        `发现${result.downgrade ? '可回退的软件版本' : '软件更新'}${target}，可在 Mower 设置 → 网络与更新中查看并安装。`,
        { duration: 6000 }
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
      messages.info(
        `发现资源更新${target ? ` ${target}` : ''}，可在 Mower 设置 → 网络与更新中查看并安装。`,
        { duration: 6000 }
      )
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
</template>
