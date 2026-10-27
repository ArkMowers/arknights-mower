import { computed, h, nextTick, ref, shallowRef, watch } from 'vue'
import { i18n } from '@/i18n'
import UpdatePreview from '@/components/UpdatePreview.vue'

function showUpdateDialog(
  dialogs,
  { title, preview, restartCount, loadComponent, validate, target }
) {
  const component = shallowRef(null)
  const updater = ref(null)
  const error = shallowRef(null)
  const errorText = computed(() => {
    if (!error.value) return ''
    if (error.value.code === 'RESOURCE_UPDATE_TARGET_CHANGED')
      return i18n.global.t('updates.resourceTargetChanged')
    return (
      error.value.response?.data?.message ||
      error.value.message ||
      i18n.global.t('updates.incomplete')
    )
  })
  let submitted = false
  let dismissed = false
  let stopLanguageWatch = () => {}
  const dismiss = () => {
    dismissed = true
    stopLanguageWatch()
  }
  const dialog = dialogs.warning({
    title: title(),
    showIcon: false,
    style: { width: 'min(560px, calc(100vw - 32px))' },
    content: () =>
      h('div', [
        component.value
          ? h(component.value, { compact: true, skipInitialCheck: true, preview, ref: updater })
          : h(UpdatePreview, preview),
        restartCount != null
          ? h(
              'p',
              { class: 'update-restart-hint update-caption' },
              i18n.global.t('updates.restartInstances', { count: restartCount })
            )
          : null,
        errorText.value
          ? h('p', { role: 'alert', class: 'update-dialog-error' }, errorText.value)
          : null
      ]),
    positiveText: i18n.global.t('updates.updateNow'),
    negativeText: i18n.global.t('runtime.cancel'),
    autoFocus: false,
    onNegativeClick: dismiss,
    onClose: dismiss,
    onMaskClick: dismiss,
    onAfterLeave: dismiss,
    onPositiveClick: async () => {
      if (submitted || dismissed) return false
      submitted = true
      dialog.loading = true
      error.value = null
      try {
        validate?.()
        const loaded = await loadComponent()
        if (dismissed) return false
        component.value = loaded.default
        dialog.positiveText = undefined
        dialog.negativeText = undefined
        await nextTick()
        if (!dismissed) {
          validate?.()
          await updater.value.installCheckedUpdate(target)
        }
      } catch (err) {
        error.value = err
      } finally {
        if (!component.value) submitted = false
        dialog.loading = false
      }
      return false
    }
  })
  stopLanguageWatch = watch(
    i18n.global.locale,
    () => {
      dialog.title = title()
      if (!component.value) {
        dialog.positiveText = i18n.global.t('updates.updateNow')
        dialog.negativeText = i18n.global.t('runtime.cancel')
      }
    },
    { flush: 'sync' }
  )
  return dialog
}

export function showSoftwareUpdateDialog(dialogs, info, selection) {
  const target = { ...selection, confirm_downgrade: selection.downgrade === true }
  const channel = target.channel || info.settings.channel
  return showUpdateDialog(dialogs, {
    title: () => i18n.global.t('settings.software.softwareUpdates'),
    preview: {
      channelKey: channel,
      channel: info.channels?.find((item) => item.value === channel)?.label || channel,
      version: target.version,
      notes: target.notes
    },
    restartCount: info.instances.length,
    loadComponent: () => import('@/components/SoftwareUpdate.vue'),
    target
  })
}

export function showResourceUpdateDialog(dialogs, resources, selection) {
  const target = { ...selection }
  return showUpdateDialog(dialogs, {
    title: () => i18n.global.t('settings.resource.resourceUpdates'),
    preview: { version: target.remote_display || target.remote_version },
    loadComponent: () => import('@/components/ResourceUpdate.vue'),
    validate() {
      if (resources.info.remote_version !== target.remote_version)
        throw Object.assign(new Error(), { code: 'RESOURCE_UPDATE_TARGET_CHANGED' })
    }
  })
}
