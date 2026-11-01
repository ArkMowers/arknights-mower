import { h, nextTick, ref, shallowRef } from 'vue'
import UpdatePreview from '@/components/UpdatePreview.vue'

function showUpdateDialog(
  dialogs,
  { title, preview, restartCount, loadComponent, validate, target }
) {
  const component = shallowRef(null)
  const updater = ref(null)
  const error = ref('')
  let submitted = false
  let dismissed = false
  const dismiss = () => {
    dismissed = true
  }
  const dialog = dialogs.warning({
    title,
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
              `重启同一安装目录下的 ${restartCount} 个实例`
            )
          : null,
        error.value ? h('p', { role: 'alert', class: 'update-dialog-error' }, error.value) : null
      ]),
    positiveText: '立即更新',
    negativeText: '取消',
    autoFocus: false,
    onNegativeClick: dismiss,
    onClose: dismiss,
    onMaskClick: dismiss,
    onPositiveClick: async () => {
      if (submitted || dismissed) return false
      submitted = true
      dialog.loading = true
      error.value = ''
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
        error.value = err.response?.data?.message || err.message || '更新未完成，请重试'
      } finally {
        if (!component.value) submitted = false
        dialog.loading = false
      }
      return false
    }
  })
  return dialog
}

export function showSoftwareUpdateDialog(dialogs, info, selection) {
  const target = { ...selection, confirm_downgrade: selection.downgrade === true }
  const channel = target.channel || info.settings.channel
  return showUpdateDialog(dialogs, {
    title: '软件更新',
    preview: {
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
    title: '资源更新',
    preview: { version: target.remote_display || target.remote_version },
    loadComponent: () => import('@/components/ResourceUpdate.vue'),
    validate() {
      if (resources.info.remote_version !== target.remote_version)
        throw new Error('资源更新目标已改变，请重新检查更新。')
    }
  })
}
