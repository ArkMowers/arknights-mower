import { i18n } from '@/i18n'

export async function requestSoftwareUpdateCheck(axios, channel) {
  const base = `${import.meta.env.VITE_HTTP_URL || ''}/software-update`
  const { data } = await axios.post(
    `${base}/check`,
    { channel },
    { headers: { 'X-Mower-Update': '1' } }
  )
  if (!data.ok)
    throw new Error(data.message || i18n.global.t('settings.softwareUpdate.checkFailed'))
  return data
}

export function confirmSoftwareInstall(
  dialogs,
  currentVersion,
  selection,
  instanceCount,
  install,
  cancel = () => {}
) {
  const target = { ...selection }
  return dialogs.warning({
    title:
      target.confirm_title ||
      i18n.global.t(
        target.downgrade
          ? 'settings.softwareUpdate.confirmRollback'
          : 'settings.softwareUpdate.confirmInstall'
      ),
    content:
      target.confirm_message ||
      [
        target.source_repo
          ? i18n.global.t('settings.softwareUpdate.repository', { repository: target.source_repo })
          : '',
        target.downgrade
          ? i18n.global.t('settings.softwareUpdate.rollbackWarning', {
              currentVersion,
              version: target.version
            })
          : i18n.global.t('settings.softwareUpdate.installVersion', { version: target.version }),
        i18n.global.t('settings.softwareUpdate.restartDetails', { count: instanceCount }),
        target.force ? i18n.global.t('settings.softwareUpdate.discardChanges') : ''
      ].join(''),
    positiveText: i18n.global.t(
      target.downgrade ? 'settings.softwareUpdate.rollback' : 'settings.softwareUpdate.install'
    ),
    negativeText: i18n.global.t('settings.softwareUpdate.cancel'),
    autoFocus: false,
    onNegativeClick: cancel,
    onClose: cancel,
    onMaskClick: cancel,
    onPositiveClick: () => install({ ...target, confirm_downgrade: target.downgrade === true })
  })
}

export function confirmForceUpdate(dialogs, version, instanceCount, install) {
  return dialogs.warning({
    title: i18n.global.t('settings.softwareUpdate.confirmForce'),
    content: i18n.global.t('settings.softwareUpdate.forceDetails', {
      version,
      count: instanceCount
    }),
    positiveText: i18n.global.t('settings.softwareUpdate.force'),
    negativeText: i18n.global.t('settings.softwareUpdate.cancel'),
    autoFocus: false,
    onPositiveClick: install
  })
}

export function confirmSourceVersion(dialogs, target, instanceCount, install) {
  return dialogs.warning({
    title: i18n.global.t(
      target.force
        ? 'settings.softwareUpdate.confirmForceSource'
        : 'settings.softwareUpdate.confirmSource'
    ),
    content: [
      target.source_repo
        ? i18n.global.t('settings.softwareUpdate.sourceRepository', {
            repository: target.source_repo,
            pull: target.source_pr
              ? i18n.global.t('settings.softwareUpdate.pullSuffix', { number: target.source_pr })
              : ''
          })
        : '',
      target.base_commit
        ? i18n.global.t('settings.softwareUpdate.mergeBase', {
            branch: target.source_branch,
            commit: target.base_commit
          })
        : '',
      i18n.global.t(
        target.source_pr
          ? 'settings.softwareUpdate.pullCommit'
          : 'settings.softwareUpdate.switchCommit',
        { commit: target.sha }
      ),
      i18n.global.t('settings.softwareUpdate.sourceDetails', { count: instanceCount }),
      i18n.global.t(
        target.force
          ? 'settings.softwareUpdate.discardChanges'
          : 'settings.softwareUpdate.restoreVersion'
      )
    ].join(''),
    positiveText: i18n.global.t(
      target.force ? 'settings.softwareUpdate.forceSwitch' : 'settings.softwareUpdate.switch'
    ),
    negativeText: i18n.global.t('settings.softwareUpdate.cancel'),
    autoFocus: false,
    onPositiveClick: install
  })
}
